import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sources_cn as SC


# ---- _slice_with_annuals：年报切片喂给「连续两年净现比偏低」的一票否决 ----
# 新浪源报表新→旧排列，年报以「报告日」1231 结尾识别。

def _df(dates):
    return pd.DataFrame({"报告日": dates, "值": list(range(len(dates)))})


def test_slice_stops_right_after_third_annual_by_default():
    # 3 个年报 + 中间夹杂的季报，默认 min_annuals=3：应切到第 3 个年报（含）
    # 为止，不多不少。
    dates = [
        "20241231", "20240930", "20240630", "20240331",
        "20231231", "20230930",
        "20221231", "20220930",
        "20211231",
    ]
    df = _df(dates)
    sliced, periods, annuals = SC._slice_with_annuals(df, min_annuals=3)
    assert annuals == 3
    assert periods == 7  # 到 20221231（第 3 个年报）为止，共 7 行
    assert list(sliced["报告日"]) == dates[:7]


def test_slice_with_fewer_than_min_annuals_returns_whole_table():
    # 全表年报数不足 min_annuals：如实返回全表与实际年报数，不能补全或截断。
    dates = ["20241231", "20240930", "20231231"]
    df = _df(dates)
    sliced, periods, annuals = SC._slice_with_annuals(df, min_annuals=3)
    assert annuals == 2
    assert periods == len(dates)
    assert list(sliced["报告日"]) == dates


def test_slice_exact_min_annuals_boundary():
    # 恰好有 2 个年报、min_annuals=2：切到第 2 个年报（含）为止。
    dates = ["20241231", "20240930", "20231231", "20220930"]
    df = _df(dates)
    sliced, periods, annuals = SC._slice_with_annuals(df, min_annuals=2)
    assert annuals == 2
    assert periods == 3
    assert list(sliced["报告日"]) == dates[:3]


def test_slice_empty_dataframe_returns_zero_counts():
    df = pd.DataFrame({"报告日": [], "值": []})
    sliced, periods, annuals = SC._slice_with_annuals(df)
    assert periods == 0
    assert annuals == 0
    assert len(sliced) == 0


def test_slice_none_dataframe_passes_through():
    sliced, periods, annuals = SC._slice_with_annuals(None)
    assert sliced is None
    assert periods == 0
    assert annuals == 0


def test_slice_missing_date_column_passes_through_unsliced():
    df = pd.DataFrame({"其它列": [1, 2, 3]})
    sliced, periods, annuals = SC._slice_with_annuals(df)
    assert periods == 0
    assert annuals == 0
    assert sliced is df
