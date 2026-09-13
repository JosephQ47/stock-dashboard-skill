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


# 五项红旗当前在任何市场都拿不到数据源，与具体公司无关：不是这次抓取失败，是
# 流水线压根没接审计意见、股权质押、退市风险、立案调查、扣非净利润的数据源。
# 放在这里而不是让调用方自己猜，callers（未来的报告层）可以据此区分「结构性
# 拿不到」与「这家公司恰好干净」，不要把两者混为一谈。
STRUCTURALLY_UNAVAILABLE_FLAGS = {
    "RECURRING": "yfinance 利润表没有扣非净利润科目，与 A 股新浪源一样两个市场都拿不到",
    "AUDIT_OPINION": "当前流水线没有对接审计意见数据源",
    "PLEDGE": "当前流水线没有对接股权质押数据源",
    "DELISTING_RISK": "当前流水线没有对接退市风险预警数据源",
    "INVESTIGATION": "当前流水线没有对接立案调查公告数据源",
}


def _transpose_statement(df):
    """把 yfinance 的报表 DataFrame（行=科目名，列=各期期末日期）转成与
    sources_cn 相同的形状：新→旧排列、每期一个 dict、`报告日` 为 YYYYMMDD
    字符串。下游 compute.extract_derived 只认这一种形状，不应该为港股/美股
    再单独适配一套读取逻辑。

    不假设 yfinance 已经按时间降序排好列（虽然实测确实如此），显式按日期
    降序排序，让这个契约不依赖 yfinance 内部实现细节。
    """
    if df is None or df.empty:
        return []
    cols_sorted = sorted(df.columns, reverse=True)
    rows = []
    for col in cols_sorted:
        date_str = col.strftime("%Y%m%d") if hasattr(col, "strftime") else str(col)
        row = {"报告日": date_str}
        for field, value in df[col].items():
            row[field] = value
        rows.append(row)
    return rows


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
            "balance": _transpose_statement(bs),
            "income": _transpose_statement(inc),
            "cashflow": _transpose_statement(cf),
            "unavailable_checks": dict(STRUCTURALLY_UNAVAILABLE_FLAGS),
            "info_keys": sorted(list(t.info.keys()))[:20] if hasattr(t, "info") else [],
        })
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    return out
