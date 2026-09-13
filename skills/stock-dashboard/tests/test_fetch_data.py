import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_data as FD
import sources_cn


# ---- completeness()：0.30/0.40/0.30 加权与 0.70 地板 ----
# 纯函数，直接构造 payload dict 喂给它，不发起任何网络请求。

def test_completeness_all_present_is_full_weight():
    payload = {
        "quote": {"price": 1.0},
        "kline": {"close": [1.0]},
        "financials": {"available": True},
    }
    assert FD.completeness(payload) == 1.0


def test_completeness_missing_quote_drops_030():
    payload = {
        "quote": None,
        "kline": {"close": [1.0]},
        "financials": {"available": True},
    }
    assert FD.completeness(payload) == 0.70


def test_completeness_missing_kline_drops_040():
    payload = {
        "quote": {"price": 1.0},
        "kline": None,
        "financials": {"available": True},
    }
    assert FD.completeness(payload) == 0.60


def test_completeness_missing_financials_drops_030():
    payload = {
        "quote": {"price": 1.0},
        "kline": {"close": [1.0]},
        "financials": None,
    }
    assert FD.completeness(payload) == 0.70


def test_completeness_financials_present_but_unavailable_counts_as_missing():
    # financials 块存在但 available=False（比如 fetch_financials 内部捕获了
    # 异常，返回了 {"available": False, "reason": ...}）也必须按缺失计权，
    # 不能因为字典非空就误判为「拿到了」。
    payload = {
        "quote": {"price": 1.0},
        "kline": {"close": [1.0]},
        "financials": {"available": False, "reason": "接口异常"},
    }
    assert FD.completeness(payload) == 0.70


def test_completeness_only_kline_is_below_floor():
    payload = {"quote": None, "kline": {"close": [1.0]}, "financials": None}
    assert FD.completeness(payload) == 0.40
    assert FD.completeness(payload) < FD.COMPLETENESS_FLOOR


def test_completeness_quote_and_financials_without_kline_is_at_floor_boundary():
    # 0.30 + 0.30 = 0.60，仍低于 0.70 的阻断线——这条专门钉住「两项凑不出
    # 阻断线」的边界，防止有人把权重改错导致这种组合被误判为「够格」。
    payload = {
        "quote": {"price": 1.0},
        "kline": None,
        "financials": {"available": True},
    }
    assert FD.completeness(payload) == 0.60
    assert FD.completeness(payload) < FD.COMPLETENESS_FLOOR


def test_completeness_nothing_present_is_zero():
    assert FD.completeness({"quote": None, "kline": None, "financials": None}) == 0.0


# ---- fetch_one() 里独立于完备率地板的硬性阻断线：行情缺失或财务不可用 ----
# 一律阻断，即使加权完备率本身达到或超过 0.70。用 monkeypatch 替换掉
# sources_cn 里会联网的 fetch_quote/fetch_kline/fetch_financials/
# fetch_pe_history/fetch_market_extras，直接构造它们的返回值，不发起任何
# 真实请求。

def _patch_cn_sources(monkeypatch, quote=None, kline=None, financials=None):
    def _quote(client, norm):
        if quote is None:
            raise RuntimeError("no quote configured")
        return quote

    def _kline(client, norm, days=250):
        return kline or {"dates": ["20240101"], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0], "source": "东财", "fetched_at": "t"}

    def _financials(norm):
        return financials if financials is not None else {"available": True, "source": "akshare", "fetched_at": "t"}

    monkeypatch.setattr(sources_cn, "fetch_quote", _quote)
    monkeypatch.setattr(sources_cn, "fetch_kline", _kline)
    monkeypatch.setattr(sources_cn, "fetch_financials", _financials)
    monkeypatch.setattr(sources_cn, "fetch_pe_history", lambda norm: {"available": False, "source": "n/a", "fetched_at": "t"})
    monkeypatch.setattr(sources_cn, "fetch_market_extras", lambda client, norm: {"available": True, "source": "akshare", "fetched_at": "t"})


def test_blocked_when_quote_missing_even_if_completeness_would_pass(monkeypatch):
    # kline + financials 到手（权重 0.40+0.30=0.70，达到地板），但行情
    # (quote) 取数全失败——硬性阻断线必须独立于加权完备率生效。
    from http_client import SourceDown

    def _quote_fails(client, norm):
        raise SourceDown("行情源全挂")

    monkeypatch.setattr(sources_cn, "fetch_quote", _quote_fails)
    _patch_cn_sources(monkeypatch)  # 覆盖 kline/financials/pe_history/extras，quote 保留上面这条失败的
    monkeypatch.setattr(sources_cn, "fetch_quote", _quote_fails)

    payload = FD.fetch_one("600519")
    assert payload["completeness"] >= FD.COMPLETENESS_FLOOR
    assert payload["blocked"] is True
    assert any("行情缺失" in r for r in payload["block_reasons"])


def test_blocked_when_financials_unavailable_even_if_completeness_would_pass(monkeypatch):
    # quote + kline 到手（0.30+0.40=0.70，达到地板），但财务不可用——同样必须
    # 独立地被硬性阻断线挡下。
    _patch_cn_sources(
        monkeypatch,
        quote={"price": 1.0, "name": "贵州茅台", "source": "腾讯", "fetched_at": "t"},
        financials={"available": False, "reason": "接口异常", "source": "akshare", "fetched_at": "t"},
    )

    payload = FD.fetch_one("600519")
    assert payload["completeness"] >= FD.COMPLETENESS_FLOOR
    assert payload["blocked"] is True
    assert any("财务数据缺失" in r for r in payload["block_reasons"])


def test_not_blocked_when_quote_kline_financials_all_present(monkeypatch):
    _patch_cn_sources(
        monkeypatch,
        quote={"price": 1.0, "name": "贵州茅台", "source": "腾讯", "fetched_at": "t"},
    )
    payload = FD.fetch_one("600519")
    assert payload["blocked"] is False
    assert payload["block_reasons"] == []
