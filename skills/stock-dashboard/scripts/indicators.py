# -*- coding: utf-8 -*-
"""技术指标。纯函数，不联网，数据不足一律返回 None。

固定 8 个互补指标，不堆砌：MA20、MA60、MA120、RSI14、MACD、布林带、ATR14、成交量均线。
"""
from __future__ import annotations


def sma(values, period):
    if values is None or len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(float(v) for v in window) / period


def _ema_series(values, period):
    if values is None or len(values) < period or period <= 0:
        return None
    k = 2.0 / (period + 1)
    seed = sum(float(v) for v in values[:period]) / period
    out = [seed]
    for v in values[period:]:
        out.append(float(v) * k + out[-1] * (1 - k))
    return out


def ema(values, period):
    series = _ema_series(values, period)
    return series[-1] if series else None


def rsi(closes, period=14):
    if closes is None or len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = float(closes[i]) - float(closes[i - 1])
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1 + rs)


def macd(closes, fast=12, slow=26, signal=9):
    if closes is None or len(closes) < slow + signal:
        return None
    fast_s = _ema_series(closes, fast)
    slow_s = _ema_series(closes, slow)
    if not fast_s or not slow_s:
        return None
    offset = len(fast_s) - len(slow_s)
    diff = [fast_s[offset + i] - slow_s[i] for i in range(len(slow_s))]
    sig_s = _ema_series(diff, signal)
    if not sig_s:
        return None
    macd_v = diff[-1]
    signal_v = sig_s[-1]
    return {"macd": macd_v, "signal": signal_v, "hist": macd_v - signal_v}


def bollinger(closes, period=20, k=2.0):
    mid = sma(closes, period)
    if mid is None:
        return None
    window = [float(v) for v in closes[-period:]]
    var = sum((v - mid) ** 2 for v in window) / period
    sd = var ** 0.5
    upper = mid + k * sd
    lower = mid - k * sd
    width = upper - lower
    pct_b = 0.5 if width == 0 else (float(closes[-1]) - lower) / width
    return {"mid": mid, "upper": upper, "lower": lower, "pct_b": max(0.0, min(1.0, pct_b))}


def atr(highs, lows, closes, period=14):
    if not highs or not lows or not closes:
        return None
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        h, l, pc = float(highs[i]), float(lows[i]), float(closes[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def bias(close, ma):
    if not ma:
        return 0.0
    return (float(close) - float(ma)) / float(ma) * 100.0


def compute_all(ohlcv):
    close = ohlcv.get("close") or []
    high = ohlcv.get("high") or []
    low = ohlcv.get("low") or []
    volume = ohlcv.get("volume") or []
    ma5 = sma(close, 5)
    last = float(close[-1]) if close else 0.0
    return {
        "last_close": last,
        "ma5": ma5,
        "ma20": sma(close, 20),
        "ma60": sma(close, 60),
        "ma120": sma(close, 120),
        "rsi14": rsi(close, 14),
        "macd": macd(close),
        "boll": bollinger(close, 20),
        "atr14": atr(high, low, close, 14),
        "bias_ma5": bias(last, ma5) if ma5 else None,
        "vol_ma5": sma(volume, 5),
        "vol_ratio": (float(volume[-1]) / sma(volume, 5)) if volume and sma(volume, 5) else None,
    }
