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
