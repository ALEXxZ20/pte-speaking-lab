import json

import httpx
import openai
import pytest

from app.providers.openai_llm import OpenAICompatibleLLMProvider


def test_compatible_provider_calls_chat_completions_and_validates_json(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][1]["content"])
        return httpx.Response(200, json={"id": "chatcmpl-test", "object": "chat.completion",
            "created": 0, "model": "gpt-6-sol", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps({"findings": supplied["findings"]})}}]})

    real_client = openai.OpenAI
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: real_client(**kwargs, http_client=httpx.Client(transport=transport)))
    provider = OpenAICompatibleLLMProvider("local-test-key", "gpt-6-sol", "http://localhost:8317/")
    findings = [{"id": "f1", "evidence_ids": ["e1"], "statement": "规则结论", "recommendation": "规则建议"}]
    evidence = [{"id": "e1", "kind": "xingji_word_color", "value": None, "unit": None, "quality": "low"}]
    assert provider.explain(findings, evidence) == findings
    assert str(requests[0].url) == "http://localhost:8317/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer local-test-key"
    assert json.loads(requests[0].content)["model"] == "gpt-6-sol"


@pytest.mark.parametrize("base_url", ["", "http://192.168.5.14:8317/v1", "http://user:pass@localhost:8317/v1",
                                       "http://localhost:8317/admin", "file:///tmp/proxy"])
def test_compatible_provider_rejects_invalid_or_insecure_urls(base_url):
    with pytest.raises(ValueError):
        OpenAICompatibleLLMProvider("test-key", "gpt-6-sol", base_url)
