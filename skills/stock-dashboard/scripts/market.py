# -*- coding: utf-8 -*-
"""市场识别与代码规范化。不联网，纯函数。"""
from __future__ import annotations

import re
from enum import Enum


class Market(str, Enum):
    CN_SH = "CN_SH"
    CN_SZ = "CN_SZ"
    CN_BJ = "CN_BJ"
    HK = "HK"
    US = "US"


CURRENCY = {
    Market.CN_SH: "CNY",
    Market.CN_SZ: "CNY",
    Market.CN_BJ: "CNY",
    Market.HK: "HKD",
    Market.US: "USD",
}

_RE_A = re.compile(r"^\d{6}$")
_RE_HK = re.compile(r"^\d{5}$")
_RE_US = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")


def _strip(code: str) -> str:
    c = code.strip().upper()
    for suf in (".SH", ".SZ", ".BJ", ".HK"):
        if c.endswith(suf) and len(c) > len(suf):
            rest = c[: -len(suf)]
            if rest.isdigit():
                return rest
    for p in ("HK.", "HK", "SH.", "SH", "SZ.", "SZ", "BJ.", "BJ"):
        if c.startswith(p) and len(c) > len(p):
            rest = c[len(p):]
            if rest.isdigit():
                return rest
    return c


def identify(code: str) -> Market:
    c = _strip(code)
    if _RE_A.match(c):
        head = c[0]
        if head == "6":
            return Market.CN_SH
        if head in ("0", "3"):
            return Market.CN_SZ
        if head in ("4", "8") or c.startswith("920"):
            return Market.CN_BJ
        raise ValueError(f"无法识别的 A 股代码: {code}")
    if _RE_HK.match(c):
        return Market.HK
    if _RE_US.match(c):
        return Market.US
    raise ValueError(f"无法识别的证券代码: {code}")


def normalize(code: str) -> dict:
    market = identify(code)
    c = _strip(code)
    if market == Market.CN_SH:
        tencent, bs, secid = f"sh{c}", f"sh.{c}", f"1.{c}"
    elif market in (Market.CN_SZ, Market.CN_BJ):
        prefix = "sz" if market == Market.CN_SZ else "bj"
        tencent, bs, secid = f"{prefix}{c}", f"{prefix}.{c}", f"0.{c}"
    elif market == Market.HK:
        tencent, bs, secid = f"hk{c}", "", f"116.{c}"
    else:
        tencent, bs, secid = "", "", ""
    return {
        "raw": code,
        "code": c,
        "market": market,
        "tencent": tencent,
        "baostock": bs,
        "eastmoney_secid": secid,
        "currency": CURRENCY[market],
    }
