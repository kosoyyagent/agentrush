"""Local subprocess sandbox — DEV FALLBACK ONLY.

Used when Docker is unavailable (local development on Windows).
Not a security boundary: subprocesses share the host kernel. The real
containment story runs on DockerSandbox on the Vultr VM. Still enforces:
temp working dir, empty env, wall-time kill, output caps, cleanup.
"""
import os
import shutil
import subprocess
import tempfile
import time

from .base import RunResult, Sandbox

MAX_OUTPUT_BYTES = 256 * 1024


def _guest_env(workdir: str) -> dict:
    env = {"HOME": workdir, "TERM": "", "TMPDIR": workdir}
    if os.name == "nt":
        env["PATH"] = os.environ.get("PATH", "")
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    else:
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return env


class LocalSandbox(Sandbox):
    def __init__(self, workdir: str | None = None):
        self._workdir = workdir or tempfile.mkdtemp(prefix="agentrush-")
        self._destroyed = False

    def run(self, command, timeout=30.0, workdir_files=None):
        if self._destroyed:
            return RunResult(False, "", "sandbox destroyed", None, 0.0, True, "destroyed")
        for rel, content in (workdir_files or {}).items():
            p = os.path.join(self._workdir, rel)
            os.makedirs(os.path.dirname(p) or self._workdir, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                command, cwd=self._workdir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                # Guests get a scrubbed environment. POSIX gets a static
                # minimal PATH so `env` shows no host paths; Windows needs
                # the host PATH (and SYSTEMROOT) just to launch a process —
                # dev only, the real boundary is DockerSandbox.
                env=_guest_env(self._workdir),
                text=True, errors="replace")
            try:
                out, err = proc.communicate(timeout=timeout)
                return RunResult(
                    proc.returncode == 0, out[:MAX_OUTPUT_BYTES],
                    err[:MAX_OUTPUT_BYTES], proc.returncode,
                    round(time.monotonic() - t0, 3))
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
                return RunResult(
                    False, out[:MAX_OUTPUT_BYTES], err[:MAX_OUTPUT_BYTES],
                    None, round(time.monotonic() - t0, 3),
                    killed=True, reason=f"timeout after {timeout}s")
        except FileNotFoundError as e:
            return RunResult(False, "", str(e), None, 0.0, False, "command not found")

    def destroy(self):
        if not self._destroyed:
            self._destroyed = True
            shutil.rmtree(self._workdir, ignore_errors=True)
