import sys
from pathlib import Path
from decimal import Decimal
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ratios as R


def test_D_converts_number():
    assert R.D(1.5) == Decimal("1.5")


def test_D_none_returns_none():
    assert R.D(None) is None


def test_D_bad_string_returns_none():
    assert R.D("--") is None


def test_cash_to_profit_normal():
    assert R.cash_to_profit(120, 100) == Decimal("1.2")


def test_cash_to_profit_zero_profit_returns_none():
    assert R.cash_to_profit(100, 0) is None


def test_accrual_ratio_formula():
    r = R.accrual_ratio(100, 60, 1000)
    assert r == Decimal("0.04")


def test_accrual_ratio_zero_assets_returns_none():
    assert R.accrual_ratio(100, 60, 0) is None


def test_receivable_gap():
    assert R.receivable_gap(30, 10) == Decimal("20")


def test_goodwill_ratio():
    assert R.goodwill_ratio(300, 1000) == Decimal("0.3")


def test_recurring_ratio():
    assert R.recurring_ratio(70, 100) == Decimal("0.7")


def test_dupont_keys():
    d = R.dupont(100, 1000, 2000, 800)
    assert set(d) == {"net_margin", "asset_turnover", "equity_multiplier", "roe"}


def test_dupont_roe_is_product():
    d = R.dupont(100, 1000, 2000, 800)
    expected = d["net_margin"] * d["asset_turnover"] * d["equity_multiplier"]
    assert d["roe"] == pytest.approx(expected)


def test_dupont_zero_equity_safe():
    d = R.dupont(100, 1000, 2000, 0)
    assert d["roe"] is None


def _clean_fin():
    return {
        "cfo": 120, "net_profit": 100, "total_assets": 1000,
        "ar_growth": 8, "revenue_growth": 10,
        "goodwill": 50, "net_assets": 1000,
        "deducted_profit": 90,
        "cash": 100, "interest_bearing_debt": 80,
        "audit_opinion": "标准无保留意见",
        "pledge_ratio": 10,
        "delisting_risk": False,
        "under_investigation": False,
        "cash_to_profit_history": [1.1, 1.2],
    }


def test_clean_company_has_no_hits():
    flags = R.check_red_flags(_clean_fin())
    assert not any(f["hit"] for f in flags)


def test_flags_cover_all_codes():
    flags = R.check_red_flags(_clean_fin())
    codes = {f["code"] for f in flags}
    assert codes == {
        "CASH_PROFIT", "ACCRUAL", "RECEIVABLE", "GOODWILL", "RECURRING",
        "BIG_DEPOSIT_LOAN", "AUDIT_OPINION", "PLEDGE", "DELISTING_RISK", "INVESTIGATION",
    }


def test_low_cash_to_profit_hits():
    fin = _clean_fin()
    fin["cfo"] = 30
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["CASH_PROFIT"]["hit"]


def test_two_year_low_cash_to_profit_is_veto():
    fin = _clean_fin()
    fin["cash_to_profit_history"] = [0.4, 0.3]
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["CASH_PROFIT"]["veto"]


def test_receivable_outgrowing_revenue_hits():
    fin = _clean_fin()
    fin["ar_growth"] = 40
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["RECEIVABLE"]["hit"]


def test_high_goodwill_hits():
    fin = _clean_fin()
    fin["goodwill"] = 400
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["GOODWILL"]["hit"]


def test_low_recurring_ratio_hits():
    fin = _clean_fin()
    fin["deducted_profit"] = 40
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["RECURRING"]["hit"]


def test_big_deposit_loan_is_veto():
    fin = _clean_fin()
    fin["cash"] = 900
    fin["interest_bearing_debt"] = 800
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["BIG_DEPOSIT_LOAN"]["hit"]
    assert flags["BIG_DEPOSIT_LOAN"]["veto"]


def test_non_standard_audit_is_veto():
    fin = _clean_fin()
    fin["audit_opinion"] = "保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["AUDIT_OPINION"]["veto"]


def test_high_pledge_is_veto():
    fin = _clean_fin()
    fin["pledge_ratio"] = 60
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["PLEDGE"]["veto"]


def test_veto_triggered_true_when_any_veto():
    fin = _clean_fin()
    fin["under_investigation"] = True
    assert R.veto_triggered(R.check_red_flags(fin))


def test_veto_triggered_false_for_clean():
    assert not R.veto_triggered(R.check_red_flags(_clean_fin()))


def test_missing_data_does_not_hit():
    fin = _clean_fin()
    fin["cfo"] = None
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["CASH_PROFIT"]["hit"]
    assert "未获取到" in flags["CASH_PROFIT"]["detail"]


# 边界值测试：确保边界值本身不命中（所有比较都是严格的）
def test_cash_to_profit_boundary_0_7_does_not_hit():
    fin = _clean_fin()
    fin["cfo"] = 70
    fin["net_profit"] = 100
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["CASH_PROFIT"]["hit"]


def test_cash_to_profit_boundary_below_0_7_hits():
    fin = _clean_fin()
    fin["cfo"] = 69
    fin["net_profit"] = 100
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["CASH_PROFIT"]["hit"]


def test_accrual_boundary_0_10_does_not_hit():
    fin = _clean_fin()
    fin["net_profit"] = 200
    fin["cfo"] = 100
    fin["total_assets"] = 1000
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["ACCRUAL"]["hit"]


def test_accrual_boundary_above_0_10_hits():
    fin = _clean_fin()
    fin["net_profit"] = 191
    fin["cfo"] = 90
    fin["total_assets"] = 1000
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["ACCRUAL"]["hit"]


def test_receivable_boundary_20_does_not_hit():
    fin = _clean_fin()
    fin["ar_growth"] = 30
    fin["revenue_growth"] = 10
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["RECEIVABLE"]["hit"]


def test_receivable_boundary_above_20_hits():
    fin = _clean_fin()
    fin["ar_growth"] = 31
    fin["revenue_growth"] = 10
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["RECEIVABLE"]["hit"]


def test_goodwill_boundary_0_30_does_not_hit():
    fin = _clean_fin()
    fin["goodwill"] = 300
    fin["net_assets"] = 1000
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["GOODWILL"]["hit"]


def test_goodwill_boundary_above_0_30_hits():
    fin = _clean_fin()
    fin["goodwill"] = 301
    fin["net_assets"] = 1000
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["GOODWILL"]["hit"]


def test_recurring_boundary_0_70_does_not_hit():
    fin = _clean_fin()
    fin["deducted_profit"] = 70
    fin["net_profit"] = 100
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["RECURRING"]["hit"]


def test_recurring_boundary_below_0_70_hits():
    fin = _clean_fin()
    fin["deducted_profit"] = 69
    fin["net_profit"] = 100
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["RECURRING"]["hit"]


def test_pledge_boundary_50_does_not_hit():
    fin = _clean_fin()
    fin["pledge_ratio"] = 50
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["PLEDGE"]["hit"]
    assert not flags["PLEDGE"]["veto"]


def test_pledge_boundary_above_50_is_veto():
    fin = _clean_fin()
    fin["pledge_ratio"] = 51
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["PLEDGE"]["hit"]
    assert flags["PLEDGE"]["veto"]


# 缺失数据测试：所有十个标志
def test_cash_profit_missing_empty_string():
    fin = _clean_fin()
    fin["cfo"] = ""
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["CASH_PROFIT"]["hit"]
    assert "未获取到" in flags["CASH_PROFIT"]["detail"]


def test_cash_profit_missing_placeholder_dash():
    fin = _clean_fin()
    fin["cfo"] = "--"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["CASH_PROFIT"]["hit"]
    assert "未获取到" in flags["CASH_PROFIT"]["detail"]


def test_accrual_missing_empty_string():
    fin = _clean_fin()
    fin["cfo"] = ""
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["ACCRUAL"]["hit"]
    assert "未获取到" in flags["ACCRUAL"]["detail"]


def test_receivable_missing_na():
    fin = _clean_fin()
    fin["ar_growth"] = "N/A"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["RECEIVABLE"]["hit"]
    assert "未获取到" in flags["RECEIVABLE"]["detail"]


def test_goodwill_missing_nan():
    fin = _clean_fin()
    fin["goodwill"] = "nan"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["GOODWILL"]["hit"]
    assert "未获取到" in flags["GOODWILL"]["detail"]


def test_recurring_missing_none():
    fin = _clean_fin()
    fin["deducted_profit"] = "None"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["RECURRING"]["hit"]
    assert "未获取到" in flags["RECURRING"]["detail"]


def test_big_deposit_loan_missing_whitespace():
    fin = _clean_fin()
    fin["cash"] = "  "
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["BIG_DEPOSIT_LOAN"]["hit"]
    assert "未获取到" in flags["BIG_DEPOSIT_LOAN"]["detail"]


def test_audit_opinion_missing_empty_string_not_veto():
    """Empty audit_opinion should not trigger veto."""
    fin = _clean_fin()
    fin["audit_opinion"] = ""
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"]
    assert not flags["AUDIT_OPINION"]["veto"]
    assert "未获取到" in flags["AUDIT_OPINION"]["detail"]


def test_audit_opinion_missing_dash():
    fin = _clean_fin()
    fin["audit_opinion"] = "--"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"]
    assert not flags["AUDIT_OPINION"]["veto"]
    assert "未获取到" in flags["AUDIT_OPINION"]["detail"]


def test_audit_opinion_clean_variant_无保留意见():
    """'无保留意见' should not trigger veto."""
    fin = _clean_fin()
    fin["audit_opinion"] = "无保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"]
    assert not flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_clean_variant_无保留():
    """'无保留' alone should not trigger veto."""
    fin = _clean_fin()
    fin["audit_opinion"] = "无保留"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"]
    assert not flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_qualified_hits_and_vetos():
    """'保留意见' without '无保留' should trigger veto."""
    fin = _clean_fin()
    fin["audit_opinion"] = "保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["AUDIT_OPINION"]["hit"]
    assert flags["AUDIT_OPINION"]["veto"]


# 五种审计意见类型的完整测试
def test_audit_opinion_type1_标准无保留意见_is_clean():
    """Type 1: 标准无保留意见 - should NOT hit (clean opinion)."""
    fin = _clean_fin()
    fin["audit_opinion"] = "标准无保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"], "标准无保留意见 should be clean"
    assert not flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_type2_带强调事项段的无保留意见_is_clean():
    """Type 2: 带强调事项段的无保留意见 - should NOT hit (clean opinion with emphasis paragraph)."""
    fin = _clean_fin()
    fin["audit_opinion"] = "带强调事项段的无保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["AUDIT_OPINION"]["hit"], "带强调事项段的无保留意见 should be clean"
    assert not flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_type3_保留意见_is_qualified():
    """Type 3: 保留意见 - should HIT and VETO (qualified opinion)."""
    fin = _clean_fin()
    fin["audit_opinion"] = "保留意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["AUDIT_OPINION"]["hit"], "保留意见 should hit and veto"
    assert flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_type4_否定意见_is_severe():
    """Type 4: 否定意见 - should HIT and VETO (most severe, no 无保留)."""
    fin = _clean_fin()
    fin["audit_opinion"] = "否定意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["AUDIT_OPINION"]["hit"], "否定意见 should hit and veto"
    assert flags["AUDIT_OPINION"]["veto"]


def test_audit_opinion_type5_无法表示意见_is_severe():
    """Type 5: 无法表示意见 - should HIT and VETO (most severe, no 无保留)."""
    fin = _clean_fin()
    fin["audit_opinion"] = "无法表示意见"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["AUDIT_OPINION"]["hit"], "无法表示意见 should hit and veto"
    assert flags["AUDIT_OPINION"]["veto"]


def test_delisting_risk_missing_empty_string_not_veto():
    """Empty delisting_risk should not trigger veto."""
    fin = _clean_fin()
    fin["delisting_risk"] = ""
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["DELISTING_RISK"]["hit"]
    assert not flags["DELISTING_RISK"]["veto"]
    assert "未获取到" in flags["DELISTING_RISK"]["detail"]


def test_delisting_risk_string_false_not_hit():
    """String 'False' should parse as False (no hit)."""
    fin = _clean_fin()
    fin["delisting_risk"] = "False"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["DELISTING_RISK"]["hit"]
    assert not flags["DELISTING_RISK"]["veto"]


def test_delisting_risk_string_否_not_hit():
    """String '否' should parse as False (no hit)."""
    fin = _clean_fin()
    fin["delisting_risk"] = "否"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["DELISTING_RISK"]["hit"]
    assert not flags["DELISTING_RISK"]["veto"]


def test_delisting_risk_string_0_not_hit():
    """String '0' should parse as False (no hit)."""
    fin = _clean_fin()
    fin["delisting_risk"] = "0"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["DELISTING_RISK"]["hit"]
    assert not flags["DELISTING_RISK"]["veto"]


def test_delisting_risk_string_true_hits_and_vetos():
    """String 'true' should parse as True (hit + veto)."""
    fin = _clean_fin()
    fin["delisting_risk"] = "true"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["DELISTING_RISK"]["hit"]
    assert flags["DELISTING_RISK"]["veto"]


def test_investigation_missing_whitespace_not_veto():
    """Whitespace-only investigation should not trigger veto."""
    fin = _clean_fin()
    fin["under_investigation"] = "   "
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["INVESTIGATION"]["hit"]
    assert not flags["INVESTIGATION"]["veto"]
    assert "未获取到" in flags["INVESTIGATION"]["detail"]


def test_investigation_string_false_not_hit():
    """String 'False' should parse as False (no hit)."""
    fin = _clean_fin()
    fin["under_investigation"] = "False"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["INVESTIGATION"]["hit"]
    assert not flags["INVESTIGATION"]["veto"]


def test_investigation_string_yes_hits_and_vetos():
    """String 'yes' should parse as True (hit + veto)."""
    fin = _clean_fin()
    fin["under_investigation"] = "yes"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert flags["INVESTIGATION"]["hit"]
    assert flags["INVESTIGATION"]["veto"]


def test_pledge_missing_na():
    fin = _clean_fin()
    fin["pledge_ratio"] = "N/A"
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["PLEDGE"]["hit"]
    assert not flags["PLEDGE"]["veto"]
    assert "未获取到" in flags["PLEDGE"]["detail"]


# 零分母情况（值存在但为零）
def test_zero_denominator_accrual_not_missing():
    """Zero total_assets should report '总资产为零', not MISSING."""
    fin = _clean_fin()
    fin["total_assets"] = 0
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["ACCRUAL"]["hit"]
    assert "总资产为零" in flags["ACCRUAL"]["detail"]
    assert "未获取到" not in flags["ACCRUAL"]["detail"]


def test_zero_denominator_goodwill_not_missing():
    """Zero net_assets should report distinct detail, not MISSING."""
    fin = _clean_fin()
    fin["net_assets"] = 0
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["GOODWILL"]["hit"]
    assert "净资产为零" in flags["GOODWILL"]["detail"]
    assert "未获取到" not in flags["GOODWILL"]["detail"]


def test_zero_denominator_recurring_not_missing():
    """Zero net_profit should report distinct detail."""
    fin = _clean_fin()
    fin["net_profit"] = 0
    flags = {f["code"]: f for f in R.check_red_flags(fin)}
    assert not flags["RECURRING"]["hit"]
    assert "归母净利润为零" in flags["RECURRING"]["detail"]
    assert "未获取到" not in flags["RECURRING"]["detail"]
