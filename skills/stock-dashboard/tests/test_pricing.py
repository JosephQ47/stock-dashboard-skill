import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pricing as P


def test_valuation_anchor_orders_bounds():
    r = P.valuation_anchor(80.0, 120.0)
    assert r["low"] == 80.0 and r["high"] == 120.0


def test_valuation_anchor_swaps_reversed_input():
    r = P.valuation_anchor(120.0, 80.0)
    assert r["low"] == 80.0 and r["high"] == 120.0


def test_valuation_anchor_none_input_raises():
    with pytest.raises(P.PricingBlocked):
        P.valuation_anchor(None, 100.0)
    with pytest.raises(P.PricingBlocked):
        P.valuation_anchor(80.0, None)


def test_technical_anchor_takes_min_and_max():
    r = P.technical_anchor(ma20=100.0, prior_low=90.0, boll_lower=95.0)
    assert r["low"] == 90.0 and r["high"] == 100.0


def test_technical_anchor_ignores_none():
    r = P.technical_anchor(ma20=100.0, prior_low=None, boll_lower=95.0)
    assert r["low"] == 95.0 and r["high"] == 100.0


def test_technical_anchor_all_none_raises():
    with pytest.raises(P.PricingBlocked):
        P.technical_anchor(None, None, None)


def test_buy_range_uses_intersection():
    val = {"low": 80.0, "high": 110.0}
    tech = {"low": 90.0, "high": 120.0}
    r = P.buy_range(val, tech)
    assert r["low"] == 90.0 and r["high"] == 110.0
    assert r["note"] is None


def test_buy_range_formula_mentions_both_anchors():
    r = P.buy_range({"low": 80.0, "high": 110.0}, {"low": 90.0, "high": 120.0})
    assert "估值锚" in r["formula"] and "技术锚" in r["formula"]


def test_buy_range_empty_intersection_falls_back_to_nearer_side():
    val = {"low": 60.0, "high": 70.0}
    tech = {"low": 90.0, "high": 100.0}
    r = P.buy_range(val, tech)
    assert r["note"] is not None
    assert r["low"] == 60.0 and r["high"] == 70.0


def test_buy_range_fallback_to_valuation_anchor():
    """When valuation is lower, note mentions 'deeper pullback'."""
    val = {"low": 50.0, "high": 60.0}
    tech = {"low": 80.0, "high": 90.0}
    r = P.buy_range(val, tech)
    assert "更深的技术回调" in r["note"] or "等待更深的技术回调" in r["note"]
    assert r["low"] == 50.0 and r["high"] == 60.0


def test_buy_range_fallback_to_technical_anchor():
    """When technical is lower, note mentions 'unconfirmed downtrend'."""
    val = {"low": 80.0, "high": 90.0}
    tech = {"low": 50.0, "high": 60.0}
    r = P.buy_range(val, tech)
    assert "趋势不确定" in r["note"] or "不确定时介入" in r["note"]
    assert r["low"] == 50.0 and r["high"] == 60.0


def test_target_price_takes_lower_of_valuation_and_resistance():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=10.0)
    assert r["price"] == 130.0


def test_target_price_implied_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=10.0)
    assert r["implied_pe"] == pytest.approx(13.0)


def test_target_price_no_eps_gives_none_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=None)
    assert r["implied_pe"] is None


def test_target_price_no_resistance_uses_valuation():
    r = P.target_price(val_high=150.0, resistance=None, eps=10.0)
    assert r["price"] == 150.0


def test_target_price_both_inputs_missing_raises():
    with pytest.raises(P.PricingBlocked):
        P.target_price(val_high=None, resistance=None, eps=10.0)


def test_target_price_negative_eps_gives_none_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=-5.0)
    assert r["price"] == 130.0
    assert r["implied_pe"] is None


def test_target_price_zero_eps_gives_none_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=0.0)
    assert r["price"] == 130.0
    assert r["implied_pe"] is None


def test_stop_loss_picks_nearer_of_two_methods():
    r = P.stop_loss(entry=100.0, atr14=3.0, prior_low=90.0)
    assert r["price"] == pytest.approx(94.0)
    assert r["method"] == "ATR"


def test_stop_loss_structure_method_when_nearer():
    r = P.stop_loss(entry=100.0, atr14=10.0, prior_low=96.0)
    assert r["price"] == pytest.approx(95.04)
    assert r["method"] == "结构"


def test_stop_loss_formula_shows_inputs():
    r = P.stop_loss(entry=100.0, atr14=3.0, prior_low=90.0)
    assert "100" in r["formula"] and "3" in r["formula"]


def test_stop_loss_missing_both_raises():
    with pytest.raises(P.PricingBlocked):
        P.stop_loss(entry=100.0, atr14=None, prior_low=None)


def test_stop_loss_prior_low_above_entry_raises():
    """When prior_low > entry, structure stop would be above entry, which is invalid."""
    with pytest.raises(P.PricingBlocked):
        P.stop_loss(entry=100.0, atr14=10.0, prior_low=105.0)


def test_gate_check_rsi_over_eighty():
    gates = P.gate_check(rsi14=85.0, bias_ma5=1.0)
    assert any("RSI14" in g for g in gates)


def test_gate_check_bias_over_five():
    gates = P.gate_check(rsi14=50.0, bias_ma5=7.0)
    assert any("乖离" in g for g in gates)


def test_gate_check_negative_bias_not_flagged():
    assert P.gate_check(rsi14=50.0, bias_ma5=-7.0) == []


def test_gate_check_clean_returns_empty():
    assert P.gate_check(rsi14=55.0, bias_ma5=2.0) == []


def test_gate_check_handles_none():
    assert P.gate_check(rsi14=None, bias_ma5=None) == []
