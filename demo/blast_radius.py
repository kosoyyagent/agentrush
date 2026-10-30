"""Blast Radius Zero demo — feeds hostile inputs at the agent and records
each containment moment. Run on the Vultr VM with sandbox=docker while
recording the demo video.

Each case prints what the guest tried and exactly where it died.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.base import make_sandbox

CASES = [
    ("rm -rf on the whole fs",
     ["sh", "-c", "rm -rf / 2>&1 | head -3; echo STILL_ALIVE; ls /"]),
    ("infinite loop",
     ["python", "-c", "while True: pass"]),
    # A bounded spawn storm, not an unbounded bomb: on Docker it runs into
    # --pids-limit (the cap does the stopping); on the local dev sandbox it
    # exits harmlessly instead of hurting the host it shares a kernel with.
    ("process spawn storm (pids limit)",
     ["sh", "-c",
      "i=0; while [ $i -lt 200 ]; do sleep 10 & i=$((i+1)); done 2>/dev/null; "
      "sleep 1; echo ALIVE:$(jobs -p | wc -l)"]),
    ("env scraping for secrets",
     ["sh", "-c", "env; cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n' | head"]),
    ("outbound network attempt",
     ["python", "-c",
      "import urllib.request;print(urllib.request.urlopen('https://example.com',timeout=5).status)"]),
]


def main(kind="auto"):
    for i, (title, cmd) in enumerate(CASES, 1):
        sb = make_sandbox(kind)
        timeout = 5 if "loop" in title or "storm" in title else 15
        print(f"[sandbox: {sb.name()}]" if i == 1 else "", end="")
        r = sb.run(cmd, timeout=timeout)
        print(f"\n=== case {i}: {title}")
        print(f"  killed={r.killed} reason={r.reason or '-'} exit={r.exit_code}")
        print(f"  stdout: {r.stdout[:240]!r}")
        print(f"  stderr: {r.stderr[:240]!r}")
        sb.destroy()
        print("  sandbox destroyed.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "auto")
