"""Reference phase, failure denominators and immutable-source contracts; no MLX/model calls."""
import copy
import json
import subprocess
import sys

import pytest

from kitguard.evaluation import score_case
from scripts.v08 import run_reference_guarded as r


def approval():
    return {"schema": "kitguard.v08.class-references-approved.v1", "status": "approved_for_development_inference",
            "selected_without_candidate_predictions": True, "no_count_or_order_overlays": True,
            "items": [{"part": p, "single_object_ai_reviewed": True, "label_basis": "author projection",
                       "notes": "AI boundary QA, not human/thread certification", "crop_xyxy": [0, 0, 10, 10]}
                      for p in ("nut", "washer")]}


@pytest.mark.parametrize("change", ["pending", "outcome_selected", "overlay", "missing_washer", "no_qa", "bad_crop"])
def test_approval_fail_closed(change):
    a = approval()
    r.validate_approval(a)
    if change == "pending":
        a["status"] = "pending"
    elif change == "outcome_selected":
        a["selected_without_candidate_predictions"] = False
    elif change == "overlay":
        a["no_count_or_order_overlays"] = False
    elif change == "missing_washer":
        a["items"].pop()
    elif change == "no_qa":
        a["items"][0]["single_object_ai_reviewed"] = False
    else:
        a["items"][0]["crop_xyxy"][0] = .5
    with pytest.raises(ValueError):
        r.validate_approval(a)


def calls(tmp_path):
    files = []
    for name in ("target", "nut", "washer", "identity_crop"):
        p = tmp_path / name
        p.write_bytes(name.encode())
        files.append({"path": name, "sha256": r.sha(p)})
    spatial = {"schema": "SpatialInventory", "images": files[:3], "max_tokens": 900, "temperature": 0,
               "status": "parsed", "prompt": "reference for nut; do NOT count it\nreference for washer; do NOT count it"}
    identity = {"schema": "IdentityResponse", "images": [files[0], files[3]], "max_tokens": 1800,
                "temperature": 0, "status": "parsed", "prompt": "Inspect candidate crops"}
    refs = {p: {"prepared_sha256": files[i]["sha256"]} for i, p in enumerate(("nut", "washer"), 1)}
    return {"generation_calls": [spatial, copy.deepcopy(spatial), identity]}, refs


def test_two_spatial_reference_calls_and_reference_free_identity(tmp_path):
    diag, refs = calls(tmp_path)
    assert r.check_reference_stages(diag, refs, tmp_path, True) == {
        "spatial_calls": 2, "identity_calls": 1, "reference_stage_contract_passed": True}
    diag["generation_calls"].pop()
    assert r.check_reference_stages(diag, refs, tmp_path, True)["identity_calls"] == 0


@pytest.mark.parametrize("mutation", ["identity_reference", "missing_reference", "reordered", "extra_call", "unparsed", "changed_file"])
def test_reference_stage_contract_rejects_scope_or_record_changes(tmp_path, mutation):
    diag, refs = calls(tmp_path)
    if mutation == "identity_reference":
        diag["generation_calls"][2]["images"].append(diag["generation_calls"][0]["images"][1])
    elif mutation == "missing_reference":
        diag["generation_calls"][0]["images"].pop()
    elif mutation == "reordered":
        diag["generation_calls"][0]["images"][1:] = reversed(diag["generation_calls"][0]["images"][1:])
    elif mutation == "extra_call":
        diag["generation_calls"].append(copy.deepcopy(diag["generation_calls"][0]))
    elif mutation == "unparsed":
        diag["generation_calls"][0]["status"] = "failed"
    else:
        (tmp_path / "nut").write_bytes(b"different")
    with pytest.raises(ValueError):
        r.check_reference_stages(diag, refs, tmp_path, True)


def test_first_call_parse_failure_stays_auditable_without_retry(tmp_path):
    diag, refs = calls(tmp_path)
    diag["generation_calls"] = diag["generation_calls"][:1]
    diag["generation_calls"][0]["status"] = "failed"
    assert r.check_reference_stages(diag, refs, tmp_path, False)["spatial_calls"] == 1


def items():
    result = []
    for n in range(51):
        c = {"id": str(n), "source_id": str(n), "sha256": f"{n:064x}", "image": str(n)+".png", "split": "holdout",
             "ground_truth": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0},
             "supported_positive_classes": ["bolt", "nut", "washer"],
             "subgroup": "loco_normal_222" if n < 16 else "screws_author_safe_crop"}
        observed = {"observed": dict(c["ground_truth"]), "issues": [],
                    "action": {"kind": "none", "message": "fixture", "region": None}}
        if n in (14, 15, 47, 48, 49, 50, 46):
            observed["issues"] = ["unclear"]
        if n in (16, 17, 18):
            observed["observed"]["washer"] = 1
        result.append({"case": c, "baseline": score_case(c, observed, 100)})
    return result


def candidate(item, *, error=None):
    row = score_case(item["case"], copy.deepcopy(item["baseline"]["observation"]), 200, error)
    return row | {"mode": r.MODE, "loaded_before": False}


def test_full51_denominator_retains_failed_and_unattempted_risk():
    dataset = items()
    rows = [candidate(i) for i in dataset[:-1]]
    rows[0] = candidate(dataset[0], error="failed before parse")
    a = r.analyze(dataset, rows)
    assert sum(a["outcomes"].values()) == a["risk_denominator"] == 51
    assert a["outcomes"]["E"] == a["outcomes"]["N"] == 1
    assert a["unmeasured_risk"] == 2 and not a["development_gate_count_conditions_passed"]
    assert a["concurrent_latency_comparison"] is False
    assert a["latency_all_attempted"]["measured"] == 50


def test_scoring_recomputed_from_observation_not_saved_flags():
    dataset = items()
    rows = [candidate(i) for i in dataset]
    for row in rows:
        row["counts_exact"] = row["actionable_counts"] = True
    a = r.analyze(dataset, rows)
    assert a["outcomes"] == {"C": 41, "W": 3, "U": 7, "E": 0, "N": 0}
    assert a["any_false_ready_images"]["all_four"] == 3


def test_gate_requires_loco_preservation_even_if_c_total_recovers():
    dataset = items()
    rows = [candidate(i) for i in dataset]
    for n in (16, 17, 18):
        rows[n]["observation"]["observed"] = dict(dataset[n]["case"]["ground_truth"])
    rows[0]["observation"]["issues"] = ["unclear"]
    a = r.analyze(dataset, rows)
    assert a["outcomes"]["C"] == 43 and a["outcomes"]["W"] == 0
    assert a["loco_C_preserved"] == 13 and not a["development_gate_count_conditions_passed"]


def test_incomplete_plan_rejected():
    with pytest.raises(ValueError, match="51-case"):
        r.analyze(items()[:50], [])


def test_module_import_and_observer_status_do_not_load_mlx():
    code = ("from scripts.v08.run_reference_guarded import observer; import sys,json; "
            "s=observer().status(); assert not s['loaded']; assert 'mlx.core' not in sys.modules; "
            "print(json.dumps({'mode':s['observation_mode'],'loaded':s['loaded']}))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mode"] == "spatial_guarded"


def test_actual_target_rotation_and_identity_crops_are_bound(tmp_path):
    from PIL import Image
    image = Image.new("RGB", (4, 3), "white")
    image.putpixel((0, 0), (0, 0, 0))
    image.save(tmp_path / "target.png")
    image.transpose(Image.Transpose.ROTATE_90).save(tmp_path / "rotated.png")
    image.crop((0, 0, 2, 2)).save(tmp_path / "crop.png")
    def ref(name):
        return {"path": name, "sha256": r.sha(tmp_path / name)}
    target, rotated, crop = ref("target.png"), ref("rotated.png"), ref("crop.png")
    diag = {"generation_calls": [{"schema": "SpatialInventory", "images": [target]},
                                  {"schema": "SpatialInventory", "images": [rotated]},
                                  {"schema": "IdentityResponse", "images": [target, crop]}],
            "identity": {"crops": [{"crop_sha256": crop["sha256"]}]}}
    assert r.check_target_stages(diag, target["sha256"], tmp_path)["identity_crop_hashes_checked"] is True
    diag["generation_calls"][1]["images"] = [target]
    with pytest.raises(ValueError, match="90-degree"):
        r.check_target_stages(diag, target["sha256"], tmp_path)


def test_final_integrity_failure_returns_nonzero_exit_without_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "run", lambda freeze, output: {"status": "failed_integrity"})
    monkeypatch.setattr(sys, "argv", ["runner", "run", "--frozen-runtime", "--freeze", str(tmp_path / "freeze.json"),
                                    "--output", str(tmp_path / "output")])
    with pytest.raises(SystemExit) as exc:
        r.main()
    assert exc.value.code == 1
