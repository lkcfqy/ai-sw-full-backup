"""Scope tampering in synthetic extensions of a recorded engineering export."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_study_export import digest, same_metrics, verify_payload

EXAMPLE = Path(__file__).resolve().parents[1] / "test-results/browser/field-study-v04/engineering-study-export.json"


@pytest.fixture
def scoped():
    payload = json.loads(EXAMPLE.read_text())
    study = payload["study"]
    study["protocol"]["inspection_scope_policy"] = "operator_region_v1"
    study["protocol_sha256"] = digest(study["protocol"])
    for case in study["cases"]:
        root_sha = hashlib.sha256(("synthetic_root_" + case["id"]).encode()).hexdigest()
        scope = {
            "mode": "region", "view_photo_id": case["photo_id"], "view_sha256": case["photo_sha256"],
            "root_photo_id": "root_" + case["id"], "root_photo_sha256": root_sha,
            "source_family_sha256": root_sha, "root_width": 300, "root_height": 200,
            "root_source_sha256": None, "root_created_at": case["registered_at"],
            "region_xyxy": [20, 30, 220, 130],
            "coordinate_space": "normalized_root_pixels_xyxy_half_open_v1",
            "derivation": "pillow_root_crop_rgb_jpeg95_v1",
            "scope_declaration": "operator_all_required_items_inside", "scope_confirmed_at": case["registered_at"],
        }
        case["inspection_scope"] = scope
        case["source_family_sha256"] = root_sha
        for trial in case["trials"].values():
            if not trial:
                continue
            checks = trial["evidence"]["checks"] + ([trial["check"]] if trial.get("check") else [])
            for check in checks:
                check["source_family_sha256"] = root_sha
                check["inspection_scope"] = {**copy.deepcopy(scope), "view_photo_id": check["photo_id"],
                                              "view_sha256": check["photo_sha256"]}
    return payload


def test_synthetic_declared_region_export_is_internally_consistent(scoped):
    result = verify_payload(scoped)
    assert result["status"] == "verified_internal_consistency", result
    assert result["photo_bytes_verified"] is False and result["physical_authenticity_verified"] is False


def test_json_client_numeric_spelling_keeps_ratios_but_not_boolean_or_float_counts():
    expected = {"correct": 1, "correct_fraction": 1.0, "timing": {"median": 12}}
    assert same_metrics({"correct": 1, "correct_fraction": 1, "timing": {"median": 12.0}}, expected)
    assert not same_metrics({"correct": True, "correct_fraction": 1, "timing": {"median": 12}}, expected)
    assert not same_metrics({"correct": 1.0, "correct_fraction": 1, "timing": {"median": 12}}, expected)
    assert not same_metrics({"correct": 1, "correct_fraction": True, "timing": {"median": 12}}, expected)


def test_equivalent_median_number_is_accepted_in_complete_export(scoped):
    for value in scoped["study"]["report"]["methods"].values():
        for name in ("terminal_elapsed_ms", "completed_elapsed_ms"):
            if value[name]["median"] is not None:
                value[name]["median"] = float(value[name]["median"])
    assert verify_payload(scoped)["status"] == "verified_internal_consistency"


@pytest.mark.parametrize("field,value", [
    ("region_xyxy", [True, 30, 220, 130]), ("region_xyxy", [20.0, 30, 220, 130]),
    ("region_xyxy", [20, 30, 220]), ("region_xyxy", [20, 30, 400, 130]),
    ("region_xyxy", [20, 30, 40, 130]), ("region_xyxy", [-1, 30, 220, 130]),
    ("root_width", True), ("root_width", 31), ("root_width", 8193),
    ("scope_declaration", None), ("scope_confirmed_at", None),
    ("scope_confirmed_at", "2000-01-01T00:00:00+00:00"),
    ("scope_confirmed_at", "2099-01-01T00:00:00+00:00"),
    ("root_created_at", "2099-01-01T00:00:00+00:00"),
    ("root_created_at", ""), ("root_created_at", False),
    ("root_photo_sha256", "0"*64), ("source_family_sha256", "1"*64),
    ("view_sha256", "2"*64), ("view_photo_id", "not_the_view"),
    ("coordinate_space", "browser_css_pixels"), ("derivation", "lossless_crop"),
])
def test_modified_scope_is_rejected(scoped, field, value):
    scoped["study"]["cases"][0]["inspection_scope"][field] = value
    assert verify_payload(scoped)["status"] == "invalid"


def test_scope_policy_prevents_silent_removal_of_case_bindings(scoped):
    del scoped["study"]["cases"][0]["inspection_scope"]
    assert verify_payload(scoped)["status"] == "invalid"


def test_crop_cannot_claim_it_is_its_own_root(scoped):
    case = scoped["study"]["cases"][0]
    case["inspection_scope"]["root_photo_id"] = case["photo_id"]
    assert verify_payload(scoped)["status"] == "invalid"


def test_selected_check_cannot_claim_a_different_valid_rectangle(scoped):
    case = scoped["study"]["cases"][0]
    trial = case["trials"]["kitguard"]
    trial["check"]["inspection_scope"]["region_xyxy"] = [30, 40, 230, 140]
    trial["evidence"]["checks"][0]["inspection_scope"]["region_xyxy"] = [30, 40, 230, 140]
    assert verify_payload(scoped)["status"] == "invalid"


def test_whole_image_cannot_use_different_bytes_from_root(scoped):
    scope = scoped["study"]["cases"][0]["inspection_scope"]
    scope.update(mode="whole_image", region_xyxy=None, derivation="normalized_root_bytes_v1")
    assert verify_payload(scoped)["status"] == "invalid"


def test_exact_root_reupload_alias_cannot_inflate_independent_cases(scoped):
    cases = scoped["study"]["cases"]
    cases[1]["inspection_scope"]["root_source_sha256"] = cases[0]["inspection_scope"]["root_photo_sha256"]
    assert verify_payload(scoped)["status"] == "invalid"


def test_restored_whole_image_with_declaration_is_supported(scoped):
    # These modifications make the entire synthetic example use a declared restored root.
    for case in scoped["study"]["cases"]:
        scope = case["inspection_scope"]
        scope.update(mode="whole_image", region_xyxy=None, derivation="normalized_root_bytes_v1",
                     root_photo_sha256=case["photo_sha256"], source_family_sha256=case["photo_sha256"])
        case["source_family_sha256"] = case["photo_sha256"]
        for trial in case["trials"].values():
            if trial:
                for check in trial["evidence"]["checks"] + ([trial["check"]] if trial.get("check") else []):
                    check["inspection_scope"] = copy.deepcopy(scope)
                    check["source_family_sha256"] = case["source_family_sha256"]
    result = verify_payload(scoped)
    assert result["status"] == "verified_internal_consistency", result
