from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sqlmodel import Session, delete, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import save_runtime_care_context, save_runtime_report_schedule
from app.db import engine, init_db
from app.models import Alert, ChatMessage, ChatThread, DailyReport, Event, GemmaFinding, WeeklyReport
from app.services.events import create_event
from app.services.utils import current_timestamp, normalize_metadata


DEMO_SOURCE = "simulated"
DEMO_ALERT_CHANNEL = "simulated_seed"
DEMO_MODE = "demo"


def local_timestamp_for(day: date, hour: int, minute: int, second: int = 0) -> str:
    dt = datetime.combine(day, time(hour=hour, minute=minute, second=second)).astimezone()
    return dt.isoformat(timespec="seconds")


def set_timestamp(session: Session, event: Event, timestamp: str) -> Event:
    event.timestamp = timestamp
    session.add(event)
    return event


def add_event(
    session: Session,
    *,
    day: date,
    hour: int,
    minute: int,
    sensor_id: str,
    room: str,
    event_type: str,
    value: object,
    metadata: dict[str, object] | None = None,
) -> Event:
    event = create_event(
        session,
        sensor_id=sensor_id,
        room=room,
        event_type=event_type,
        value=value,
        source=DEMO_SOURCE,
        metadata_json={"seeded": True, **(metadata or {})},
        trigger_alerts=False,
    )
    return set_timestamp(session, event, local_timestamp_for(day, hour, minute))


def add_alert(session: Session, *, event: Event | None, timestamp: str, severity: str, message: str, alert_type: str = "likely_fall") -> Alert:
    alert = Alert(
        timestamp=timestamp,
        event_id=event.id if event else None,
        severity=severity,
        alert_type=alert_type,
        message=message,
        sent_channel=DEMO_ALERT_CHANNEL,
        sent_success=True,
        metadata_json=normalize_metadata({"seeded": True, "mock_delivery": True, "mode": DEMO_MODE}),
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def demo_care_context(now: str) -> dict[str, object]:
    return {
        "residents": [
            {
                "id": "resident_david",
                "name": "David Cohen",
                "rooms": ["bedroom", "bathroom", "living_room"],
                "context": (
                    "David is an 82-year-old resident in the demo home. He usually rests in the bedroom, "
                    "spends afternoons in the living room, and needs caregiver review after repeated likely-fall signals."
                ),
                "created_at": now,
                "updated_at": now,
            }
        ],
        "manual_rooms": ["bedroom", "bathroom", "living_room"],
        "deleted_rooms": [],
        "sensor_assignments": {
            "demo_fda2_bedroom": "bedroom",
            "demo_fda2_living_room": "living_room",
            "demo_bha2_bedside": "bedroom",
            "demo_mmwave_bathroom": "bathroom",
        },
        "sensor_names": {
            "demo_fda2_bedroom": "Bedroom fall sensor",
            "demo_fda2_living_room": "Living room fall sensor",
            "demo_bha2_bedside": "Bedside heart and breathing sensor",
            "demo_mmwave_bathroom": "Bathroom presence sensor",
        },
        "sensor_contexts": {
            "demo_fda2_bedroom": "Ceiling-mounted mmWave fall sensor covering bed exit and bedroom walkway.",
            "demo_fda2_living_room": "Living room mmWave fall sensor covering chair and open floor area.",
            "demo_bha2_bedside": "Bedside vitals sensor for non-diagnostic heart and breathing trend context.",
            "demo_mmwave_bathroom": "Bathroom motion/presence signal for nighttime activity trends.",
        },
        "sensor_led_colors": {
            "demo_fda2_bedroom": "#14b8a6",
            "demo_fda2_living_room": "#3b82f6",
            "demo_bha2_bedside": "#a855f7",
            "demo_mmwave_bathroom": "#f59e0b",
        },
        "room_display_names": {
            "bedroom": "Bedroom",
            "bathroom": "Bathroom",
            "living_room": "Living Room",
        },
        "updated_at": now,
    }


def add_daily_reports(session: Session, today: date) -> None:
    for offset in range(2, -1, -1):
        day = today - timedelta(days=offset)
        text = (
            f"Daily Caregiver Report - {day.isoformat()}\n\n"
            "Gemma summary: Demo data shows local sensor coverage across bedroom, bathroom, and living room. "
            "One clustered likely-fall pattern was detected this week and nighttime bathroom activity is elevated "
            "compared with the earlier baseline. Review the incident timeline and room fall risks.\n\n"
            "Not a medical diagnosis."
        )
        report = DailyReport(
            date=day.isoformat(),
            report_text=text,
            created_at=local_timestamp_for(day, 20, 0),
            metadata_json=normalize_metadata({"mode": DEMO_MODE, "seeded": True, "model_name": "gemma4:e2b"}),
        )
        session.add(report)
    session.commit()


def weekly_pdf_bytes(today: date) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Emergyx Care Weekly Safety & Wellness Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Demo week ending {today.isoformat()} - generated for hackathon judges.", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("Resident Safety Score: 35 / 100 - High concern", styles["Heading2"]),
        Paragraph("System Reliability Score: 96 / 100 - Excellent", styles["Heading2"]),
        Spacer(1, 12),
        Paragraph(
            "Gemma analysis: two likely fall episodes were identified from clustered fall-like detections. "
            "Nighttime bathroom activity increased versus baseline. Caregiver review is recommended. "
            "Not a medical diagnosis.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()


def add_weekly_report(session: Session, today: date) -> None:
    start = today - timedelta(days=6)
    report = WeeklyReport(
        start_date=start.isoformat(),
        end_date=today.isoformat(),
        created_at=current_timestamp(),
        mode=DEMO_MODE,
        filename=f"emergyx-weekly-demo-{start.isoformat()}-{today.isoformat()}.pdf",
        model_name="gemma4:e2b",
        pdf_bytes=weekly_pdf_bytes(today),
        metadata_json=normalize_metadata({"mode": DEMO_MODE, "seeded": True, "used_mock": False}),
    )
    session.add(report)
    session.commit()


def add_chat(session: Session, today: date) -> None:
    now = current_timestamp()
    thread = ChatThread(
        title="Judge demo: what changed this week?",
        mode=DEMO_MODE,
        created_at=now,
        updated_at=now,
        metadata_json=normalize_metadata({"seeded": True}),
    )
    session.add(thread)
    session.commit()
    session.refresh(thread)
    messages = [
        ("user", "What should I pay attention to this week?", None),
        (
            "assistant",
            (
                "This demo week shows two likely fall episodes, elevated nighttime bathroom activity, "
                "and reliable sensor coverage. Review the clustered bedroom incident, check lighting and trip risks, "
                "and compare future vitals against David's personal baseline. Not a medical diagnosis."
            ),
            "gemma4:e2b",
        ),
    ]
    for role, content, model in messages:
        session.add(
            ChatMessage(
                thread_id=thread.id or 0,
                role=role,
                content=content,
                created_at=now,
                model_name=model,
                used_mock=False if model else None,
                metadata_json=normalize_metadata({"seeded": True, "tools_used": ["events", "reports", "care_context"]}),
            )
        )
    session.commit()


def add_gemma_finding(session: Session, today: date, alert: Alert | None) -> None:
    finding = GemmaFinding(
        created_at=current_timestamp(),
        mode=DEMO_MODE,
        source_filter="__demo_simulated__",
        pattern_type="nighttime_activity",
        severity="medium",
        title="Nighttime bathroom activity increased",
        summary=(
            "Gemma found more nighttime bathroom presence readings than the earlier baseline, alongside a recent "
            "likely-fall episode. This is caregiver context and should be reviewed without assuming a medical cause."
        ),
        evidence_json=normalize_metadata([
            "5 nighttime bathroom readings in the latest demo night",
            "2 likely fall episodes this week",
            "All demo sensors reported fresh seeded data",
        ]),
        caregiver_action="Review the bathroom path, lighting, rugs, and support rails; continue monitoring tonight.",
        model_name="gemma4:e2b",
        send_alert=True,
        alert_id=alert.id if alert else None,
        fingerprint=f"demo-{today.isoformat()}-nighttime-activity",
        metadata_json=normalize_metadata({"seeded": True, "overall_summary": "Judge demo pattern finding"}),
    )
    session.add(finding)
    session.commit()


def clear_seeded(session: Session) -> None:
    session.exec(delete(ChatMessage).where(ChatMessage.metadata_json.contains('"seeded"')))
    session.exec(delete(ChatThread).where(ChatThread.metadata_json.contains('"seeded"')))
    session.exec(delete(GemmaFinding).where(GemmaFinding.metadata_json.contains('"seeded"')))
    session.exec(delete(WeeklyReport).where(WeeklyReport.metadata_json.contains('"seeded"')))
    session.exec(delete(DailyReport).where(DailyReport.metadata_json.contains('"seeded"')))
    session.exec(delete(Alert).where(Alert.sent_channel == DEMO_ALERT_CHANNEL))
    session.exec(delete(Event).where(Event.source == DEMO_SOURCE))
    session.commit()


def seed(*, reset: bool = True) -> None:
    init_db()
    today = datetime.now().astimezone().date()
    rng = random.Random(42)
    now = current_timestamp()

    with Session(engine) as session:
        if reset:
            clear_seeded(session)

        save_runtime_care_context(demo_care_context(now))
        save_runtime_report_schedule(
            {
                "daily_enabled": True,
                "daily_time": "20:00",
                "daily_send_telegram": False,
                "weekly_enabled": True,
                "weekly_day": 0,
                "weekly_time": "09:00",
                "weekly_send_telegram": False,
                "pattern_enabled": True,
                "pattern_interval_minutes": 60,
                "pattern_send_telegram": False,
                "last_pattern_summary": "Demo pattern monitor is enabled for the judge walkthrough.",
            }
        )

        latest_alert: Alert | None = None
        for days_back in range(13, -1, -1):
            day = today - timedelta(days=days_back)
            hr_base = 78 + (0 if days_back > 6 else 5)
            rr_base = 14 + (0 if days_back > 6 else 1)

            day_activity_hours = (7, 10, 14) if days_back == 0 else (7, 12, 18)
            for hour in day_activity_hours:
                add_event(
                    session,
                    day=day,
                    hour=hour,
                    minute=rng.randint(0, 20),
                    sensor_id="demo_fda2_living_room",
                    room="living_room",
                    event_type="person_present",
                    value=True,
                    metadata={"period": f"{hour}:00"},
                )
                add_event(
                    session,
                    day=day,
                    hour=hour,
                    minute=rng.randint(25, 45),
                    sensor_id="demo_fda2_living_room",
                    room="living_room",
                    event_type="illuminance",
                    value=round(35 + rng.random() * 80, 1),
                    metadata={"period": f"{hour}:00"},
                )

            vital_hours = (6, 15) if days_back == 0 else (6, 22)
            for hour in vital_hours:
                add_event(
                    session,
                    day=day,
                    hour=hour,
                    minute=rng.randint(0, 30),
                    sensor_id="demo_bha2_bedside",
                    room="bedroom",
                    event_type="heart_rate",
                    value=hr_base + rng.randint(-5, 7),
                    metadata={"unit": "bpm"},
                )
                add_event(
                    session,
                    day=day,
                    hour=hour,
                    minute=rng.randint(31, 55),
                    sensor_id="demo_bha2_bedside",
                    room="bedroom",
                    event_type="respiration_rate",
                    value=round(rr_base + rng.uniform(-1.5, 2.0), 1),
                    metadata={"unit": "breaths/min"},
                )
                add_event(
                    session,
                    day=day,
                    hour=hour,
                    minute=rng.randint(0, 55),
                    sensor_id="demo_bha2_bedside",
                    room="bedroom",
                    event_type="distance",
                    value=round(52 + rng.uniform(-6, 8), 1),
                    metadata={"unit": "cm"},
                )

            if days_back <= 4:
                for index in range(1 if days_back else 5):
                    event_hour = (1 + min(index, 2)) if days_back == 0 else (23 if index < 3 else 2)
                    add_event(
                        session,
                        day=day,
                        hour=event_hour,
                        minute=(10 + index * 7) % 60,
                        sensor_id="demo_mmwave_bathroom",
                        room="bathroom",
                        event_type="person_present",
                        value=True,
                        metadata={"scenario": "nighttime_bathroom_activity"},
                    )

            if days_back == 3:
                cluster: list[Event] = []
                for minute in (58, 61, 63, 65):
                    hour = 17 + minute // 60
                    real_minute = minute % 60
                    cluster.append(
                        add_event(
                            session,
                            day=day,
                            hour=hour,
                            minute=real_minute,
                            sensor_id="demo_fda2_bedroom",
                            room="bedroom",
                            event_type="fall_detected",
                            value=True,
                            metadata={"scenario": "clustered_likely_fall"},
                        )
                    )
                clear_event = add_event(
                    session,
                    day=day,
                    hour=18,
                    minute=8,
                    sensor_id="demo_fda2_bedroom",
                    room="bedroom",
                    event_type="fall_detected",
                    value=False,
                    metadata={"scenario": "fall_cleared"},
                )
                latest_alert = add_alert(
                    session,
                    event=cluster[0],
                    timestamp=cluster[0].timestamp,
                    severity="high",
                    message=(
                        "Mock caregiver alert: Gemma/rules flagged a likely fall episode in Bedroom. "
                        "Four raw detections occurred within 7 minutes. Please review the incident timeline."
                    ),
                )
                _ = clear_event

            if days_back == 1:
                fall = add_event(
                    session,
                    day=day,
                    hour=7,
                    minute=52,
                    sensor_id="demo_fda2_living_room",
                    room="living_room",
                    event_type="fall_detected",
                    value=True,
                    metadata={"scenario": "single_likely_fall"},
                )
                add_event(
                    session,
                    day=day,
                    hour=7,
                    minute=58,
                    sensor_id="demo_fda2_living_room",
                    room="living_room",
                    event_type="fall_detected",
                    value=False,
                    metadata={"scenario": "fall_cleared"},
                )
                add_alert(
                    session,
                    event=fall,
                    timestamp=fall.timestamp,
                    severity="medium",
                    message="Mock caregiver alert: single likely-fall signal in Living Room. Caregiver review recommended.",
                )

        add_daily_reports(session, today)
        add_weekly_report(session, today)
        add_chat(session, today)
        add_gemma_finding(session, today, latest_alert)
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a polished Emergyx Care judge demo dataset.")
    parser.add_argument("--no-reset", action="store_true", help="Append demo data instead of clearing previous seeded demo rows.")
    parser.add_argument("--scenario", default="polished_judge_demo", choices=["polished_judge_demo"])
    args = parser.parse_args()
    seed(reset=not args.no_reset)
    print(f"Seeded {args.scenario} at {current_timestamp()}")


if __name__ == "__main__":
    main()
