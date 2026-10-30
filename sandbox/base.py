"""Sandbox executor interface — every agent action runs inside one of these.

Contract:
    sb = make_sandbox(cfg)          # fresh isolated env per task
    r = sb.run(command, timeout)    # execute, capture, enforce limits
    sb.destroy()                    # ALWAYS called after the task

Rules the orchestrator relies on (containment-first):
- no host filesystem access from inside the sandbox
- no secrets/env keys passed in — the sandbox gets an empty environment
  plus only the task payload
- hard caps on wall time, memory, output size
- destroy() must leave nothing running, even after errors
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    wall_sec: float
    killed: bool = False          # True when we stopped it (timeout / loop)
    reason: str = ""              # why it was killed / failed


class Sandbox:
    """Base class — implementations must never let guest code touch the host."""

    def run(self, command: list[str], timeout: float = 30.0,
            workdir_files: dict[str, str] | None = None) -> RunResult:
        raise NotImplementedError

    def destroy(self) -> None:
        raise NotImplementedError

    def name(self) -> str:
        return type(self).__name__


def make_sandbox(kind: str = "auto", **kw) -> Sandbox:
    """Factory: docker on the Vultr VM, local subprocess only for dev."""
    if kind == "auto":
        try:
            from .docker_sandbox import docker_available
            kind = "docker" if docker_available() else "local"
        except Exception:
            kind = "local"
    if kind == "docker":
        from .docker_sandbox import DockerSandbox
        return DockerSandbox(**kw)
    if kind == "local":
        from .local_sandbox import LocalSandbox
        return LocalSandbox(**kw)
    raise ValueError(f"unknown sandbox kind: {kind}")
