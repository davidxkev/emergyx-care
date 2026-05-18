#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODEL="${GEMMA_MODEL:-gemma4:e2b}"

echo "Starting Emergyx Care judge demo with Gemma model: ${MODEL}"
echo "This may take several minutes the first time while Docker builds and Ollama pulls the model."

GEMMA_MODEL="$MODEL" docker compose up --build -d --force-recreate demo-seed backend frontend

echo
echo "Emergyx Care demo is starting."
echo "Dashboard: http://localhost:3000/dashboard?mode=demo"
echo "Reports:   http://localhost:3000/reports?mode=demo"
echo "Chat:      http://localhost:3000/chat?mode=demo"
echo "API:       http://localhost:8000/health"
echo
echo "Run ./scripts/verify_demo.sh to check readiness."
