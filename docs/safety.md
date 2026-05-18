# Emergyx Care Safety Notes

Emergyx Care is a **privacy-first caregiver-support prototype**. It is not a
medical device, not a diagnostic tool, and not a substitute for a direct
caregiver check-in.

## Hard boundaries

- **Not a medical device.** Nothing in this system is regulated, validated, or
  certified for clinical use.
- **Not for diagnosis.** No score, label, or trend in this system should be
  interpreted as a diagnosis or a clinical recommendation.
- **Not for baby monitoring, not for SIDS prevention.** The MR60BHA2 is framed
  only as an *optional* bedside sleep/rest sensor and not as anything that
  watches infants.
- **No camera.** Sensing is 60 GHz mmWave only. There is no image, no audio,
  no video.
- **Local-first.** The raw home timeline lives in a local SQLite file. The
  dashboard is intended for the home network only.
- **Urgent alerts are rule-based.** A fixed rule (`fall_detected=true →
  immediate caregiver alert`) is the urgent path. The LLM is *never* the
  urgent decision-maker.
- **Trend analysis is advisory only.** Local trends and unusual-change flags
  are caregiver context after events are logged; they never trigger urgent
  safety actions by themselves.
- **Telegram explanations are follow-ups only.** If enabled, Gemma/deterministic
  explanation messages are sent after the immediate alert and never block alert
  delivery.
- **Telegram commands are local-data only.** The command worker only responds to
  the configured caregiver chat and answers from the local SQLite timeline.

## Reliability notes

- mmWave sensing is sensitive to placement, orientation, and obstructions.
- False positives and false negatives are possible.
- Always describe an event as a **likely fall**, never a *definite* fall.
- Caregivers must verify the person's condition directly. The Telegram alert
  text says so explicitly.

## Light context wording

Illuminance is included as **context only**. Use:

- "Light context: dark, 0.3 lux."
- "The room was categorized as dark."
- "This may be useful context for the caregiver."

Avoid:

- "The patient fell because it was dark."
- "Darkness caused the fall."
- "The room was unsafe."

## What Gemma is and isn't allowed to say

Gemma is **bounded** by a fixed system prompt:

- **Allowed**: summarizing the structured local timeline, naming what was
  observed, mentioning light context as context only, recommending a direct
  caregiver check-in after an urgent event, repeating the prototype/not a
  medical device disclaimer.
- **Disallowed**: diagnosis, severity scoring, prescribing actions beyond
  "check on the person directly," inventing events that are not in the data,
  overclaiming about sensing capabilities.

If Gemma is offline the same wording rules are enforced by deterministic
fallback text.

## Product wording guidance

Use:

- "likely fall"
- "caregiver-support tool"
- "local event timeline"
- "privacy-first"
- "rule-based urgent alerts"
- "Gemma explains and summarizes after safety rules fire"

Do not use:

- "diagnostic system"
- "guaranteed fall prevention"
- "baby monitoring"
- "SIDS prevention"
- "near-fall detection"
- "through-wall vision"
