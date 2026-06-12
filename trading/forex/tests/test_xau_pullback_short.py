import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.xau_pullback_short import AssetPullbackPolicy, XauPullbackShortFilter


def downtrend_candles(count=80, start=4300.0, step=-2.0):
    candles = []
    for i in range(count):
        close = start + step * i
        candles.append({
            "time": i,
            "open": close + 0.6,
            "high": close + 1.2,
            "low": close - 1.2,
            "close": close,
            "volume": 1000,
        })
    return candles


def test_xau_pullback_allows_rejection_short():
    primary = downtrend_candles()
    # Replace the latest candle with a pullback into the falling mean and bearish rejection.
    primary[-1] = {
        "time": 79,
        "open": 4148.0,
        "high": 4151.0,
        "low": 4139.0,
        "close": 4144.0,
        "volume": 1000,
    }
    higher = downtrend_candles(start=4400.0, step=-3.0)
    filter_ = XauPullbackShortFilter()

    decision = filter_._evaluate_candles("XAUUSDm", primary, higher, price=4144.0)

    assert decision.allowed is True
    assert decision.action == "SHORT"
    assert decision.confidence >= 72
    assert decision.basket_max_positions >= 2


def test_xau_pullback_blocks_chasing_far_below_mean():
    primary = downtrend_candles()
    primary[-1] = {
        "time": 79,
        "open": 4125.0,
        "high": 4128.0,
        "low": 4115.0,
        "close": 4118.0,
        "volume": 1000,
    }
    higher = downtrend_candles(start=4400.0, step=-3.0)
    filter_ = XauPullbackShortFilter()

    decision = filter_._evaluate_candles("XAUUSDm", primary, higher, price=4118.0)

    assert decision.allowed is False
    assert "not near EMA20" in decision.reason or "avoids chasing" in decision.reason


def test_xau_pullback_blocks_when_higher_timeframe_not_down():
    primary = downtrend_candles()
    higher = downtrend_candles(start=4000.0, step=3.0)
    filter_ = XauPullbackShortFilter()

    decision = filter_._evaluate_candles("XAUUSDm", primary, higher, price=4144.0)

    assert decision.allowed is False
    assert "trend alignment" in decision.reason


def uptrend_candles(count=80, start=1.0800, step=0.0008):
    candles = []
    for i in range(count):
        close = start + step * i
        candles.append({
            "time": i,
            "open": close - 0.0002,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "volume": 1000,
        })
    return candles


def test_fx_pullback_allows_bullish_rejection_long_with_single_basket():
    primary = uptrend_candles()
    primary[-1] = {
        "time": 79,
        "open": 1.1359,
        "high": 1.1370,
        "low": 1.1355,
        "close": 1.1363,
        "volume": 1000,
    }
    higher = uptrend_candles(start=1.0700, step=0.0010)
    filter_ = XauPullbackShortFilter()

    decision = filter_._evaluate_candles("EURUSDm", primary, higher, price=1.1363)

    assert decision.allowed is True
    assert decision.action == "LONG"
    assert decision.policy_key == "EUR"
    assert decision.basket_max_positions == 1


def test_high_volatility_clamps_xau_basket_to_one():
    primary = downtrend_candles()
    primary[-1] = {
        "time": 79,
        "open": 4148.0,
        "high": 4151.0,
        "low": 4139.0,
        "close": 4144.0,
        "volume": 1000,
    }
    higher = downtrend_candles(start=4400.0, step=-3.0)
    high_vol_policy = AssetPullbackPolicy(
        key="XAU",
        primary_timeframe="H1",
        higher_timeframe="H4",
        ema_touch_pct=0.35,
        max_extension_pct=0.80,
        min_confidence=72,
        basket_max_positions=3,
        basket_cooldown_seconds=180,
        high_vol_atr_pct=0.01,
    )
    filter_ = XauPullbackShortFilter()

    decision = filter_._evaluate_candles("XAUUSDm", primary, higher, price=4144.0, policy=high_vol_policy)

    assert decision.allowed is True
    assert decision.volatility == "high"
    assert decision.basket_max_positions == 1
