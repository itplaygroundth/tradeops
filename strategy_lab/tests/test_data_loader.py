from strategy_lab.data import fetch_binance_ohlcv, normalize_timeframe


def test_normalize_timeframe_accepts_binance_alias():
    assert normalize_timeframe("15m") == "M15"
    assert normalize_timeframe("H1") == "H1"


def test_fetch_binance_ohlcv_parses_rows(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'[[1600000000000,"100","110","90","105","12",0,0,0,"7"]]'

    def fake_urlopen(url, timeout=15):
        assert "BTCUSDT" in url
        assert "interval=15m" in url
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    candles = fetch_binance_ohlcv("BTCUSDT", timeframe="M15", count=1)

    assert candles == [{
        "time": 1600000000,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 12.0,
        "taker_buy": 7.0,
    }]

