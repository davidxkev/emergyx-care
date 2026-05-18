from __future__ import annotations

from aioesphomeapi.core import APIConnectionError
from fastapi import APIRouter, HTTPException
import httpx

from app.config import (
    delete_runtime_fda2_sensor,
    get_settings,
    load_runtime_care_context,
    load_runtime_gemma_config,
    load_runtime_telegram_config,
    save_runtime_care_context,
    save_runtime_gemma_config,
    save_runtime_telegram_config,
)
from app.schemas import (
    CareContextRead,
    CareContextUpdate,
    CareContextUpdateResponse,
    GemmaModelPullRequest,
    GemmaSettingsRead,
    GemmaSettingsUpdate,
    GemmaSettingsUpdateResponse,
    SensorDeleteResponse,
    SensorAutoDetectRequest,
    SensorAutoDetectResponse,
    SensorIngestionRestartResponse,
    SensorLedCommandRequest,
    SensorLedCommandResponse,
    TelegramSettingsRead,
    TelegramSettingsUpdate,
    TelegramSettingsUpdateResponse,
)
from app.services.gemma_agent import gemma_status_snapshot
from app.services.fda2_led import SensorLedError, command_sensor_led
from app.services.ingestion_control import restart_ingestion
from app.services.sensor_autodetect import discover_and_configure_sensors
from app.services.telegram import send_telegram_message
from app.services.utils import current_timestamp


router = APIRouter(prefix="/settings", tags=["settings"])


def _mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 10:
        return "configured"
    return f"{token[:5]}...{token[-4:]}"


def _telegram_settings_read() -> TelegramSettingsRead:
    settings = get_settings()
    return TelegramSettingsRead(
        configured=bool(settings.telegram_bot_token and settings.telegram_chat_id),
        bot_token_set=bool(settings.telegram_bot_token),
        bot_token_masked=_mask_token(settings.telegram_bot_token),
        chat_id=settings.telegram_chat_id or None,
        send_gemma_explanations=settings.telegram_send_gemma_explanations,
        poll_timeout_seconds=settings.telegram_poll_timeout_seconds,
        poll_interval_seconds=settings.telegram_poll_interval_seconds,
    )


def _gemma_settings_read() -> GemmaSettingsRead:
    settings = get_settings()
    status = gemma_status_snapshot()
    return GemmaSettingsRead(
        enabled=settings.gemma_enabled,
        model=settings.gemma_model,
        ollama_base_url=settings.ollama_base_url,
        gemma_first_notifications=settings.gemma_first_notifications,
        status=str(status.get("status") or "unknown"),
        reachable=bool(status.get("reachable")),
        installed_models=[
            str(item) for item in (status.get("installed_models") or []) if item
        ],
        error=str(status.get("error")) if status.get("error") else None,
    )


def _clean_string_list(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


def _clean_string_map(values: dict[str, str]) -> dict[str, str]:
    return {
        key.strip(): value.strip()
        for key, value in values.items()
        if key.strip() and value.strip()
    }


def _care_context_read() -> CareContextRead:
    raw = load_runtime_care_context()
    return CareContextRead.model_validate(
        {
            "residents": raw.get("residents") or [],
            "manual_rooms": raw.get("manual_rooms") or [],
            "deleted_rooms": raw.get("deleted_rooms") or [],
            "sensor_assignments": raw.get("sensor_assignments") or {},
            "sensor_names": raw.get("sensor_names") or {},
            "sensor_contexts": raw.get("sensor_contexts") or {},
            "sensor_led_colors": raw.get("sensor_led_colors") or {},
            "room_display_names": raw.get("room_display_names") or {},
            "updated_at": raw.get("updated_at"),
        }
    )


@router.get("/gemma", response_model=GemmaSettingsRead)
def get_gemma_settings() -> GemmaSettingsRead:
    return _gemma_settings_read()


@router.post("/gemma", response_model=GemmaSettingsUpdateResponse)
def update_gemma_settings(payload: GemmaSettingsUpdate) -> GemmaSettingsUpdateResponse:
    save_runtime_gemma_config(
        {
            **load_runtime_gemma_config(),
            "gemma_enabled": payload.enabled,
            "gemma_model": payload.model.strip(),
            "ollama_base_url": payload.ollama_base_url.strip().rstrip("/"),
            "gemma_first_notifications": payload.gemma_first_notifications,
        }
    )
    return GemmaSettingsUpdateResponse(
        success=True,
        message="Gemma/Ollama settings saved.",
        settings=_gemma_settings_read(),
    )


@router.post("/gemma/pull", response_model=GemmaSettingsUpdateResponse)
def pull_gemma_model(payload: GemmaModelPullRequest) -> GemmaSettingsUpdateResponse:
    settings = get_settings()
    model = payload.model.strip()
    try:
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/pull",
            json={"name": model, "stream": False},
            timeout=900.0,
        )
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama model pull failed: {exc}") from exc

    if payload.save_as_current:
        save_runtime_gemma_config(
            {
                **load_runtime_gemma_config(),
                "gemma_enabled": True,
                "gemma_model": model,
                "ollama_base_url": settings.ollama_base_url.rstrip("/"),
            }
        )
    return GemmaSettingsUpdateResponse(
        success=True,
        message=f"Model {model} is available in Ollama.",
        settings=_gemma_settings_read(),
    )


@router.get("/care-context", response_model=CareContextRead)
def get_care_context() -> CareContextRead:
    return _care_context_read()


@router.post("/care-context", response_model=CareContextUpdateResponse)
def update_care_context(payload: CareContextUpdate) -> CareContextUpdateResponse:
    clean = {
        "residents": [
            resident.model_dump()
            for resident in payload.residents
            if resident.id.strip() and resident.name.strip()
        ],
        "manual_rooms": _clean_string_list(payload.manual_rooms),
        "deleted_rooms": _clean_string_list(payload.deleted_rooms),
        "sensor_assignments": _clean_string_map(payload.sensor_assignments),
        "sensor_names": _clean_string_map(payload.sensor_names),
        "sensor_contexts": _clean_string_map(payload.sensor_contexts),
        "sensor_led_colors": _clean_string_map(payload.sensor_led_colors),
        "room_display_names": _clean_string_map(payload.room_display_names),
        "updated_at": current_timestamp(),
    }
    save_runtime_care_context(clean)
    return CareContextUpdateResponse(
        success=True,
        message="Care context saved.",
        context=_care_context_read(),
    )


@router.get("/telegram", response_model=TelegramSettingsRead)
def get_telegram_settings() -> TelegramSettingsRead:
    return _telegram_settings_read()


@router.post("/telegram", response_model=TelegramSettingsUpdateResponse)
def update_telegram_settings(payload: TelegramSettingsUpdate) -> TelegramSettingsUpdateResponse:
    runtime = load_runtime_telegram_config()
    token = (payload.bot_token or "").strip()
    chat_id = (payload.chat_id or "").strip()

    if payload.clear_bot_token:
        runtime["telegram_bot_token"] = ""
    elif token:
        runtime["telegram_bot_token"] = token

    if payload.clear_chat_id:
        runtime["telegram_chat_id"] = ""
    elif chat_id:
        runtime["telegram_chat_id"] = chat_id

    runtime["telegram_send_gemma_explanations"] = payload.send_gemma_explanations
    runtime["telegram_poll_timeout_seconds"] = payload.poll_timeout_seconds
    runtime["telegram_poll_interval_seconds"] = payload.poll_interval_seconds
    save_runtime_telegram_config(runtime)

    test_success: bool | None = None
    if payload.send_test_message:
        test_success = send_telegram_message(
            "Emergyx Care Telegram setup test\n\n"
            f"Sent at {current_timestamp()}.\n\n"
            "This is a prototype caregiver-support channel. Not a medical device."
        )

    read = _telegram_settings_read()
    message = "Telegram settings saved."
    if payload.send_test_message:
        message += " Test message sent." if test_success else " Test message failed."
    return TelegramSettingsUpdateResponse(
        success=True,
        message=message,
        settings=read,
        test_success=test_success,
    )


@router.post("/led", response_model=SensorLedCommandResponse)
async def set_sensor_led(payload: SensorLedCommandRequest) -> SensorLedCommandResponse:
    try:
        result = await command_sensor_led(
            sensor_id=payload.sensor_id,
            hex_color=payload.hex_color,
            brightness=payload.brightness,
            flash_seconds=payload.flash_seconds,
            turn_off=payload.turn_off,
        )
    except SensorLedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (APIConnectionError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"Sensor connection failed: {exc}") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=f"Sensor command timed out: {exc}") from exc

    action = "turned off" if result.turn_off else "updated"
    return SensorLedCommandResponse(
        success=True,
        sensor_id=result.sensor.sensor_id,
        room=result.sensor.room,
        rgb_light_key=result.rgb_light_key,
        discovered=result.discovered,
        hex_color=result.hex_color,
        message=f"{result.sensor.room} LED {action}.",
    )


@router.post("/sensors/auto-detect", response_model=SensorAutoDetectResponse)
async def auto_detect_sensors(payload: SensorAutoDetectRequest) -> SensorAutoDetectResponse:
    settings = get_settings()
    result = await discover_and_configure_sensors(
        settings=settings,
        hosts=payload.hosts,
        include_subnet_scan=payload.include_subnet_scan,
        timeout_seconds=payload.timeout_seconds,
        concurrency=payload.concurrency,
        room_hint=payload.room_hint,
    )
    return SensorAutoDetectResponse(
        success=True,
        scanned_hosts=int(result.get("scanned_hosts", 0)),
        discovered=result.get("discovered", []),
    )


@router.post("/sensors/restart-ingestion", response_model=SensorIngestionRestartResponse)
async def restart_sensor_ingestion() -> SensorIngestionRestartResponse:
    success, restarted, pid, message = restart_ingestion()
    if not success:
        raise HTTPException(status_code=503, detail=message)
    return SensorIngestionRestartResponse(
        success=True,
        restarted=restarted,
        pid=pid,
        message=message,
    )


@router.delete("/sensors/{sensor_id}", response_model=SensorDeleteResponse)
async def delete_sensor(sensor_id: str) -> SensorDeleteResponse:
    removed = delete_runtime_fda2_sensor(sensor_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=(
                "Sensor was not found in runtime-discovered sensors. "
                "Sensors configured directly in environment variables must be removed from configuration."
            ),
        )

    success, restarted, pid, message = restart_ingestion()
    if not success:
        raise HTTPException(status_code=503, detail=message)
    return SensorDeleteResponse(
        success=True,
        sensor_id=sensor_id,
        removed=True,
        restarted=restarted,
        pid=pid,
        message=f"Removed {sensor_id}. {message}",
    )
