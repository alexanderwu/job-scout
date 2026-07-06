"""LLM provider tests — request contracts, without models or keys.

The same MockTransport trick the source adapters use: we can't run
Ollama or call Anthropic here, but we CAN pin down the exact request
each provider sends and how it handles the documented response/failure
shapes. When someone runs them for real, the only untested part is the
service itself.
"""

import httpx
import pytest

from jobscout.config import Settings
from jobscout.llm import (
    AnthropicProvider,
    LLMError,
    OllamaProvider,
    llm_from_settings,
)


def client_returning(
    payload: object, status: int = 200
) -> tuple[httpx.Client, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_ollama_request_shape_and_response() -> None:
    http, requests = client_returning({"response": "  Drafted text.  "})
    provider = OllamaProvider(model="llama3.1:8b", http=http)

    text = provider.generate("PROMPT", system="SYSTEM", max_tokens=99)

    assert text == "Drafted text."
    request = requests[0]
    assert str(request.url) == "http://localhost:11434/api/generate"
    import json

    body = json.loads(request.content)
    assert body["model"] == "llama3.1:8b"
    assert body["prompt"] == "PROMPT"
    assert body["system"] == "SYSTEM"
    assert body["stream"] is False
    assert body["options"] == {"num_predict": 99}


def test_ollama_connection_failure_has_actionable_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = OllamaProvider(http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError, match="ollama pull"):
        provider.generate("hi")


def test_anthropic_request_shape_and_response() -> None:
    http, requests = client_returning(
        {"content": [{"type": "text", "text": "Dear team,"}, {"type": "text", "text": " hi."}]}
    )
    provider = AnthropicProvider(model="claude-sonnet-5", api_key="sk-test", http=http)

    text = provider.generate("PROMPT", system="SYSTEM")

    assert text == "Dear team, hi."
    request = requests[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "sk-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    import json

    body = json.loads(request.content)
    assert body["model"] == "claude-sonnet-5"
    assert body["system"] == "SYSTEM"
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]


def test_anthropic_without_key_explains_privacy_tradeoff() -> None:
    provider = AnthropicProvider(api_key="")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        provider.generate("hi")


def test_llm_from_settings() -> None:
    assert llm_from_settings(Settings(llm_provider="none")) is None
    assert isinstance(llm_from_settings(Settings(llm_provider="ollama")), OllamaProvider)
    assert isinstance(llm_from_settings(Settings(llm_provider="anthropic")), AnthropicProvider)
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm_from_settings(Settings(llm_provider="gpt5"))
