#!/usr/bin/env bash
set -euo pipefail

API="${EMERGYX_API_BASE_URL:-http://localhost:8000}"

check() {
  local label="$1"
  local url="$2"
  echo "Checking ${label}..."
  curl -fsS "$url" >/tmp/emergyx-check.json
}

check "API health" "${API}/health"
check "demo events" "${API}/events?mode=demo&limit=5"
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/emergyx-check.json').read_text())
if not isinstance(payload, list) or not payload:
    raise SystemExit('Expected seeded demo events, found none.')
PY

check "demo alerts" "${API}/alerts?mode=demo&limit=5"
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/emergyx-check.json').read_text())
if not isinstance(payload, list) or not payload:
    raise SystemExit('Expected seeded demo alerts, found none.')
PY

check "demo reports" "${API}/reports/daily?mode=demo&limit=3"
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/emergyx-check.json').read_text())
if not isinstance(payload, list) or not payload:
    raise SystemExit('Expected seeded daily reports, found none.')
PY

check "Gemma findings" "${API}/reports/gemma-findings?mode=demo&limit=3"
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/emergyx-check.json').read_text())
if not isinstance(payload, list) or not payload:
    raise SystemExit('Expected seeded Gemma findings, found none.')
PY

check "Gemma status" "${API}/agent/status"
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/emergyx-check.json').read_text())
if payload.get('status') != 'online':
    raise SystemExit(f"Expected Gemma online, got: {payload}")
PY

rm -f /tmp/emergyx-check.json
echo "Emergyx Care judge demo verification passed."
