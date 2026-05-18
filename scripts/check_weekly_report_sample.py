from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Alert, Event
from app.services.weekly_reports import (
    _alert_delivery_summary,
    _cluster_fall_episodes,
    _resident_safety_score,
    _system_reliability_score,
    format_room_name,
)
from app.services.utils import current_timestamp


def _event(timestamp: str, room: str, event_type: str, value: str, sensor_id: str = "sample") -> Event:
    return Event(
        timestamp=timestamp,
        sensor_id=sensor_id,
        room=room,
        event_type=event_type,
        value=value,
        source="live",
    )


def main() -> None:
    falls = [
        _event("2026-05-14T17:58:00+02:00", "auto_room_209", "fall_detected", "true", "sensor_209"),
        _event("2026-05-14T18:00:00+02:00", "auto_room_209", "fall_detected", "true", "sensor_209"),
        _event("2026-05-14T18:03:00+02:00", "auto_room_209", "fall_detected", "true", "sensor_209"),
        _event("2026-05-14T18:05:00+02:00", "auto_room_209", "fall_detected", "true", "sensor_209"),
        _event("2026-05-16T07:52:00+02:00", "auto_room_153", "fall_detected", "true", "sensor_153"),
    ]
    episodes = _cluster_fall_episodes(None, falls)  # type: ignore[arg-type]
    alerts = [
        Alert(
            timestamp="2026-05-14T18:00:30+02:00",
            event_id=None,
            severity="critical",
            alert_type="fall",
            message="sample",
            sent_channel="telegram",
            sent_success=True,
        )
        for _ in range(5)
    ]
    reliability_rows = [
        {"staleness": "fresh"},
        {"staleness": "fresh"},
        {"staleness": "fresh"},
    ]
    safety = _resident_safety_score(
        episodes=episodes,
        raw_fall_detections=len(falls),
        generated_at=current_timestamp(),
    )
    reliability = _system_reliability_score(events=falls, alerts=alerts, reliability_rows=reliability_rows)
    delivery = _alert_delivery_summary(alerts, episodes)

    assert format_room_name("auto_room_209") == "Sensor Area 209"
    assert len(falls) == 5
    assert len(episodes) == 2
    assert episodes[0]["raw_detection_count"] == 4
    assert episodes[0]["confidence"] == "High"
    assert episodes[1]["raw_detection_count"] == 1
    assert safety["label"] == "High concern"
    assert reliability["label"] == "Excellent"
    assert delivery["alerts_sent"] == 5
    assert "sent alert" not in " ".join(safety["decreases"]).lower()
    print("weekly report sample checks passed")


if __name__ == "__main__":
    main()
