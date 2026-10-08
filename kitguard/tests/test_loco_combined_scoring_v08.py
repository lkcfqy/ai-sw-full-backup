"""Synthetic contracts only: no LOCO images, model, or new truth files."""
import copy
import subprocess
import sys

import pytest
from pydantic import ValidationError

from kitguard.app import decide
from kitguard.schemas import Observation, ObservedCounts, Requirements
from scripts.v08 import score_loco_combined as scoring


def test_standalone_scorer_imports_no_production_pixels_or_model_libraries():
    result = subprocess.run([sys.executable, "-I", "-c",
                             ("import runpy,sys;runpy.run_path(sys.argv[1]);"
                              "assert not any(n in sys.modules for n in ['torch','mlx','mlx_vlm','PIL','kitguard'])"),
                             scoring.__file__], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def observation(vector, kind="none", issues=None):
    return {"observed": dict(zip(scoring.PARTS, vector, strict=True)), "issues": issues or [],
            "action": {"kind": kind, "message": "SYNTHETIC CPU", "region": None}}


def cohort():
    return [{"id": f"synthetic-{i:02d}", "source_sha256": f"{i:064x}",
             "ground_truth": dict(zip(scoring.PARTS, group, strict=True))}
            for i, group in enumerate(g for g in scoring.COMBINED_GROUPS for _ in range(6))]


def row(case, obs):
    return {"case_id": case["id"], "source_sha256": case["source_sha256"],
            "state": "completed", "observation": obs}


def test_observation_four_is_valid_but_matched_bom_is_na_not_error():
    case = cohort()[-1]
    obs = observation((2, 4, 0, 0))
    assert ObservedCounts.model_validate(obs["observed"]).nut == 4
    with pytest.raises(ValidationError):
        Requirements.model_validate(obs["observed"])
    scored = scoring.score_case(case, row(case, obs))
    assert scored["outcome"] == "C"
    assert scored["matched_order"] == {"applicability": "not_applicable_due_to_order_limit",
                                        "requirements": None, "decision": None}
    assert scored["normal_order"]["decision"] == "correct"
    assert scored["normal_order"]["correct_adjustment"] is True
    assert scored["all_four_panel"]["mismatched_orders"] == 255
    assert scored["all_four_panel"]["any_false_ready"] is False


def test_clipping_four_to_three_creates_wrong_ready_on_legal_bom():
    case = cohort()[-1]
    scored = scoring.score_case(case, row(case, observation((2, 3, 0, 0))))
    assert scored["outcome"] == "W"
    assert scored["all_four_panel"]["false_ready_orders"] == [dict(zip(scoring.PARTS, (2, 3, 0, 0), strict=True))]
    assert scored["normal_order"]["correct_adjustment"] is False
    bracket_error = scoring.score_case(cohort()[6], row(cohort()[6], observation((2, 1, 3, 1))))
    assert bracket_error["outcome"] == "W"
    assert bracket_error["all_four_panel"]["any_false_ready"] is True
    assert bracket_error["source_supported_panel"]["any_false_ready"] is False


def test_complete_cohort_controls_and_per_image_denominators():
    cases = cohort()
    constant = scoring.summarize(cases, scoring.comparator_rows(cases, "constant_normal"))
    refused = scoring.summarize(cases, scoring.comparator_rows(cases, "always_abstain"))
    assert constant["outcomes"] == dict(zip("CWUEN", (0, 24, 0, 0, 0), strict=True))
    assert refused["outcomes"] == dict(zip("CWUEN", (0, 0, 24, 0, 0), strict=True))
    assert constant["all_four_panel"]["planned_mismatched_orders"] == 6108
    assert constant["source_supported_panel"]["planned_mismatched_orders"] == 1500
    assert constant["all_four_panel"]["observed_any_false_ready_images"] == 24
    assert refused["all_four_panel"]["observed_any_false_ready_images"] == 0
    assert refused["matched_order_correct_ready"] == refused["normal_order_correct_adjustment"] == 0
    assert all(group["planned"] == 6 for group in constant["groups"])
    assert len(scoring.legal_orders()) == 255
    assert len(scoring.legal_orders(scoring.PARTS[:3])) == 63
    assert all(order["bracket"] == 0 for order in scoring.legal_orders(scoring.PARTS[:3]))


def test_exact_counts_keep_all_24_and_only_12_have_matching_orders():
    cases = cohort()
    result = scoring.summarize(cases, [row(c, observation(tuple(c["ground_truth"].values()))) for c in cases])
    assert result["outcomes"]["C"] == 24
    assert result["matched_order_correct_ready"] == 12
    assert result["matched_order_not_applicable"] == 12
    assert result["normal_order_correct_adjustment"] == 24
    assert result["all_four_panel"]["observed_any_false_ready_images"] == 0


def test_failures_and_missing_stay_unmeasured_with_full_denominator():
    cases = cohort()
    failed = row(cases[0], observation((2, 0, 4, 0))) | {"state": "error", "error": "SYNTHETIC failure"}
    malformed = row(cases[1], observation((True, 0, 4, 0)))
    result = scoring.summarize(cases, [failed, malformed])
    assert result["outcomes"] == dict(zip("CWUEN", (0, 0, 0, 2, 22), strict=True))
    assert result["all_four_panel"]["unmeasured_images"] == 24
    assert result["all_four_panel"]["planned_mismatched_orders"] == 6108
    assert all(r["all_four_panel"]["any_false_ready"] is None for r in result["cases"])
    assert all(r["counts_exact"] is None for r in result["cases"])


def test_dropped_cases_normal_pool_and_wrong_source_binding_are_rejected():
    cases = cohort()
    with pytest.raises(ValueError):
        scoring.summarize(cases[:-1], [])
    changed = copy.deepcopy(cases)
    changed[0]["ground_truth"] = dict(scoring.NORMAL)
    with pytest.raises(ValueError):
        scoring.summarize(changed, [])
    wrong = row(cases[0], observation((2, 0, 4, 0))) | {"source_sha256": "f" * 64}
    with pytest.raises(ValueError):
        scoring.score_case(cases[0], wrong)
    with pytest.raises(ValueError):
        scoring.summarize(cases, [row(cases[0], observation((2, 0, 4, 0)))] * 2)


@pytest.mark.parametrize("obs", [observation((2, 4, 0, 0)), observation((2, 3, 0, 0)),
                                observation((2, 2, 2, 0)), observation((2, None, 2, 0)),
                                observation((2, 1, 3, 0), "manual"),
                                observation((2, 1, 3, 0), issues=["unclear"])])
def test_projection_matches_real_decide_on_all_255_legal_boms(obs):
    parsed = Observation.model_validate(obs)
    for requirement in scoring.legal_orders():
        Requirements.model_validate(requirement)
        snapshot = {"id": "synthetic", "revision": 1, "requirements": requirement, "checks": []}
        actual = decide(snapshot, parsed, "synthetic-photo", 0)["decision"]
        assert scoring.decision(scoring.projection(obs), requirement) == actual
