#!/usr/bin/env bash
# ci_walkthrough.sh — non-interactive twin of record_demo.sh.
# Same steps, but pauses are timed sleeps so the whole session can be
# captured under `asciinema rec` in CI. Requires: curl, python3,
# orchestrator already listening on $BASE.

set -u
BASE="${BASE:-http://127.0.0.1:8080}"
beat() { sleep "${1:-3}"; }

clear
echo "=== AgentRush - Blast Radius Zero ==="
echo "Sandboxed execution agent on Vultr"
beat 4

echo "## 1. Health - orchestrator up, sandbox backend = docker"
curl -s "$BASE/api/health"; echo
beat 5

echo "## 2. Submit a real task through the web API (POST /api/run)"
RESP=$(curl -s -X POST "$BASE/api/run" \
  -H 'content-type: application/json' \
  -d '{"task":"Fetch https://example.com, summarise what the page says in one sentence, and compute the sha256 of the page body.","sandbox":"docker"}')
echo "$RESP"
JOB=$(echo "$RESP" | python3 -c 'import json,sys;print(json.load(sys.stdin)["job"])' 2>/dev/null || true)
echo "job id: $JOB"
beat 5

echo "## 3. Poll the run: plan -> host fetch -> sandboxed code"
for i in $(seq 1 30); do
  OUT=$(curl -s "$BASE/api/result/$JOB")
  echo "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("state"), "| steps:", len(d.get("record",{}).get("steps") or []))' 2>/dev/null || echo "$OUT"
  echo "$OUT" | grep -q '"state": *"done"' && break
  sleep 4
done
beat 4

echo "## 4. Verifiable record - commands, sha256 outputs, sandbox_destroyed"
curl -s "$BASE/api/result/$JOB" | python3 -m json.tool | head -60
beat 6

echo "## 5. Containment suite - six attacks, all die inside the sandbox"
python3 demo/blast_radius.py docker
beat 5

echo "## done - plan, fetch, contained execution, verifiable record."
beat 4
