"""Tests for PriceHistory candle aggregation (bucket_seconds mode).

Ticks bucket into OHLC candles by timestamp. Indicators then operate on
candle closes (and true high/low for ATR), so the indicator period is constant
in TIME rather than in tick count.
"""
from engine.price_history import PriceHistory


def test_legacy_mode_is_raw_ticks():
    """bucket_seconds=0 keeps the old behaviour: 1 tick = 1 data point."""
    h = PriceHistory(maxlen=100, bucket_seconds=0)
    for i in range(5):
        h.add(100.0 + i, volume=1.0, timestamp=float(i))
    assert h.count == 5
    assert h.current == 104.0


def test_ticks_in_same_bucket_form_one_candle():
    h = PriceHistory(maxlen=100, bucket_seconds=300)  # M5
    # all within the same 300s bucket (t=0..299)
    h.add(100.0, volume=1.0, timestamp=10.0)   # open
    h.add(105.0, volume=2.0, timestamp=120.0)  # high
    h.add(98.0, volume=1.5, timestamp=200.0)   # low
    h.add(101.0, volume=1.0, timestamp=299.0)  # close
    # one in-progress candle
    assert h.count == 1
    assert h.current == 101.0          # close = last price
    assert h.opens[-1] == 100.0
    assert h.highs[-1] == 105.0
    assert h.lows[-1] == 98.0
    assert h.volumes[-1] == 5.5        # summed


def test_new_bucket_rolls_candle():
    h = PriceHistory(maxlen=100, bucket_seconds=300)
    h.add(100.0, volume=1.0, timestamp=10.0)    # bucket 0
    h.add(102.0, volume=1.0, timestamp=120.0)   # bucket 0 -> close 102
    h.add(103.0, volume=1.0, timestamp=350.0)   # bucket 1 -> rolls
    assert h.count == 2
    # finalized candle 0 close = 102, candle 1 (in progress) close = 103
    assert list(h.prices)[-2] == 102.0
    assert h.current == 103.0


def test_atr_uses_true_high_low_in_candle_mode():
    h = PriceHistory(maxlen=100, bucket_seconds=300)
    # build candles each with a known high/low range; one tick per bucket plus
    # an intra-bucket spike to set high/low
    base = 100.0
    for b in range(20):
        t0 = b * 300 + 10
        h.add(base, volume=1.0, timestamp=float(t0))        # open=close base
        h.add(base + 2.0, volume=1.0, timestamp=float(t0 + 50))  # high
        h.add(base - 2.0, volume=1.0, timestamp=float(t0 + 100))  # low
        h.add(base, volume=1.0, timestamp=float(t0 + 150))   # close back to base
        base += 0.0  # flat closes
    atr = h.atr(14)
    assert atr is not None
    # true range per candle ~ high-low = 4.0 (closes are flat), so ATR ~ 4.0
    assert 3.0 < atr < 5.0


def test_seed_candle_backfill():
    h = PriceHistory(maxlen=100, bucket_seconds=900)  # M15
    for i in range(30):
        h.seed_candle(open_=100.0 + i, high=101.0 + i, low=99.0 + i,
                      close=100.5 + i, volume=10.0)
    assert h.count == 30
    assert h.current == 100.5 + 29
    assert h.highs[-1] == 101.0 + 29
    assert h.lows[-1] == 99.0 + 29
    # indicators usable after backfill
    assert h.sma(5) is not None
    assert h.rsi(14) is not None


def test_seed_then_live_tick_extends():
    h = PriceHistory(maxlen=100, bucket_seconds=300)
    for i in range(10):
        h.seed_candle(open_=100.0, high=101.0, low=99.0, close=100.0, volume=5.0)
    assert h.count == 10
    # a live tick in a new bucket opens candle 11
    h.add(102.0, volume=1.0, timestamp=999999.0)
    assert h.count == 11
    assert h.current == 102.0


def test_cvd_tracks_true_aggressor_side():
    """CVD = buy aggressor volume - sell aggressor volume, from the is_buy flag,
    NOT inferred from price direction."""
    h = PriceHistory(maxlen=100, bucket_seconds=300)
    # one candle per bucket; alternate buy/sell-heavy
    h.add(100.0, volume=10.0, timestamp=10.0, is_buy=True)    # +10
    h.add(100.0, volume=3.0, timestamp=20.0, is_buy=False)    # -3  (same candle)
    # candle 0: buy=10 sell=3 -> net +7
    h.add(101.0, volume=2.0, timestamp=310.0, is_buy=True)    # candle 1 buy=2
    h.add(101.0, volume=8.0, timestamp=320.0, is_buy=False)   # candle 1 sell=8 -> net -6
    assert h.buy_vols[0] == 10.0
    assert h.sell_vols[0] == 3.0
    assert h.buy_vols[1] == 2.0
    assert h.sell_vols[1] == 8.0
    # total cvd = (10-3) + (2-8) = 7 - 6 = 1
    assert h.cvd(30) == 1.0


def test_cvd_sign_independent_of_price():
    """Price can rise while sellers dominate (distribution) -> negative CVD."""
    h = PriceHistory(maxlen=100, bucket_seconds=300)
    for i in range(5):
        # price rising each candle, but every trade is a sell aggressor
        h.add(100.0 + i, volume=5.0, timestamp=float(i * 300 + 10), is_buy=False)
    assert h.cvd(30) == -25.0  # all sells, despite rising price


def test_seed_candle_taker_buy_split():
    h = PriceHistory(maxlen=100, bucket_seconds=900)
    h.seed_candle(open_=100.0, high=101.0, low=99.0, close=100.5,
                  volume=10.0, buy_vol=7.0, sell_vol=3.0)
    assert h.buy_vols[-1] == 7.0
    assert h.sell_vols[-1] == 3.0
    assert h.cvd(30) == 4.0


def test_seed_candle_defaults_to_half_split():
    h = PriceHistory(maxlen=100, bucket_seconds=900)
    h.seed_candle(open_=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)
    # no taker-buy info -> 50/50
    assert h.buy_vols[-1] == 5.0
    assert h.sell_vols[-1] == 5.0
    assert h.cvd(30) == 0.0


def test_legacy_mode_cvd():
    """Raw-tick mode still accumulates buy/sell per tick."""
    h = PriceHistory(maxlen=100, bucket_seconds=0)
    h.add(100.0, volume=4.0, timestamp=1.0, is_buy=True)
    h.add(100.0, volume=1.0, timestamp=2.0, is_buy=False)
    assert h.cvd(30) == 3.0
