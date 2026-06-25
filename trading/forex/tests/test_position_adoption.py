import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.agent_manager import ForexAgentManager, MANAGED_MAGIC


class FakeAgent:
    def __init__(self, symbol):
        self.dna = SimpleNamespace(symbol=symbol, name="FX-RESTORED")
        self._open_ticket = None
        self._open_entry = 0.0
        self._open_side = ""
        self._open_sl = 0.0
        self._open_tp = 0.0
        self._open_risk_amount = 0.0

    @property
    def is_in_trade(self):
        return self._open_ticket is not None


def test_adopts_managed_position_after_restart():
    manager = ForexAgentManager.__new__(ForexAgentManager)
    manager.agents = [FakeAgent("EURUSDm")]

    manager._adopt_live_positions([{
        "ticket": 123,
        "symbol": "EURUSDm",
        "type": "BUY",
        "price_open": 1.16,
        "sl": 1.15,
        "tp": 1.18,
        "magic": MANAGED_MAGIC,
    }])

    agent = manager.agents[0]
    assert agent._open_ticket == 123
    assert agent._open_side == "BUY"
    assert agent._open_entry == 1.16
