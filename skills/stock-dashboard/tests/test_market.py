import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from market import Market, identify, normalize


def test_identify_shanghai():
    assert identify("600519") == Market.CN_SH


def test_identify_shenzhen_main():
    assert identify("000001") == Market.CN_SZ


def test_identify_chinext():
    assert identify("300750") == Market.CN_SZ


def test_identify_beijing():
    assert identify("830799") == Market.CN_BJ


def test_identify_hk_five_digit():
    assert identify("00700") == Market.HK


def test_identify_hk_with_prefix():
    assert identify("HK00700") == Market.HK


def test_identify_us():
    assert identify("AAPL") == Market.US


def test_identify_us_lowercase():
    assert identify("aapl") == Market.US


def test_identify_rejects_garbage():
    with pytest.raises(ValueError):
        identify("12")


def test_normalize_shanghai_fields():
    r = normalize("600519")
    assert r["code"] == "600519"
    assert r["market"] == Market.CN_SH
    assert r["tencent"] == "sh600519"
    assert r["baostock"] == "sh.600519"
    assert r["eastmoney_secid"] == "1.600519"
    assert r["currency"] == "CNY"


def test_normalize_shenzhen_fields():
    r = normalize("000001")
    assert r["tencent"] == "sz000001"
    assert r["baostock"] == "sz.000001"
    assert r["eastmoney_secid"] == "0.000001"


def test_normalize_hk_fields():
    r = normalize("00700")
    assert r["code"] == "00700"
    assert r["tencent"] == "hk00700"
    assert r["eastmoney_secid"] == "116.00700"
    assert r["currency"] == "HKD"


def test_normalize_us_fields():
    r = normalize("aapl")
    assert r["code"] == "AAPL"
    assert r["currency"] == "USD"


def test_normalize_keeps_raw():
    assert normalize("HK00700")["raw"] == "HK00700"
