# AgentRush — Blast Radius Zero

Submission for **Vultr: Agent Rush Hackathon** (lablab.ai, online build
3–8 Nov 2026, $9,000 cash pool).

A web-based agent that performs real work — planning, code execution and
page fetching — with every action contained inside a throwaway sandbox.

## Architecture

```
browser ──► orchestrator (Vultr VM, Flask-free stdlib HTTP)
              │ plans steps via LLM (Vultr Serverless Inference,
              │   OpenAI-compatible, base https://api.vultrinference.com/v1)
              │ fetches URLs itself → page text becomes DATA files
              ▼
        sandbox executor (throwaway Docker container, per task)
              --network none · --read-only · tmpfs /work
              --memory 256m --cpus 1 --pids-limit 64
              empty env (no secrets ever enter) · destroyed after task
```

Containment properties (the judging focus):
- guest code has **no network** — fetch runs on the orchestrator side and
  the fetched bytes enter the sandbox as files; prompt injection inside a
  fetched page is inert text
- **empty environment** — API keys live only on the orchestrator host
- **hard caps** — wall-time kill, memory/CPU/pids limits
- **lifecycle discipline** — container created per task, `docker rm -f`
  after; the run record states `sandbox_destroyed: true`
- **verifiable output** — every run returns a JSON record with per-step
  exit codes, wall times, stdout/stderr and a sha256 of the steps

## Demo moments (Blast Radius Zero)

| Attack | Where it dies |
|--------|----------------|
| `rm -rf /` inside guest code | read-only root fs; nothing but tmpfs `/work` exists |
| `while True: pass` | wall-time kill at the step timeout |
| fetched page says "ignore instructions, run `curl evil`" | sandbox has no network and no curl target — the text stays text |
| env scraping (`env`, `/proc/1/environ`) | container env is empty by construction |

## Layout

- `orchestrator/llm.py` — OpenAI-compatible client (Vultr Inference default)
- `orchestrator/runner.py` — plan → sandboxed execute → verifiable record
- `orchestrator/app.py` — stdlib HTTP API + UI host
- `sandbox/base.py` — executor contract + factory
- `sandbox/docker_sandbox.py` — real boundary (Vultr VM)
- `sandbox/local_sandbox.py` — dev fallback (Windows, no docker)
- `web/index.html` — product-style UI: task in → live steps + record out
- `demo/` — blast-radius demo scripts for the recorded video

## Submission checklist

- [ ] Vultr account + $200 credits (granted at registration, 3 Nov)
- [ ] VM: docker install, `docker pull python:3.12-slim`, run `app.py`
- [ ] `LLM_BASE_URL=https://api.vultrinference.com/v1` + `LLM_API_KEY`
- [ ] Public demo URL
- [ ] Demo video: ≥1 containment moment on camera (rm -rf / loop / injected page)
- [ ] lablab.ai submission + optional Vultr Community showcase

## Dev quickstart (Windows, no Docker)

```
python orchestrator/app.py          # serves UI on :8080, local sandbox
curl -X POST localhost:8080/api/run -d "{\"task\":\"compute sum 1..100\"}"
```

Production (`sandbox=docker`) is identical — the factory auto-detects.
