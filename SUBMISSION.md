# AgentRush — Blast Radius Zero

**Track:** Vultr Agent Rush Hackathon — sandboxed execution agent

## The pitch (30 words)

An agent that does real work — plans tasks, fetches pages, runs
generated code — with every single action contained inside a throwaway
Docker sandbox. The blast radius is zero and we prove it on camera.

## What it does

1. User submits a task in the web UI ("fetch this page, analyse it,
   write the result").
2. The orchestrator plans steps with an LLM running on **Vultr
   Serverless Inference** (OpenAI-compatible).
3. URL fetches run on the orchestrator host — the sandbox has no
   network, so page text enters as plain data files.
4. Generated code executes inside a **fresh Docker container per
   task**: `--network none`, `--read-only` root fs, tmpfs workdir,
   `--memory 256m --cpus 1 --pids-limit 64`, `--cap-drop ALL`,
   `no-new-privileges`, empty environment, wall-time kill.
5. Every run returns a verifiable JSON record: per-step commands,
   sha256 of outputs, `sandbox_destroyed: true`.

## Why "Blast Radius Zero" is literal

- **No network** inside the sandbox: prompt injection inside a fetched
  page is inert text — there is no channel for it to act through.
- **No secrets**: API keys live only on the orchestrator host
  (systemd EnvironmentFile); the guest env is empty.
- **No persistence**: read-only fs + tmpfs; container is `docker rm -f`'d
  after the task, clean or crashed.
- **No SSRF through the planner**: fetch targets are validated as
  publicly routable at every redirect hop.
- **Bounded by construction**: plan length, fetch count, queue depth,
  result store, wall time — all hard-capped.

## The demo

`demo/blast_radius.py` runs five containment cases live:
`rm -rf /` against the read-only fs, an infinite loop against the
wall-time kill, a spawn storm against `--pids-limit`, an env scrape
against the empty environment, and an outbound connection against
`--network none`. Each prints exactly where the attack died.

## Stack

- **Vultr Serverless Inference** for planning (kimi-k2-instruct-0905)
- **Vultr VM** hosts the orchestrator + web UI (stdlib Python HTTP,
  zero heavy deps)
- **Docker** provides the security boundary; a documented local
  subprocess fallback exists for dev only
- ~500 lines of Python, 13 unit tests

## Judge checklist

- [ ] Real work end-to-end: plan → fetch → execute → verifiable record
- [ ] Containment moment shown live on camera
- [ ] Vultr products used: VM + Serverless Inference
- [ ] Reproducible: `deploy/vultr_setup.sh` one-shot on Ubuntu 24.04
