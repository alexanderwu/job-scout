"""LLM providers — optional prose polish behind one small interface.

PLAN.md's decision, implemented literally: every copilot feature
(tailoring advice, cover letters) computes its *content* determin-
istically (skill overlap, template assembly) and an LLM, when one is
configured, only turns that content into better prose. Consequences:

- LLM_PROVIDER=none (the default) keeps every feature working — the
  output is a labeled scaffold instead of polished prose;
- features are testable without any model or key;
- swapping local/paid is one .env change, per PLAN.md's "most likely
  candidate for a paid API: cover letters".

Providers:
- :class:`OllamaProvider` — local (http://localhost:11434), free,
  private. Written against Ollama's documented /api/generate contract
  and tested against a mock transport; needs a machine with Ollama to
  run for real.
- :class:`AnthropicProvider` — paid API for when local quality
  disappoints. Calls the Messages API with plain httpx rather than the
  anthropic SDK: one POST doesn't justify a dependency, and the
  request shape stays visible/testable.

Sync interface, same reasoning as EmbeddingProvider: callers that live
in async contexts wrap calls in ``asyncio.to_thread``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from jobscout.config import Settings

DEFAULT_TIMEOUT = 120.0  # local models on modest hardware are slow; be patient


class LLMError(RuntimeError):
    """Provider-level failure (connection, auth, bad response shape)."""


class LLMProvider(ABC):
    name: ClassVar[str]

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        """One prompt in, one completion out. Raises LLMError on failure."""


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        http: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=DEFAULT_TIMEOUT)

    def generate(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        try:
            response = self._http.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "system": system or "",
                    "stream": False,  # one JSON body; streaming buys nothing for a batch draft
                    "options": {"num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            text = response.json().get("response", "")
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Ollama request failed ({exc}). Is Ollama running and the "
                f"model pulled? (`ollama pull {self._model}`) — or set "
                "LLM_PROVIDER=none/anthropic in .env."
            ) from exc
        if not text.strip():
            raise LLMError("Ollama returned an empty response")
        return str(text).strip()


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        api_key: str | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._http = http or httpx.Client(timeout=DEFAULT_TIMEOUT)

    def generate(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        if not self._api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set — export it (or put it in .env) "
                "to use LLM_PROVIDER=anthropic. Note: unlike Ollama, this "
                "sends resume/job text to Anthropic's API."
            )
        body: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        try:
            response = self._http.post(
                "https://api.anthropic.com/v1/messages",
                json=body,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            response.raise_for_status()
            content = response.json()["content"]
        except (httpx.HTTPError, KeyError) as exc:
            raise LLMError(f"Anthropic API request failed: {exc}") from exc
        parts = [block.get("text", "") for block in content if block.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise LLMError("Anthropic API returned no text content")
        return text


def llm_from_settings(settings: Settings) -> LLMProvider | None:
    """None means "no LLM configured" — features fall back to templates."""
    if settings.llm_provider == "none":
        return None
    if settings.llm_provider == "ollama":
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_url)
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(
            model=settings.anthropic_model, api_key=settings.anthropic_api_key or None
        )
    raise ValueError(
        f"unknown LLM_PROVIDER {settings.llm_provider!r}; expected 'none', 'ollama', or 'anthropic'"
    )
