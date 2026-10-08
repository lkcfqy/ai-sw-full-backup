"""Synthetic contracts only; never read interim candidate predictions or call models."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.v08 import audit_reference_guarded as a


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def row(case, *, wrong=False, uncertain=False, error=None):
    counts = dict(case["ground_truth"])
    if wrong:
        counts["bracket"] = 1
    obs = {"observed": counts, "issues": ["unclear"] if uncertain else [],
           "action": {"kind": "recapture" if uncertain else "none", "message": "fixture", "region": None}}
    return {"case_id": case["id"], "observation": obs, "error": error, "counts_exact": not wrong and not error,
            "actionable_counts": not uncertain and not error, "latency_ms": 100, "loaded_before": True}


def dataset():
    items = []
    for n in range(51):
        c = {"id": str(n), "ground_truth": {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0},
             "subgroup": "loco_normal_222" if n < 16 else "screws_author_safe_crop",
             "supported_positive_classes": ["bolt", "nut", "washer"]}
        items.append({"case": c, "baseline": row(c, wrong=n in (16, 17, 18), uncertain=n in (14, 15, 46, 47, 48, 49, 50))})
    return items


def test_incomplete_guard_precedes_prediction_read(tmp_path):
    write(tmp_path / "run.json", {"status": "running"})
    with pytest.raises(a.AuditError, match="predictions intentionally unread"):
        a.audit(tmp_path, tmp_path, tmp_path / "no-freeze")
    assert not (tmp_path / "predictions.jsonl").exists()


def test_completed_requires_all51(tmp_path):
    write(tmp_path / "run.json", {"status": "completed", "planned": 51, "completed_attempts": 50})
    with pytest.raises(a.AuditError, match="51"):
        a.completed_metadata(tmp_path)


def test_independent_counts_panels_and_old_group_denominators():
    items = dataset()
    result = a.summarize(items, [i["baseline"] for i in items])
    assert result["outcomes"] == {"C": 41, "W": 3, "U": 7, "E": 0, "N": 0}
    assert result["any_false_ready_images"] == {"all_four": 3, "source_supported": 0}
    assert result["loco_old_C"] == result["loco_C_preserved"] == 14
    assert len(result["original_wrong_cases"]) == 3
    assert not result["development_gate_count_conditions_passed"]


def test_error_and_missing_rows_do_not_disappear_from_full_denominator():
    items = dataset()
    rows = [copy.deepcopy(i["baseline"]) for i in items[:-1]]
    rows[0] = row(items[0]["case"], error="runtime failure")
    result = a.summarize(items, rows)
    assert result["outcomes"]["E"] == result["outcomes"]["N"] == 1
    assert sum(result["outcomes"].values()) == result["risk_denominator"] == 51
    assert result["unmeasured_risk"] == 2
    assert result["latency_all_attempted"]["measured"] == 50


def test_loco_preservation_is_required_even_when_total_c_recovers():
    items = dataset()
    rows = [row(i["case"]) for i in items]
    rows[0] = row(items[0]["case"], uncertain=True)
    result = a.summarize(items, rows)
    assert result["outcomes"]["C"] == 50 and result["outcomes"]["W"] == 0
    assert result["loco_C_preserved"] == 13
    assert not result["development_gate_count_conditions_passed"]


def test_saved_score_flags_are_not_self_proof():
    items = dataset()
    rows = [copy.deepcopy(i["baseline"]) for i in items]
    rows[16]["counts_exact"] = True
    with pytest.raises(a.AuditError, match="scoring flags"):
        a.summarize(items, rows)


@pytest.mark.parametrize("variant", ["success", "second_parse_failure", "identity_id_contract", "runtime_no_return",
                                      "changed_reference", "changed_rotation", "identity_reference", "changed_raw",
                                      "changed_failure_crop", "changed_prompt"])
def test_exact_frozen_cpu_replay_and_negative_contracts(tmp_path, variant):
    # Fresh isolated interpreter avoids pytest's current-workspace kitguard imports.
    root = str(a.ROOT)
    entry = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    command = [sys.executable, "-I", "-c", entry, root, str(Path(__file__).resolve()), variant, str(tmp_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["model_called"] is False


def test_only_exact_empty_frozen_store_runtime_database_is_allowed(tmp_path):
    import sqlite3

    from kitguard.app import create_app

    create_app(data_dir=tmp_path / "data")
    receipt = a.snapshot_runtime_files(tmp_path, {})
    assert len(receipt["data/kitguard.sqlite3"]["table_rows"]) == 7
    assert set(receipt["data/kitguard.sqlite3"]["table_rows"].values()) == {0}
    with sqlite3.connect(tmp_path / "data/kitguard.sqlite3") as conn:
        conn.execute("INSERT INTO orders VALUES (?,?)", ("unexpected", "{}"))
    conn.close()
    with pytest.raises(a.AuditError, match="not empty"):
        a.snapshot_runtime_files(tmp_path, {})
    with sqlite3.connect(tmp_path / "data/kitguard.sqlite3") as conn:
        conn.execute("DELETE FROM orders")
    conn.close()
    (tmp_path / "extra.py").write_text("x=1")
    with pytest.raises(a.AuditError, match="unlisted source"):
        a.snapshot_runtime_files(tmp_path, {})


def fixture_worker(variant, temporary):
    import shutil
    import types

    from PIL import Image

    frozen = a.H.load_frozen_modules((a.ROOT / a.FREEZE_REL).parent / "source_snapshot")
    # Resolve before passing into import-boundary checks.
    root = Path(temporary)
    target = root / "normalized.jpg"
    Image.new("RGB", (80, 72), (220, 215, 200)).save(target)
    refs = {}
    for n, part in enumerate(("nut", "washer")):
        p = root / f"{part}.png"
        Image.new("RGB", (40, 36), (150 + 40*n, 110, 100)).save(p)
        refs[part] = p
    engine = frozen.vision.LocalVision(observation_mode="spatial_guarded", image_max_side=1536)
    case_dir = root / "case"
    engine.artifact_dir = case_dir
    inv = {"objects": [{"part": "nut", "center": [.5, .5]}], "uncertain_parts": [], "issues": [],
           "action": {"kind": "none", "message": "fixture"}}
    ident = {"objects": [{"id": "p002" if variant in {"identity_id_contract", "changed_failure_crop"} else "p001", "part": "nut",
                           "status": "independent_object", "opening": "through_hole", "issue": ""}]}

    def fake(self, system, prompt, images, schema, *, max_tokens=450):
        calls = self._observation_attempt.setdefault("generation_calls", [])
        number = len(calls) + 1
        directory = case_dir / f"call-{number:02d}"
        directory.mkdir(parents=True)
        saved = []
        for i, source in enumerate(images, 1):
            dst = directory / f"image-{i:02d}.png"
            shutil.copyfile(source, dst)
            saved.append({"path": str(dst.relative_to(case_dir)), "sha256": a.sha(dst)})
        raw = "not-json" if variant == "second_parse_failure" and number == 2 else json.dumps(inv if schema.__name__ == "SpatialInventory" else ident)
        runtime = {"seconds": 0., "prompt_tokens": 10, "generation_tokens": 10,
                   "mlx_reported_peak_memory_gb": .01, "finish_reason": "stop"}
        record = {"schema": schema.__name__, "system": system, "prompt": prompt, "max_tokens": max_tokens,
                  "temperature": 0, "images": saved, "status": "parsed", "raw_text": raw, "runtime": runtime}
        self._last_inference = copy.deepcopy(runtime)
        try:
            if variant == "runtime_no_return" and number == 3:
                record.update(raw_text=None, runtime=None)
                self._last_inference = None
                raise frozen.vision.ModelUnavailableError("synthetic runtime failure")
            parsed = frozen.vision._parse_json(raw, schema)
            record["parsed"] = parsed.model_dump()
        except Exception as exc:  # Preserve synthetic error exactly like the recorder.
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            calls.append(record)
            write(directory / "generation.json", record)
            raise
        calls.append(record)
        write(directory / "generation.json", record)
        return parsed

    engine._generate = types.MethodType(fake, engine)
    observation, error = None, None
    try:
        observation = engine._observe(target, refs)
    except Exception as exc:  # noqa: BLE001 -- preserve only synthetic failures, no actual model involved.
        error = f"{type(exc).__name__}: {exc}"
    record = {"observation": observation, "error": error,
              "observation_diagnostics": copy.deepcopy(engine._observation_attempt),
              "observer_status": copy.deepcopy(engine.status())}
    calls = record["observation_diagnostics"]["generation_calls"]
    negative = variant in {"changed_reference", "changed_rotation", "identity_reference", "changed_raw", "changed_failure_crop", "changed_prompt"}
    if variant == "changed_reference":
        Image.new("RGB", (40, 36), "blue").save(refs["nut"])
    elif variant == "changed_rotation":
        calls[1]["images"][0]["sha256"] = calls[0]["images"][0]["sha256"]
        shutil.copyfile(case_dir / calls[0]["images"][0]["path"], case_dir / calls[1]["images"][0]["path"])
    elif variant == "identity_reference":
        calls[2]["images"][1]["sha256"] = calls[0]["images"][1]["sha256"]
        shutil.copyfile(case_dir / calls[0]["images"][1]["path"], case_dir / calls[2]["images"][1]["path"])
    elif variant == "changed_raw":
        calls[0]["raw_text"] = calls[0]["raw_text"].replace('"nut"', '"washer"')
    elif variant == "changed_failure_crop":
        record["observation_diagnostics"]["identity"]["crops"][0]["source_sha256"] = "0" * 64
    elif variant == "changed_prompt":
        calls[0]["prompt"] += " extra instruction"
    for n, call in enumerate(calls, 1):
        write(case_dir / f"call-{n:02d}/generation.json", call)
    write(root / "fixture_record.json", record)
    other = frozen.vision.LocalVision(observation_mode="spatial_guarded", image_max_side=1536)
    try:
        counts, opaque = a.replay(other, target, refs, case_dir, record, frozen)
    except a.AuditError:
        assert negative, variant
    else:
        assert not negative, variant
        assert counts["calls"] == (2 if variant == "second_parse_failure" else 3)
        assert bool(opaque) is (variant == "runtime_no_return")
    assert not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules)
    print(json.dumps({"variant": variant, "model_called": False}))


if __name__ == "__main__":
    fixture_worker(sys.argv[1], sys.argv[2])
