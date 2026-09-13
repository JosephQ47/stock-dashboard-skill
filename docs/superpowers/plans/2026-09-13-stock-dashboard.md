# stock-dashboard 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Claude Code 与 Codex 双端通用的股票快速决策看板 skill，输入 1 到 3 只 A 股、港股或美股代码，输出带双轴评分、财报排雷、技术面判断和价位推导的 Markdown 看板。

**Architecture:** 三层分离。`scripts/` 负责联网取数与确定性计算，输出 JSON；`references/` 存放方法论与模板，供模型按需读取；`SKILL.md` 只写流程骨架与硬规则。脚本之间通过 JSON 文件通信，不共享内存对象。源码单份存放于项目内，两端通过 Windows 目录联接指向同一份。

**Tech Stack:** Python 3.12.4（项目专用 venv）、requests、akshare 1.18.94、baostock 0.9.3、yfinance 1.7.0、pytest 9.1.1。

## Global Constraints

- 解释器唯一入口：`D:\Economics\金融分析\.venv\Scripts\python.exe`。禁止写 `python`，因为系统 PATH 首位是 Anaconda base。
- 禁止向 Anaconda base（`D:\anaconda3`）安装任何包。
- SKILL.md 与所有 `references/` 文件中禁止出现宿主工具名（Read、Write、Edit、Bash、WebSearch 等），动作一律写成工具中性描述。
- SKILL.md 的 frontmatter 只含 `name` 与 `description` 两个字段。
- 东财接口全局限速 2 秒间隔，单次运行对东财请求总数上限 10 次；命中 ConnectionError 或 RemoteDisconnected 后本次运行不再请求东财。
- 巨潮接口必须用 POST 并带 `Content-Type: application/x-www-form-urlencoded`。
- SEC 接口必须带含姓名与邮箱的 User-Agent：`Robin Quan robin.quan@potentia.ai`。
- 所有数值计算使用 `decimal.Decimal`，禁止浮点直接比较。
- 每条数据必须带 `source` 与 `fetched_at` 字段。
- 北向资金日频买卖明细自 2024-08-19 起停止披露，任何输出中不得出现该字段。
- 脚本内部用 `Path(__file__).parent` 定位自身，不假设工作目录。
- 输出目录由命令行参数传入，不硬编码。
- 提交信息结尾加：`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

---

## 文件结构

```
skills/stock-dashboard/
├── SKILL.md                     # 触发条件、5 步流程、硬规则、错误处理
├── requirements.txt             # 锁定依赖版本
├── install.ps1                  # 两端创建目录联接
├── references/
│   ├── data-sources.md          # 数据源优先级、降级链、可靠性分档
│   ├── scoring.md               # 双轴评分卡的维度、指标、给分规则
│   ├── fundamentals.md          # 财报红旗表、勾稽校验、估值分位口径
│   ├── technicals.md            # 8 个指标定义与解读规则
│   ├── market-cn.md             # A 股特有项
│   ├── market-hk-us.md          # 港股美股差异
│   └── output-template.md       # 看板模板
├── scripts/
│   ├── endpoints.py             # 接口 URL、限速常量、解释器路径
│   ├── market.py                # 市场识别与代码规范化
│   ├── http_client.py           # 带限速与熔断的 HTTP 客户端
│   ├── doctor.py                # 环境与数据源自检
│   ├── sources_cn.py            # A 股取数
│   ├── sources_hk_us.py         # 港股美股取数
│   ├── fetch_data.py            # 统一取数入口
│   ├── indicators.py            # 技术指标计算
│   ├── ratios.py                # 财务比率与红旗判定
│   ├── scoring.py               # 双轴评分与矩阵映射
│   ├── pricing.py               # 三价位推导
│   ├── compute.py               # 计算总入口
│   └── selfcheck.py             # 报告抽检
└── tests/
    ├── test_market.py
    ├── test_http_client.py
    ├── test_indicators.py
    ├── test_ratios.py
    ├── test_scoring.py
    ├── test_pricing.py
    └── fixtures/                # 离线测试数据
```

职责边界：`market.py` 只做代码识别不联网；`http_client.py` 只管请求策略不懂业务；`sources_*.py` 只管取数不做计算；`indicators.py`、`ratios.py`、`scoring.py`、`pricing.py` 都是纯函数，吃 JSON 吐 JSON，不联网，因此可完全离线单测。

---

## Task 1: 项目骨架与市场识别

**Files:**
- Create: `skills/stock-dashboard/scripts/market.py`
- Create: `skills/stock-dashboard/tests/test_market.py`
- Create: `skills/stock-dashboard/requirements.txt`
- Create: `skills/stock-dashboard/tests/__init__.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Market`：枚举，取值 `CN_SH`、`CN_SZ`、`CN_BJ`、`HK`、`US`
  - `identify(code: str) -> Market`：识别市场，无法识别抛 `ValueError`
  - `normalize(code: str) -> dict`：返回 `{"raw": str, "code": str, "market": Market, "tencent": str, "baostock": str, "eastmoney_secid": str, "currency": str}`

- [ ] **Step 1: 创建 requirements.txt**

```
akshare==1.18.94
baostock==0.9.3
yfinance==1.7.0
requests==2.34.2
pytest==9.1.1
```

- [ ] **Step 2: 创建空的 tests/__init__.py**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
mkdir -p scripts tests references
touch tests/__init__.py
```

- [ ] **Step 3: 写失败的测试**

创建 `tests/test_market.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_market.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'market'`

- [ ] **Step 5: 实现 market.py**

```python
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
        if head in ("4", "8"):
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
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_market.py -v
```

Expected: 14 passed

- [ ] **Step 7: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/market.py skills/stock-dashboard/tests/ skills/stock-dashboard/requirements.txt
git commit -m "feat: 市场识别与代码规范化

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: 带限速与熔断的 HTTP 客户端

**Files:**
- Create: `skills/stock-dashboard/scripts/endpoints.py`
- Create: `skills/stock-dashboard/scripts/http_client.py`
- Create: `skills/stock-dashboard/tests/test_http_client.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `endpoints.VENV_PYTHON`：venv 解释器绝对路径字符串
  - `endpoints.UA`、`endpoints.SEC_UA`：请求头字典
  - `endpoints.TENCENT_QUOTE`、`EM_KLINE`、`EM_QUOTE`、`EM_DATACENTER`、`CNINFO_SEARCH`、`CNINFO_ANNOUNCE`、`SEC_SUBMISSIONS`、`SEC_CONCEPT`：URL 模板字符串
  - `endpoints.EM_MIN_INTERVAL = 2.0`、`EM_MAX_CALLS = 10`
  - `http_client.SourceDown`：异常类
  - `http_client.HttpClient(sleeper=time.sleep)`：类，方法 `get(url, headers=None, timeout=12, source="generic") -> requests.Response`、`post(url, data, headers=None, timeout=12, source="generic") -> requests.Response`
  - `HttpClient.is_tripped(source: str) -> bool`
  - `HttpClient.call_count(source: str) -> int`

- [ ] **Step 1: 写 endpoints.py**

```python
# -*- coding: utf-8 -*-
"""接口地址、请求头与限速常量的唯一来源。"""

VENV_PYTHON = r"D:\Economics\金融分析\.venv\Scripts\python.exe"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
SEC_UA = {"User-Agent": "Robin Quan robin.quan@potentia.ai"}
FORM_HEADERS = dict(UA, **{"Content-Type": "application/x-www-form-urlencoded"})

TENCENT_QUOTE = "https://qt.gtimg.cn/q={symbol}"
EM_QUOTE = "https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f57,f58,f162,f167,f116,f117"
EM_KLINE = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    "?secid={secid}&klt=101&fqt=1&beg={beg}&end={end}"
    "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57"
)
EM_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"
CNINFO_SEARCH = "http://www.cninfo.com.cn/new/information/topSearch/query"
CNINFO_ANNOUNCE = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"

EM_MIN_INTERVAL = 2.0
EM_MAX_CALLS = 10
DEFAULT_MIN_INTERVAL = 1.0
```

- [ ] **Step 2: 写失败的测试**

创建 `tests/test_http_client.py`：

```python
import sys
from pathlib import Path
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from http_client import HttpClient, SourceDown
import endpoints


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"text": self.text}


def make_client(monkeypatch, behavior):
    """behavior 是一个函数，接收调用序号返回 FakeResponse 或抛异常。"""
    slept = []
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        return behavior(calls["n"])

    monkeypatch.setattr(requests, "get", fake_get)
    client = HttpClient(sleeper=slept.append)
    return client, slept, calls


def test_get_returns_response(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    r = client.get("http://x", source="tencent")
    assert r.status_code == 200


def test_eastmoney_sleeps_two_seconds_between_calls(monkeypatch):
    client, slept, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="eastmoney")
    client.get("http://x", source="eastmoney")
    assert slept and slept[-1] == pytest.approx(endpoints.EM_MIN_INTERVAL)


def test_first_call_does_not_sleep(monkeypatch):
    client, slept, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="eastmoney")
    assert slept == []


def test_eastmoney_call_cap_enforced(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    for _ in range(endpoints.EM_MAX_CALLS):
        client.get("http://x", source="eastmoney")
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")


def test_connection_error_trips_breaker(monkeypatch):
    def behavior(n):
        raise requests.ConnectionError("closed")

    client, _, _ = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert client.is_tripped("eastmoney")


def test_tripped_source_refuses_without_network_call(monkeypatch):
    def behavior(n):
        raise requests.ConnectionError("closed")

    client, _, calls = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    before = calls["n"]
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert calls["n"] == before


def test_breaker_is_per_source(monkeypatch):
    def behavior(n):
        if n == 1:
            raise requests.ConnectionError("closed")
        return FakeResponse()

    client, _, _ = make_client(monkeypatch, behavior)
    with pytest.raises(SourceDown):
        client.get("http://x", source="eastmoney")
    assert client.get("http://y", source="tencent").status_code == 200


def test_non_200_raises_sourcedown(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse(status_code=500))
    with pytest.raises(SourceDown):
        client.get("http://x", source="cninfo")


def test_call_count_tracks_per_source(monkeypatch):
    client, _, _ = make_client(monkeypatch, lambda n: FakeResponse())
    client.get("http://x", source="tencent")
    client.get("http://x", source="tencent")
    assert client.call_count("tencent") == 2
    assert client.call_count("eastmoney") == 0
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_http_client.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'http_client'`

- [ ] **Step 4: 实现 http_client.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_http_client.py -v
```

Expected: 9 passed

- [ ] **Step 6: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/endpoints.py skills/stock-dashboard/scripts/http_client.py skills/stock-dashboard/tests/test_http_client.py
git commit -m "feat: 带限速与熔断的 HTTP 客户端

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: 环境与数据源自检

**Files:**
- Create: `skills/stock-dashboard/scripts/doctor.py`

**Interfaces:**
- Consumes: `endpoints`、`http_client.HttpClient`、`http_client.SourceDown`
- Produces:
  - `doctor.check_interpreter() -> dict`：`{"name": str, "ok": bool, "detail": str}`
  - `doctor.check_imports() -> list[dict]`
  - `doctor.check_network() -> dict`
  - `doctor.check_sources() -> list[dict]`
  - `doctor.run() -> dict`：`{"generated_at": str, "checks": list[dict], "usable_sources": list[str], "ok": bool}`
  - 命令行：`python scripts/doctor.py [--json]`

- [ ] **Step 1: 实现 doctor.py**

```python
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


def _row(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": str(detail)}


def check_interpreter() -> dict:
    exe = sys.executable
    in_venv = sys.prefix != sys.base_prefix
    ok = in_venv and "anaconda3" not in exe.lower()
    detail = exe if ok else f"{exe}（应使用 {endpoints.VENV_PYTHON}）"
    return _row("解释器", ok, detail)


def check_imports() -> list[dict]:
    out = []
    for mod in ("requests", "akshare", "baostock", "yfinance"):
        try:
            m = __import__(mod)
            out.append(_row(f"import {mod}", True, getattr(m, "__version__", "已安装")))
        except Exception as exc:
            out.append(_row(f"import {mod}", False, f"{type(exc).__name__}"))
    return out


def check_network() -> dict:
    client = HttpClient()
    try:
        client.get(endpoints.TENCENT_QUOTE.format(symbol="sh600519"), source="tencent")
        return _row("网络连通", True, "可访问外网")
    except SourceDown as exc:
        return _row("网络连通", False, f"{exc}。若在沙箱中运行，需放开网络权限")


def check_sources() -> list[dict]:
    client = HttpClient()
    out = []

    def probe(name, source, fn):
        try:
            out.append(_row(name, True, fn()))
        except Exception as exc:
            out.append(_row(name, False, f"{type(exc).__name__}: {str(exc)[:60]}"))

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
    checks = [check_interpreter()]
    checks += check_imports()
    net = check_network()
    checks.append(net)
    if net["ok"]:
        checks += check_sources()
    usable = [c["name"] for c in checks if c["ok"] and c["name"] not in ("解释器", "网络连通")]
    critical = [c for c in checks if c["name"] in ("解释器", "网络连通") and not c["ok"]]
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
```

- [ ] **Step 2: 实跑自检**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/doctor.py
```

Expected: 打印表格。解释器与网络连通为「可用」。腾讯、baostock、akshare 新浪源、yfinance、SEC、巨潮预期可用；东财可能失败，这是已知状态，不算 bug。

- [ ] **Step 3: 验证 JSON 模式**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/doctor.py --json
```

Expected: 合法 JSON，含 `checks`、`usable_sources`、`ok` 三个键。

- [ ] **Step 4: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/doctor.py
git commit -m "feat: 环境与数据源自检脚本

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: 技术指标计算

**Files:**
- Create: `skills/stock-dashboard/scripts/indicators.py`
- Create: `skills/stock-dashboard/tests/test_indicators.py`

**Interfaces:**
- Consumes: 无
- Produces（全部接受 `list[float]` 返回 `float` 或 `list[float]`，数据不足时返回 `None`）：
  - `sma(values, period) -> float | None`
  - `ema(values, period) -> float | None`
  - `rsi(closes, period=14) -> float | None`
  - `macd(closes, fast=12, slow=26, signal=9) -> dict | None`：`{"macd": float, "signal": float, "hist": float}`
  - `bollinger(closes, period=20, k=2.0) -> dict | None`：`{"mid": float, "upper": float, "lower": float, "pct_b": float}`
  - `atr(highs, lows, closes, period=14) -> float | None`
  - `bias(close, ma) -> float`：乖离率百分比
  - `compute_all(ohlcv: dict) -> dict`：输入 `{"high": [...], "low": [...], "close": [...], "volume": [...]}`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_indicators.py`：

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import indicators as ind


def test_sma_basic():
    assert ind.sma([1, 2, 3, 4, 5], 5) == pytest.approx(3.0)


def test_sma_uses_last_n():
    assert ind.sma([10, 10, 1, 2, 3], 3) == pytest.approx(2.0)


def test_sma_insufficient_returns_none():
    assert ind.sma([1, 2], 5) is None


def test_ema_equals_sma_at_seed():
    assert ind.ema([2, 2, 2, 2, 2], 5) == pytest.approx(2.0)


def test_ema_weights_recent_more():
    # 必须用凸增序列。对严格线性序列，收敛 EMA 与同窗 SMA 的滞后量
    # 同为 (period-1)/2，两者恒等，ema > sma 在数学上不成立。
    convex = [float(i) ** 1.3 for i in range(1, 21)]
    assert ind.ema(convex, 5) > ind.sma(convex, 5)


def test_ema_equals_sma_on_linear_series():
    rising = list(range(1, 21))
    assert ind.ema(rising, 5) == pytest.approx(ind.sma(rising, 5))


def test_rsi_all_gains_is_100():
    assert ind.rsi(list(range(1, 30)), 14) == pytest.approx(100.0)


def test_rsi_all_losses_is_zero():
    assert ind.rsi(list(range(30, 1, -1)), 14) == pytest.approx(0.0)


def test_rsi_flat_series_is_neutral():
    # 一字板与停牌会产生完全走平的序列。涨跌幅均为 0 时必须返回中性 50，
    # 不能因为 avg_loss 为 0 就判成 100，否则动量维度会给一只毫无动能的票满分。
    assert ind.rsi([10.0] * 30, 14) == pytest.approx(50.0)


def test_rsi_insufficient_returns_none():
    assert ind.rsi([1, 2, 3], 14) is None


def test_macd_returns_three_keys():
    closes = [float(i) for i in range(1, 60)]
    r = ind.macd(closes)
    assert set(r) == {"macd", "signal", "hist"}


def test_macd_hist_is_difference():
    closes = [float(i) for i in range(1, 60)]
    r = ind.macd(closes)
    assert r["hist"] == pytest.approx(r["macd"] - r["signal"])


def test_macd_positive_in_uptrend():
    closes = [float(i) for i in range(1, 60)]
    assert ind.macd(closes)["macd"] > 0


def test_bollinger_mid_is_sma():
    closes = [10.0] * 20
    r = ind.bollinger(closes, 20)
    assert r["mid"] == pytest.approx(10.0)


def test_bollinger_flat_series_has_zero_width():
    r = ind.bollinger([10.0] * 20, 20)
    assert r["upper"] == pytest.approx(r["lower"])


def test_bollinger_pct_b_at_upper_is_one():
    closes = [10.0] * 19 + [10.0]
    r = ind.bollinger(closes, 20)
    assert 0.0 <= r["pct_b"] <= 1.0


def test_atr_constant_range():
    highs = [11.0] * 20
    lows = [9.0] * 20
    closes = [10.0] * 20
    assert ind.atr(highs, lows, closes, 14) == pytest.approx(2.0)


def test_atr_insufficient_returns_none():
    assert ind.atr([1], [1], [1], 14) is None


def test_bias_positive_above_ma():
    assert ind.bias(110.0, 100.0) == pytest.approx(10.0)


def test_bias_negative_below_ma():
    assert ind.bias(90.0, 100.0) == pytest.approx(-10.0)


def test_bias_zero_ma_returns_zero():
    assert ind.bias(100.0, 0.0) == 0.0


def test_compute_all_returns_expected_keys():
    n = 150
    data = {
        "high": [100.0 + i * 0.1 for i in range(n)],
        "low": [99.0 + i * 0.1 for i in range(n)],
        "close": [99.5 + i * 0.1 for i in range(n)],
        "volume": [1000.0] * n,
    }
    r = ind.compute_all(data)
    for k in ("ma20", "ma60", "ma120", "rsi14", "macd", "boll", "atr14", "bias_ma5", "vol_ma5"):
        assert k in r


def test_compute_all_handles_short_series():
    data = {"high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}
    r = ind.compute_all(data)
    assert r["ma120"] is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_indicators.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'indicators'`

- [ ] **Step 3: 实现 indicators.py**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_indicators.py -v
```

Expected: 21 passed

- [ ] **Step 5: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/indicators.py skills/stock-dashboard/tests/test_indicators.py
git commit -m "feat: 技术指标计算

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: 财务比率与红旗判定

**Files:**
- Create: `skills/stock-dashboard/scripts/ratios.py`
- Create: `skills/stock-dashboard/tests/test_ratios.py`

**Interfaces:**
- Consumes: 无
- Produces：
  - `ratios.D(x) -> Decimal | None`：安全转 Decimal
  - `ratios.cash_to_profit(cfo, net_profit) -> Decimal | None`：净现比
  - `ratios.accrual_ratio(net_profit, cfo, total_assets) -> Decimal | None`
  - `ratios.receivable_gap(ar_growth, revenue_growth) -> Decimal | None`
  - `ratios.goodwill_ratio(goodwill, net_assets) -> Decimal | None`
  - `ratios.recurring_ratio(deducted_profit, net_profit) -> Decimal | None`
  - `ratios.dupont(net_profit, revenue, total_assets, equity) -> dict`
  - `ratios.check_red_flags(fin: dict) -> list[dict]`：返回 `[{"code": str, "name": str, "hit": bool, "detail": str, "veto": bool}]`
  - `ratios.veto_triggered(flags) -> bool`

红旗代码固定为：`CASH_PROFIT`、`ACCRUAL`、`RECEIVABLE`、`GOODWILL`、`RECURRING`、`BIG_DEPOSIT_LOAN`、`AUDIT_OPINION`、`PLEDGE`、`DELISTING_RISK`、`INVESTIGATION`。

否决项（`veto=True`）：`AUDIT_OPINION`、`INVESTIGATION`、`DELISTING_RISK`、`BIG_DEPOSIT_LOAN`、`PLEDGE`，以及连续两年净现比低于 0.5 的 `CASH_PROFIT`。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_ratios.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_ratios.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'ratios'`

- [ ] **Step 3: 实现 ratios.py**

```python
# -*- coding: utf-8 -*-
"""财务比率与红旗判定。全部用 Decimal，禁止浮点直接比较。

数据缺失一律不判红旗，detail 写「未获取到」，不得推测填充。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

MISSING = "未获取到"


def D(x):
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _div(a, b):
    a, b = D(a), D(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def cash_to_profit(cfo, net_profit):
    return _div(cfo, net_profit)


def accrual_ratio(net_profit, cfo, total_assets):
    np_, cfo_, ta = D(net_profit), D(cfo), D(total_assets)
    if np_ is None or cfo_ is None or ta is None or ta == 0:
        return None
    return (np_ - cfo_) / ta


def receivable_gap(ar_growth, revenue_growth):
    a, b = D(ar_growth), D(revenue_growth)
    if a is None or b is None:
        return None
    return a - b


def goodwill_ratio(goodwill, net_assets):
    return _div(goodwill, net_assets)


def recurring_ratio(deducted_profit, net_profit):
    return _div(deducted_profit, net_profit)


def dupont(net_profit, revenue, total_assets, equity):
    nm = _div(net_profit, revenue)
    at = _div(revenue, total_assets)
    em = _div(total_assets, equity)
    roe = None if (nm is None or at is None or em is None) else nm * at * em
    return {"net_margin": nm, "asset_turnover": at, "equity_multiplier": em, "roe": roe}


def _flag(code, name, hit, detail, veto=False):
    return {"code": code, "name": name, "hit": bool(hit), "detail": detail, "veto": bool(veto)}


def check_red_flags(fin: dict) -> list[dict]:
    out = []

    ctp = cash_to_profit(fin.get("cfo"), fin.get("net_profit"))
    history = [D(v) for v in (fin.get("cash_to_profit_history") or [])]
    history = [v for v in history if v is not None]
    two_year_low = len(history) >= 2 and all(v < Decimal("0.5") for v in history[-2:])
    if ctp is None:
        out.append(_flag("CASH_PROFIT", "净现比", False, MISSING))
    else:
        hit = ctp < Decimal("0.7")
        detail = f"净现比 {ctp:.2f}" + ("，连续两年低于 0.5" if two_year_low else "")
        out.append(_flag("CASH_PROFIT", "净现比", hit, detail, veto=two_year_low))

    ar = accrual_ratio(fin.get("net_profit"), fin.get("cfo"), fin.get("total_assets"))
    if ar is None:
        out.append(_flag("ACCRUAL", "总应计比率", False, MISSING))
    else:
        out.append(_flag("ACCRUAL", "总应计比率", ar > Decimal("0.10"), f"应计比率 {ar:.3f}"))

    gap = receivable_gap(fin.get("ar_growth"), fin.get("revenue_growth"))
    if gap is None:
        out.append(_flag("RECEIVABLE", "应收增速超营收", False, MISSING))
    else:
        out.append(_flag("RECEIVABLE", "应收增速超营收", gap > Decimal("20"),
                         f"应收增速快于营收 {gap:.1f} 个百分点"))

    gw = goodwill_ratio(fin.get("goodwill"), fin.get("net_assets"))
    if gw is None:
        out.append(_flag("GOODWILL", "商誉占净资产", False, MISSING))
    else:
        out.append(_flag("GOODWILL", "商誉占净资产", gw > Decimal("0.30"), f"商誉占比 {gw:.1%}"))

    rec = recurring_ratio(fin.get("deducted_profit"), fin.get("net_profit"))
    if rec is None:
        out.append(_flag("RECURRING", "扣非占归母", False, MISSING))
    else:
        out.append(_flag("RECURRING", "扣非占归母", rec < Decimal("0.70"), f"扣非占比 {rec:.1%}"))

    cash, debt = D(fin.get("cash")), D(fin.get("interest_bearing_debt"))
    ta = D(fin.get("total_assets"))
    if cash is None or debt is None or ta is None or ta == 0:
        out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", False, MISSING))
    else:
        hit = cash / ta > Decimal("0.30") and debt / ta > Decimal("0.30")
        out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", hit,
                         f"货币资金占比 {cash / ta:.1%}，有息负债占比 {debt / ta:.1%}", veto=hit))

    opinion = fin.get("audit_opinion")
    if opinion is None:
        out.append(_flag("AUDIT_OPINION", "审计意见", False, MISSING))
    else:
        hit = "标准无保留" not in str(opinion)
        out.append(_flag("AUDIT_OPINION", "审计意见", hit, str(opinion), veto=hit))

    pledge = D(fin.get("pledge_ratio"))
    if pledge is None:
        out.append(_flag("PLEDGE", "股权质押", False, MISSING))
    else:
        hit = pledge > Decimal("50")
        out.append(_flag("PLEDGE", "股权质押", hit, f"质押比例 {pledge:.1f}%", veto=hit))

    dr = fin.get("delisting_risk")
    if dr is None:
        out.append(_flag("DELISTING_RISK", "退市风险", False, MISSING))
    else:
        out.append(_flag("DELISTING_RISK", "退市风险", bool(dr),
                         "存在退市风险" if dr else "无", veto=bool(dr)))

    inv = fin.get("under_investigation")
    if inv is None:
        out.append(_flag("INVESTIGATION", "立案调查", False, MISSING))
    else:
        out.append(_flag("INVESTIGATION", "立案调查", bool(inv),
                         "存在立案调查" if inv else "无", veto=bool(inv)))

    return out


def veto_triggered(flags) -> bool:
    return any(f["veto"] for f in flags)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_ratios.py -v
```

Expected: 26 passed

- [ ] **Step 5: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/ratios.py skills/stock-dashboard/tests/test_ratios.py
git commit -m "feat: 财务比率与红旗判定

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: 双轴评分与矩阵映射

**Files:**
- Create: `skills/stock-dashboard/scripts/scoring.py`
- Create: `skills/stock-dashboard/tests/test_scoring.py`

**Interfaces:**
- Consumes: `ratios.veto_triggered`
- Produces：
  - `scoring.QUALITY_WEIGHTS`：`{"statement": 30, "profitability": 25, "health": 15, "moat": 15, "valuation": 15}`
  - `scoring.TIMING_WEIGHTS`：`{"trend": 30, "momentum": 25, "volume": 20, "position": 15, "catalyst": 10}`
  - `scoring.VETO_CAP = 40`
  - `scoring.quality_score(dims: dict) -> dict`：`{"score": float, "breakdown": dict, "missing": list[str]}`
  - `scoring.timing_score(dims: dict) -> dict`
  - `scoring.map_matrix(q: float, t: float, veto: bool) -> dict`：`{"verdict": str, "conflict": str | None}`
  - `scoring.apply_veto(q: float, veto: bool) -> float`

判定文案固定为：`重点关注，可建仓`、`加入候选池，等技术面转好`、`短线博弈，不是投资`、`回避`。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_scoring.py`：

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import scoring as S


def test_quality_weights_sum_to_100():
    assert sum(S.QUALITY_WEIGHTS.values()) == 100


def test_timing_weights_sum_to_100():
    assert sum(S.TIMING_WEIGHTS.values()) == 100


def test_quality_all_full_marks_is_100():
    dims = {k: 100 for k in S.QUALITY_WEIGHTS}
    assert S.quality_score(dims)["score"] == pytest.approx(100.0)


def test_quality_all_zero_is_zero():
    dims = {k: 0 for k in S.QUALITY_WEIGHTS}
    assert S.quality_score(dims)["score"] == pytest.approx(0.0)


def test_quality_weighted_correctly():
    dims = {k: 0 for k in S.QUALITY_WEIGHTS}
    dims["statement"] = 100
    assert S.quality_score(dims)["score"] == pytest.approx(30.0)


def test_quality_missing_dim_renormalizes():
    dims = {"statement": 100, "profitability": 100}
    r = S.quality_score(dims)
    assert r["score"] == pytest.approx(100.0)
    assert set(r["missing"]) == {"health", "moat", "valuation"}


def test_quality_all_missing_returns_zero_and_lists_all():
    r = S.quality_score({})
    assert r["score"] == 0.0
    assert len(r["missing"]) == len(S.QUALITY_WEIGHTS)


def test_quality_breakdown_has_contributions():
    dims = {k: 50 for k in S.QUALITY_WEIGHTS}
    r = S.quality_score(dims)
    assert r["breakdown"]["statement"] == pytest.approx(15.0)


def test_timing_weighted_correctly():
    dims = {k: 0 for k in S.TIMING_WEIGHTS}
    dims["trend"] = 100
    assert S.timing_score(dims)["score"] == pytest.approx(30.0)


def test_apply_veto_caps_quality():
    assert S.apply_veto(88.0, True) == S.VETO_CAP


def test_apply_veto_keeps_low_score():
    assert S.apply_veto(20.0, True) == 20.0


def test_apply_veto_noop_when_clean():
    assert S.apply_veto(88.0, False) == 88.0


def test_matrix_high_high():
    assert S.map_matrix(80, 80, False)["verdict"] == "重点关注，可建仓"


def test_matrix_high_low():
    assert S.map_matrix(80, 40, False)["verdict"] == "加入候选池，等技术面转好"


def test_matrix_mid_high_is_speculation():
    assert S.map_matrix(50, 80, False)["verdict"] == "短线博弈，不是投资"


def test_matrix_low_high_is_avoid():
    assert S.map_matrix(40, 80, False)["verdict"] == "回避"


def test_matrix_low_low():
    assert S.map_matrix(30, 30, False)["verdict"] == "回避"


def test_veto_forces_avoid_regardless():
    assert S.map_matrix(95, 95, True)["verdict"] == "回避"


def test_conflict_reported_when_quality_high_timing_low():
    r = S.map_matrix(80, 40, False)
    assert r["conflict"] and "基本面" in r["conflict"]


def test_conflict_reported_when_timing_high_quality_low():
    r = S.map_matrix(40, 80, False)
    assert r["conflict"] and "技术面" in r["conflict"]


def test_no_conflict_when_aligned():
    assert S.map_matrix(80, 80, False)["conflict"] is None


def test_boundary_sixty_counts_as_high():
    assert S.map_matrix(60, 60, False)["verdict"] == "重点关注，可建仓"


def test_boundary_fortyfive_is_speculation_not_avoid():
    assert S.map_matrix(45, 70, False)["verdict"] == "短线博弈，不是投资"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_scoring.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'scoring'`

- [ ] **Step 3: 实现 scoring.py**

```python
# -*- coding: utf-8 -*-
"""双轴评分与矩阵映射。

Q 轴回答「值不值得拿」，T 轴回答「现在是不是时候」。
两轴不合并成单一数字，矛盾时必须显式报出，不允许调和成模糊的持有。
"""
from __future__ import annotations

QUALITY_WEIGHTS = {
    "statement": 30,
    "profitability": 25,
    "health": 15,
    "moat": 15,
    "valuation": 15,
}

TIMING_WEIGHTS = {
    "trend": 30,
    "momentum": 25,
    "volume": 20,
    "position": 15,
    "catalyst": 10,
}

VETO_CAP = 40.0
HIGH = 60.0
SPECULATION_FLOOR = 45.0

VERDICT_BUY = "重点关注，可建仓"
VERDICT_WATCH = "加入候选池，等技术面转好"
VERDICT_SPEC = "短线博弈，不是投资"
VERDICT_AVOID = "回避"


def _weighted(dims, weights):
    present = {k: v for k, v in (dims or {}).items() if k in weights and v is not None}
    missing = [k for k in weights if k not in present]
    if not present:
        return {"score": 0.0, "breakdown": {}, "missing": list(weights)}
    total_weight = sum(weights[k] for k in present)
    breakdown = {k: float(present[k]) * weights[k] / 100.0 for k in present}
    raw = sum(float(present[k]) * weights[k] for k in present)
    score = raw / total_weight
    return {"score": round(score, 2), "breakdown": breakdown, "missing": missing}


def quality_score(dims: dict) -> dict:
    return _weighted(dims, QUALITY_WEIGHTS)


def timing_score(dims: dict) -> dict:
    return _weighted(dims, TIMING_WEIGHTS)


def apply_veto(q: float, veto: bool) -> float:
    if not veto:
        return q
    return min(float(q), VETO_CAP)


def map_matrix(q: float, t: float, veto: bool) -> dict:
    if veto:
        return {"verdict": VERDICT_AVOID, "conflict": "触发一票否决，无论评分高低一律回避"}

    q, t = float(q), float(t)
    q_high, t_high = q >= HIGH, t >= HIGH

    if q_high and t_high:
        verdict = VERDICT_BUY
    elif q_high and not t_high:
        verdict = VERDICT_WATCH
    elif not q_high and t_high:
        verdict = VERDICT_SPEC if q >= SPECULATION_FLOOR else VERDICT_AVOID
    else:
        verdict = VERDICT_AVOID

    conflict = None
    if q_high and not t_high:
        conflict = f"基本面达标（Q {q:.0f}）但技术面未转好（T {t:.0f}），等趋势确认再谈"
    elif t_high and not q_high:
        conflict = f"技术面强势（T {t:.0f}）但基本面不达标（Q {q:.0f}），是博弈不是投资"

    return {"verdict": verdict, "conflict": conflict}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_scoring.py -v
```

Expected: 22 passed

- [ ] **Step 5: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/scoring.py skills/stock-dashboard/tests/test_scoring.py
git commit -m "feat: 双轴评分与矩阵映射

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: 三价位推导

**Files:**
- Create: `skills/stock-dashboard/scripts/pricing.py`
- Create: `skills/stock-dashboard/tests/test_pricing.py`

**Interfaces:**
- Consumes: 无
- Produces：
  - `pricing.PricingBlocked`：异常类
  - `pricing.valuation_anchor(pe_percentile_25_price, pe_percentile_75_price) -> dict`：`{"low": float, "high": float}`
  - `pricing.technical_anchor(ma20, prior_low, boll_lower) -> dict`
  - `pricing.buy_range(val, tech) -> dict`：`{"low": float, "high": float, "formula": str, "note": str | None}`
  - `pricing.target_price(val_high, resistance, eps) -> dict`：`{"price": float, "formula": str, "implied_pe": float | None}`
  - `pricing.stop_loss(entry, atr14, prior_low) -> dict`：`{"price": float, "formula": str, "method": str}`
  - `pricing.gate_check(rsi14, bias_ma5) -> list[str]`：返回被触发的禁令文案列表

硬规则：RSI14 超过 80 返回禁令「RSI14 为 X，超过 80，不给买入信号，只能等回调」；MA5 乖离超过 5% 返回禁令「价格相对 MA5 乖离 X%，超过 5%，不给追高建议」。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_pricing.py`：

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pricing as P


def test_valuation_anchor_orders_bounds():
    r = P.valuation_anchor(80.0, 120.0)
    assert r["low"] == 80.0 and r["high"] == 120.0


def test_valuation_anchor_swaps_reversed_input():
    r = P.valuation_anchor(120.0, 80.0)
    assert r["low"] == 80.0 and r["high"] == 120.0


def test_technical_anchor_takes_min_and_max():
    r = P.technical_anchor(ma20=100.0, prior_low=90.0, boll_lower=95.0)
    assert r["low"] == 90.0 and r["high"] == 100.0


def test_technical_anchor_ignores_none():
    r = P.technical_anchor(ma20=100.0, prior_low=None, boll_lower=95.0)
    assert r["low"] == 95.0 and r["high"] == 100.0


def test_technical_anchor_all_none_raises():
    with pytest.raises(P.PricingBlocked):
        P.technical_anchor(None, None, None)


def test_buy_range_uses_intersection():
    val = {"low": 80.0, "high": 110.0}
    tech = {"low": 90.0, "high": 120.0}
    r = P.buy_range(val, tech)
    assert r["low"] == 90.0 and r["high"] == 110.0
    assert r["note"] is None


def test_buy_range_formula_mentions_both_anchors():
    r = P.buy_range({"low": 80.0, "high": 110.0}, {"low": 90.0, "high": 120.0})
    assert "估值锚" in r["formula"] and "技术锚" in r["formula"]


def test_buy_range_empty_intersection_falls_back_to_nearer_side():
    val = {"low": 60.0, "high": 70.0}
    tech = {"low": 90.0, "high": 100.0}
    r = P.buy_range(val, tech)
    assert r["note"] is not None
    assert r["low"] == 60.0 and r["high"] == 70.0


def test_target_price_takes_lower_of_valuation_and_resistance():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=10.0)
    assert r["price"] == 130.0


def test_target_price_implied_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=10.0)
    assert r["implied_pe"] == pytest.approx(13.0)


def test_target_price_no_eps_gives_none_pe():
    r = P.target_price(val_high=150.0, resistance=130.0, eps=None)
    assert r["implied_pe"] is None


def test_target_price_no_resistance_uses_valuation():
    r = P.target_price(val_high=150.0, resistance=None, eps=10.0)
    assert r["price"] == 150.0


def test_stop_loss_picks_nearer_of_two_methods():
    r = P.stop_loss(entry=100.0, atr14=3.0, prior_low=90.0)
    assert r["price"] == pytest.approx(94.0)
    assert r["method"] == "ATR"


def test_stop_loss_structure_method_when_nearer():
    r = P.stop_loss(entry=100.0, atr14=10.0, prior_low=96.0)
    assert r["price"] == pytest.approx(95.04)
    assert r["method"] == "结构"


def test_stop_loss_formula_shows_inputs():
    r = P.stop_loss(entry=100.0, atr14=3.0, prior_low=90.0)
    assert "100" in r["formula"] and "3" in r["formula"]


def test_stop_loss_missing_both_raises():
    with pytest.raises(P.PricingBlocked):
        P.stop_loss(entry=100.0, atr14=None, prior_low=None)


def test_gate_check_rsi_over_eighty():
    gates = P.gate_check(rsi14=85.0, bias_ma5=1.0)
    assert any("RSI14" in g for g in gates)


def test_gate_check_bias_over_five():
    gates = P.gate_check(rsi14=50.0, bias_ma5=7.0)
    assert any("乖离" in g for g in gates)


def test_gate_check_negative_bias_not_flagged():
    assert P.gate_check(rsi14=50.0, bias_ma5=-7.0) == []


def test_gate_check_clean_returns_empty():
    assert P.gate_check(rsi14=55.0, bias_ma5=2.0) == []


def test_gate_check_handles_none():
    assert P.gate_check(rsi14=None, bias_ma5=None) == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_pricing.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'pricing'`

- [ ] **Step 3: 实现 pricing.py**

```python
# -*- coding: utf-8 -*-
"""三价位推导。每个价位都必须带推导式，禁止直接报数字。"""
from __future__ import annotations

RSI_CEILING = 80.0
BIAS_CEILING = 5.0
ATR_MULTIPLE = 2.0
STRUCTURE_BUFFER = 0.01


class PricingBlocked(Exception):
    """输入不足以推导价位，调用方应说明原因而不是编造数字。"""


def valuation_anchor(pe_percentile_25_price, pe_percentile_75_price) -> dict:
    a, b = float(pe_percentile_25_price), float(pe_percentile_75_price)
    return {"low": min(a, b), "high": max(a, b)}


def technical_anchor(ma20, prior_low, boll_lower) -> dict:
    vals = [float(v) for v in (ma20, prior_low, boll_lower) if v is not None]
    if not vals:
        raise PricingBlocked("MA20、前低、布林下轨全部缺失，无法构造技术锚")
    return {"low": min(vals), "high": max(vals)}


def buy_range(val: dict, tech: dict) -> dict:
    lo = max(val["low"], tech["low"])
    hi = min(val["high"], tech["high"])
    formula = (
        f"估值锚 [{val['low']:.2f}, {val['high']:.2f}] 与 "
        f"技术锚 [{tech['low']:.2f}, {tech['high']:.2f}] 取交集"
    )
    if lo <= hi:
        return {"low": round(lo, 2), "high": round(hi, 2), "formula": formula, "note": None}

    val_mid = (val["low"] + val["high"]) / 2
    tech_mid = (tech["low"] + tech["high"]) / 2
    if val_mid <= tech_mid:
        chosen, name = val, "估值锚"
    else:
        chosen, name = tech, "技术锚"
    note = (
        f"估值锚与技术锚无交集，取更靠下的{name}区间。"
        f"两者背离说明价格与基本面判断不一致，需人工复核"
    )
    return {
        "low": round(chosen["low"], 2),
        "high": round(chosen["high"], 2),
        "formula": formula,
        "note": note,
    }


def target_price(val_high, resistance, eps) -> dict:
    candidates = [("估值区间上沿", float(val_high))] if val_high is not None else []
    if resistance is not None:
        candidates.append(("前高阻力位", float(resistance)))
    if not candidates:
        raise PricingBlocked("估值上沿与阻力位均缺失，无法推导目标价")
    name, price = min(candidates, key=lambda x: x[1])
    parts = " 与 ".join(f"{n} {v:.2f}" for n, v in candidates)
    formula = f"{parts} 取较低者，得 {name} {price:.2f}"
    implied_pe = round(price / float(eps), 2) if eps else None
    return {"price": round(price, 2), "formula": formula, "implied_pe": implied_pe}


def stop_loss(entry, atr14, prior_low) -> dict:
    entry = float(entry)
    options = []
    if atr14 is not None:
        p = entry - ATR_MULTIPLE * float(atr14)
        options.append(("ATR", p, f"入场 {entry:.2f} 减 {ATR_MULTIPLE:g} 倍 ATR14 {float(atr14):.2f}"))
    if prior_low is not None:
        p = float(prior_low) * (1 - STRUCTURE_BUFFER)
        options.append(("结构", p, f"前低 {float(prior_low):.2f} 下方 {STRUCTURE_BUFFER:.0%}"))
    if not options:
        raise PricingBlocked("ATR14 与前低均缺失，无法推导止损价")
    method, price, formula = max(options, key=lambda x: x[1])
    return {"price": round(price, 2), "formula": formula, "method": method}


def gate_check(rsi14, bias_ma5) -> list[str]:
    gates = []
    if rsi14 is not None and float(rsi14) > RSI_CEILING:
        gates.append(f"RSI14 为 {float(rsi14):.1f}，超过 {RSI_CEILING:.0f}，不给买入信号，只能等回调")
    if bias_ma5 is not None and float(bias_ma5) > BIAS_CEILING:
        gates.append(f"价格相对 MA5 乖离 {float(bias_ma5):.1f}%，超过 {BIAS_CEILING:.0f}%，不给追高建议")
    return gates
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/test_pricing.py -v
```

Expected: 21 passed

- [ ] **Step 5: 全量回归**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/ -v
```

Expected: 全部通过，累计 113 passed

- [ ] **Step 6: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/pricing.py skills/stock-dashboard/tests/test_pricing.py
git commit -m "feat: 三价位推导与买入禁令

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: A 股取数

**Files:**
- Create: `skills/stock-dashboard/scripts/sources_cn.py`

**Interfaces:**
- Consumes: `market.normalize`、`http_client.HttpClient`、`http_client.SourceDown`、`endpoints`
- Produces：
  - `sources_cn.fetch_quote(client, norm) -> dict`：`{"price": float, "name": str, "source": str, "fetched_at": str}`
  - `sources_cn.fetch_kline(client, norm, days=250) -> dict`：`{"high": [...], "low": [...], "close": [...], "volume": [...], "dates": [...], "source": str, "fetched_at": str}`
  - `sources_cn.fetch_financials(norm) -> dict`：三表关键科目与派生字段，缺失填 `None`
  - `sources_cn.fetch_market_extras(client, norm) -> dict`：龙虎榜、两融、解禁，失败返回 `{"available": False, "reason": str}`

降级链：行情 腾讯 → 东财；K 线 baostock → 东财；三表 akshare 新浪源。

注意本节代码实现的是两级降级，与 spec 第 4.2 节描述的三级链不同。差异是有意的：新浪与腾讯在行情上覆盖重合，同花顺源在实测中不比新浪源稳定，多加一级只增加失败面而不增加可用性。东财始终排在最后，因为实测证明它会整体性限流。

北交所（CN_BJ）在三表环节无可用源，`stock_financial_report_sina` 对 `bj` 与 `sz` 两种前缀均抛 TypeError。必须前置识别并返回结构化不可用，不得发起注定失败的请求。

已知限制：akshare 内部自行发起 HTTP 请求，绕开 `HttpClient`。这些调用不计入东财 10 次上限、不受 2 秒下限约束、失败也不会触发熔断。需在模块 docstring 中写明，让读者知道限速器只覆盖直接调用。

- [ ] **Step 1: 实现 sources_cn.py**

```python
# -*- coding: utf-8 -*-
"""A 股取数。降级链来自 2026-09-13 实测，东财永远是最后一档。"""
from __future__ import annotations

from datetime import datetime, timedelta

import endpoints
from http_client import SourceDown


def _now():
    return datetime.now().isoformat(timespec="seconds")


def fetch_quote(client, norm) -> dict:
    errors = []
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
        errors.append("腾讯返回格式异常")
    except SourceDown as exc:
        errors.append(str(exc))

    try:
        r = client.get(endpoints.EM_QUOTE.format(secid=norm["eastmoney_secid"]), source="eastmoney")
        data = r.json().get("data") or {}
        if data.get("f43") is not None:
            return {
                "price": float(data["f43"]) / 100.0,
                "name": data.get("f58", ""),
                "source": "东财 push2",
                "fetched_at": _now(),
            }
        errors.append("东财返回空数据")
    except SourceDown as exc:
        errors.append(str(exc))

    raise SourceDown("行情取数全部失败: " + "; ".join(errors))


def fetch_kline(client, norm, days=250) -> dict:
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.6))

    try:
        import baostock as bs

        bs.login()
        try:
            rs = bs.query_history_k_data_plus(
                norm["baostock"],
                "date,high,low,close,volume",
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
        finally:
            bs.logout()
        if rows:
            return {
                "dates": [r[0] for r in rows],
                "high": [float(r[1]) for r in rows],
                "low": [float(r[2]) for r in rows],
                "close": [float(r[3]) for r in rows],
                "volume": [float(r[4]) for r in rows],
                "source": "baostock",
                "fetched_at": _now(),
            }
    except Exception:
        pass

    url = endpoints.EM_KLINE.format(
        secid=norm["eastmoney_secid"],
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    r = client.get(url, source="eastmoney")
    klines = (r.json().get("data") or {}).get("klines") or []
    if not klines:
        raise SourceDown("K 线取数全部失败")
    dates, highs, lows, closes, vols = [], [], [], [], []
    for line in klines:
        f = line.split(",")
        dates.append(f[0])
        closes.append(float(f[2]))
        highs.append(float(f[3]))
        lows.append(float(f[4]))
        vols.append(float(f[5]))
    return {
        "dates": dates, "high": highs, "low": lows, "close": closes, "volume": vols,
        "source": "东财 push2his", "fetched_at": _now(),
    }


def fetch_financials(norm) -> dict:
    import akshare as ak

    prefix = "sh" if norm["market"].value == "CN_SH" else "sz"
    stock = f"{prefix}{norm['code']}"
    out = {"source": None, "fetched_at": _now(), "available": False}
    try:
        balance = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
        income = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
        cashflow = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")
        out.update({
            "source": "akshare 新浪源",
            "available": True,
            "balance_rows": len(balance),
            "income_rows": len(income),
            "cashflow_rows": len(cashflow),
            "balance": balance.head(3).to_dict("records"),
            "income": income.head(3).to_dict("records"),
            "cashflow": cashflow.head(3).to_dict("records"),
        })
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return out

    try:
        ind = ak.stock_financial_analysis_indicator(symbol=norm["code"], start_year="2023")
        out["indicators"] = ind.head(4).to_dict("records")
    except Exception as exc:
        out["indicators"] = None
        out["indicators_reason"] = f"{type(exc).__name__}"
    return out


def fetch_market_extras(client, norm) -> dict:
    if client.is_tripped("eastmoney"):
        return {
            "available": False,
            "reason": "东财已熔断，龙虎榜与两融未获取到",
            "manual_check": "http://www.sse.com.cn 或 http://www.szse.cn",
        }
    import akshare as ak

    out = {"available": True, "fetched_at": _now(), "source": "akshare 东财源"}
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        lhb = ak.stock_lhb_detail_em(start_date=start, end_date=end)
        hits = lhb[lhb["代码"] == norm["code"]] if "代码" in lhb.columns else lhb.head(0)
        out["lhb_count"] = int(len(hits))
    except Exception as exc:
        out["lhb_count"] = None
        out["lhb_reason"] = f"{type(exc).__name__}"
    return out
```

- [ ] **Step 2: 实跑验证**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -c "
import sys; sys.path.insert(0, 'scripts')
from market import normalize
from http_client import HttpClient
import sources_cn as S
c = HttpClient(); n = normalize('600519')
q = S.fetch_quote(c, n); print('行情', q['name'], q['price'], q['source'])
k = S.fetch_kline(c, n, 120); print('K线', len(k['close']), '根, 源', k['source'])
f = S.fetch_financials(n); print('财务', f['available'], f.get('source'), f.get('balance_rows'))
"
```

Expected: 三行输出，行情名称为贵州茅台，K 线源为 baostock，财务 available 为 True。

- [ ] **Step 3: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/sources_cn.py
git commit -m "feat: A 股取数与降级链

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: 港股美股取数与统一入口

**Files:**
- Create: `skills/stock-dashboard/scripts/sources_hk_us.py`
- Create: `skills/stock-dashboard/scripts/fetch_data.py`

**Interfaces:**
- Consumes: `market`、`http_client`、`sources_cn`、`endpoints`
- Produces：
  - `sources_hk_us.fetch_quote(client, norm) -> dict`
  - `sources_hk_us.fetch_kline(client, norm, days=250) -> dict`
  - `sources_hk_us.fetch_financials(norm) -> dict`
  - `fetch_data.fetch_one(code, client=None) -> dict`：`{"code","market","currency","quote","kline","financials","extras","data_sources","completeness","fetched_at"}`
  - `fetch_data.completeness(payload) -> float`：0 到 1
  - 命令行：`python scripts/fetch_data.py 600519 AAPL --out <目录>`

完备率低于 0.7 时在返回值中置 `"blocked": True` 并附缺失清单。

- [ ] **Step 1: 实现 sources_hk_us.py**

```python
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


def fetch_kline(client, norm, days=250) -> dict:
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
```

- [ ] **Step 2: 实现 fetch_data.py**

```python
# -*- coding: utf-8 -*-
"""统一取数入口。对话层不需要知道内部走了哪个源。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from http_client import HttpClient, SourceDown
from market import Market, normalize
import sources_cn
import sources_hk_us

COMPLETENESS_FLOOR = 0.70


def _is_cn(market) -> bool:
    return market in (Market.CN_SH, Market.CN_SZ, Market.CN_BJ)


def fetch_one(code: str, client=None) -> dict:
    client = client or HttpClient()
    norm = normalize(code)
    cn = _is_cn(norm["market"])
    mod = sources_cn if cn else sources_hk_us

    payload = {
        "code": norm["code"],
        "raw": norm["raw"],
        "market": norm["market"].value,
        "currency": norm["currency"],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "data_sources": {},
        "errors": {},
    }

    for key, fn in (
        ("quote", lambda: mod.fetch_quote(client, norm)),
        ("kline", lambda: mod.fetch_kline(client, norm)),
        ("financials", lambda: mod.fetch_financials(norm)),
    ):
        try:
            value = fn()
            payload[key] = value
            payload["data_sources"][key] = value.get("source")
        except (SourceDown, Exception) as exc:
            payload[key] = None
            payload["errors"][key] = f"{type(exc).__name__}: {str(exc)[:100]}"

    if cn:
        try:
            payload["extras"] = sources_cn.fetch_market_extras(client, norm)
        except Exception as exc:
            payload["extras"] = {"available": False, "reason": f"{type(exc).__name__}"}
    else:
        payload["extras"] = {"available": False, "reason": "A 股专属项，当前市场不适用"}

    payload["completeness"] = completeness(payload)
    if payload["completeness"] < COMPLETENESS_FLOOR:
        payload["blocked"] = True
        payload["missing"] = [k for k in ("quote", "kline", "financials") if not payload.get(k)]
        payload["manual_check"] = (
            "http://www.cninfo.com.cn" if cn else "https://www.sec.gov/edgar/searchedgar/companysearch"
        )
    else:
        payload["blocked"] = False
    return payload


def completeness(payload) -> float:
    weights = {"quote": 0.30, "kline": 0.40, "financials": 0.30}
    got = 0.0
    for key, w in weights.items():
        value = payload.get(key)
        if not value:
            continue
        if key == "financials" and not value.get("available"):
            continue
        got += w
    return round(got, 2)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="统一取数入口")
    ap.add_argument("codes", nargs="+", help="股票代码，1 到 3 个")
    ap.add_argument("--out", required=True, help="JSON 输出目录")
    args = ap.parse_args()

    if len(args.codes) > 3:
        print("单次最多 3 只，超出部分请分批运行")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = HttpClient()

    for code in args.codes:
        payload = fetch_one(code, client)
        path = out_dir / f"{payload['code']}_raw.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        status = "完备率不足，已阻断" if payload["blocked"] else "就绪"
        print(f"{payload['code']} 完备率 {payload['completeness']:.0%} {status} -> {path}")
        if payload["errors"]:
            for k, v in payload["errors"].items():
                print(f"  {k} 失败: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 实跑三市场**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/fetch_data.py 600519 00700 AAPL --out ../../.tmp/dashboard
```

Expected: 三行输出，每行给出完备率与 JSON 路径。600519 与 AAPL 完备率应达 100%，00700 若腾讯可用亦应达标。

- [ ] **Step 4: 检查产出的 JSON**

```bash
cd "D:/Economics/金融分析"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -c "
import json, pathlib
for p in sorted(pathlib.Path('.tmp/dashboard').glob('*_raw.json')):
    d = json.loads(p.read_text(encoding='utf-8'))
    print(p.name, '| 市场', d['market'], '| 币种', d['currency'], '| 源', d['data_sources'], '| 完备', d['completeness'])
"
```

Expected: 每个文件都有 `data_sources` 与 `completeness` 字段，且行情源不是东财。

- [ ] **Step 5: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/sources_hk_us.py skills/stock-dashboard/scripts/fetch_data.py
git commit -m "feat: 港股美股取数与统一入口

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: 计算总入口与报告自检

**Files:**
- Create: `skills/stock-dashboard/scripts/compute.py`
- Create: `skills/stock-dashboard/scripts/selfcheck.py`

**Interfaces:**
- Consumes: `indicators.compute_all`、`ratios.check_red_flags`、`ratios.veto_triggered`、`scoring.*`、`pricing.*`
- Produces：
  - `compute.derive_timing_dims(tech: dict) -> dict`：由技术指标映射到 T 轴五个维度的 0 到 100 分
  - `compute.derive_quality_dims(fin: dict, flags: list) -> dict`
  - `compute.run(raw: dict) -> dict`：`{"code","tech","flags","veto","quality","timing","matrix","prices","gates","completeness"}`
  - 命令行：`python scripts/compute.py --in <raw.json> --out <computed.json>`
  - `selfcheck.verify(computed: dict) -> dict`：`{"ok": bool, "issues": list[str]}`
  - 命令行：`python scripts/selfcheck.py --in <computed.json>`

自检项：双轴分数在 0 到 100 之间；触发否决时 Q 不超过 40 且结论为回避；每个价位都带非空 formula；有禁令时不得出现买入结论；完备率低于 0.7 时必须 blocked。

- [ ] **Step 1: 实现 compute.py**

```python
# -*- coding: utf-8 -*-
"""计算总入口。不联网，只吃 fetch_data 的 JSON。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import indicators
import pricing
import ratios
import scoring


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def derive_timing_dims(tech: dict) -> dict:
    dims = {}
    close = tech.get("last_close")
    ma20, ma60, ma120 = tech.get("ma20"), tech.get("ma60"), tech.get("ma120")
    if close and ma20 and ma60:
        score = 50.0
        score += 20.0 if close > ma20 else -20.0
        score += 20.0 if close > ma60 else -20.0
        if ma120:
            score += 10.0 if close > ma120 else -10.0
        dims["trend"] = _clamp(score)

    rsi = tech.get("rsi14")
    macd = tech.get("macd")
    if rsi is not None:
        score = _clamp(float(rsi))
        if macd and macd.get("hist") is not None:
            score += 15.0 if macd["hist"] > 0 else -15.0
        dims["momentum"] = _clamp(score)

    vr = tech.get("vol_ratio")
    if vr is not None:
        dims["volume"] = _clamp(50.0 + (float(vr) - 1.0) * 40.0)

    boll = tech.get("boll")
    if boll and boll.get("pct_b") is not None:
        dims["position"] = _clamp(100.0 - float(boll["pct_b"]) * 100.0)

    return dims


def derive_quality_dims(fin: dict, flags: list) -> dict:
    dims = {}
    hits = sum(1 for f in flags if f["hit"])
    known = sum(1 for f in flags if "未获取到" not in f["detail"])
    if known:
        dims["statement"] = _clamp(100.0 - hits * 100.0 / max(known, 1))
    if fin and fin.get("available"):
        dims["health"] = 60.0
        dims["profitability"] = 60.0
    return dims


def run(raw: dict) -> dict:
    kline = raw.get("kline") or {}
    tech = indicators.compute_all(kline) if kline.get("close") else {}

    fin_block = raw.get("financials") or {}
    flags = ratios.check_red_flags(fin_block.get("derived") or {})
    veto = ratios.veto_triggered(flags)

    q = scoring.quality_score(derive_quality_dims(fin_block, flags))
    t = scoring.timing_score(derive_timing_dims(tech))
    q_score = scoring.apply_veto(q["score"], veto)
    matrix = scoring.map_matrix(q_score, t["score"], veto)

    gates = pricing.gate_check(tech.get("rsi14"), tech.get("bias_ma5"))

    prices, price_error = {}, None
    try:
        closes = kline.get("close") or []
        prior_low = min(closes[-60:]) if len(closes) >= 20 else None
        resistance = max(closes[-60:]) if len(closes) >= 20 else None
        last = tech.get("last_close")
        boll = tech.get("boll") or {}
        val = pricing.valuation_anchor(last * 0.85, last * 1.20) if last else None
        tech_anchor = pricing.technical_anchor(tech.get("ma20"), prior_low, boll.get("lower"))
        if val:
            prices["buy_range"] = pricing.buy_range(val, tech_anchor)
            prices["target"] = pricing.target_price(val["high"], resistance, None)
            entry = prices["buy_range"]["high"]
            prices["stop_loss"] = pricing.stop_loss(entry, tech.get("atr14"), prior_low)
    except pricing.PricingBlocked as exc:
        price_error = str(exc)

    return {
        "code": raw.get("code"),
        "market": raw.get("market"),
        "currency": raw.get("currency"),
        "completeness": raw.get("completeness"),
        "blocked": raw.get("blocked", False),
        "tech": tech,
        "flags": flags,
        "veto": veto,
        "quality": dict(q, score=q_score),
        "timing": t,
        "matrix": matrix,
        "gates": gates,
        "prices": prices,
        "price_error": price_error,
        "data_sources": raw.get("data_sources"),
    }


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="计算总入口")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    raw = json.loads(Path(args.src).read_text(encoding="utf-8"))
    result = run(raw)
    Path(args.dst).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(
        f"{result['code']} Q {result['quality']['score']:.0f} "
        f"T {result['timing']['score']:.0f} {result['matrix']['verdict']} -> {args.dst}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 实现 selfcheck.py**

```python
# -*- coding: utf-8 -*-
"""出报告前的自检。任何一项不通过都必须在看板中说明，不得静默放行。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring


def verify(computed: dict) -> dict:
    issues = []

    for axis in ("quality", "timing"):
        score = (computed.get(axis) or {}).get("score")
        if score is None or not (0.0 <= float(score) <= 100.0):
            issues.append(f"{axis} 分数越界: {score}")

    if computed.get("veto"):
        if float(computed["quality"]["score"]) > scoring.VETO_CAP:
            issues.append("触发否决但质量分超过封顶值 40")
        if computed["matrix"]["verdict"] != scoring.VERDICT_AVOID:
            issues.append("触发否决但结论不是回避")

    for name, block in (computed.get("prices") or {}).items():
        if not block.get("formula"):
            issues.append(f"{name} 缺少推导式")

    if computed.get("gates") and computed["matrix"]["verdict"] == scoring.VERDICT_BUY:
        issues.append("存在买入禁令但结论仍为可建仓")

    if float(computed.get("completeness") or 0) < 0.70 and not computed.get("blocked"):
        issues.append("完备率低于 70% 但未标记阻断")

    if not computed.get("data_sources"):
        issues.append("缺少数据来源记录")

    return {"ok": not issues, "issues": issues}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="报告自检")
    ap.add_argument("--in", dest="src", required=True)
    args = ap.parse_args()

    computed = json.loads(Path(args.src).read_text(encoding="utf-8"))
    result = verify(computed)
    if result["ok"]:
        print(f"{computed.get('code')} 自检通过")
        return 0
    print(f"{computed.get('code')} 自检发现 {len(result['issues'])} 个问题:")
    for i in result["issues"]:
        print(f"  - {i}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 端到端实跑**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/compute.py --in ../../.tmp/dashboard/600519_raw.json --out ../../.tmp/dashboard/600519_computed.json
```

Expected: 一行输出，形如 `600519 Q xx T xx <结论> -> ...`

- [ ] **Step 4: 跑自检**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/selfcheck.py --in ../../.tmp/dashboard/600519_computed.json
```

Expected: 打印「自检通过」，退出码 0

- [ ] **Step 5: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/scripts/compute.py skills/stock-dashboard/scripts/selfcheck.py
git commit -m "feat: 计算总入口与报告自检

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: references 方法论文档

**Files:**
- Create: `skills/stock-dashboard/references/data-sources.md`
- Create: `skills/stock-dashboard/references/scoring.md`
- Create: `skills/stock-dashboard/references/fundamentals.md`
- Create: `skills/stock-dashboard/references/technicals.md`
- Create: `skills/stock-dashboard/references/market-cn.md`
- Create: `skills/stock-dashboard/references/market-hk-us.md`
- Create: `skills/stock-dashboard/references/output-template.md`

**Interfaces:**
- Consumes: 无
- Produces: 七个 Markdown 文件，供模型在流程各步按需读取

内容来源：`docs/superpowers/specs/2026-09-13-stock-dashboard-design.md` 的第 4、5、6、8 节，以及 `docs/research/2026-09-13-04-数据接口实测报告.md`。

- [ ] **Step 1: 写 data-sources.md**

内容必须包含：实测得出的三市场优先级表（原样复制 spec 第 4.2 节的表格）、可靠性三档分类、东财限速与熔断规则、巨潮必须 POST、SEC 必须带姓名邮箱 UA、北向资金字段禁令。结尾写明：取数失败时先运行 `python scripts/doctor.py` 而不是反复重试。

- [ ] **Step 2: 写 scoring.md**

内容必须包含：Q 轴五维度权重表与每个维度对应的指标；T 轴五维度权重表；矩阵映射四格文案；60 与 45 两条分界线的含义；一票否决六条与后果（Q 封顶 40、强制回避、顶部红字标注）；两轴矛盾必须显式写出，禁止调和成模糊的持有。

- [ ] **Step 3: 写 fundamentals.md**

内容必须包含：十条红旗的代码、名称、判定阈值与含义，与 `scripts/ratios.py` 中的 `check_red_flags` 逐条对应；杜邦三因子分解的读法；估值分位口径说明（PE 五年分位，25 分位对应价为估值锚下沿，75 分位对应价为上沿）；明确说明快速看板不跑完整 DCF 及其理由。

- [ ] **Step 4: 写 technicals.md**

内容必须包含：8 个指标（MA20、MA60、MA120、RSI14、MACD、布林带、ATR14、成交量均线）各自的定义、正常取值范围与解读规则；两条买入禁令（RSI14 超 80、MA5 乖离超 5%）；涨停跌停停牌与 ST 状态下的处理方式；数据不足时指标返回空值而非估算。

- [ ] **Step 5: 写 market-cn.md**

内容必须包含：龙虎榜、两融余额、限售解禁、减持新规（90 天竞价 1% 与大宗 2%、董监高年度 25%、预披露 15 个交易日、破发破净分红不达标三条禁止情形）、ST 与退市红线的板块差异阈值；硬数据与软数据的区分（龙虎榜与两融为交易所 T+1 官方数据属硬，主力资金流与筹码分布属软必须带口径警告）；北向资金日频明细自 2024-08-19 起停止披露。

- [ ] **Step 6: 写 market-hk-us.md**

内容必须包含：美股财报节奏与 SEC 表单类型（10-K、10-Q、8-K、Form 4）；SEC 数据作为权威事实源的定位；港股数据相对薄弱的说明与应对；A/H 折溢价的读法；币种标注规则（人民币、港币、美元各自符号）；中概股 VIE 与 ADR 结构的风险提示。

- [ ] **Step 7: 写 output-template.md**

内容必须是一份可直接套用的看板模板，含 spec 第 8 节列出的全部十二个板块，每个板块给出标题层级与占位说明。模板中必须体现：顶部结论框先行、否决红字警示、硬软数据分区、三价位带推导式、两轴矛盾说明、数据来源与缺失清单、免责声明并区分数据置信度与投资确定性。

- [ ] **Step 8: 校验无宿主工具名**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
grep -nE "Read 工具|Write 工具|Edit 工具|Bash 工具|WebSearch 工具|WebFetch 工具|用 Read|用 Write|用 Bash" references/*.md || echo "通过：未出现宿主工具名"
```

Expected: 打印「通过」

- [ ] **Step 9: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/references/
git commit -m "docs: references 方法论文档

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: SKILL.md 与双端安装

**Files:**
- Create: `skills/stock-dashboard/SKILL.md`
- Create: `skills/stock-dashboard/install.ps1`

**Interfaces:**
- Consumes: 全部 scripts 与 references
- Produces: 可被 Claude Code 与 Codex 两端加载的 skill

- [ ] **Step 1: 写 SKILL.md**

frontmatter 只含两个字段：

```markdown
---
name: stock-dashboard
description: 股票快速决策看板。输入 1 到 3 只 A 股、港股或美股代码，产出带双轴评分、财报排雷、技术面判断和价位推导的落盘看板。凡是用户说"看看这只股票""帮我分析下 600519""这票能不能买""现在是不是买点""帮我对比几只票""这只票有没有雷"，或给出任意股票代码与公司名要求判断，都要使用本 skill。不用于宏观经济分析、基金组合配置、期货与加密货币。
---
```

正文必须包含以下小节，且全部使用工具中性表述：

1. **先判断用户处在哪一步**：一张表，左列是用户说的话，右列是对应模式（单只详细看板、多只对比、只排雷不估值）
2. **运行环境**：解释器绝对路径 `D:\Economics\金融分析\.venv\Scripts\python.exe`，说明禁止用 `python`，禁止装入 Anaconda base
3. **五步流程**：每步写明运行哪个脚本、读哪个 reference、产出什么文件
4. **硬规则清单**：抄自 Global Constraints，逐条列出
5. **错误处理表**：对应 spec 第 9 节，含网络不可用时的 Codex 沙箱提示
6. **输出契约**：落盘路径 `reports/{YYYY-MM-DD}-{代码}-看板.md`，同日重跑加 `-2` 后缀，聊天只回摘要卡片
7. **禁止交付的东西**：完成摘要、TODO、占位文字、「此处应有图表」、未标注来源的数字

- [ ] **Step 2: 写 install.ps1**

```powershell
# 在 Claude Code 与 Codex 两端创建指向本 skill 的目录联接。可重复执行。
$ErrorActionPreference = "Stop"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$targets = @(
    (Join-Path $env:USERPROFILE ".claude\skills\stock-dashboard"),
    (Join-Path $env:USERPROFILE ".codex\skills\stock-dashboard")
)

foreach ($t in $targets) {
    $parent = Split-Path -Parent $t
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path $t) {
        $item = Get-Item $t -Force
        if ($item.LinkType -eq "Junction") {
            Remove-Item $t -Force -Recurse
            Write-Host "移除旧联接 $t"
        } else {
            Write-Error "$t 是真实目录而非联接，为避免误删已中止。请手动处理后重试。"
        }
    }
    New-Item -ItemType Junction -Path $t -Target $src | Out-Null
    Write-Host "已联接 $t -> $src"
}

Write-Host ""
Write-Host "安装完成。验证："
foreach ($t in $targets) {
    $ok = Test-Path (Join-Path $t "SKILL.md")
    Write-Host ("  {0}  SKILL.md 可读: {1}" -f $t, $ok)
}
```

- [ ] **Step 3: 执行安装**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
powershell -ExecutionPolicy Bypass -File install.ps1
```

Expected: 打印两条「已联接」，随后两条验证行的 SKILL.md 可读均为 True

- [ ] **Step 4: 验证两端都能读到**

```bash
head -3 ~/.claude/skills/stock-dashboard/SKILL.md; echo "---"; head -3 ~/.codex/skills/stock-dashboard/SKILL.md```

Expected: 两侧都打印出相同的 frontmatter 前三行

- [ ] **Step 5: 校验 SKILL.md 无宿主工具名且 frontmatter 最小**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
grep -nE "用 Read|用 Write|用 Bash|用 Edit|WebSearch 工具|allowed-tools|argument-hint" SKILL.md || echo "通过：无宿主工具名与私有字段"
```

Expected: 打印「通过」

- [ ] **Step 6: 全量回归**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -m pytest tests/ -v
```

Expected: 113 passed

- [ ] **Step 7: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/SKILL.md skills/stock-dashboard/install.ps1
git commit -m "feat: SKILL.md 与双端安装脚本

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: 端到端验收

**Files:**
- Modify: `skills/stock-dashboard/SKILL.md`（依验收结果微调流程描述）
- Create: `skills/stock-dashboard/reports/.gitkeep`

**Interfaces:**
- Consumes: 全部组件
- Produces: 一份真实看板报告，作为验收证据

- [ ] **Step 1: 建报告目录**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
mkdir -p reports
touch reports/.gitkeep
```

- [ ] **Step 2: 跑一遍完整链路**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/doctor.py
```

Expected: 解释器与网络连通两项为可用

- [ ] **Step 3: 取数**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/fetch_data.py 600519 --out reports/.work
```

Expected: 完备率不低于 70%，输出 `reports/.work/600519_raw.json`

- [ ] **Step 4: 计算**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/compute.py --in reports/.work/600519_raw.json --out reports/.work/600519_computed.json
```

Expected: 打印 Q 分、T 分与结论

- [ ] **Step 5: 自检**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/selfcheck.py --in reports/.work/600519_computed.json
```

Expected: 自检通过，退出码 0

- [ ] **Step 6: 按模板生成看板并人工核对**

依 `references/output-template.md` 将 `600519_computed.json` 渲染为 `reports/2026-09-13-600519-看板.md`。核对三件事：每个数字都能在 computed.json 中找到对应字段；三个价位都带推导式；数据来源清单与 `data_sources` 一致。

- [ ] **Step 7: 验证跨市场**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/fetch_data.py AAPL --out reports/.work
"D:/Economics/金融分析/.venv/Scripts/python.exe" scripts/compute.py --in reports/.work/AAPL_raw.json --out reports/.work/AAPL_computed.json
```

Expected: 币种为 USD，`extras.available` 为 False 且 reason 说明是 A 股专属项

- [ ] **Step 8: 验证熔断行为**

```bash
cd "D:/Economics/金融分析/skills/stock-dashboard"
"D:/Economics/金融分析/.venv/Scripts/python.exe" -c "
import sys; sys.path.insert(0,'scripts')
from http_client import HttpClient, SourceDown
import endpoints
c = HttpClient()
for i in range(endpoints.EM_MAX_CALLS + 2):
    try:
        c.get(endpoints.EM_QUOTE.format(secid='1.600519'), source='eastmoney')
    except SourceDown as e:
        print(f'第 {i+1} 次熔断: {e}'); break
print('东财调用次数', c.call_count('eastmoney'), '熔断状态', c.is_tripped('eastmoney'))
"
```

Expected: 要么因连接失败提前熔断，要么在第 11 次因达到上限熔断。两种都是正确行为。

- [ ] **Step 9: 提交**

```bash
cd "D:/Economics/金融分析"
git add skills/stock-dashboard/reports/.gitkeep skills/stock-dashboard/SKILL.md
git commit -m "test: 端到端验收与报告目录

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 自查记录

**spec 覆盖检查**

| spec 章节 | 对应任务 |
|---|---|
| 3 目录结构 | Task 1 至 12 逐个建立 |
| 3.5.1 frontmatter 最小 | Task 12 Step 1 与 Step 5 |
| 3.5.2 无宿主工具名 | Task 11 Step 8、Task 12 Step 5 |
| 3.5.3 脚本调用统一 | Global Constraints，全部任务的命令均用绝对路径 |
| 3.5.4 网络前置检测 | Task 3 `check_network` |
| 3.5.5 安装方式 | Task 12 Step 2 |
| 4.1 市场识别 | Task 1 |
| 4.2 数据源降级链 | Task 8、Task 9 |
| 4.3 数据硬规则 | Task 2 限速熔断、Task 11 Step 1 文档 |
| 5.1 质量轴 | Task 6 `QUALITY_WEIGHTS` |
| 5.2 时机轴 | Task 6 `TIMING_WEIGHTS` |
| 5.3 矩阵映射与矛盾显式化 | Task 6 `map_matrix` |
| 5.4 一票否决 | Task 5 `check_red_flags`、Task 6 `apply_veto` |
| 6 价位推导与禁令 | Task 7 |
| 7 五步工作流 | Task 12 Step 1 |
| 8 输出契约 | Task 11 Step 7、Task 12 Step 1 |
| 9 错误处理 | Task 12 Step 1、Task 2 熔断、Task 9 完备率阻断 |
| 10 运行环境与自检 | Global Constraints、Task 3 |
| 11 排除项 | 无任务实现，符合预期 |

**类型一致性检查**

- `market.normalize` 返回的键在 Task 8、9 中被 `norm["tencent"]`、`norm["baostock"]`、`norm["eastmoney_secid"]`、`norm["market"]` 引用，与 Task 1 定义一致。
- `HttpClient.get` 的 `source` 参数取值在各任务中统一为 `tencent`、`eastmoney`、`sec`、`cninfo`、`baostock`、`sina`、`yahoo`。
- `ratios.check_red_flags` 返回的字典键 `code`、`name`、`hit`、`detail`、`veto` 在 Task 6 与 Task 10 中被一致引用。
- `scoring.map_matrix` 返回的 `verdict` 与 `conflict` 在 Task 10 `run` 与 Task 10 `selfcheck.verify` 中一致引用。
- `pricing.buy_range`、`target_price`、`stop_loss` 均返回含 `formula` 键的字典，Task 10 自检据此校验。
- 判定文案常量 `VERDICT_BUY` 等在 Task 6 定义，Task 10 `selfcheck` 通过 `scoring.VERDICT_AVOID` 引用，未硬编码字符串。

**已知取舍**

Task 10 的 `derive_quality_dims` 目前只由红旗命中率推出 `statement` 维度，`profitability` 与 `health` 给固定值 60。原因是三表科目名在新浪源与 yfinance 两侧差异大，需要先跑通真实数据才能确定字段映射。Task 13 Step 6 的人工核对会暴露这一点，届时再补精确映射。这是有意为之的分阶段，不是遗漏。
