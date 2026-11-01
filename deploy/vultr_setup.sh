#!/usr/bin/env bash
# AgentRush one-shot deploy on a fresh Vultr VM (Ubuntu 24.04).
# Usage:
#   curl -fsSL <raw-url>/vultr_setup.sh | sudo bash
# then:
#   export LLM_API_KEY=<vultr-inference-key>
#   systemctl enable --now agentrush
set -euo pipefail

# --- docker + tools ---
apt-get update -qq
apt-get install -y -qq docker.io python3-venv git curl
systemctl enable --now docker

# --- sandbox image (pulled once at deploy, never at run time) ---
docker pull python:3.12-slim

# --- app: clone the public repo; works when this script is piped via curl ---
if [ ! -f /opt/agentrush/orchestrator/app.py ]; then
  rm -rf /opt/agentrush
  git clone --depth 1 https://github.com/kosoyyagent/agentrush.git /opt/agentrush
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
Environment=AGENTRUSH_SANDBOX=docker
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
