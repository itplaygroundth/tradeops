import sys
import asyncio
from pathlib import Path
from urllib import error
from json import JSONDecodeError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import engine.hermes_client as hermes_mod


def test_hermes_defaults_to_9router(monkeypatch):
    monkeypatch.delenv("HERMES_URL", raising=False)
    monkeypatch.delenv("HERMES_MODEL", raising=False)
    monkeypatch.setenv("NINEROUTER_URL", "http://127.0.0.1:20128")
    monkeypatch.setenv("NINEROUTER_MODEL", "FreeCombo")

    client = hermes_mod.HermesClient()

    assert client.url == "http://127.0.0.1:20128/v1/chat/completions"
    assert client.model == "FreeCombo"


def test_hermes_reads_timeout_and_retries_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LLM_RETRIES", "4")

    client = hermes_mod.HermesClient()

    assert client.timeout == 45
    assert client.retries == 4


def test_hermes_auth_header(monkeypatch):
    client = hermes_mod.HermesClient(url="http://example.test/v1/chat/completions")
    client.api_key = "sk-test"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"{}"}}]}'

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(hermes_mod.request, "urlopen", fake_urlopen)

    client._post_json(client.url, {"model": "FreeCombo"})

    assert captured["auth"] == "Bearer sk-test"


def test_select_winner_disables_streaming(monkeypatch):
    client = hermes_mod.HermesClient(url="http://example.test/v1/chat/completions")
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"winner_idx": 0, "reasoning": "ok", "confidence": 0.9}'}}]}

    monkeypatch.setattr(client, "_post_with_retries", fake_post)

    result = asyncio.run(client.select_winner({"results": []}))

    assert captured["payload"]["stream"] is False
    assert result["winner_idx"] == 0


def test_hermes_retries_json_decode_error(monkeypatch):
    client = hermes_mod.HermesClient(retries=2, timeout=0.1)
    attempts = {"count": 0}

    def fake_post_json(*args, **kwargs):
        attempts["count"] += 1
        raise JSONDecodeError("bad", "", 0)

    monkeypatch.setattr(client, "_post_json", fake_post_json)

    try:
        client._post_with_retries({"model": "FreeCombo"})
        assert False, "Expected HermesError"
    except hermes_mod.HermesError:
        pass

    assert attempts["count"] == 2


def test_hermes_retries(monkeypatch):
    client = hermes_mod.HermesClient(retries=2, timeout=0.1)

    # monkeypatch urllib.request.urlopen to raise URLError
    def fake_urlopen(req, timeout=None):
        raise error.URLError("test unreachable")

    monkeypatch.setattr(hermes_mod.request, "urlopen", fake_urlopen)

    try:
        asyncio.run(client.select_winner({}))
        assert False, "Expected HermesError"
    except hermes_mod.HermesError:
        pass


def test_loads_first_json_object_ignores_extra_text():
    content = 'analysis first {"approved": true, "reason": "ok"} trailing {"ignored": true}'

    parsed = hermes_mod._loads_first_json_object(content)

    assert parsed == {"approved": True, "reason": "ok"}


def test_loads_first_json_object_strips_thinking_block():
    content = '<thinking>idx 0 has {bad} higher sharpe</thinking>{"winner_idx": 0}'

    parsed = hermes_mod._loads_first_json_object(content)

    assert parsed == {"winner_idx": 0}


def test_select_winner_retries_on_no_json(monkeypatch):
    """A response that is only a truncated <thinking> block (no JSON) must be
    retried, because the LLM is stochastic and a re-roll usually returns JSON."""
    client = hermes_mod.HermesClient(retries=3, timeout=0.1)
    calls = {"count": 0}

    def fake_post(payload):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"choices": [{"message": {"content": "<thinking>"}}]}
        return {"choices": [{"message": {"content": '{"winner_idx": 1, "reasoning": "ok", "confidence": 0.8}'}}]}

    monkeypatch.setattr(client, "_post_with_retries", fake_post)

    result = asyncio.run(client.select_winner({"results": []}))

    assert calls["count"] == 2
    assert result["winner_idx"] == 1
