import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import selfcheck as SC
import scoring as S


def _base_computed(**overrides):
    base = {
        "code": "X",
        "completeness": 1.0,
        "blocked": False,
        "quality": {"score": 70.0},
        "timing": {"score": 70.0},
        "veto": False,
        "matrix": {"verdict": S.VERDICT_WATCH, "conflict": None},
        "gates": [],
        "prices": {"buy_range": {"formula": "some formula"}},
        "data_sources": {"quote": "tencent"},
    }
    base.update(overrides)
    return base


def test_clean_payload_passes():
    r = SC.verify(_base_computed())
    assert r["ok"]
    assert r["issues"] == []


def test_score_out_of_range_is_issue():
    r = SC.verify(_base_computed(quality={"score": 150.0}))
    assert not r["ok"]
    assert any("quality" in i for i in r["issues"])


def test_veto_but_quality_above_cap_is_issue():
    r = SC.verify(_base_computed(veto=True, quality={"score": 41.0}, matrix={"verdict": S.VERDICT_AVOID}))
    assert not r["ok"]
    assert any("封顶" in i for i in r["issues"])


def test_veto_but_verdict_not_avoid_is_issue():
    r = SC.verify(_base_computed(veto=True, quality={"score": 40.0}, matrix={"verdict": S.VERDICT_WATCH}))
    assert not r["ok"]
    assert any("否决" in i for i in r["issues"])


def test_price_without_formula_is_issue():
    r = SC.verify(_base_computed(prices={"target": {"price": 100}}))
    assert not r["ok"]
    assert any("推导式" in i for i in r["issues"])


def test_gate_with_buy_verdict_is_issue():
    r = SC.verify(_base_computed(gates=["RSI 超买"], matrix={"verdict": S.VERDICT_BUY}))
    assert not r["ok"]
    assert any("禁令" in i for i in r["issues"])


def test_low_completeness_not_blocked_is_issue():
    r = SC.verify(_base_computed(completeness=0.5, blocked=False))
    assert not r["ok"]
    assert any("完备率" in i for i in r["issues"])


def test_missing_data_sources_is_issue():
    r = SC.verify(_base_computed(data_sources=None))
    assert not r["ok"]
    assert any("数据来源" in i for i in r["issues"])


# ---- 新增方向：blocked=True 时结论/价位不能装作数据齐全 ----

def test_blocked_with_buy_verdict_is_issue():
    r = SC.verify(_base_computed(blocked=True, matrix={"verdict": S.VERDICT_BUY, "conflict": None}))
    assert not r["ok"]
    assert any("回避" in i for i in r["issues"])


def test_blocked_with_watch_verdict_is_issue():
    r = SC.verify(_base_computed(blocked=True, matrix={"verdict": S.VERDICT_WATCH, "conflict": None}))
    assert not r["ok"]
    assert any("回避" in i for i in r["issues"])


def test_blocked_with_prices_is_issue_even_if_avoid():
    r = SC.verify(_base_computed(
        blocked=True,
        matrix={"verdict": S.VERDICT_AVOID, "conflict": "数据被阻断"},
        prices={"buy_range": {"formula": "f"}},
    ))
    assert not r["ok"]
    assert any("价位" in i for i in r["issues"])


def test_blocked_avoid_and_no_prices_passes():
    r = SC.verify(_base_computed(
        blocked=True,
        completeness=0.5,
        matrix={"verdict": S.VERDICT_AVOID, "conflict": "数据被阻断"},
        prices={},
    ))
    assert r["ok"]
    assert r["issues"] == []
