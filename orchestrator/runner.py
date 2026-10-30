"""Task runner — plans with the LLM, executes each step inside the sandbox,
fetches URLs on the host side (sandbox has no network), and produces a
verifiable run record.

The fetch path is where prompt injection lives: page text is DATA fed to
the sandbox via stdin/file, never executed. The containment demo relies on
this boundary staying strict.
"""
import hashlib
import json
import time
import urllib.request

from sandbox.base import make_sandbox

UA = {"User-Agent": "agentrush/0.1 (+verifiable-execution agent)"}
MAX_FETCH = 512 * 1024


def host_fetch(url: str, timeout: float = 15.0) -> dict:
    """Fetch on the ORCHESTRATOR side; the sandbox itself has no network."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(MAX_FETCH)
        return {"ok": True, "status": r.status, "url": url,
                "bytes": len(body), "text": body.decode("utf-8", "replace"),
                "sha256": hashlib.sha256(body).hexdigest()}
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)[:300]}


def run_task(task: str, llm, sandbox_kind: str = "auto",
             step_timeout: float = 30.0) -> dict:
    record = {"task": task, "sandbox": None, "steps": [],
              "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    sb = make_sandbox(sandbox_kind)
    record["sandbox"] = sb.name()
    try:
        steps = llm.plan(task)
        fetched: dict[str, dict] = {}
        for s in steps:
            action = s.get("action", "python")
            entry = {"step": s.get("step"), "action": action,
                     "why": s.get("why", "")}
            if action == "fetch":
                res = host_fetch(s.get("command", ""))
                fetched[res["url"]] = res
                entry["result"] = {k: res[k] for k in
                                   ("ok", "status", "bytes", "sha256", "error")
                                   if k in res}
            elif action in ("shell", "python"):
                cmd = s.get("command", "")
                if action == "python":
                    cmd_argv = ["python", "-c", cmd]
                else:
                    cmd_argv = ["sh", "-c", cmd]
                # fetched pages are passed in as files — data, not code
                files = {f"page_{i}.txt": f.get("text", "")
                         for i, f in enumerate(fetched.values())}
                r = sb.run(cmd_argv, timeout=step_timeout,
                           workdir_files=files)
                entry["result"] = {
                    "ok": r.ok, "exit_code": r.exit_code,
                    "stdout": r.stdout[:4000], "stderr": r.stderr[:2000],
                    "wall_sec": r.wall_sec, "killed": r.killed,
                    "reason": r.reason}
            else:
                entry["result"] = {"ok": False, "error": f"unknown action {action}"}
            record["steps"].append(entry)
        record["fetched"] = [{k: v[k] for k in ("ok", "status", "bytes", "sha256")
                              if k in v} | {"url": v["url"]}
                             for v in fetched.values()]
    finally:
        sb.destroy()
        record["sandbox_destroyed"] = True
    record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["record_sha256"] = hashlib.sha256(
        json.dumps(record["steps"], sort_keys=True).encode()).hexdigest()
    return record
