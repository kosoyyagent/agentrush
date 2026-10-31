#!/usr/bin/env bash
# record_demo.sh — walk through the AgentRush demo live for the video.
# Run on the Vultr VM after deploy/vultr_setup.sh. Requires: curl, jq (optional).
# Screen-record this terminal (OBS/asciinema) while it runs; each step pauses
# so narration can keep pace. Total ~3 min.

set -u
BASE="${BASE:-http://127.0.0.1:8080}"
pause() { echo; read -r -p "[demo] Enter to continue…" _; echo; }

clear
echo "=== AgentRush — Blast Radius Zero ==="
echo "Sandboxed execution agent on Vultr"
pause

echo "## 1. Health — orchestrator up, planner reachable"
curl -s "$BASE/health" || true
pause

echo "## 2. Submit a real task through the web API"
RESP=$(curl -s -X POST "$BASE/api/tasks" \
  -H 'content-type: application/json' \
  -d '{"task":"Fetch https://example.com, summarise what the page says in one sentence, and compute the sha256 of the page body."}')
echo "$RESP"
TASK=$(echo "$RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
echo "task id: $TASK"
pause

echo "## 3. Watch the run: plan on Vultr Serverless Inference -> host fetch -> sandboxed code"
for i in $(seq 1 30); do
  OUT=$(curl -s "$BASE/api/tasks/$TASK")
  echo "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("status"), "| steps:", len(d.get("record",{}).get("steps") or []))' 2>/dev/null || echo "$OUT"
  echo "$OUT" | grep -q '"status": *"done"' && break
  sleep 4
done
pause

echo "## 4. Verifiable record — commands, sha256 outputs, sandbox destroyed"
curl -s "$BASE/api/tasks/$TASK" | python3 -m json.tool | head -60
pause

echo "## 5. The money shot — six live attacks on the sandbox"
python3 demo/blast_radius.py
pause

echo "=== done: plan -> fetch -> contained execution -> verified record ==="
