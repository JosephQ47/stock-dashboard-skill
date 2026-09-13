import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sources_hk_us as SHU


# ---- _transpose_statement：yfinance 报表 DataFrame -> A 股同形状 list[dict] ----
# yfinance 的真实返回：行 = 科目名（字符串索引），列 = 各期期末日期
# （pandas.Timestamp），且列在源数据里已经是新→旧排列——但本函数不能依赖
# 这个「实测确实如此」的隐含顺序，必须自己显式按日期降序排序，这里故意把
# 列打乱（旧的排前面）来验证这一点，而不是拿一个已经有序的 fixture蒙混过关。

def _yf_like_frame():
    # 列刻意乱序：最旧的放最前面，中间夹一个乱入的，最新的放最后。
    cols = [
        pd.Timestamp("2022-09-30"),
        pd.Timestamp("2024-09-30"),
        pd.Timestamp("2023-09-30"),
    ]
    data = {
        cols[0]: {"Total Assets": 800.0, "Goodwill": 50.0},
        cols[1]: {"Total Assets": 1000.0, "Goodwill": float("nan")},
        cols[2]: {"Total Assets": 900.0, "Goodwill": 50.0},
    }
    return pd.DataFrame(data)


def test_transpose_orders_newest_first_regardless_of_input_column_order():
    df = _yf_like_frame()
    rows = SHU._transpose_statement(df)
    assert [r["报告日"] for r in rows] == ["20240930", "20230930", "20220930"]


def test_transpose_preserves_field_values_per_period():
    df = _yf_like_frame()
    rows = SHU._transpose_statement(df)
    newest = rows[0]
    assert newest["报告日"] == "20240930"
    assert newest["Total Assets"] == 1000.0
    import math
    assert math.isnan(newest["Goodwill"])

    oldest = rows[-1]
    assert oldest["报告日"] == "20220930"
    assert oldest["Total Assets"] == 800.0
    assert oldest["Goodwill"] == 50.0


def test_transpose_date_format_is_yyyymmdd_string_like_sina_source():
    # 下游 compute.extract_derived 用「报告日」字符串按 1231/其它后缀做年报
    # 判定与同比对齐，必须是 YYYYMMDD 字符串，不能是 Timestamp 或其它格式。
    df = _yf_like_frame()
    rows = SHU._transpose_statement(df)
    for r in rows:
        assert isinstance(r["报告日"], str)
        assert len(r["报告日"]) == 8
        assert r["报告日"].isdigit()


def test_transpose_empty_dataframe_returns_empty_list():
    assert SHU._transpose_statement(pd.DataFrame()) == []


def test_transpose_none_returns_empty_list():
    assert SHU._transpose_statement(None) == []


def test_transpose_non_timestamp_column_falls_back_to_str():
    # 极端情况下列不是 Timestamp（比如已经是字符串）时，不应崩溃，直接
    # str() 一下；排序仍按字符串排序生效。
    df = pd.DataFrame({"20230930": {"Total Assets": 1.0}, "20240930": {"Total Assets": 2.0}})
    rows = SHU._transpose_statement(df)
    assert [r["报告日"] for r in rows] == ["20240930", "20230930"]
