"""Local Ollama provider tests (PLAN.md Phase 4) against a mock HTTP
transport — the same ``httpx.MockTransport`` pattern
``test_hiring_cafe.py`` uses, so no real Ollama server is needed."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from jobscout.llm.ollama import DEFAULT_BASE_URL, DEFAULT_MODEL, LocalOllamaProvider


def make_client(response_text: str) -> tuple[httpx.AsyncClient, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"response": response_text})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


async def test_generate_posts_expected_request_and_parses_response() -> None:
    client, requests = make_client("Dear Hiring Manager, ...")
    provider = LocalOllamaProvider(client, base_url="http://ollama.local", model="llama3.2")

    result = await provider.generate("Write a cover letter.")

    assert result == "Dear Hiring Manager, ..."
    assert requests == [{"model": "llama3.2", "prompt": "Write a cover letter.", "stream": False}]


async def test_generate_strips_surrounding_whitespace() -> None:
    client, _ = make_client("  Dear Hiring Manager, ...  \n")
    provider = LocalOllamaProvider(client)

    result = await provider.generate("Write a cover letter.")

    assert result == "Dear Hiring Manager, ..."


async def test_generate_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LocalOllamaProvider(client)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate("Write a cover letter.")


def test_base_url_and_model_fall_back_to_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-host:1234")
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")
    client = httpx.AsyncClient()

    provider = LocalOllamaProvider(client)

    assert provider._base_url == "http://custom-host:1234"
    assert provider._model == "custom-model"


def test_base_url_and_model_default_when_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    client = httpx.AsyncClient()

    provider = LocalOllamaProvider(client)

    assert provider._base_url == DEFAULT_BASE_URL
    assert provider._model == DEFAULT_MODEL
