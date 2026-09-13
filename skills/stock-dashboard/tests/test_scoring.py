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


def test_quality_breakdown_sums_to_score_with_partial_dims():
    dims = {"statement": 100, "profitability": 0}
    r = S.quality_score(dims)
    # breakdown sum may have more precision than score (which is rounded to 2 decimals)
    assert sum(r["breakdown"].values()) == pytest.approx(r["score"], abs=0.01)


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
    r = S.map_matrix(30, 30, False)
    assert r["verdict"] == "回避"
    assert r["conflict"] is None


def test_veto_forces_avoid_regardless():
    assert S.map_matrix(95, 95, True)["verdict"] == "回避"


def test_conflict_reported_when_quality_high_timing_low():
    r = S.map_matrix(80, 40, False)
    assert r["conflict"] and "基本面" in r["conflict"]


def test_conflict_reported_when_timing_high_quality_low_speculation():
    r = S.map_matrix(50, 80, False)
    assert r["verdict"] == "短线博弈，不是投资"
    assert r["conflict"] and "技术面强势" in r["conflict"]
    assert "是博弈不是投资" in r["conflict"]


def test_conflict_reported_when_timing_high_quality_low_avoid():
    r = S.map_matrix(40, 80, False)
    assert r["verdict"] == "回避"
    assert r["conflict"] and "技术面强势" in r["conflict"]
    assert "坚决回避" in r["conflict"]


def test_no_conflict_when_aligned():
    assert S.map_matrix(80, 80, False)["conflict"] is None


def test_boundary_sixty_counts_as_high():
    assert S.map_matrix(60, 60, False)["verdict"] == "重点关注，可建仓"


def test_boundary_fortyfive_is_speculation_not_avoid():
    assert S.map_matrix(45, 70, False)["verdict"] == "短线博弈，不是投资"


def test_boundary_59_9_high_timing_not_high_quality():
    assert S.map_matrix(59.9, 60, False)["verdict"] == "短线博弈，不是投资"


def test_boundary_60_high_quality_not_high_timing():
    assert S.map_matrix(60, 59.9, False)["verdict"] == "加入候选池，等技术面转好"


def test_boundary_45_high_timing_speculation_floor():
    assert S.map_matrix(45, 60, False)["verdict"] == "短线博弈，不是投资"


def test_boundary_44_9_high_timing_below_speculation_floor():
    assert S.map_matrix(44.9, 60, False)["verdict"] == "回避"


def test_boundary_45_below_high_timing():
    assert S.map_matrix(45, 59.9, False)["verdict"] == "回避"
