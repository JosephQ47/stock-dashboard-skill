# -*- coding: utf-8 -*-
"""环境与数据源自检。首次使用或取数失败时先运行。

实测结论：数据源可用性随时间与 IP 状态变化，不能假设它们都在。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import endpoints
from http_client import HttpClient, SourceDown


def _row(name, ok, detail, critical=False):
    return {"name": name, "ok": bool(ok), "detail": str(detail), "critical": critical}


def check_interpreter() -> dict:
    exe = sys.executable
    in_venv = sys.prefix != sys.base_prefix
    ok = in_venv and "anaconda3" not in exe.lower()
    detail = exe if ok else f"{exe}（应使用 {endpoints.VENV_PYTHON}）"
    return _row("解释器", ok, detail, critical=True)


def check_imports() -> list[dict]:
    out = []
    for mod in ("requests", "akshare", "baostock", "yfinance"):
        try:
            m = __import__(mod)
            out.append(_row(f"import {mod}", True, getattr(m, "__version__", "已安装")))
        except Exception as exc:
            out.append(_row(f"import {mod}", False, f"{type(exc).__name__}"))
    return out


def check_network(client: HttpClient) -> dict:
    try:
        client.get(endpoints.TENCENT_QUOTE.format(symbol="sh600519"), source="tencent")
        return _row("网络连通", True, "可访问外网", critical=True)
    except SourceDown as exc:
        return _row("网络连通", False, f"{exc}。若在沙箱中运行，需放开网络权限", critical=True)


def check_sources(client: HttpClient) -> list[dict]:
    out = []

    def probe(name, source, fn):
        try:
            out.append(_row(name, True, fn()))
        except Exception as exc:
            detail = f"{type(exc).__name__}: {str(exc)[:60]}"
            if client.is_tripped(source):
                detail = f"{detail} (已熔断)"
            out.append(_row(name, False, detail))

    probe("腾讯 A股行情", "tencent", lambda: _tencent(client, "sh600519"))
    probe("腾讯 港股行情", "tencent", lambda: _tencent(client, "hk00700"))
    probe("baostock K线", "baostock", _baostock)
    probe("akshare 新浪三表", "sina", _akshare_statement)
    probe("yfinance 美股", "yahoo", _yfinance)
    probe("SEC submissions", "sec", lambda: _sec(client))
    probe("巨潮 公告", "cninfo", lambda: _cninfo(client))
    probe("东财 K线", "eastmoney", lambda: _eastmoney(client))
    return out


def _tencent(client, symbol):
    r = client.get(endpoints.TENCENT_QUOTE.format(symbol=symbol), source="tencent")
    parts = r.text.split("~")
    if len(parts) < 4:
        raise ValueError("返回格式异常")
    return f"{parts[1]} {parts[3]}"


def _baostock():
    import baostock as bs

    bs.login()
    try:
        rs = bs.query_history_k_data_plus(
            "sh.600519", "date,close", start_date="2026-08-01", frequency="d", adjustflag="2"
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    if not rows:
        raise ValueError("无数据返回")
    return f"{len(rows)} 行，末行 {rows[-1]}"


def _akshare_statement():
    import akshare as ak

    df = ak.stock_financial_report_sina(stock="sh600519", symbol="资产负债表")
    if df is None or len(df) == 0:
        raise ValueError("无数据返回")
    return f"{len(df)} 行"


def _yfinance():
    import yfinance as yf

    hist = yf.Ticker("AAPL").history(period="5d")
    if len(hist) == 0:
        raise ValueError("无数据返回")
    return f"{len(hist)} 行"


def _sec(client):
    r = client.get(
        endpoints.SEC_SUBMISSIONS.format(cik="0000320193"),
        headers=endpoints.SEC_UA,
        source="sec",
    )
    return f"{len(r.text)} 字节"


def _cninfo(client):
    r = client.post(
        endpoints.CNINFO_SEARCH, data={"keyWord": "600519", "maxNum": "5"}, source="cninfo"
    )
    return f"{len(r.text)} 字节"


def _eastmoney(client):
    url = endpoints.EM_KLINE.format(secid="1.600519", beg="20260801", end="20260913")
    r = client.get(url, source="eastmoney")
    klines = (r.json().get("data") or {}).get("klines") or []
    if not klines:
        raise ValueError("无 K 线返回")
    return f"{len(klines)} 根"


def run() -> dict:
    client = HttpClient()
    checks = [check_interpreter()]
    checks += check_imports()
    net = check_network(client)
    checks.append(net)
    if net["ok"]:
        checks += check_sources(client)
    usable = [c["name"] for c in checks if c["ok"] and not c.get("critical", False)]
    critical = [c for c in checks if c.get("critical", False) and not c["ok"]]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "usable_sources": usable,
        "ok": not critical,
    }


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="环境与数据源自检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    report = run()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"自检时间 {report['generated_at']}")
    print("-" * 62)
    for c in report["checks"]:
        mark = "可用" if c["ok"] else "失败"
        print(f"{c['name']:<20} {mark:<6} {c['detail']}")
    print("-" * 62)
    print(f"可用数据源 {len(report['usable_sources'])} 项")
    if not report["ok"]:
        print("关键项失败，先解决解释器或网络问题再取数")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
