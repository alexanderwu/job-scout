"""Local Ollama LLM provider (PLAN.md Phase 4 default).

Free, private (resume/job data never leaves the machine), no API key.
Calls Ollama's ``/api/generate`` endpoint directly over ``httpx`` — no
extra dependency, since ``httpx`` is already used throughout this
codebase's other HTTP clients.
"""

from __future__ import annotations

import os

import httpx

from jobscout.llm.base import LLMProvider

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"


class LocalOllamaProvider(LLMProvider):
    """Generates text with a locally running Ollama server.

    The ``httpx.AsyncClient`` is injected rather than created here so
    the caller controls its lifecycle and timeout (cover-letter
    generation on local hardware can take tens of seconds) and tests can
    pass a client wired to a mock transport — the same injection
    pattern ``HiringCafeSource`` and ``LocalEmbeddingProvider`` use.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._http = http
        self._base_url = base_url or os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        self._model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)

    async def generate(self, prompt: str) -> str:
        response = await self._http.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        return str(response.json()["response"]).strip()
