from strategy_lab.optimizer import _default_grid_for


def test_default_grid_varies_by_strategy_type():
    assert "breakout_lookback" in _default_grid_for("breakout")
    assert "mean_window" in _default_grid_for("mean_reversion")
    assert "fast_sma" in _default_grid_for("trend_following")
