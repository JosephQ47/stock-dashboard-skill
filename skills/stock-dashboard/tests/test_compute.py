import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import compute as C
import scoring as S


def _cn_fin_block():
    """两期年报：今年 20241231 对去年同期 20231231，足够算 ar_growth/revenue_growth
    与 cash_to_profit_history。数值取自贵州茅台真实取数时观察到的量级和结构
    （商誉恒为空、短期/长期借款恒为空），但简化为整数方便手算校验。
    """
    balance = [
        {
            "报告日": "20241231", "资产总计": 1000, "商誉": float("nan"),
            "货币资金": 200, "短期借款": float("nan"), "长期借款": float("nan"),
            "应收账款": 120, "所有者权益(或股东权益)合计": 600,
        },
        {
            "报告日": "20231231", "资产总计": 900, "商誉": float("nan"),
            "货币资金": 180, "短期借款": float("nan"), "长期借款": float("nan"),
            "应收账款": 100, "所有者权益(或股东权益)合计": 550,
        },
    ]
    income = [
        {"报告日": "20241231", "净利润": 80, "营业收入": 500},
        {"报告日": "20231231", "净利润": 70, "营业收入": 450},
    ]
    cashflow = [
        {"报告日": "20241231", "经营活动产生的现金流量净额": 90},
        {"报告日": "20231231", "经营活动产生的现金流量净额": 60},
    ]
    return {"available": True, "balance": balance, "income": income, "cashflow": cashflow}


def _us_fin_block():
    """yfinance 转置后的形状：英文科目名，报告日为财年结束日（这里用 09-30
    模拟苹果这种非日历年财年）。"""
    balance = [
        {
            "报告日": "20240930", "Total Assets": 1000, "Goodwill": 50,
            "Stockholders Equity": 600, "Cash And Cash Equivalents": 300,
            "Current Debt": 40, "Long Term Debt": 60, "Accounts Receivable": 120,
        },
        {
            "报告日": "20230930", "Total Assets": 900, "Goodwill": 50,
            "Stockholders Equity": 550, "Cash And Cash Equivalents": 250,
            "Current Debt": 30, "Long Term Debt": 50, "Accounts Receivable": 100,
        },
    ]
    income = [
        {"报告日": "20240930", "Net Income": 80, "Total Revenue": 500},
        {"报告日": "20230930", "Net Income": 70, "Total Revenue": 450},
    ]
    cashflow = [
        {"报告日": "20240930", "Operating Cash Flow": 90},
        {"报告日": "20230930", "Operating Cash Flow": 60},
    ]
    return {"available": True, "balance": balance, "income": income, "cashflow": cashflow}


# ---- extract_derived: A 股 ----

def test_extract_derived_cn_maps_direct_fields():
    d = C.extract_derived("CN_SH", _cn_fin_block())
    assert d["cfo"] == Decimal("90")
    assert d["net_profit"] == Decimal("80")
    assert d["total_assets"] == Decimal("1000")
    assert d["net_assets"] == Decimal("600")
    assert d["cash"] == Decimal("200")


def test_extract_derived_cn_nan_goodwill_and_debt_are_omitted_not_zero():
    d = C.extract_derived("CN_SH", _cn_fin_block())
    assert "goodwill" not in d
    assert "interest_bearing_debt" not in d


def test_extract_derived_cn_interest_bearing_debt_requires_both_legs():
    fin = _cn_fin_block()
    fin["balance"][0]["短期借款"] = 50
    fin["balance"][1]["短期借款"] = 40
    # 长期借款仍是 NaN：只拿到一侧，不应该当 0 处理去求和
    d = C.extract_derived("CN_SH", fin)
    assert "interest_bearing_debt" not in d
    fin["balance"][0]["长期借款"] = 30
    d2 = C.extract_derived("CN_SH", fin)
    assert d2["interest_bearing_debt"] == Decimal("80")


def test_extract_derived_cn_yoy_growth_uses_same_period_last_year():
    d = C.extract_derived("CN_SH", _cn_fin_block())
    assert float(d["ar_growth"]) == pytest.approx(20.0)
    assert float(d["revenue_growth"]) == pytest.approx((500 - 450) / 450 * 100)


def test_extract_derived_cn_cash_to_profit_history_two_annuals():
    d = C.extract_derived("CN_SH", _cn_fin_block())
    hist = d["cash_to_profit_history"]
    assert len(hist) == 2
    assert Decimal("90") / Decimal("80") in hist
    assert Decimal("60") / Decimal("70") in hist


def test_extract_derived_cn_history_keeps_single_valid_year_honestly():
    """两期年报里有一期净利润缺失，不应该把另一期也一起丢掉。"""
    fin = _cn_fin_block()
    fin["income"][1]["净利润"] = None
    d = C.extract_derived("CN_SH", fin)
    hist = d["cash_to_profit_history"]
    assert len(hist) == 1
    assert hist[0] == Decimal("90") / Decimal("80")


def test_extract_derived_no_data_source_fields_stay_absent():
    d = C.extract_derived("CN_SH", _cn_fin_block())
    for key in ("deducted_profit", "audit_opinion", "pledge_ratio", "delisting_risk", "under_investigation"):
        assert key not in d


def test_extract_derived_unavailable_financials_returns_empty():
    assert C.extract_derived("CN_SH", {"available": False}) == {}
    assert C.extract_derived("CN_SH", None) == {}


def test_extract_derived_unknown_market_returns_empty():
    assert C.extract_derived(None, _cn_fin_block()) == {}


# ---- extract_derived: 港股/美股（yfinance 转置后形状）----

def test_extract_derived_us_maps_english_field_names():
    d = C.extract_derived("US", _us_fin_block())
    assert d["cfo"] == Decimal("90")
    assert d["net_profit"] == Decimal("80")
    assert d["goodwill"] == Decimal("50")
    assert d["interest_bearing_debt"] == Decimal("100")
    assert float(d["ar_growth"]) == pytest.approx(20.0)


def test_extract_derived_hk_shares_us_field_map():
    d = C.extract_derived("HK", _us_fin_block())
    assert d["net_profit"] == Decimal("80")


# ---- derive_quality_dims ----

def test_derive_quality_dims_health_and_profitability_from_real_data():
    fin = _cn_fin_block()
    derived = C.extract_derived("CN_SH", fin)
    import ratios
    flags = ratios.check_red_flags(derived)
    dims = C.derive_quality_dims(fin, flags, "CN_SH")
    assert dims["health"] == pytest.approx(60.0)
    assert dims["profitability"] == pytest.approx(50.0 + (80 / 500) * 200)


def test_derive_quality_dims_omits_dims_when_inputs_missing():
    dims = C.derive_quality_dims({}, [], "CN_SH")
    assert "health" not in dims
    assert "profitability" not in dims


def test_derive_quality_dims_works_for_us_field_names():
    fin = _us_fin_block()
    dims = C.derive_quality_dims(fin, [], "US")
    assert dims["health"] == pytest.approx(60.0)


# ---- run(): blocked payload must degrade, not issue a confident verdict ----

def _kline(n=130, price=10.0):
    return {
        "close": [price] * n, "high": [price + 0.5] * n,
        "low": [price - 0.5] * n, "volume": [1000.0] * n,
    }


def test_run_blocked_forces_avoid_and_drops_prices():
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 0.70, "blocked": True,
        "block_reasons": ["行情缺失：现价、买入区间、目标价与止损价均无法给出"],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    assert result["blocked"] is True
    assert result["matrix"]["verdict"] == S.VERDICT_AVOID
    assert "行情缺失" in result["matrix"]["conflict"]
    assert result["prices"] == {}
    assert result["price_error"] and "阻断" in result["price_error"]


def test_run_not_blocked_still_prices_normally():
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    assert result["blocked"] is False
    # 未阻断时应该正常推导出买入区间，而不是被无条件塞进阻断话术
    assert "buy_range" in result["prices"]
    assert "数据被阻断" not in (result["matrix"].get("conflict") or "")
