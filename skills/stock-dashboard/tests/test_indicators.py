import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import indicators as ind


def test_sma_basic():
    assert ind.sma([1, 2, 3, 4, 5], 5) == pytest.approx(3.0)


def test_sma_uses_last_n():
    assert ind.sma([10, 10, 1, 2, 3], 3) == pytest.approx(2.0)


def test_sma_insufficient_returns_none():
    assert ind.sma([1, 2], 5) is None


def test_ema_equals_sma_at_seed():
    assert ind.ema([2, 2, 2, 2, 2], 5) == pytest.approx(2.0)


def test_ema_weights_recent_more():
    # Use convex increasing series where EMA genuinely exceeds SMA
    series = [float(i) ** 1.3 for i in range(1, 21)]
    assert ind.ema(series, 5) > ind.sma(series, 5)


def test_rsi_all_gains_is_100():
    assert ind.rsi(list(range(1, 30)), 14) == pytest.approx(100.0)


def test_rsi_all_losses_is_zero():
    assert ind.rsi(list(range(30, 1, -1)), 14) == pytest.approx(0.0)


def test_rsi_insufficient_returns_none():
    assert ind.rsi([1, 2, 3], 14) is None


def test_rsi_flat_series_is_50():
    # Flat series (no movement) should return 50 (neutral)
    assert ind.rsi([10.0] * 20, 14) == pytest.approx(50.0)


def test_macd_returns_three_keys():
    closes = [float(i) for i in range(1, 60)]
    r = ind.macd(closes)
    assert set(r) == {"macd", "signal", "hist"}


def test_macd_hist_is_difference():
    closes = [float(i) for i in range(1, 60)]
    r = ind.macd(closes)
    assert r["hist"] == pytest.approx(r["macd"] - r["signal"])


def test_macd_positive_in_uptrend():
    closes = [float(i) for i in range(1, 60)]
    assert ind.macd(closes)["macd"] > 0


def test_bollinger_mid_is_sma():
    closes = [10.0] * 20
    r = ind.bollinger(closes, 20)
    assert r["mid"] == pytest.approx(10.0)


def test_bollinger_flat_series_has_zero_width():
    r = ind.bollinger([10.0] * 20, 20)
    assert r["upper"] == pytest.approx(r["lower"])


def test_bollinger_pct_b_at_upper_is_one():
    # Price at upper band should give pct_b close to 1.0
    closes = [10.0] * 19 + [10.0 + 2.0 * 0.894427]  # upper = mid + k*sd, with sd≈0.894 for this series
    r = ind.bollinger(closes, 20, k=2.0)
    assert r["pct_b"] > 0.95


def test_atr_constant_range():
    highs = [11.0] * 20
    lows = [9.0] * 20
    closes = [10.0] * 20
    assert ind.atr(highs, lows, closes, 14) == pytest.approx(2.0)


def test_atr_insufficient_returns_none():
    assert ind.atr([1], [1], [1], 14) is None


def test_bias_positive_above_ma():
    assert ind.bias(110.0, 100.0) == pytest.approx(10.0)


def test_bias_negative_below_ma():
    assert ind.bias(90.0, 100.0) == pytest.approx(-10.0)


def test_bias_zero_ma_returns_zero():
    assert ind.bias(100.0, 0.0) == 0.0


def test_compute_all_returns_expected_keys():
    n = 150
    data = {
        "high": [100.0 + i * 0.1 for i in range(n)],
        "low": [99.0 + i * 0.1 for i in range(n)],
        "close": [99.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    }
    r = ind.compute_all(data)
    for k in ("ma20", "ma60", "ma120", "rsi14", "macd", "boll", "atr14", "bias_ma5", "vol_ma5"):
        assert k in r


def test_compute_all_handles_short_series():
    data = {"high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}
    r = ind.compute_all(data)
    assert r["ma120"] is None
