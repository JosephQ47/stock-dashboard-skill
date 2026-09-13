# -*- coding: utf-8 -*-
"""港股与美股取数。港股行情走腾讯，K 线与财务走 yfinance，美股财务可回查 SEC。"""
from __future__ import annotations

from datetime import datetime

import endpoints
from http_client import SourceDown


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _yf_symbol(norm):
    if norm["market"].value == "HK":
        return f"{int(norm['code']):04d}.HK"
    return norm["code"]


def fetch_quote(client, norm) -> dict:
    if norm["market"].value == "HK":
        try:
            r = client.get(endpoints.TENCENT_QUOTE.format(symbol=norm["tencent"]), source="tencent")
            parts = r.text.split("~")
            if len(parts) > 3:
                return {
                    "price": float(parts[3]),
                    "name": parts[1],
                    "source": "腾讯 qt.gtimg.cn",
                    "fetched_at": _now(),
                }
        except SourceDown:
            pass

    try:
        import yfinance as yf

        t = yf.Ticker(_yf_symbol(norm))
        hist = t.history(period="5d")
        if len(hist) == 0:
            raise SourceDown("yfinance 无行情返回")
        return {
            "price": float(hist["Close"].iloc[-1]),
            "name": _yf_symbol(norm),
            "source": "yfinance",
            "fetched_at": _now(),
        }
    except SourceDown:
        raise
    except Exception as exc:
        raise SourceDown(f"yfinance 连接失败: {type(exc).__name__}: {exc}") from exc


def fetch_kline(client, norm, days=250) -> dict:
    try:
        import yfinance as yf

        period = "2y" if days > 250 else "1y"
        hist = yf.Ticker(_yf_symbol(norm)).history(period=period)
        if len(hist) == 0:
            raise SourceDown("yfinance 无 K 线返回")
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "high": [float(v) for v in hist["High"]],
            "low": [float(v) for v in hist["Low"]],
            "close": [float(v) for v in hist["Close"]],
            "volume": [float(v) for v in hist["Volume"]],
            "source": "yfinance",
            "fetched_at": _now(),
        }
    except SourceDown:
        raise
    except Exception as exc:
        raise SourceDown(f"yfinance 连接失败: {type(exc).__name__}: {exc}") from exc


def fetch_financials(norm) -> dict:
    import yfinance as yf

    out = {"source": "yfinance", "fetched_at": _now(), "available": False}
    try:
        t = yf.Ticker(_yf_symbol(norm))
        bs = t.balance_sheet
        inc = t.income_stmt
        cf = t.cashflow
        out.update({
            "available": True,
            "balance_rows": int(bs.shape[0]),
            "income_rows": int(inc.shape[0]),
            "cashflow_rows": int(cf.shape[0]),
            "info_keys": sorted(list(t.info.keys()))[:20] if hasattr(t, "info") else [],
        })
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    return out
