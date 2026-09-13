# 数据源与降级链

本文件是取数阶段的方法论依据。数字与规则全部来自 `scripts/endpoints.py`、
`scripts/http_client.py`、`scripts/sources_cn.py`、`scripts/sources_hk_us.py`、
`scripts/fetch_data.py` 的实际实现，以及 2026-09-13 的实测记录
（`docs/research/2026-09-13-04-数据接口实测报告.md`）。取数失败时按本文件的
降级顺序处理，不要凭经验另选源。

## 核心实测结论

东财接口会按源 IP 整体限流：本次测试中同一批接口首轮全部可达，几分钟后无论
经由 akshare 封装还是裸 HTTP 直连，全部不可达，且恢复时间未知。这不是库的
问题，是服务端封禁。因此东财不得出现在任何关键路径的首选位置，降级链中也
不得同时放两个东财源——那等于没有降级。腾讯与 baostock 在同一时段全程稳定，
这是行情走腾讯优先、K 线走 baostock 优先的直接依据。

## 三市场数据源优先级表

以下表格原样对应 spec 第 4.2 节，来自实测而非纸面设计：

| 数据类 | 首选 | 降级 1 | 降级 2 |
|---|---|---|---|
| A股 实时行情 | 腾讯 qt.gtimg.cn | 新浪 | 东财 push2 |
| A股 历史 K 线 | baostock | 腾讯 | 东财 push2his |
| A股 三大报表 | akshare 新浪源 `stock_financial_report_sina` | akshare 同花顺源 | 巨潮公告人工核查 |
| A股 财务指标 | akshare `stock_financial_analysis_indicator` | 由三表自算 | — |
| A股 业绩预告 | akshare `stock_yjyg_em` | 巨潮公告 | — |
| A股 龙虎榜、两融、解禁 | akshare 东财源 | 交易所官网 | 标注未获取到 |
| 港股 行情 | 腾讯 hk | yfinance | akshare 港股 |
| 美股 行情与财务 | yfinance | SEC EDGAR | — |
| 美股 权威财务 | SEC companyconcept / submissions | — | — |
| 公告全文 | 巨潮（POST） | 交易所官网 | — |

当前 `scripts/sources_cn.py`、`scripts/sources_hk_us.py` 的实际降级实现：

- A 股行情 `fetch_quote`：先腾讯，失败则东财 push2（两级，均由 `HttpClient`
  统一限速与熔断保护），无新浪兜底档。
- A 股 K 线 `fetch_kline`：先 baostock，失败或空结果则东财 push2his；不设腾讯
  中间档。
- 港股/美股行情 `fetch_quote`：港股先腾讯 hk 再 yfinance；美股直接 yfinance。
- 港股/美股 K 线与财务：统一走 yfinance，无东财或 SEC 兜底档；美股财务的
  SEC 补充目前仅体现在方法论层面，`sources_hk_us.py` 尚未接入 SEC 数据抓取。

写方法论文件时以 spec 表格为设计意图基准，但描述实际行为时以脚本为准，二者
不一致处见文末「已知偏差」。

## 可靠性三档分类

- **高可靠**：腾讯行情、baostock、yfinance、SEC EDGAR、巨潮 POST、akshare
  新浪源财务。本次实测中全程稳定。
- **中可靠**：akshare 的业绩预告与龙虎榜。依赖东财数据源，本次可用但同属
  高风险源。
- **低可靠**：东财全部行情接口。本次测试中被限流后整体不可达。

龙虎榜、两融、解禁属于东财独有数据，取不到时直接标注「未获取到」并给出交易
所官网核查链接，不阻断看板主流程——这些是软数据或辅助项，缺失不影响双轴评
分主干。

## 东财限速与熔断规则

来自 `scripts/endpoints.py` 与 `scripts/http_client.py` 的常量与实现：

- 东财请求间隔下限：`EM_MIN_INTERVAL = 2.0` 秒
- 单次运行对东财的调用上限：`EM_MAX_CALLS = 10` 次，达到上限即熔断
- 其他数据源的默认调用间隔下限：`DEFAULT_MIN_INTERVAL = 1.0` 秒
- 命中连接失败（`ConnectionError`/`Timeout`）时，该源立即被标记熔断
  （`self._tripped.add(source)`），本次运行内不再对该源发起任何请求
- 熔断状态按 `source` 名维护，不是全局熔断——例如东财熔断不影响腾讯

**重要架构限制**：以上限速、调用上限与熔断保护，只作用于经由
`HttpClient.get`/`HttpClient.post` 发出的请求。`sources_cn.py` 中
`fetch_market_extras`（龙虎榜 `stock_lhb_detail_em`）与 `fetch_financials`
（`stock_financial_analysis_indicator`、`stock_financial_report_sina` 等）里
对 akshare 函数的调用，由 akshare 内部自行发起 HTTP 请求，完全绕开
`HttpClient`。这意味着：

- 这些 akshare 调用不计入东财的 10 次调用上限，也不受 2 秒间隔约束
- 即使 `HttpClient` 已判定东财熔断，这些 akshare 调用仍可能持续向东财发起请求
- 这些调用的失败不会触发熔断机制

这是当前实现的架构层面限制，本任务范围内未做处理，取数时如果观察到耗时异常
长或反复失败，应联想到这一点，而不是误以为熔断没生效。

## 巨潮必须 POST

`CNINFO_SEARCH`（`topSearch/query`）与 `CNINFO_ANNOUNCE`（`hisAnnouncement/query`）
都必须用 POST，且请求头需包含 `Content-Type: application/x-www-form-urlencoded`
（对应 `endpoints.FORM_HEADERS`）。用 GET 请求会返回 HTTP 500，不是查询参数
问题，是接口本身只接受 POST。

## SEC 必须带姓名邮箱 UA

SEC 的接口（`SEC_SUBMISSIONS`、`SEC_CONCEPT`）要求 `User-Agent` 中包含真实
姓名与邮箱，否则拒绝访问。当前实现中固定使用
`endpoints.SEC_UA = {"User-Agent": "Robin Quan robin.quan@potentia.ai"}`，
已通过实测验证可用。不要替换成通用字符串（如 `python-requests/x.x`），会被拒。

## 北向资金字段禁令

北向资金日频买卖明细自 2024-08-19 起官方已停止披露。看板任何位置都不得出现
「北向资金」「北向净流入」等相关字段或数值，包括在市场特有项、软数据区、
多空理由中——即使某个数据源仍返回历史遗留字段，也必须过滤掉，不得引用。

## 硬数据与软数据

- **硬数据**：交易所披露的行情、财报、龙虎榜、两融，来自 `source` 字段标为
  官方或准官方来源的数据。
- **软数据**：主力资金流、筹码分布、千股千评等衍生或估算指标，必须在看板中
  单独分区并附带口径警告，不得与硬数据混排。

每条数据都带 `source` 与 `fetched_at` 字段（见各 `fetch_*` 函数返回值），
写看板时原样引用这两个字段，不要省略。

## 取数失败的处理顺序

取数失败或结果异常时，先运行：

```
python scripts/doctor.py
```

逐项检查解释器、依赖库、网络连通性、各数据源可用性，根据 `doctor.py` 输出
判断走降级链的哪一档，而不是对同一个源反复重试。实测证明数据源可用性会随
时间与 IP 状态变化，不能假设它们都在；`doctor.py` 存在的意义就是把这个不确
定性显式探测出来，而不是靠猜测或反复试错去发现。

## 已知偏差记录

写作本文件时对照 spec 第 4.2 节与脚本实现发现：spec 表格中「A股 实时行情」
写着「腾讯 → 新浪 → 东财」三档，但 `sources_cn.fetch_quote` 的实际实现只有
「腾讯 → 东财」两档，没有新浪中间档；「港股 行情」表格写「腾讯 → yfinance →
akshare 港股」三档，`sources_hk_us.fetch_quote` 实际只有「腾讯 → yfinance」
两档，没有 akshare 港股兜底。以实际脚本行为为准，方法论描述已按此更正。
