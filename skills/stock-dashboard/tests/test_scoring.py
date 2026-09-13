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


def test_conflict_distinguishes_44_9_from_45_0():
    conflict_44_9 = S.map_matrix(44.9, 60, False)["conflict"]
    conflict_45_0 = S.map_matrix(45.0, 60, False)["conflict"]
    assert conflict_44_9 != conflict_45_0
    assert "44.9" in conflict_44_9
    assert "45.0" in conflict_45_0


# ---- 证据（evidence）：quality_score/timing_score 必须报出实际有多少权重在场 ----

def test_quality_score_reports_evidence_fraction():
    dims = {k: 100 for k in S.QUALITY_WEIGHTS}
    r = S.quality_score(dims)
    assert r["evidence"] == pytest.approx(1.0)
    assert r["dims_present"] == len(S.QUALITY_WEIGHTS)
    assert r["dims_total"] == len(S.QUALITY_WEIGHTS)


def test_quality_score_thin_evidence_single_dim():
    r = S.quality_score({"statement": 100})
    assert r["score"] == pytest.approx(100.0)
    assert r["evidence"] == pytest.approx(S.QUALITY_WEIGHTS["statement"] / 100.0)
    assert r["dims_present"] == 1


def test_quality_score_all_missing_has_zero_evidence():
    r = S.quality_score({})
    assert r["evidence"] == 0.0
    assert r["dims_present"] == 0
    assert r["dims_total"] == len(S.QUALITY_WEIGHTS)


def test_timing_score_reports_evidence_fraction():
    dims = {"trend": 50}
    r = S.timing_score(dims)
    assert r["evidence"] == pytest.approx(S.TIMING_WEIGHTS["trend"] / 100.0)
    assert r["dims_present"] == 1


# ---- map_matrix: 证据单薄时不得断言基本面达标/太弱，只能说证据不足 ----

def test_map_matrix_without_evidence_arg_keeps_old_behavior():
    # 不传 q_dims_present 时（旧调用方式），行为必须与修复前完全一致。
    r = S.map_matrix(80, 40, False)
    assert r["verdict"] == S.VERDICT_WATCH
    assert "基本面达标" in r["conflict"]


def test_map_matrix_thin_evidence_watch_reports_insufficient_not_sound():
    # 复现报告里的注入场景：Q=100 但只有 1 个维度在场，T 未转好。
    r = S.map_matrix(100.0, 54.89, False, q_dims_present=1)
    assert r["verdict"] == S.VERDICT_WATCH  # 结论本身不变
    assert "基本面达标" not in r["conflict"]
    assert "证据" in r["conflict"] and ("单薄" in r["conflict"] or "不足" in r["conflict"])


def test_map_matrix_thin_evidence_enough_dims_keeps_sound_claim():
    # 维度数达到下限时，恢复原来的「达标」措辞。
    r = S.map_matrix(80, 40, False, q_dims_present=S.QUALITY_MIN_DIMS_FOR_CLAIM)
    assert "基本面达标" in r["conflict"]


def test_map_matrix_mirror_case_thin_evidence_does_not_assert_weak():
    # 镜像场景：0 个质量维度在场，T 高，旧代码会断言「基本面太弱不足投资」，
    # 修复后必须改成「证据不足」，不能替一个从未评估过的基本面下结论。
    r = S.map_matrix(0.0, 69.5, False, q_dims_present=0)
    assert r["verdict"] == S.VERDICT_AVOID
    assert "太弱" not in r["conflict"]
    assert "证据" in r["conflict"]


def test_map_matrix_mirror_case_thin_evidence_speculation_branch():
    r = S.map_matrix(50.0, 80.0, False, q_dims_present=1)
    assert r["verdict"] == S.VERDICT_SPEC
    assert "不达标" not in r["conflict"]
    assert "证据" in r["conflict"]
