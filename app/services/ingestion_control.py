from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
PID_PATH = BASE_DIR / "data" / "ingestion.pid"
LOG_PATH = BASE_DIR / "data" / "ingestion.log"


def _read_pid() -> int | None:
    try:
        if not PID_PATH.exists():
            return None
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return int(raw)
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    try:
        PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        try:
            status = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "stat="],
                text=True,
            ).strip()
            if "Z" in status:
                return False
        except Exception:
            pass
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _pid_command(pid: int) -> str | None:
    try:
        output = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
        )
    except Exception:
        return None
    command = output.strip()
    return command or None


def _is_ingestion_process(pid: int) -> bool:
    command = _pid_command(pid)
    if not command:
        return False
    return "run_sensor_ingestion.py" in command


def _python_for_ingestion() -> str:
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def stop_ingestion(timeout_seconds: float = 8.0) -> tuple[bool, str]:
    pid = _read_pid()
    if pid is None:
        return True, "No managed ingestion process found."

    if not _is_running(pid):
        _clear_pid()
        return True, "Ingestion process was not running."

    if not _is_ingestion_process(pid):
        _clear_pid()
        return True, f"Ignored stale pid {pid}; it is not the ingestion process."

    try:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            _clear_pid()
            return True, "Ingestion process already exited."
        except Exception:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_pid()
        return True, "Ingestion process already exited."
    except Exception as exc:
        return False, f"Failed to stop ingestion process {pid}: {exc}"

    deadline = time.time() + max(0.2, timeout_seconds)
    while time.time() < deadline:
        if not _is_running(pid):
            _clear_pid()
            return True, f"Stopped ingestion process {pid}."
        time.sleep(0.15)

    try:
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    time.sleep(0.15)
    if not _is_running(pid):
        _clear_pid()
        return True, f"Stopped ingestion process {pid}."
    return False, f"Timed out stopping ingestion process {pid}."


def start_ingestion() -> tuple[bool, int | None, str]:
    existing_pid = _read_pid()
    if existing_pid is not None:
        if _is_running(existing_pid) and _is_ingestion_process(existing_pid):
            return True, existing_pid, f"Ingestion already running (pid {existing_pid})."
        _clear_pid()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    python_exec = _python_for_ingestion()
    command = [python_exec, str(BASE_DIR / "scripts" / "run_sensor_ingestion.py")]

    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    time.sleep(0.2)
    if process.poll() is not None:
        return False, None, "Ingestion process exited immediately. Check data/ingestion.log."

    _write_pid(process.pid)
    return True, process.pid, f"Started ingestion process (pid {process.pid})."


def restart_ingestion() -> tuple[bool, bool, int | None, str]:
    stopped_ok, stop_message = stop_ingestion()
    if not stopped_ok:
        started_ok, pid, start_message = start_ingestion()
        if started_ok:
            return True, False, pid, f"{stop_message} {start_message}"
        return False, False, pid, f"{stop_message} {start_message}"

    started_ok, pid, start_message = start_ingestion()
    if not started_ok:
        return False, False, pid, start_message
    return True, True, pid, f"{stop_message} {start_message}"
