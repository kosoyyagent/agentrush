#!/usr/bin/env bash
# AgentRush one-shot deploy on a fresh Vultr VM (Ubuntu 24.04).
# Usage:
#   curl -fsSL <raw-url>/vultr_setup.sh | sudo bash
# then:
#   export LLM_API_KEY=<vultr-inference-key>
#   systemctl enable --now agentrush
set -euo pipefail

# --- docker ---
if ! command -v docker >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq docker.io python3-venv git
fi
systemctl enable --now docker

# --- sandbox image (pulled once at deploy, never at run time) ---
docker pull python:3.12-slim

# --- app ---
install -d -m755 /opt/agentrush
# expects this script to run inside or beside the cloned repo;
# on the VM: git clone <repo> /opt/agentrush
if [ ! -f /opt/agentrush/orchestrator/app.py ]; then
  echo ">>> clone the repo into /opt/agentrush first, or run this script from it" >&2
  SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  cp -r "$SRC_DIR"/{orchestrator,sandbox,web,demo} /opt/agentrush/
fi

# --- service ---
cat >/etc/systemd/system/agentrush.service <<'UNIT'
[Unit]
Description=AgentRush sandboxed execution agent
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/agentrush
Environment=PORT=8080
Environment=LLM_BASE_URL=https://api.vultrinference.com/v1
EnvironmentFile=-/opt/agentrush/env
ExecStart=/usr/bin/python3 /opt/agentrush/orchestrator/app.py
Restart=always
RestartSec=3
# the ORCHESTRATOR holds the key; the sandbox containers get an empty env
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

touch /opt/agentrush/env  # put LLM_API_KEY=... here (chmod 600)
chmod 600 /opt/agentrush/env
systemctl daemon-reload
systemctl enable --now agentrush

# --- firewall: only the web port ---
if command -v ufw >/dev/null; then
  ufw allow 8080/tcp || true
fi

echo "=== AgentRush deployed. Health:"
sleep 1
curl -s localhost:8080/api/health || true
echo
echo "Put LLM_API_KEY=<key> into /opt/agentrush/env, then: systemctl restart agentrush"
