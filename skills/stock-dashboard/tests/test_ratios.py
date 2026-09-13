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
    assert R.cash_to_profit(120, 100) == pytest.approx(Decimal("1.2"))


def test_cash_to_profit_zero_profit_returns_none():
    assert R.cash_to_profit(100, 0) is None


def test_accrual_ratio_formula():
    r = R.accrual_ratio(100, 60, 1000)
    assert r == pytest.approx(Decimal("0.04"))


def test_accrual_ratio_zero_assets_returns_none():
    assert R.accrual_ratio(100, 60, 0) is None


def test_receivable_gap():
    assert R.receivable_gap(30, 10) == pytest.approx(Decimal("20"))


def test_goodwill_ratio():
    assert R.goodwill_ratio(300, 1000) == pytest.approx(Decimal("0.3"))


def test_recurring_ratio():
    assert R.recurring_ratio(70, 100) == pytest.approx(Decimal("0.7"))


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
