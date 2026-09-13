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


# ---- run(): extras 必须原样透传到 computed，不能在 raw -> computed 之间丢失 ----

def test_run_carries_extras_through_for_cn():
    extras = {
        "available": True,
        "source": "akshare",
        "fetched_at": "2026-09-13T00:00:00",
        "dragon_tiger": {"hit": False},
        "margin_trading": {"available": True},
        "lockup": {"available": True},
    }
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "data_sources": {"kline": "东财", "financials": "akshare"},
        "extras": extras,
    }
    result = C.run(raw)
    assert result["extras"] == extras
    assert result["extras"]["source"] == "akshare"
    assert result["extras"]["fetched_at"] == "2026-09-13T00:00:00"


def test_run_carries_extras_through_for_us_inapplicable():
    # 港股/美股没有龙虎榜/两融/解禁这套 A 股特有机制：extras 应该是「不适用于
    # 该市场」的结构化说明，而不是抓取失败的「缺失」，两者的区别必须能只从
    # computed JSON 里看出来。
    extras = {
        "available": False,
        "reason": "A 股专属数据，当前市场不适用",
        "source": "n/a",
        "fetched_at": "2026-09-13T19:27:00",
    }
    raw = {
        "code": "AAPL", "market": "US", "currency": "USD",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": {},
        "data_sources": {"kline": "yfinance"},
        "extras": extras,
    }
    result = C.run(raw)
    assert result["extras"] == extras
    assert result["extras"]["available"] is False
    assert "不适用" in result["extras"]["reason"]


def test_run_missing_extras_is_none_not_crash():
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    assert result["extras"] is None


# ---- derive_valuation_anchor(): PE 五年分位估值锚 ----

def _pe_block(pe_history, current_pe, days_used=None, available=True, reason=None):
    return {
        "source": "akshare stock_value_em",
        "fetched_at": "2026-09-13T00:00:00",
        "available": available,
        "reason": reason,
        "pe_ttm_history": pe_history,
        "current_pe_ttm": current_pe,
        "days_used": days_used if days_used is not None else len(pe_history or []),
    }


def test_derive_valuation_anchor_percentile_prices():
    """current_pe/pe25/pe75 均已知时，25/75 分位价必须等于 current_price * (分位PE/当前PE)。"""
    history = [float(x) for x in range(1, 101)]  # 1..100，25 分位=25.75，75 分位=75.25
    pe_block = _pe_block(history, current_pe=50.0)
    val, reason = C.derive_valuation_anchor(pe_block, current_price=100.0, market="CN_SH")
    assert reason is None
    assert val is not None
    expected_low = 100.0 * (25.75 / 50.0)
    expected_high = 100.0 * (75.25 / 50.0)
    assert val["low"] == pytest.approx(expected_low)
    assert val["high"] == pytest.approx(expected_high)
    # formula 必须能核对算术：当前 PE、分位 PE、天数、结果价格都要出现
    assert "50.00" in val["formula"]
    assert "25.75" in val["formula"] or "25.7" in val["formula"]
    assert f"{expected_low:.2f}" in val["formula"]


def test_derive_valuation_anchor_short_history_reports_days_used():
    """历史不足五年（1220 个交易日）时，如实报告实际天数，并注明不足五年。"""
    history = [10.0, 12.0, 14.0, 16.0, 18.0]  # 仅 5 天
    pe_block = _pe_block(history, current_pe=14.0)
    val, reason = C.derive_valuation_anchor(pe_block, current_price=100.0, market="CN_SH")
    assert reason is None
    assert val is not None
    assert "5 个交易日" in val["formula"]
    assert "不足五年" in val["formula"]
    assert val["meta"]["days_used"] == 5


def test_derive_valuation_anchor_negative_pe_blocked():
    """亏损（PE 为负）不得产生估值锚，必须给出明确原因。"""
    pe_block = _pe_block([10.0, 12.0, -5.0], current_pe=-69.73)
    val, reason = C.derive_valuation_anchor(pe_block, current_price=15.0, market="CN_SH")
    assert val is None
    assert reason is not None
    assert "-69.73" in reason
    assert "亏损" in reason or "异常" in reason


def test_derive_valuation_anchor_zero_pe_blocked():
    pe_block = _pe_block([10.0, 12.0, 14.0], current_pe=0.0)
    val, reason = C.derive_valuation_anchor(pe_block, current_price=15.0, market="CN_SH")
    assert val is None
    assert reason is not None


def test_derive_valuation_anchor_us_market_omitted_not_faked():
    """港股/美股没有五年 PE 历史数据源，必须省略估值锚，而不是用现价百分比冒充。"""
    val, reason = C.derive_valuation_anchor({"available": False}, current_price=100.0, market="US")
    assert val is None
    assert "港股/美股" in reason
    assert "五年" in reason


def test_derive_valuation_anchor_unavailable_pe_block():
    val, reason = C.derive_valuation_anchor(
        {"available": False, "reason": "akshare 请求失败"}, current_price=100.0, market="CN_SH"
    )
    assert val is None
    assert "akshare 请求失败" in reason


def test_derive_valuation_anchor_missing_current_price():
    pe_block = _pe_block([10.0, 12.0, 14.0], current_pe=12.0)
    val, reason = C.derive_valuation_anchor(pe_block, current_price=None, market="CN_SH")
    assert val is None
    assert "现价" in reason


# ---- 证据字段：flags_evidence 与 quality.dims_present 必须能只从 computed 里读出 ----

def test_run_reports_flags_evidence_and_quality_dims_present():
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    # _cn_fin_block 只有 cfo/net_profit/total_assets/ar_growth/revenue_growth
    # 齐全，能判定的红旗是 CASH_PROFIT/ACCRUAL/RECEIVABLE 三条，其余七条
    # （GOODWILL/RECURRING/BIG_DEPOSIT_LOAN/AUDIT_OPINION/PLEDGE/
    # DELISTING_RISK/INVESTIGATION）都没有数据源，标「未获取到」。
    assert result["flags_evidence"] == {"known": 3, "total": 10, "hits": 0}
    assert result["quality"]["dims_present"] == 3  # statement/health/profitability
    assert result["quality"]["dims_total"] == len(S.QUALITY_WEIGHTS)


# ---- 端到端否决：BIG_DEPOSIT_LOAN / 连续两年净现比过低都必须能一路打到
# matrix=回避、quality<=40，而不是只在 test_scoring.py 里用手写的 q/t 数值
# 单测 veto 分支。这是唯一两条有真实数据源的一票否决路径，此前从未被端到
# 端跑过。----

def test_run_end_to_end_big_deposit_loan_veto_forces_avoid_and_caps_quality():
    fin = _cn_fin_block()
    # 补上短期/长期借款，使货币资金、有息负债占总资产比例均超过 30%
    # （200/1000=20% 不够，改成货币资金 400、有息负债合计 350，总资产 1000，
    # 是一张能真实存在的资产负债表：现金多、同时背着大额有息负债）。
    fin["balance"][0]["货币资金"] = 400
    fin["balance"][0]["短期借款"] = 200
    fin["balance"][0]["长期借款"] = 150
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": fin,
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    flags = {f["code"]: f for f in result["flags"]}
    assert flags["BIG_DEPOSIT_LOAN"]["hit"]
    assert flags["BIG_DEPOSIT_LOAN"]["veto"]
    assert result["veto"] is True
    assert result["quality"]["score"] <= S.VETO_CAP
    assert result["matrix"]["verdict"] == S.VERDICT_AVOID


def test_run_end_to_end_two_year_low_cash_profit_veto_forces_avoid():
    fin = _cn_fin_block()
    # 把最近两期的经营现金流压低，使两年净现比都低于 0.5（cfo/net_profit）。
    fin["cashflow"][0]["经营活动产生的现金流量净额"] = 30  # 30/80 = 0.375
    fin["cashflow"][1]["经营活动产生的现金流量净额"] = 20  # 20/70 ≈ 0.286
    raw = {
        "code": "600519", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": fin,
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    flags = {f["code"]: f for f in result["flags"]}
    assert flags["CASH_PROFIT"]["veto"]
    assert result["veto"] is True
    assert result["quality"]["score"] <= S.VETO_CAP
    assert result["matrix"]["verdict"] == S.VERDICT_AVOID


def test_run_falls_back_to_technical_anchor_when_valuation_blocked():
    """估值锚被阻断（亏损）时，买入区间必须退化为纯技术锚，而不是整体不给价位。"""
    raw = {
        "code": "600793", "market": "CN_SH", "currency": "CNY",
        "completeness": 1.0, "blocked": False, "block_reasons": [],
        "kline": _kline(),
        "financials": _cn_fin_block(),
        "pe_history": _pe_block([10.0, 12.0, -5.0], current_pe=-69.73),
        "data_sources": {"kline": "东财", "financials": "akshare"},
    }
    result = C.run(raw)
    assert "buy_range" in result["prices"]
    assert result["prices"]["valuation"]["available"] is False
    assert "亏损" in result["prices"]["valuation"]["reason"]
    assert "技术锚" in result["prices"]["buy_range"]["formula"]
    assert "估值锚" in result["prices"]["buy_range"]["note"]
