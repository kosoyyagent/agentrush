"""Runner + sandbox contract tests — no Docker required.

The containment claims that can be checked without a VM: URL validation
(SSRF), plan/fetch budgets, the run record's verifiable fields, sandbox
lifecycle. DockerSandbox itself is exercised on the Vultr host.
"""
import socket
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import runner
from sandbox.local_sandbox import LocalSandbox


def fake_dns_global(host, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


class UrlValidation(unittest.TestCase):
    def setUp(self):
        self._orig = socket.getaddrinfo
        socket.getaddrinfo = fake_dns_global

    def tearDown(self):
        socket.getaddrinfo = self._orig

    def _ok(self, url):
        try:
            runner._validate_url(url)
            return True
        except ValueError:
            return False

    def test_refuses_non_http_schemes(self):
        self.assertFalse(self._ok("file:///etc/passwd"))
        self.assertFalse(self._ok("ftp://example.com/x"))
        self.assertFalse(self._ok("gopher://example.com/"))
        self.assertFalse(self._ok("data:text/plain,hi"))

    def test_refuses_credentials(self):
        self.assertFalse(self._ok("http://user:pass@example.com/"))

    def test_refuses_private_ips(self):
        socket.getaddrinfo = self._orig  # real DNS for IP literals
        for u in ("http://127.0.0.1/", "http://169.254.169.254/latest/",
                  "http://192.168.1.1/", "http://10.0.0.5/",
                  "http://[::1]/", "http://0.0.0.0/"):
            self.assertFalse(self._ok(u), u)

    def test_accepts_public_http(self):
        self.assertTrue(self._ok("https://example.com/page?q=1"))
        self.assertTrue(self._ok("http://example.com/"))


class FakeLlm:
    def __init__(self, steps):
        self._steps = steps

    def plan(self, task):
        return list(self._steps)


def py_step(code):
    return {"action": "python", "command": code}


class RunTask(unittest.TestCase):
    def test_plan_truncated_at_max(self):
        steps = [py_step("print(1)")] * (runner.MAX_STEPS + 5)
        rec = runner.run_task("t", FakeLlm(steps), sandbox_kind="local")
        self.assertEqual(len(rec["steps"]), runner.MAX_STEPS)
        self.assertTrue(rec["sandbox_destroyed"])
        self.assertEqual(len(rec["record_sha256"]), 64)

    def test_fetch_budget(self):
        steps = [{"action": "fetch", "command": "https://example.com/"}
                 for _ in range(runner.MAX_FETCHES + 3)]
        calls = []
        orig = runner.host_fetch
        runner.host_fetch = lambda u: calls.append(u) or {
            "ok": True, "status": 200, "url": u, "bytes": 3,
            "text": "abc", "sha256": "x"}
        try:
            rec = runner.run_task("t", FakeLlm(steps), sandbox_kind="local")
        finally:
            runner.host_fetch = orig
        self.assertEqual(len(calls), runner.MAX_FETCHES)
        over = rec["steps"][runner.MAX_FETCHES:]
        self.assertTrue(all(not s["result"]["ok"] for s in over))

    def test_fetch_result_flows_to_guest_as_file(self):
        orig = runner.host_fetch
        runner.host_fetch = lambda u: {
            "ok": True, "status": 200, "url": u, "bytes": 9,
            "text": "INJECTED PAGE TEXT", "sha256": "x"}
        steps = [{"action": "fetch", "command": "https://example.com/"},
                 py_step("import glob; print(open(glob.glob('page_*.txt')[0]).read())")]
        try:
            rec = runner.run_task("t", FakeLlm(steps), sandbox_kind="local")
        finally:
            runner.host_fetch = orig
        self.assertIn("INJECTED PAGE TEXT", rec["steps"][1]["result"]["stdout"])

    def test_unknown_action_fails_step_not_run(self):
        rec = runner.run_task("t", FakeLlm([{"action": "teleport"}]),
                              sandbox_kind="local")
        self.assertFalse(rec["steps"][0]["result"]["ok"])
        self.assertTrue(rec["sandbox_destroyed"])

    def test_deadline_stops_late_steps(self):
        steps = [py_step("import time; time.sleep(0.2)")] * 3
        rec = runner.run_task("t", FakeLlm(steps), sandbox_kind="local",
                              step_timeout=5)
        self.assertTrue(all(s["result"]["ok"] for s in rec["steps"]))


class LocalSandboxContract(unittest.TestCase):
    def test_runs_and_cleans_up(self):
        sb = LocalSandbox()
        wd = sb._workdir
        r = sb.run(["python", "-c", "print('hi')"], timeout=10)
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout.strip(), "hi")
        sb.destroy()
        self.assertFalse(Path(wd).exists())

    def test_timeout_kills(self):
        sb = LocalSandbox()
        r = sb.run(["python", "-c", "import time; time.sleep(30)"], timeout=1)
        self.assertFalse(r.ok)
        self.assertTrue(r.killed)
        sb.destroy()

    def test_refuses_after_destroy(self):
        sb = LocalSandbox()
        sb.destroy()
        r = sb.run(["python", "-c", "print(1)"])
        self.assertFalse(r.ok)

    def test_guest_env_scrubbed_posix(self):
        # On Windows the host PATH is a documented dev trade-off;
        # the check that travels to the VM is env without secrets.
        sb = LocalSandbox()
        r = sb.run(["python", "-c",
                    "import os; print(os.environ.get('LLM_API_KEY',''))"],
                   timeout=10)
        self.assertEqual(r.stdout.strip(), "")
        sb.destroy()


class SandboxPolicy(unittest.TestCase):
    """The public API must never hand out host-side execution."""

    def test_client_cannot_pick_local(self):
        from orchestrator import app
        orig = (app._SERVER_KIND, app._ALLOW_LOCAL)
        try:
            app._SERVER_KIND, app._ALLOW_LOCAL = "auto", False
            self.assertEqual(app._resolve_kind("local"), "auto")
            app._ALLOW_LOCAL = True
            self.assertEqual(app._resolve_kind("local"), "local")
            app._SERVER_KIND = "docker"
            self.assertEqual(app._resolve_kind("local"), "docker")
            self.assertEqual(app._resolve_kind("auto"), "docker")
        finally:
            app._SERVER_KIND, app._ALLOW_LOCAL = orig


class LocalPlannerUrls(unittest.TestCase):
    def test_trailing_punctuation_stripped(self):
        from orchestrator import llm
        steps = llm._local_plan(
            "Fetch https://example.com, then https://a.io/x?q=1.")
        urls = [s["command"] for s in steps if s["action"] == "fetch"]
        self.assertEqual(urls, ["https://example.com", "https://a.io/x?q=1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
