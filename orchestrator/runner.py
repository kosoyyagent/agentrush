"""Task runner — plans with the LLM, executes each step inside the sandbox,
fetches URLs on the host side (sandbox has no network), and produces a
verifiable run record.

The fetch path is where prompt injection lives: page text is DATA fed to
the sandbox via stdin/file, never executed. The containment demo relies on
this boundary staying strict.

SSRF defence is two-layer: (1) scheme/host/credential checks plus a
globally-routable-only DNS filter, and (2) DNS is resolved ONCE and the
socket connects to that address — so a host that answers differently on
the second lookup (rebinding) cannot swap a public IP for 169.254.169.254
between validation and connect. Every redirect hop re-runs both layers.
"""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
import urllib.parse

from sandbox.base import make_sandbox

UA = {"User-Agent": "agentrush/0.1 (+verifiable-execution agent)"}
MAX_FETCH = 512 * 1024
_REDIRECT_LIMIT = 5
_tls = ssl.create_default_context()


def _resolve_public(host: str) -> list[str]:
    """All A/AAAA addresses, verified globally routable. Empty -> refuse."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    addrs = []
    for i in infos:
        try:
            ip = ipaddress.ip_address(i[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            return []               # one bad answer poisons the whole name
        addrs.append(i[4][0])
    return addrs


def _validate_url(url: str) -> None:
    """Structural checks only — scheme, credentials, host present."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https"):
        raise ValueError("fetch scheme must be http or https")
    if u.username or u.password:
        raise ValueError("credentials in fetch URLs are refused")
    if not u.hostname:
        raise ValueError("missing host")


def _url_allowed(url: str) -> bool:
    """Full policy check: structural + public DNS. Used by tests and by
    anything that wants a boolean rather than the pinned connection."""
    try:
        _validate_url(url)
        u = urllib.parse.urlsplit(url)
        return bool(_resolve_public(u.hostname))
    except (ValueError, UnicodeError):
        return False


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPSConnection that dials a pre-validated IP while keeping TLS
    SNI and certificate verification on the real hostname — the second
    DNS lookup (the rebinding window) never happens."""

    def __init__(self, ip: str, host: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=_tls)
        self._pinned_ip = ip
        self._sni_host = host

    def connect(self):
        sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(
            sock, server_hostname=self._sni_host)


def _pinned_get(url: str, timeout: float):
    """One GET with DNS pinned: connect to the IP we validated, keep the
    Host header and TLS SNI on the original hostname. Rebinding between
    resolve and connect is impossible — there is no second lookup."""
    u = urllib.parse.urlsplit(url)
    host = u.hostname
    addrs = _resolve_public(host)
    if not addrs:
        raise ValueError(f"refusing non-public host {host!r}")
    port = u.port or (443 if u.scheme == "https" else 80)
    target = urllib.parse.urlunsplit(
        ("", "", u.path or "/", u.query, "")).rstrip("/") or "/"

    if u.scheme == "https":
        conn = _PinnedHTTPS(addrs[0], host, port, timeout)
    else:
        conn = http.client.HTTPConnection(addrs[0], port, timeout=timeout)
    conn.request("GET", target, headers={
        "Host": host if u.port is None else f"{host}:{u.port}", **UA})
    resp = conn.getresponse()
    return conn, resp


def host_fetch(url: str, timeout: float = 15.0) -> dict:
    """Fetch on the ORCHESTRATOR side; the sandbox itself has no network.
    URLs come from the LLM plan (untrusted) — scheme, host, resolved
    addresses and every redirect hop are checked so the fetch can't be
    turned inward (SSRF), and DNS is pinned per hop against rebinding."""
    current = url
    try:
        for _ in range(_REDIRECT_LIMIT + 1):
            _validate_url(current)
            conn, resp = _pinned_get(current, timeout)
            try:
                if resp.status in (301, 302, 303, 307, 308) and \
                        resp.getheader("Location"):
                    loc = urllib.parse.urljoin(
                        current, resp.getheader("Location"))
                    resp.read()
                    current = loc
                    continue
                body = resp.read(MAX_FETCH)
            finally:
                conn.close()
            if resp.status in (301, 302, 303, 307, 308):
                continue
            return {"ok": True, "status": resp.status, "url": current,
                    "bytes": len(body),
                    "text": body.decode("utf-8", "replace"),
                    "sha256": hashlib.sha256(body).hexdigest()}
        return {"ok": False, "url": current, "error": "redirect limit"}
    except Exception as e:
        return {"ok": False, "url": current, "error": str(e)[:300]}


MAX_STEPS = 20          # the planner is untrusted — no unbounded loops
MAX_FETCHES = 8
RUN_DEADLINE_SEC = 300  # whole-run wall clock, on top of per-step timeouts


def run_task(task: str, llm, sandbox_kind: str = "auto",
             step_timeout: float = 30.0) -> dict:
    record = {"task": task, "sandbox": None, "steps": [],
              "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    sb = make_sandbox(sandbox_kind)
    record["sandbox"] = sb.name()
    try:
        steps = [s for s in llm.plan(task)
                 if isinstance(s, dict)][:MAX_STEPS]
        deadline = time.monotonic() + RUN_DEADLINE_SEC
        fetched: dict[str, dict] = {}
        fetch_calls = 0  # the budget counts calls, not distinct URLs
        for s in steps:
            if time.monotonic() > deadline:
                record["steps"].append(
                    {"step": s.get("step"), "action": s.get("action"),
                     "result": {"ok": False,
                                "error": "run deadline exceeded"}})
                break
            action = s.get("action", "python")
            entry = {"step": s.get("step"), "action": action,
                     "why": s.get("why", "")}
            if action == "fetch":
                if fetch_calls >= MAX_FETCHES:
                    res = {"ok": False, "url": s.get("command", ""),
                           "error": "fetch budget exceeded"}
                else:
                    fetch_calls += 1
                    res = host_fetch(s.get("command", ""))
                if res.get("ok"):
                    fetched[res["url"]] = res
                else:
                    fetched.setdefault(res["url"], res)
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
