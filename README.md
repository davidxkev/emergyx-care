# Emergyx Care

<p align="center">
  <strong>Privacy-first fall detection and caregiver intelligence, powered locally by Gemma 4 E2B.</strong>
</p>

<p align="center">
  <img alt="Prototype" src="https://img.shields.io/badge/status-hackathon%20prototype-blue">
  <img alt="Local first" src="https://img.shields.io/badge/privacy-local--first-0f766e">
  <img alt="Gemma 4 E2B" src="https://img.shields.io/badge/model-Gemma%204%20E2B-7c3aed">
  <img alt="Ollama" src="https://img.shields.io/badge/runtime-Ollama-111827">
  <img alt="FastAPI" src="https://img.shields.io/badge/backend-FastAPI-059669">
  <img alt="Next.js" src="https://img.shields.io/badge/frontend-Next.js-111827">
  <img alt="Docker" src="https://img.shields.io/badge/demo-Docker-2563eb">
</p>

Emergyx Care is a local-first caregiver safety prototype for homes, assisted
living rooms, and nursing environments. It monitors camera-free sensor activity,
detects likely fall/emergency patterns, sends caregiver alerts, and uses
**Gemma 4 E2B via Ollama** to explain incidents, answer caregiver questions, and
generate daily/weekly care reports.

The recommended judging path runs fully in **demo mode**: no real sensors,
Telegram credentials, cloud AI, or manual database setup required.

> **Prototype only. Not a medical device. Not a medical diagnosis.**

## Judge TL;DR

```bash
git clone <repo-url>
cd emergyx-care
ollama pull gemma4:e2b
./scripts/start_demo.sh
./scripts/verify_demo.sh
```

Open:

```text
http://localhost:3000/dashboard?mode=demo
```

Expected verification output:

```text
Emergyx Care judge demo verification passed.
```

## Demo Media

Add these before final submission:

| Asset | Path or link |
| --- | --- |
| Demo video | `<add link>` |
| Care Overview screenshot | `docs/screenshots/overview.png` |
| Gemma Assistant screenshot | `docs/screenshots/chat.png` |
| Reports screenshot | `docs/screenshots/reports.png` |
| Sensors screenshot | `docs/screenshots/sensors.png` |
| Residents screenshot | `docs/screenshots/residents.png` |
| Settings screenshot | `docs/screenshots/settings.png` |

When screenshots are available, add them near the top of this README so judges
can see the working product before reading setup details.

## Why It Matters

Many home safety systems either require cameras, depend on cloud processing, or
produce raw alerts without enough context for caregivers. Emergyx Care shows a
privacy-first alternative:

- Camera-free mmWave-style sensing.
- Local event storage.
- Local Gemma 4 E2B analysis through Ollama.
- Immediate rule-based safety alerts.
- Caregiver-facing explanations and reports.
- Demo mode that reproduces the full workflow without hardware.

## What Gemma 4 E2B Does

Emergyx Care does not use Gemma as a generic chatbot. Gemma acts as the local
caregiver intelligence layer.

Gemma receives structured local context, including:

- Resident context.
- Room and sensor context.
- Recent timeline events.
- Fall-like detections and clustered fall episodes.
- Heart-rate and respiration summaries.
- Nighttime activity.
- Alert delivery status.
- Sensor reliability.
- Report history and caregiver notes.

Gemma is used for:

- Answering caregiver questions.
- Explaining why an alert happened.
- Generating daily care snapshots.
- Generating weekly safety and wellness reports.
- Identifying patterns such as repeated nighttime movement or clustered fall-like events.
- Turning raw sensor timelines into caregiver-friendly summaries.
- Drafting practical caregiver recommendations.

Urgent alerts are rule-based and immediate by default. Gemma explains,
summarizes, and reports after events are logged, so emergency alerting does not
depend on model latency.

## 3-Minute Demo Script

| Time | Action | What judges should see |
| --- | --- | --- |
| 0:00 | Open `http://localhost:3000/dashboard?mode=demo` | Seeded resident, local safety state, recent care activity, Gemma status |
| 0:30 | Trigger a demo likely-fall scenario | Dashboard updates, alert is created, local timeline records the event |
| 1:00 | Open Chat and ask "Why was I alerted?" | Gemma answers from Emergyx local context |
| 1:45 | Ask "What is the latest heart rate and breathing rate?" | Gemma uses the latest local sensor-like readings |
| 2:15 | Open Reports | Daily reports, weekly PDF reports, pattern monitor, scheduling |
| 2:45 | Open Sensors and Residents | Rooms, sensor assignments, resident context used by Gemma |
| 3:00 | Open Settings | Gemma/Ollama setup, Telegram setup, report schedule, privacy notes |

## Feature Status

| Feature | Status | Notes |
| --- | --- | --- |
| Demo mode without hardware | Ready | Seeded residents, rooms, events, alerts, reports, and Gemma context |
| Local Gemma chat | Ready | Uses Gemma 4 E2B through Ollama |
| Daily reports | Ready | Generated from local timeline context |
| Weekly PDF reports | Ready | Caregiver-facing report with scores, incidents, trends, Gemma analysis |
| Gemma pattern monitor | Ready | Scans local care data for notable patterns |
| Rule-based urgent alerts | Ready | Does not wait for AI inference |
| Gemma-first notifications | Experimental | Optional setting for Gemma-drafted alert decisions |
| Telegram alerts | Optional | Requires bot token and chat ID, mock alerts work in demo mode |
| Live ESPHome sensors | Optional | Requires local Seeed hardware and network setup |
| Public hosted demo | Not included | Use local Docker demo or LAN phone access |

## Dashboard Pages

Emergyx Care currently uses a six-page dashboard structure:

| Page | Route | What it contains |
| --- | --- | --- |
| Overview | `/dashboard` | Safety state, latest incident, care graph, recent activity, alerts, Gemma status, demo actions |
| Chat | `/chat` | Gemma caregiver assistant, saved threads, new chat, delete confirmation, export, optional reasoning display |
| Reports | `/reports` | Daily reports, weekly PDF reports, Gemma Pattern Monitor, trend analysis, report scheduling |
| Sensors | `/sensors` | Sensor inventory, rooms, add/delete rooms, sensor assignment, sensor names, context, telemetry, RGB detect controls |
| Residents | `/residents` | Add/edit/delete residents, assign sensor-backed rooms, resident/location context |
| Settings | `/settings` | Runtime status, Telegram setup, Gemma/Ollama setup, Gemma-first toggle, nighttime trends, report schedule, privacy notes |

The old `/details` route redirects to `/residents`.

## Quickstart With Docker

Required:

- Docker Desktop running.
- Ollama installed.
- Gemma 4 E2B pulled locally.

Run:

```bash
ollama pull gemma4:e2b
./scripts/start_demo.sh
```

Open:

```text
http://localhost:3000/dashboard?mode=demo
```

Verify:

```bash
./scripts/verify_demo.sh
```

Useful demo URLs:

```text
http://localhost:3000/dashboard?mode=demo
http://localhost:3000/chat?mode=demo
http://localhost:3000/reports?mode=demo
http://localhost:3000/sensors?mode=demo
http://localhost:3000/residents?mode=demo
http://localhost:3000/settings?mode=demo
```

## Quickstart Without Docker

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.demo .env
ollama pull gemma4:e2b
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open:

```text
http://localhost:3000/dashboard?mode=demo
```

## Services And Ports

| Service | URL | Purpose |
| --- | --- | --- |
| Frontend | `http://localhost:3000` | Next.js caregiver dashboard |
| Backend | `http://localhost:8000` | FastAPI API, scheduler, reports, alerts |
| Ollama | `http://localhost:11434` | Local Gemma 4 E2B inference |
| SQLite | `data/` | Local care timeline and app state |

## Requirements

Required:

- macOS, Linux, or Windows with WSL/Docker support.
- Docker Desktop, recommended for judge reproducibility.
- Ollama.
- Gemma 4 E2B model available in Ollama.

Recommended:

- 8 GB RAM minimum.
- 16 GB RAM preferred for smoother local model use.
- Chrome, Safari, or Edge.

Optional:

- Telegram bot token and chat ID.
- Seeed Studio fall sensor.
- Seeed Studio heart/breathing sensor.
- Phone on the same Wi-Fi for LAN dashboard access.

## Gemma Model

This project is configured for Gemma 4 E2B.

The Ollama model tag used by the app is:

```text
gemma4:e2b
```

Pull it before running locally:

```bash
ollama pull gemma4:e2b
```

If your Ollama installation uses a different local tag for Gemma 4 E2B, set:

```bash
GEMMA_MODEL=your-local-model-tag
```

The Docker demo also respects `GEMMA_MODEL`.

## Privacy Model

In the default local demo:

- Sensor/demo events are stored locally in SQLite.
- Gemma runs locally through Ollama.
- No camera is used.
- No resident timeline is sent to a cloud AI service.
- Telegram is optional.
- Demo mode can use mock alerts instead of real Telegram credentials.

Emergyx Care is designed around the principle that sensitive home-care data
should be processed locally whenever possible.

## Architecture

```text
Demo scenarios or ESPHome mmWave sensors
        |
        v
FastAPI backend
        |
        |-- SQLite local timeline
        |-- Event classification
        |-- Rule-based alert service
        |-- Report scheduler
        |-- Gemma context builder
        |-- Gemma findings
        |-- Telegram integration
        |
        v
Ollama running Gemma 4 E2B locally
        |
        |-- Chat answers
        |-- Incident explanations
        |-- Daily reports
        |-- Weekly reports
        |-- Pattern summaries
        |-- Optional notification drafting
        |
        v
Next.js caregiver dashboard
        |
        |-- Overview
        |-- Chat
        |-- Reports
        |-- Sensors
        |-- Residents
        |-- Settings
```

## Reports

Emergyx supports:

- Daily reports.
- Weekly reports.
- Weekly PDF export.
- Scheduled daily report time.
- Scheduled weekly report day/time.
- Telegram report delivery toggle.
- Autonomous Gemma pattern scans.

The weekly report is designed as a caregiver-facing report, not a raw event log.
It includes:

- Executive summary.
- Resident Safety Score.
- System Reliability Score.
- Clustered fall episodes.
- Room activity trends.
- Nighttime and bathroom trends.
- Sleep/rest signals.
- Alert delivery summary.
- Gemma analysis.
- Caregiver recommendations.
- Technical appendix.
- Safety disclaimer.

## Telegram

Telegram is optional. Demo mode can use mock alerts, so judges do not need a
Telegram token.

For real Telegram alerts, configure:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_SEND_GEMMA_EXPLANATIONS=false
```

Telegram command examples:

```text
/status
/dashboard
/latest
/report
/ask What happened today?
```

The `/dashboard` command can send the LAN dashboard link for phone access.

## Live Sensors

Live sensors are optional. The submission demo does not require hardware.

Supported live hardware path:

- Seeed Studio mmWave fall sensor with ESPHome.
- Seeed Studio heart/breathing sensor with ESPHome.
- Local LAN ESPHome API.
- Python ingestion using `aioesphomeapi`.

Real sensor mode depends on local hardware, network IPs, and ESPHome entity
keys. Use demo mode for judging unless the hardware is physically available.

## Phone Access

Phone access works when the laptop and phone are on the same Wi-Fi.

Find the laptop LAN IP.

macOS:

```bash
ifconfig
```

Look for an address like:

```text
192.168.1.35
```

Open this on the phone:

```text
http://<LAPTOP_LAN_IP>:3000/dashboard?mode=demo
```

Example:

```text
http://192.168.1.35:3000/dashboard?mode=demo
```

Do not use `localhost` from the phone. On a phone, `localhost` means the phone
itself, not the laptop.

If the phone cannot load the page:

- Confirm both devices are on the same Wi-Fi.
- Confirm the frontend was started with `--hostname 0.0.0.0`.
- Confirm the backend is listening on `0.0.0.0:8000`.
- Allow incoming connections if macOS or Windows firewall asks.
- Avoid guest Wi-Fi networks that block device-to-device traffic.

## Environment Variables

Core demo:

```env
EMERGYX_DEMO_PROFILE=true
MOCK_ALERT_CHANNEL=true
GEMMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
GEMMA_MODEL=gemma4:e2b
```

Telegram:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_SEND_GEMMA_EXPLANATIONS=false
```

Live sensor environment example:

```env
FDA2_SENSOR_IP=192.168.1.154
FDA2_SENSOR_ID=fda2_main
FDA2_ROOM=bedroom
FDA2_PERSON_KEY=807585817
FDA2_FALL_KEY=3722878921
FDA2_LIGHT_KEY=107269002
FDA2_RGB_LIGHT_KEY=3365290969
ENABLE_ILLUMINANCE=true
```

Multiple live sensors can be configured with `FDA2_SENSORS` JSON.

## Verification Commands

Backend compile check:

```bash
./.venv/bin/python -m compileall app scripts/seed_demo_data.py
```

Frontend lint:

```bash
cd frontend
npm run lint
```

Frontend production build:

```bash
cd frontend
npm run build
```

Demo verification:

```bash
./scripts/verify_demo.sh
```

Check backend health:

```bash
curl -s http://localhost:8000/health
```

Check Gemma status:

```bash
curl -s http://localhost:8000/agent/status
```

Check demo dashboard data:

```bash
curl -s 'http://localhost:8000/dashboard?mode=demo'
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Gemma is offline | Run `ollama serve`, then `ollama pull gemma4:e2b`, then check `/agent/status` |
| Docker command fails | Make sure Docker Desktop is installed and running |
| Port already in use | Stop the old process on ports `3000`, `8000`, or `11434` |
| Phone cannot connect | Use the laptop LAN IP, same Wi-Fi, and `--hostname 0.0.0.0` |
| Telegram does not respond | Confirm bot token, chat ID, backend process, and Telegram worker |
| Live sensor is missing | Use demo mode, or confirm ESPHome IP, port `6053`, and entity keys |

## Important Files

Backend:

```text
app/main.py
app/models.py
app/config.py
app/routers/
app/services/events.py
app/services/alerts.py
app/services/gemma_agent.py
app/services/gemma_findings.py
app/services/weekly_reports.py
app/services/report_scheduler.py
app/services/telegram.py
app/services/telegram_bot.py
```

Frontend:

```text
frontend/src/app/
frontend/src/components/mvpblocks/
frontend/src/components/ui/
frontend/src/lib/api.ts
frontend/src/lib/types.ts
```

Demo and deployment:

```text
.env.demo
docker-compose.yml
Dockerfile.backend
frontend/Dockerfile
scripts/start_demo.sh
scripts/verify_demo.sh
scripts/seed_demo_data.py
scripts/run_sensor_ingestion.py
```

Local data:

```text
data/
```

## Reproducibility Notes

The demo is designed to work without:

- Real sensors.
- Telegram credentials.
- Public hosting.
- Kaggle.
- Colab.
- Manual database setup.

The demo uses seeded local data and mock alerts so judges can evaluate the full
caregiver experience quickly.

Known external dependency:

- Ollama must be running and must have access to `gemma4:e2b` or the configured
  Gemma 4 E2B model tag.

If Gemma is unavailable, some AI-powered paths may fall back to deterministic
summaries or show Gemma as offline. For the intended hackathon demo, run Ollama
with Gemma 4 E2B available.

## Known Limitations

- This is a hackathon prototype, not a validated medical device.
- Demo mode uses seeded events and mock alerts.
- Live sensor mode depends on local ESPHome configuration and network availability.
- Gemma summaries are explanatory and should not be treated as clinical diagnosis.
- Fall detection accuracy has not been clinically validated.
- The system should not be used as the only source of emergency detection or
  clinical decision-making.
- Real-world deployment would require hardware validation, caregiver workflow
  testing, safety review, privacy review, and regulatory assessment.

## Submission Recommendation

Submit with:

- The repository.
- This README.
- A short demo video.
- Screenshots of Care Overview, Gemma Assistant, Reports, Sensors, Residents,
  and Settings.
- Clear note that the recommended judging path is demo mode.

Recommended judge command sequence:

```bash
git clone <repo-url>
cd emergyx-care
ollama pull gemma4:e2b
./scripts/start_demo.sh
./scripts/verify_demo.sh
```

Then open:

```text
http://localhost:3000/dashboard?mode=demo
```

## Safety Disclaimer

Emergyx Care is a hackathon prototype and caregiver-support demo.

It is not a medical device, does not diagnose medical conditions, and should not
be used as the only source of emergency detection or clinical decision-making.

Gemma-generated explanations and reports are intended to help caregivers
understand logged events. They do not replace professional medical evaluation,
emergency services, or validated clinical monitoring systems.
