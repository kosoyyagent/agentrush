"""Docker sandbox — the real containment boundary (runs on the Vultr VM).

Every task gets a throwaway container:
- --network none            no outbound net from guest code (orchestrator
                            fetches URLs itself and passes content in)
- --memory / --cpus caps    resource limits per run
- --read-only root fs       guest writes only to a tmpfs /work
- --rm + explicit destroy   nothing survives the task
- empty env                 secrets never enter the container
"""
import json
import shutil
import subprocess
import time

from .base import RunResult, Sandbox

IMAGE = "python:3.12-slim"
MAX_OUTPUT_BYTES = 256 * 1024


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                       capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


class DockerSandbox(Sandbox):
    def __init__(self, image: str = IMAGE, mem_mb: int = 256, cpus: float = 1.0,
                 pids: int = 64):
        self.image = image
        self.mem_mb = mem_mb
        self.cpus = cpus
        self.pids = pids
        self._container = None
        self._destroyed = False

    def _spawn(self):
        name = f"agentrush-{int(time.time()*1000)}"
        cmd = [
            "docker", "run", "-d", "--name", name,
            "--network", "none",
            "--memory", f"{self.mem_mb}m",
            "--cpus", str(self.cpus),
            "--pids-limit", str(self.pids),
            "--read-only",
            "--tmpfs", "/work:rw,noexec,nosuid,size=64m",
            "--env", "HOME=/work",
            "-w", "/work",
            self.image, "sleep", "3600",
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        self._container = name

    def run(self, command, timeout=30.0, workdir_files=None):
        if self._destroyed:
            return RunResult(False, "", "sandbox destroyed", None, 0.0, True, "destroyed")
        try:
            if self._container is None:
                self._spawn()
        except subprocess.CalledProcessError as e:
            return RunResult(False, "", e.stderr.decode()[:500], None, 0.0,
                             False, "container spawn failed")
        for rel, content in (workdir_files or {}).items():
            b64 = __import__("base64").b64encode(content.encode()).decode()
            self._exec(["sh", "-c", f"mkdir -p /work/'$(dirname {rel})' && "
                                    f"echo {b64} | base64 -d > /work/{rel}"])
        t0 = time.monotonic()
        try:
            r = self._exec(command, timeout=timeout)
            return RunResult(r.returncode == 0,
                             r.stdout[:MAX_OUTPUT_BYTES],
                             r.stderr[:MAX_OUTPUT_BYTES],
                             r.returncode, round(time.monotonic() - t0, 3))
        except subprocess.TimeoutExpired:
            return RunResult(False, "", "", None,
                             round(time.monotonic() - t0, 3),
                             killed=True, reason=f"timeout after {timeout}s")

    def _exec(self, command, timeout=60):
        return subprocess.run(
            ["docker", "exec", self._container, *command],
            capture_output=True, text=True, timeout=timeout)

    def destroy(self):
        if not self._destroyed:
            self._destroyed = True
            if self._container:
                subprocess.run(["docker", "rm", "-f", self._container],
                               capture_output=True, timeout=30)
                self._container = None
