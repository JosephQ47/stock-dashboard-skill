# -*- coding: utf-8 -*-
"""带限速、调用上限与熔断的 HTTP 客户端。

东财会按源 IP 整体限流，一旦连接被断开，本次运行内不再请求该源。
"""
from __future__ import annotations

import time

import requests

import endpoints


class SourceDown(Exception):
    """数据源当前不可用，调用方应走降级链。"""


class HttpClient:
    def __init__(self, sleeper=time.sleep):
        self._sleep = sleeper
        self._last_call: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._tripped: set[str] = set()

    def is_tripped(self, source: str) -> bool:
        return source in self._tripped

    def call_count(self, source: str) -> int:
        return self._counts.get(source, 0)

    def _interval(self, source: str) -> float:
        if source == "eastmoney":
            return endpoints.EM_MIN_INTERVAL
        return endpoints.DEFAULT_MIN_INTERVAL

    def _guard(self, source: str) -> None:
        if source in self._tripped:
            raise SourceDown(f"{source} 已熔断，本次运行内不再请求")
        if source == "eastmoney" and self._counts.get(source, 0) >= endpoints.EM_MAX_CALLS:
            self._tripped.add(source)
            raise SourceDown(f"eastmoney 达到本次运行调用上限 {endpoints.EM_MAX_CALLS}")
        last = self._last_call.get(source)
        if last is not None:
            self._sleep(self._interval(source))

    def _record(self, source: str) -> None:
        self._last_call[source] = time.monotonic()
        self._counts[source] = self._counts.get(source, 0) + 1

    def _finish(self, resp, source: str):
        if resp.status_code != 200:
            raise SourceDown(f"{source} 返回 HTTP {resp.status_code}")
        return resp

    def get(self, url, headers=None, timeout=12, source="generic"):
        self._guard(source)
        try:
            resp = requests.get(url, headers=headers or endpoints.UA, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            self._tripped.add(source)
            self._record(source)
            raise SourceDown(f"{source} 连接失败: {type(exc).__name__}") from exc
        self._record(source)
        return self._finish(resp, source)

    def post(self, url, data, headers=None, timeout=12, source="generic"):
        self._guard(source)
        try:
            resp = requests.post(
                url, data=data, headers=headers or endpoints.FORM_HEADERS, timeout=timeout
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            self._tripped.add(source)
            self._record(source)
            raise SourceDown(f"{source} 连接失败: {type(exc).__name__}") from exc
        self._record(source)
        return self._finish(resp, source)
