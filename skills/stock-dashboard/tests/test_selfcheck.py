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


# ---- prices["valuation"] 是估值锚参数块，不是价位，不该被要求带 formula ----

def test_valuation_block_without_formula_is_not_an_issue():
    r = SC.verify(_base_computed(prices={
        "buy_range": {"formula": "f"},
        "valuation": {
            "current_pe_ttm": 30.0, "current_pe_percentile": 40.0,
            "pe25": 25.0, "pe75": 35.0, "days_used": 1220,
            "days_required_for_5y": 1220, "source": "akshare",
            "fetched_at": "2026-09-13T00:00:00",
            "low": 90.0, "high": 110.0,
        },
    }))
    assert r["ok"]
    assert r["issues"] == []


def test_valuation_unavailable_block_without_formula_is_not_an_issue():
    # PE 数据不可用时 valuation 退化为 {"available": False, "reason": ...}，
    # 同样不需要 formula。
    r = SC.verify(_base_computed(prices={
        "buy_range": {"formula": "f"},
        "valuation": {"available": False, "reason": "当前 PE(TTM) 未获取到"},
    }))
    assert r["ok"]
    assert r["issues"] == []


def test_target_still_requires_formula_even_with_valuation_present():
    # 真正的价位块（这里是 target）漏了 formula 时，即便 valuation 被豁免，
    # selfcheck 也必须照样能查出来——不能因为加了豁免就连带放过其它价位块。
    r = SC.verify(_base_computed(prices={
        "buy_range": {"formula": "f"},
        "valuation": {"low": 90.0, "high": 110.0},
        "target": {"price": 100.0},
    }))
    assert not r["ok"]
    assert any("target" in i and "推导式" in i for i in r["issues"])


def test_new_unknown_price_block_without_formula_is_still_caught():
    # 白名单排除机制：不在 compute.NON_PRICE_LEVEL_PRICE_BLOCKS 里的任何新
    # 子块（模拟以后新增的一个价位类型），只要缺 formula 就必须被抓到，不能
    # 因为它不认识这个名字就放过。
    r = SC.verify(_base_computed(prices={
        "buy_range": {"formula": "f"},
        "second_target": {"price": 200.0},
    }))
    assert not r["ok"]
    assert any("second_target" in i and "推导式" in i for i in r["issues"])


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


# ---- 证据单薄却给出自信结论：复现报告里 Q=100（仅 1 个维度）、结论
# 「加入候选池，等技术面转好」但 10 条红旗只判了 1 条的注入场景 ----

def test_thin_evidence_watch_verdict_is_issue():
    r = SC.verify(_base_computed(
        quality={"score": 100.0, "dims_present": 1, "dims_total": 5},
        matrix={"verdict": S.VERDICT_WATCH, "conflict": "基本面达标（Q 100.0）但技术面未转好"},
        flags_evidence={"known": 1, "total": 10, "hits": 0},
    ))
    assert not r["ok"]
    assert any("单薄" in i for i in r["issues"])


def test_thin_evidence_buy_verdict_is_issue():
    r = SC.verify(_base_computed(
        quality={"score": 100.0, "dims_present": 1, "dims_total": 5},
        timing={"score": 80.0},
        matrix={"verdict": S.VERDICT_BUY, "conflict": None},
        flags_evidence={"known": 1, "total": 10, "hits": 0},
    ))
    assert not r["ok"]
    assert any("单薄" in i for i in r["issues"])


def test_genuine_600519_style_evidence_passes_self_check():
    # 真实 600519 一次跑下来是 3 个质量维度、10 条红旗里 3 条有真实判定，
    # 阈值（2）不应误伤这种正常报告。
    r = SC.verify(_base_computed(
        quality={"score": 96.74, "dims_present": 3, "dims_total": 5},
        matrix={"verdict": S.VERDICT_WATCH, "conflict": "基本面达标（Q 96.7）但技术面未转好"},
        flags_evidence={"known": 3, "total": 10, "hits": 0},
    ))
    assert r["ok"]
    assert r["issues"] == []


def test_thin_dims_but_enough_flags_is_not_flagged_alone():
    # 只有一个信号薄弱（维度数低但红旗判定数够）时不误报——两个信号必须
    # 同时低于下限才判定为证据单薄，这是比只看一个信号更保守的选择。
    r = SC.verify(_base_computed(
        quality={"score": 100.0, "dims_present": 1, "dims_total": 5},
        matrix={"verdict": S.VERDICT_WATCH, "conflict": None},
        flags_evidence={"known": 5, "total": 10, "hits": 0},
    ))
    assert r["ok"]
    assert r["issues"] == []


def test_missing_evidence_fields_does_not_crash_or_flag():
    # 旧格式 computed（没有 dims_present/flags_evidence）必须保持向后兼容，
    # 不能因为新增字段缺失就崩溃或误报。
    r = SC.verify(_base_computed(
        matrix={"verdict": S.VERDICT_WATCH, "conflict": None},
    ))
    assert r["ok"]
    assert r["issues"] == []


def test_avoid_verdict_with_thin_evidence_is_not_flagged():
    # 证据单薄检查只针对「基本面达标」类结论（BUY/WATCH），回避结论本身
    # 已经是保守的，不需要额外标记。
    r = SC.verify(_base_computed(
        quality={"score": 30.0, "dims_present": 0, "dims_total": 5},
        matrix={"verdict": S.VERDICT_AVOID, "conflict": None},
        flags_evidence={"known": 0, "total": 10, "hits": 0},
    ))
    assert r["ok"]
    assert r["issues"] == []
