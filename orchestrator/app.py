"""Web app — task submission + live run records. Stdlib-only HTTP server
(deployed behind the Vultr VM's public IP; swap for FastAPI if preferred).

Endpoints:
  GET  /                -> web UI (web/index.html)
  POST /api/run         -> {"task": "..."}  -> run record JSON
  GET  /api/health      -> {"ok": true, "sandbox": "docker|local"}
"""
import json
import os
import sys
import threading
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.llm import LLM
from orchestrator.runner import run_task
from sandbox.base import make_sandbox

WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"
_jobs: queue.Queue = queue.Queue()
_results: dict[str, dict] = {}
_llm = LLM()


def _worker():
    while True:
        jid, task, kind = _jobs.get()
        try:
            _results[jid] = {"state": "running"}
            _results[jid] = {"state": "done",
                             "record": run_task(task, _llm, kind)}
        except Exception as e:
            _results[jid] = {"state": "error", "error": str(e)[:500]}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            self._send(200, WEB.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            try:
                sb = make_sandbox("auto"); kind = sb.name(); sb.destroy()
            except Exception:
                kind = "none"
            self._send(200, json.dumps({"ok": True, "sandbox": kind}))
        elif self.path.startswith("/api/result/"):
            jid = self.path.rsplit("/", 1)[-1]
            self._send(200 if jid in _results else 404,
                       json.dumps(_results.get(jid, {"error": "unknown id"})))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/run":
            return self._send(404, json.dumps({"error": "not found"}))
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(min(n, 64 * 1024)) or b"{}")
        except ValueError:
            return self._send(400, json.dumps({"error": "bad json"}))
        task = str(body.get("task", ""))[:4000].strip()
        if not task:
            return self._send(400, json.dumps({"error": "empty task"}))
        jid = os.urandom(8).hex()
        kind = body.get("sandbox", "auto")
        _jobs.put((jid, task, kind))
        self._send(202, json.dumps({"job": jid, "poll": f"/api/result/{jid}"}))

    def log_message(self, *a):
        pass


def main(port=8080):
    threading.Thread(target=_worker, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"agentrush on :{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main(int(os.environ.get("PORT", "8080")))
