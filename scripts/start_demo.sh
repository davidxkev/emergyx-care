#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODEL="${GEMMA_MODEL:-gemma4:e2b}"

echo "Starting Emergyx Care judge demo with Gemma model: ${MODEL}"
echo "This may take several minutes the first time while Docker builds and Ollama pulls the model."

MEM_BYTES="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
if [[ "$MEM_BYTES" =~ ^[0-9]+$ ]] && [ "$MEM_BYTES" -gt 0 ] && [ "$MEM_BYTES" -lt 12000000000 ]; then
  echo
  echo "Warning: Docker currently has less than 12 GB RAM available."
  echo "Gemma 4 E2B may fail to load and Ollama may return HTTP 500."
  echo "The demo will still run with seeded data and graceful fallback messages."
  echo "For full Gemma replies, increase Docker Desktop memory to 12 GB or more."
  echo
fi

GEMMA_MODEL="$MODEL" docker compose up --build -d --force-recreate demo-seed backend frontend

echo
echo "Emergyx Care demo is starting."
echo "Dashboard: http://localhost:3000/dashboard?mode=demo"
echo "Reports:   http://localhost:3000/reports?mode=demo"
echo "Chat:      http://localhost:3000/chat?mode=demo"
echo "API:       http://localhost:8000/health"
echo
echo "Run ./scripts/verify_demo.sh to check readiness."
