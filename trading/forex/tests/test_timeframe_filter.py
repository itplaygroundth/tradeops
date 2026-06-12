import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.timeframe_filter import MultiTimeframeFilter


def candles(start=1.0, step=0.001, count=80):
    return [
        {
            "time": i,
            "open": start + step * i,
            "high": start + step * i + abs(step),
            "low": start + step * i - abs(step),
            "close": start + step * i,
            "volume": 1000,
        }
        for i in range(count)
    ]


class FakeMTFClient:
    def __init__(self, by_tf):
        self.by_tf = by_tf
        self.calls = []

    async def get_ohlcv(self, symbol, timeframe="M15", count=200):
        self.calls.append((symbol, timeframe, count))
        return self.by_tf[timeframe]


async def _eval(filter_, client, symbol, action, tf):
    return await filter_.evaluate(client, symbol, action, tf)


def test_mtf_allows_xau_when_primary_and_higher_align():
    import asyncio
    client = FakeMTFClient({"H1": candles(4400, 1.0), "H4": candles(4300, 1.2)})
    filter_ = MultiTimeframeFilter(cache_seconds=60)

    decision = asyncio.run(_eval(filter_, client, "XAUUSDm", "BUY", "H1"))

    assert decision.allowed is True
    assert decision.primary_timeframe == "H1"
    assert decision.higher_timeframe == "H4"
    assert decision.primary_trend == "up"
    assert decision.higher_trend == "up"


def test_mtf_blocks_xau_when_higher_timeframe_conflicts():
    import asyncio
    client = FakeMTFClient({"H1": candles(4400, 1.0), "H4": candles(4500, -1.0)})
    filter_ = MultiTimeframeFilter(cache_seconds=60)

    decision = asyncio.run(_eval(filter_, client, "XAUUSDm", "BUY", "H1"))

    assert decision.allowed is False
    assert "conflict" in decision.reason


def test_mtf_uses_policy_timeframe_for_xau_even_when_dna_is_lower():
    import asyncio
    client = FakeMTFClient({"H1": candles(4400, 1.0), "H4": candles(4300, 1.2)})
    filter_ = MultiTimeframeFilter(cache_seconds=60)

    decision = asyncio.run(_eval(filter_, client, "XAUUSDm", "BUY", "M15"))

    assert decision.allowed is True
    assert decision.primary_timeframe == "H1"
    assert decision.higher_timeframe == "H4"


def test_mtf_blocks_fx_primary_trend_when_higher_is_range():
    import asyncio
    range_h1 = candles(1.2, 0.0)
    client = FakeMTFClient({"M15": candles(1.1, 0.001), "H1": range_h1})
    filter_ = MultiTimeframeFilter(cache_seconds=60)

    decision = asyncio.run(_eval(filter_, client, "GBPUSDm", "BUY", "M15"))

    assert decision.allowed is False
    assert "higher H1 is range" in decision.reason


def test_mtf_summary_tracks_policy_and_decision_metrics():
    import asyncio
    client = FakeMTFClient({"H1": candles(4400, 0.0), "H4": candles(4300, 1.2)})
    filter_ = MultiTimeframeFilter(cache_seconds=60)

    decision = asyncio.run(_eval(filter_, client, "XAUUSDm", "BUY", "H1"))
    summary = filter_.summary()

    assert decision.allowed is False
    assert summary["policy"]["enabled"] is True
    assert summary["latest"]["XAUUSDm"]["primary_timeframe"] == "H1"
    assert summary["metrics"]["XAUUSDm"]["evaluations"] == 1
    assert summary["metrics"]["XAUUSDm"]["blocked"] == 1
    assert "MTF primary H1 is range" in summary["metrics"]["XAUUSDm"]["block_reasons"]
