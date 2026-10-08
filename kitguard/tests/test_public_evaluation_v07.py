"""Check novel-source selection and paired-risk denominators without a model."""
import copy
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from scripts.v07.analyze_public_paired import CANDIDATE_MODE, MODES, analyze, orders
from scripts.v07.prepare_public_evaluation import select_views, verify_crop
from scripts.v07.run_public_paired import ROOT, engine_factory, schedule, source_hashes


def case(number):
    return {"id": f"c{number}", "source_id": f"s{number}", "image": f"{number}.png",
            "sha256": f"{number:064x}", "split": "holdout", "subgroup": "screws",
            "supported_positive_classes": ["bolt", "nut"],
            "ground_truth": {"bolt": 2, "nut": 1, "washer": 0, "bracket": 0}}


def record(item, mode, *, changes=None, uncertain=False, error=None):
    counts = dict(item["ground_truth"]) | (changes or {})
    observation = {"observed": counts, "issues": ["unclear"] if uncertain else [],
                   "action": {"kind": "recapture" if uncertain else "none", "message": "fixture", "region": None},
                   "backend": "test"}
    return {"case_id": item["id"], "source_id": item["source_id"], "sha256": item["sha256"],
            "mode": mode, "observation": observation, "latency_ms": 1000, "error": error, "loaded_before": True}


def test_entire_plan_denominator_includes_missing_failed_and_uncertain():
    cases = [case(i) for i in range(1, 5)]
    rows = [record(cases[0], "spatial_guarded"),
            record(cases[1], "spatial_guarded", uncertain=True),
            record(cases[2], "spatial_guarded", error="model failed")]
    summary = analyze({"cases": cases}, rows)
    guarded = summary["modes"]["spatial_guarded"]["all"]
    assert guarded["outcomes"] == {"C": 1, "W": 0, "U": 1, "E": 1, "N": 1}
    assert guarded["correct_actionable_rate"] == .25
    assert guarded["false_ready_denominator"] == 4
    assert guarded["unmeasured_risk_images"] == 2
    assert summary["engineering_acceptance_passed"] is False


def test_false_ready_panel_catches_unsupported_category_hallucination():
    item = case(1)
    summary = analyze({"cases": [item]}, [record(item, "spatial_guarded", changes={"bracket": 1})])
    result = summary["modes"]["spatial_guarded"]["all"]
    assert result["outcomes"]["W"] == 1
    assert result["any_false_ready_images"] == 1
    assert result["source_supported_any_false_ready_images"] == 0
    assert len(list(orders(("bolt", "nut", "washer", "bracket")))) == 255


def test_exact_uncertain_is_not_correct_actionable_or_false_ready():
    item = case(1)
    result = analyze({"cases": [item]}, [record(item, "spatial_guarded", uncertain=True)])
    assert result["modes"]["spatial_guarded"]["all"]["outcomes"]["U"] == 1
    assert result["modes"]["spatial_guarded"]["all"]["any_false_ready_images"] == 0


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_source", "unknown_case", "unknown_mode"])
def test_rejects_mismatched_or_duplicate_result_rows(mutation):
    item = case(1)
    row = record(item, "spatial_guarded")
    rows = [row]
    if mutation == "duplicate":
        rows.append(copy.deepcopy(row))
    elif mutation == "wrong_source":
        row["sha256"] = "0" * 64
    elif mutation == "unknown_case":
        row["case_id"] = "outside-plan"
    else:
        row["mode"] = "unfrozen"
    with pytest.raises(ValueError):
        analyze({"cases": [item]}, rows)


def test_paired_run_order_alternates_without_omitting_any_attempt():
    items = [case(i) for i in range(1, 4)]
    planned = schedule(items)
    assert len(planned) == 6
    assert [mode for _, mode, _ in planned] == ["spatial_inventory", "spatial_guarded", "spatial_guarded", "spatial_inventory", "spatial_inventory", "spatial_guarded"]


def test_three_method_schedule_balances_every_position_across_51_photos():
    methods = (*MODES, CANDIDATE_MODE)
    plan = schedule([case(i) for i in range(1, 52)], methods)
    assert len(plan) == 153
    assert set(Counter((mode, position) for _, mode, position in plan).values()) == {17}
    assert len({(c["id"], mode) for c, mode, _ in plan}) == 153


def test_optional_candidate_keeps_full_plan_and_same_acceptance_gates():
    item = case(1)
    methods = (*MODES, CANDIDATE_MODE)
    result = analyze({"cases": [item]}, [record(item, mode) for mode in MODES], modes=methods)
    assert result["modes"][CANDIDATE_MODE]["all"]["outcomes"]["N"] == 1
    assert result["comparisons_vs_inventory"][CANDIDATE_MODE]["engineering_acceptance_passed"] is False


@pytest.mark.parametrize("candidate_ms,passes", [(800, True), (801, False)])
def test_candidate_further_validation_requires_20_percent_speed_gain(candidate_ms, passes):
    item = case(1)
    methods = (*MODES, CANDIDATE_MODE)
    rows = [record(item, mode) for mode in methods]
    rows[-1]["latency_ms"] = candidate_ms
    result = analyze({"cases": [item]}, rows, modes=methods)
    gate = result["selective_identity_further_validation_gate"]
    assert gate["eligible_for_further_validation"] is passes
    assert gate["automatic_promotion"] is False


def test_candidate_speed_cannot_make_up_for_correct_coverage_loss():
    items = [case(i) for i in range(1, 11)]
    methods = (*MODES, CANDIDATE_MODE)
    rows = [record(item, mode) for item in items for mode in methods]
    for row in rows:
        if row["mode"] == CANDIDATE_MODE:
            row["latency_ms"] = 100
    rows[-1] = record(items[-1], CANDIDATE_MODE, uncertain=True)
    result = analyze({"cases": items}, rows, modes=methods)
    gate = result["selective_identity_further_validation_gate"]
    assert gate["checks"]["coverage_at_least_90_percent"] is True
    assert gate["checks"]["correct_actionable_no_lower_than_guarded"] is False
    assert gate["eligible_for_further_validation"] is False


def test_all_methods_share_identical_recording_boundary_without_loading_model():
    from scripts.probe_selective_identity import SelectiveIdentityVision

    methods = (*MODES, CANDIDATE_MODE)
    engines = engine_factory(methods)
    for method, engine in engines.items():
        assert engine._generate.__func__ is SelectiveIdentityVision._generate
        assert engine.status()["observation_mode"] == method


def test_source_selection_chooses_one_view_and_is_input_order_independent():
    views = [{"id": f"v{source}-{variant}", "source_sha256": source,
              "ground_truth": {"bolt": variant, "nut": 1, "washer": 0, "bracket": 0}}
             for source in ("a", "b", "c") for variant in (1, 2)]
    result = select_views(views)
    assert result == select_views(list(reversed(views)))
    assert len(result) == len({v["source_sha256"] for v in result}) == 3


def test_rotated_author_boundary_is_checked_instead_of_center_only():
    view = {"crop_xyxy": [0, 0, 100, 100], "source_width": 200, "source_height": 200,
            "included_annotation_ids": [1], "excluded_annotation_ids": [],
            "ground_truth": {"bolt": 1, "nut": 0, "washer": 0, "bracket": 0}}
    ann = {1: {"bbox": [50, 50, 20, 20, .4], "category_id": 1}}
    verify_crop(view, ann)
    ann[1]["bbox"][1] = 80
    with pytest.raises(ValueError, match="safety margin"):
        verify_crop(view, ann)


def test_all_correct_baseline_is_not_evidence_of_safety_improvement():
    item = case(1)
    result = analyze({"cases": [item]}, [record(item, mode) for mode in ("spatial_inventory", "spatial_guarded")])
    assert result["engineering_acceptance_passed"] is True
    assert result["descriptive_safety_advantage_observed"] is False
    assert result["default_change_authorized_by_this_report"] is False


def test_frozen_snapshot_import_is_isolated_and_does_not_load_model(tmp_path):
    snapshot = tmp_path / "snapshot"
    expected = source_hashes()
    for relative in expected:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    fixture = tmp_path / "engineering.png"
    Image.new("RGB", (64, 64), "white").save(fixture)
    entry = (
        "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "from scripts.v07.run_public_paired import ROOT,source_hashes;"
        "from scripts.run_benchmark import app_upload_bytes;"
        "from kitguard import vision;"
        "normalized=app_upload_bytes(Path(sys.argv[2]));"
        "print(json.dumps({'root':str(ROOT),'hashes':source_hashes(),"
        "'model_loaded':vision._RUNTIME is not None,'isolated':bool(sys.flags.isolated),"
        "'normalized_jpeg':normalized[:2]==bytes([255,216])}))"
    )
    result = subprocess.run([sys.executable, "-I", "-c", entry, str(snapshot), str(fixture)],
                            capture_output=True, text=True, check=True, cwd=ROOT)
    report = json.loads(result.stdout)
    assert Path(report["root"]) == snapshot
    assert report["hashes"] == expected
    assert report["model_loaded"] is False
    assert report["isolated"] is True
    assert report["normalized_jpeg"] is True
