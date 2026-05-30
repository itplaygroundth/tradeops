import sys
import asyncio
from pathlib import Path
from urllib import error

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import engine.hermes_client as hermes_mod


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
