# Emergyx Care Hardware Notes

## Sensors

- **2 × Seeed Studio MR60FDA2** — 60 GHz mmWave fall-detection kit, includes
  XIAO ESP32C6, ships with stock ESPHome firmware.
- **1 × Seeed Studio MR60BHA2** — 60 GHz breathing/heart-rate sensor. Optional,
  bedside/sleep-only framing. **Not** baby monitoring, **not** medical
  monitoring.

## Proven path

The current working chain is:

```text
MR60FDA2 #1
   → ESPHome native API (port 6053)
   → aioesphomeapi
   → app.sensor_ingestion.FDA2IngestionManager
   → app.services.events.create_event
   → SQLite (data/emergyx_care.db)
   → app.services.alerts.handle_event_alerts → optional Telegram
```

A real-fall trigger was captured at `2026-04-30 21:56:58` local time.

## Operator-specific values

These are read from `.env` and are specific to a single sensor. They are
**not committed** to source control:

- `FDA2_SENSOR_IP` — current LAN address of the sensor (e.g. `192.168.1.154`)
- `FDA2_API_PASSWORD` — optional, only set if the device requires it
- `FDA2_PERSON_KEY` — entity key for "Person Information"
- `FDA2_FALL_KEY` — entity key for "Falling Information"
- `FDA2_LIGHT_KEY` — entity key for "Seeed MR60FDA2 Illuminance"
- `FDA2_RGB_LIGHT_KEY` — optional entity key for "Seeed MR60FDA2 RGB Light";
  if omitted, the Settings page command path tries to auto-discover it by name

When both FDA2 sensors are active, prefer `FDA2_SENSORS` instead of the legacy
single-sensor fields. Keep the value on one line in `.env`; it is formatted
below for readability:

```env
FDA2_SENSORS='[
  {"sensor_id":"fda2_living_room","room":"living_room","host":"192.168.1.154","port":6053,"person_key":807585817,"fall_key":3722878921,"light_key":107269002,"rgb_light_key":3365290969,"enable_illuminance":true},
  {"sensor_id":"fda2_bedroom","room":"bedroom","host":"192.168.1.155","port":6053,"person_key":111111111,"fall_key":222222222,"light_key":333333333,"rgb_light_key":444444444,"enable_illuminance":true}
]'
```

The ingestion manager keeps last-seen values and illuminance throttling per
`sensor_id`, so a second FDA2 does not suppress or overwrite the first sensor's
state changes.

## Observed entity names on the sensor

- Person Information
- Falling Information
- Seeed MR60FDA2 Illuminance
- Seeed MR60FDA2 RGB Light
- Get Radar Parameters
- Reset
- Set Install Height
- Set Height Threshold
- Set Sensitivity

The first three are consumed by the live safety pipeline. The RGB light is
controlled only from the Settings page for setup/room identification. The rest
are sensor configuration controls and are intentionally untouched at runtime.

## Mounting and power

- **Power**: 5 V / 1 A
- **Recommended placement**: 2.2 m – 3.0 m, looking down into the room
- **Successful real fall trigger**: ceiling-mounted at ~2.8 m

Mounting affects reliability. The fall-detection cone is narrower than a
camera and is sensitive to tilt and yaw.

## Illuminance / light context

`ENABLE_ILLUMINANCE=true` enables the light path. The ingestion manager
throttles writes:

- Always save when the lux **category** changes (`dark`, `dim`, `low_indoor`,
  `normal_indoor`, `bright`).
- Otherwise save at most once per `ILLUMINANCE_MIN_INTERVAL_SECONDS` (default 60).

Light is treated as **context only** in alerts, the dashboard, and Gemma.
Emergyx Care never claims darkness causes a fall.

## MR60BHA2 positioning

The MR60BHA2 is reserved as a future bedside sleep/rest sensor. It is **not**
the fall sensor and is intentionally not framed as a baby monitor, an apnea
device, or a vital-signs medical product.
