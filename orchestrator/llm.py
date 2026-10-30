"""OpenAI-compatible LLM client — Vultr Serverless Inference by default.

Base URL configurable: https://api.vultrinference.com/v1 in production,
any OpenAI-compatible endpoint in dev. No secrets in code — key comes
from env on the orchestrator host only (never inside the sandbox).
"""
import json
import os
import urllib.request

DEFAULT_BASE = "https://api.vultrinference.com/v1"
DEFAULT_MODEL = os.environ.get("AGENTRUSH_MODEL", "kimi-k2-instruct-0905")


class LLM:
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL")
                         or DEFAULT_BASE).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

    def chat(self, messages, temperature=0.2, max_tokens=2048):
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]

    def plan(self, task: str) -> list[dict]:
        """Turn a user task into ordered execution steps (JSON)."""
        out = self.chat([
            {"role": "system", "content": (
                "You are the planning layer of a sandboxed execution agent. "
                "Decompose the task into at most 5 steps. Each step is a JSON "
                "object: {\"step\": n, \"action\": \"shell|python|fetch\", "
                "\"command\": \"<shell or python code or url>\", \"why\": \"...\"}. "
                "Return ONLY a JSON array. Code runs in an isolated sandbox "
                "with no network and no secrets — fetch steps run on the host "
                "orchestrator which passes page text into the sandbox.")},
            {"role": "user", "content": task},
        ])
        start, end = out.find("["), out.rfind("]")
        if start == -1 or end == -1:
            return [{"step": 1, "action": "python",
                     "command": "print('planner returned no steps')",
                     "why": "fallback"}]
        try:
            steps = json.loads(out[start:end + 1])
            return steps if isinstance(steps, list) else [steps]
        except ValueError:
            return [{"step": 1, "action": "python",
                     "command": f"print({out[:500]!r})", "why": "raw reply"}]
