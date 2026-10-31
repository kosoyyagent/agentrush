# Demo narration — ~3 minutes, synced to record_demo.sh

**(intro, ~15s)**
"This is AgentRush — an agent that plans, fetches, and runs generated code,
with every action contained inside a throwaway Docker sandbox. The blast
radius is zero, and I'm going to prove it live."

**(step 1 — health, ~10s)**
"The orchestrator is up on this Vultr VM, and the sandbox backend is real
Docker — no simulation."

**(step 2 — submit task, ~20s)**
"I submit a task through the web API: fetch example.com, summarise the page,
and hash the body. Notice the task itself is a possible injection vector —
that's the point."

**(step 3 — run, ~30s)**
"While it runs: the plan comes from Vultr Serverless Inference. The URL fetch
happens on the orchestrator host — the sandbox has no network at all, so page
content enters only as plain data. The generated code executes inside a fresh
container: read-only filesystem, empty environment, pids limit, all
capabilities dropped, and a hard wall-time kill."

**(step 4 — record, ~25s)**
"Here's the verifiable record: every step's command, the sha256 of each
output, and `sandbox_destroyed: true`. Anyone can re-run and check the
hashes."

**(step 5 — blast_radius, ~60s)**
"Now the containment suite. `rm -rf --no-preserve-root /` dies on the
read-only filesystem. An infinite loop dies on the wall-time kill. A fork
bomb hits the pids limit. An environment scrape finds nothing — the keys
live only on the host. An outbound connection fails — there's no network.
And a prompt-injection payload embedded in fetched data parses as inert
text, because there is no channel for it to act through."

**(close, ~15s)**
"Plan, fetch, contained execution, verifiable record — on Vultr VM and
Vultr Serverless Inference. Blast radius: zero."
