# Emergyx Care Architecture

Emergyx Care is a **local-first caregiver-support system** for elderly home
safety. The architecture is shaped by one default rule:

> Urgent fall alerts are rule-based by default. When Gemma-first notifications
> or the Gemma Pattern Monitor are enabled, Gemma can decide whether caregiver
> attention is needed and write the dashboard/Telegram alert text.

## Layered view

```text
Sensors            →   detect events
Rules/Gemma        →   configured alert decision layer
SQLite             →   local memory / private care timeline
Trend service      →   deterministic local trend snapshots / unusual flags
Gemma (Ollama)     →   explanation, reasoning, reporting, Q&A, pattern findings
Telegram + UI      →   caregiver communication
```

## Data flow

1. **MR60FDA2** publishes state changes over the ESPHome native API on the LAN.
2. **`FDA2IngestionManager`** subscribes via `aioesphomeapi`, maps known entity
   keys to typed event names (`person_present`, `fall_detected`, `illuminance`),
   and throttles illuminance writes by category change OR a configurable time
   window so the DB is not spammed with every lux fluctuation. With
   `FDA2_SENSORS`, it runs one reconnecting listener per configured sensor.
3. **`services.events.create_event`** writes a normalized row to SQLite.
4. **`services.alerts.handle_event_alerts`** runs synchronously inside the same
   request. By default, if the event is `fall_detected=true`, it:
   - reads the latest light context from the same `sensor_id`;
   - builds a plain-text caregiver alert (with light category if available);
   - calls `services.telegram.send_telegram_message` (skips cleanly when not
     configured);
   - writes an `Alert` row regardless of Telegram outcome, so the dashboard
     and the audit log still reflect the event.
   If `gemma_first_notifications` is enabled, likely falls and major vital
   changes are routed through Gemma first; only Gemma-approved notifications
   create dashboard/Telegram alerts.
5. Separately, the caregiver (or an automation) requests an explanation, a
   Q&A answer, or a daily report. Those calls go through:
   - **`services.incidents.get_incident_context`** which reconstructs the
     before/event/after window plus light context plus the linked alert;
   - **`services.gemma_agent`** which builds a structured prompt from that
     local data, calls Ollama if enabled, and falls back to deterministic
     caregiver text otherwise. Each call is recorded as an `AgentDecision`.
6. The caregiver can also request trend snapshots (`/trends/today`,
   `/trends/week`) where **`services.trends`** computes local SQLite trend JSON:
   today vs previous 7 days, falls, alerts sent, nighttime movement, light
   context, freshness/offline state, and notable changes.
7. `POST /agent/analyze-trends` feeds that structured trend JSON to Gemma for a
   conservative caregiver explanation (or deterministic fallback). This is
   post-event context only.
8. The report scheduler can also run the **Gemma Pattern Monitor**. Findings are
   stored in `gemma_findings`; medium/high findings can create dashboard alerts
   and optional Telegram messages.
8. Optionally, `TELEGRAM_SEND_GEMMA_EXPLANATIONS=true` sends a second
   non-blocking Telegram follow-up with the Gemma/deterministic explanation
   after the urgent alert is already sent/logged. The first Telegram alert
   still never waits on Gemma. Fall alerts also include inline action buttons
   for Explain, Live status, Latest event, and Daily report.
9. Optionally, `scripts/run_telegram_bot.py` starts a long-polling Telegram
   command worker for `/status`, `/latest`, `/explain`, `/report`, `/ask`,
   `/trends`, `/changes`, `/dashboard`, and `/help`. It only responds to
   `TELEGRAM_CHAT_ID`.
10. The polished **Next.js dashboard** at `/dashboard` renders the live timeline,
   FDA2 coverage, incident state, Gemma chat, details, and reporting UI against
   the FastAPI API. The FastAPI/Jinja dashboard remains available as a local
   fallback.

## Storage

SQLite lives at `data/emergyx_care.db` and contains the core care tables:

- `events` — every observed sensor state change (live or simulated).
- `alerts` — every urgent caregiver alert with channel + send status.
- `agent_decisions` — every Gemma call (input summary, output text, model
  name, used_mock flag, tools used). This is auditable.
- `daily_reports` — persisted Gemma daily reports per date.
- `weekly_reports` — persisted weekly PDF reports.
- `chat_threads` / `chat_messages` — local Gemma chat history.
- `gemma_findings` — autonomous Gemma pattern findings.

## What Gemma sees

Gemma is **only** ever given structured local data assembled from the four
tables above. It receives:

- An incident reconstruction (event + person_present before/after + fall clear
  + light context + linked alert + duration), or
- A "today" snapshot (events, alerts, incidents, light), or
- A "for date" snapshot for the daily report.

Gemma never gets raw network traffic, never gets shell access, never gets a
web search tool. The Ollama call uses a fixed system prompt that enforces the
caregiver wording rules.

## Failure modes

- **Ollama offline / unreachable / disabled.** Every Gemma entry point falls
  back to a deterministic caregiver-friendly summary built from the same
  local data. The dashboard labels the result accordingly.
- **Telegram offline / not configured.** Alerts are still saved to the local
  `alerts` table. The dashboard and the local timeline still update. Telegram
  commands are optional and run in a separate worker.
- **Sensor disconnect.** `FDA2IngestionManager` retries on a configurable
  delay. The rest of the API keeps serving the local timeline.

## Safety principle (restated)

The deterministic alert path remains the default and works without Gemma.
Gemma-first notifications and pattern-monitor alerts are explicit settings for
the demo/product experience, not hidden behavior.
