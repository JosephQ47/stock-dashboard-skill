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
    """When valuation is lower, note says fundamentals look expensive relative to the technical band."""
    val = {"low": 50.0, "high": 60.0}
    tech = {"low": 80.0, "high": 90.0}
    r = P.buy_range(val, tech)
    assert "偏贵" in r["note"]
    assert "需人工复核" in r["note"]
    assert r["low"] == 50.0 and r["high"] == 60.0


def test_buy_range_fallback_to_technical_anchor():
    """When technical is lower, note says fundamentals look cheap but must not claim broken
    support or an uncertain trend — the anchors' relative position alone cannot establish that."""
    val = {"low": 80.0, "high": 90.0}
    tech = {"low": 50.0, "high": 60.0}
    r = P.buy_range(val, tech)
    assert "偏便宜" in r["note"]
    assert "需人工复核" in r["note"]
    assert "不代表技术支撑被跌破" in r["note"]
    assert "不代表趋势不确定" in r["note"]
    assert r["low"] == 50.0 and r["high"] == 60.0


def test_buy_range_fallback_technical_anchor_600519_shape():
    """Regression for the 600519 case: valuation anchor entirely above both price and the
    technical anchor (cheap-by-PE stock whose technical band sits below the fair-value band).
    The note must describe only the anchors' relative position, not price action."""
    val = {"low": 1381.84, "high": 2459.69}
    tech = {"low": 1168.63, "high": 1298.32}
    r = P.buy_range(val, tech)
    assert r["low"] == 1168.63 and r["high"] == 1298.32
    assert "偏便宜" in r["note"]
    assert "需人工复核" in r["note"]
    assert "不代表技术支撑被跌破" in r["note"]
    assert "不代表趋势不确定" in r["note"]


def test_buy_range_technical_only_uses_tech_bounds():
    tech = {"low": 90.0, "high": 100.0}
    r = P.buy_range_technical_only(tech, "当前 PE(TTM) 为 -69.73（公司亏损），估值分位数没有意义")
    assert r["low"] == 90.0 and r["high"] == 100.0
    assert "估值锚" in r["formula"]
    assert "亏损" in r["formula"]
    assert "亏损" in r["note"]


def test_buy_range_formula_shows_valuation_derivation_when_present():
    val = {
        "low": 80.0, "high": 110.0,
        "formula": "当前 PE(TTM) 20.00（处于历史 5.0 分位），历史 1220 个交易日 中 25 分位 PE 25.00、75 分位 PE 40.00，按现价 100.00 换算得 [80.00, 110.00]",
    }
    tech = {"low": 90.0, "high": 120.0}
    r = P.buy_range(val, tech)
    assert "PE(TTM) 20.00" in r["formula"]
    assert "25 分位 PE 25.00" in r["formula"]
    assert "技术锚" in r["formula"]


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


def test_stop_loss_valid_atr_with_invalid_structure():
    """When structure candidate is invalid but ATR is valid, return ATR with note."""
    r = P.stop_loss(entry=100.0, atr14=3.0, prior_low=105.0)
    assert r["price"] == pytest.approx(94.0)
    assert r["method"] == "ATR"
    assert r["note"] is not None
    assert "结构" in r["note"] and "舍弃" in r["note"]


def test_stop_loss_negative_atr_stop_raises():
    """When ATR alone produces negative stop, raise PricingBlocked."""
    with pytest.raises(P.PricingBlocked):
        P.stop_loss(entry=100.0, atr14=60.0, prior_low=None)


def test_stop_loss_valid_structure_with_invalid_atr():
    """When ATR candidate is invalid but structure is valid, return structure with note."""
    r = P.stop_loss(entry=100.0, atr14=60.0, prior_low=90.0)
    assert r["price"] == pytest.approx(89.1)
    assert r["method"] == "结构"
    assert r["note"] is not None
    assert "ATR" in r["note"] and "舍弃" in r["note"]


def test_stop_loss_both_candidates_invalid_raises():
    """When both ATR and structure candidates are invalid, raise PricingBlocked."""
    with pytest.raises(P.PricingBlocked):
        P.stop_loss(entry=100.0, atr14=60.0, prior_low=105.0)


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
