"""Completed-only independent CPU audit of the frozen fixed-reference development trial.

No candidate runner/analyzer import, no model call, no workspace kitguard import.
Raw strings are replayed through the pinned source snapshot. Scores and rule panels
are independently derived with a separately pinned, previously audited helper.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import platform
import shutil
import sqlite3
import sys
import tempfile
import types
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE_REL = "docs/v0.8/reference_guarded_freeze_v1/freeze.json"
FREEZE_SHA = "6530e2341a60fd99fb758eac2c5f3d6010f7b8c973be71a800ad5ca0d2578462"
HELPER_REL = "scripts/v07/audit_public_paired.py"
HELPER_SHA = "4ed25dcb8b832adf027c72abddea76b0363d3b06125ad6e864621d6340d7a5f6"
MODE = "spatial_guarded_fixed_class_references_v1"
IDENTITY_KEYS = ("label", "repo_id", "revision", "observer_protocol_sha256", "observer_source_hashes",
                 "observation_mode", "image_max_side", "path")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_helper():
    path = ROOT / HELPER_REL
    if sha(path) != HELPER_SHA:
        raise ValueError("Independent audit helper source changed")
    spec = importlib.util.spec_from_file_location("reference_audit_pinned_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load_helper()
need, read, inside, AuditError = H.need, H.read, H.inside, H.AuditError


def completed_metadata(run):
    meta = read(run / "run.json")
    need(meta.get("status") == "completed", "Run incomplete; candidate predictions intentionally unread")
    need(meta.get("planned") == meta.get("completed_attempts") == 51, "All 51 attempts required")
    need(meta.get("source_changed") is False and meta.get("final_integrity_verified") is True,
         "Run source/final integrity unverified")
    need(meta.get("isolated_python") is True and meta.get("model_called_in_setup") is False,
         "Frozen isolated runtime/setup contract missing")
    need(meta.get("automatic_promotion") is False, "No automatic promotion authorized")
    need(datetime.fromisoformat(meta["finished_at"]) >= datetime.fromisoformat(meta["started_at"]), "Invalid run timestamps")
    return meta


def verify_ref(root, record):
    path = inside(root, record["path"])
    need(sha(path) == record["sha256"], f"Evidence changed: {record['path']}")
    return path


def snapshot_runtime_files(snapshot, source_hashes):
    """Only the frozen app's default empty SQLite side effect is a non-source file."""
    actual = {str(p.relative_to(snapshot)) for p in snapshot.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    need(set(source_hashes) <= actual, "Snapshot is missing source or assets")
    extras = actual - set(source_hashes)
    need(extras <= {"data/kitguard.sqlite3"}, "Snapshot contains unlisted source or asset")
    receipts = {}
    for relative in extras:
        path = inside(snapshot, relative)
        with closing(sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)) as conn:
            schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            schema_hash = hashlib.sha256(json.dumps(schema).encode()).hexdigest()
            need(schema_hash == "c267cbc14454e2d9f87f56a75bf36c690e763027f714181faa9434b77eed22ba",
                 "Default runtime database schema differs from inspected frozen Store schema")
            tables = [name for kind, name, _table, _sql in schema if kind == "table"]
            sizes = {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
            need(all(count == 0 for count in sizes.values()), "Default runtime database is not empty")
            need(conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "Runtime database integrity differs")
        receipts[relative] = {"sha256": sha(path), "schema_sha256": schema_hash, "table_rows": sizes,
                              "origin": "frozen app.py module-level create_app default Store; upload helper uses separate temporary directories"}
    return receipts


def verify_freeze(root, run, path, meta):
    need(sha(path) == sha(run / "freeze.json") == meta["freeze_sha256"] == FREEZE_SHA, "Pinned freeze mismatch")
    freeze = read(path)
    snapshot = path.parent / "source_snapshot"
    need(freeze["schema"] == "kitguard.v08.reference-guarded.freeze.v1", "Unexpected freeze schema")
    need(Path(meta["runtime_source_root"]).resolve() == snapshot.resolve(), "Unfrozen runtime source")
    need(Path(meta["project_root"]).resolve() == Path(freeze["project_root"]).resolve() == root, "Data root mismatch")
    need(datetime.fromisoformat(freeze["created_at"]) <= datetime.fromisoformat(meta["started_at"]), "Freeze after run start")
    for name, digest in freeze["source_hashes"].items():
        need(sha(inside(snapshot, name)) == digest, f"Frozen source changed: {name}")
    snapshot_runtime_files(snapshot, freeze["source_hashes"])
    versions = {"python": platform.python_version(), **{p: importlib.metadata.version(p)
                for p in ("mlx", "mlx-vlm", "transformers", "pydantic", "pillow", "fastapi", "httpx")}}
    need(versions == freeze["versions"], "CPU replay library versions differ from freeze")
    for record in [freeze["approval"], *freeze["baseline_files"]]:
        verify_ref(root, record)
    manifest = read(run / "manifest.json")
    need(manifest == {"cases": [item["case"] for item in freeze["cases"]]}, "Run manifest differs from freeze")
    baseline_file = next(r for r in freeze["baseline_files"] if r["path"].endswith("predictions.jsonl"))
    baseline = {r["case_id"]: r for r in map(json.loads, verify_ref(root, baseline_file).read_text().splitlines())
                if r["mode"] == "spatial_guarded"}
    need(len(baseline) == 51 and all(item["baseline"] == baseline[item["case"]["id"]] for item in freeze["cases"]),
         "Historical guarded baseline copy differs")
    return freeze, snapshot


def verify_model(model):
    need(sha(model["manifest_path"]) == model["manifest_sha256"], "Model manifest changed")
    manifest = read(model["manifest_path"])
    need(manifest["repo_id"] == model["status"]["repo_id"] and manifest["revision"] == model["status"]["revision"],
         "Model manifest identity differs")
    expected = {str((Path(model["status"]["path"]) / r["path"]).resolve()): r for r in manifest["files"]}
    need(set(expected) == {r["path"] for r in model["files"]}, "Missing/unlisted model payload")
    for record in model["files"]:
        path = Path(record["path"])
        stat = path.stat()
        need(stat.st_size == record["bytes"] == expected[str(path)]["bytes"]
             and stat.st_mtime_ns == record["mtime_ns"] and stat.st_ino == record["inode"], "Model file identity changed")
        need(sha(path) == record["sha256"] == expected[str(path)]["sha256"], "Model payload changed")
    return len(expected)


def pixel_sha(image):
    return hashlib.sha256(str(image.size).encode() + b"|RGB|" + image.convert("RGB").tobytes()).hexdigest()


def verify_references(root, freeze, frozen):
    from PIL import Image
    approval = read(verify_ref(root, freeze["approval"]))
    need(approval["status"] == "approved_for_development_inference"
         and approval["selected_without_candidate_predictions"] is True
         and approval["no_count_or_order_overlays"] is True, "Reference approval missing")
    approved = {r["part"]: r for r in approval["items"]}
    need(set(approved) == set(freeze["references"]) == {"nut", "washer"} and len(approval["items"]) == 2,
         "Exactly one fixed reference per nut/washer class required")
    cases = [r["case"] for r in freeze["cases"]]
    refs = {}
    for part, record in freeze["references"].items():
        need(record["approval"] == approved[part] and approved[part]["single_object_ai_reviewed"] is True, "Reference approval differs")
        source, crop = verify_ref(root, record["source"]), verify_ref(root, record["crop"])
        need(record["source"]["sha256"] == approved[part]["source_sha256"]
             and record["crop"]["sha256"] == approved[part]["crop_sha256"], "Approved reference hash mismatch")
        with Image.open(source) as raw, Image.open(crop) as cut:
            raw, cut = raw.convert("RGB"), cut.convert("RGB")
            rect = approved[part]["crop_xyxy"]
            need(all(type(v) is int for v in rect) and 0 <= rect[0] < rect[2] <= raw.width
                 and 0 <= rect[1] < rect[3] <= raw.height, "Invalid reference rectangle")
            extracted = raw.crop(rect)
            need(extracted.size == cut.size and extracted.tobytes() == cut.tobytes(), "Reference crop edited")
            need(pixel_sha(raw) == record["source_rgb_sha256"] and pixel_sha(cut) == record["crop_rgb_sha256"]
                 and list(cut.size) == record["crop_size"], "Reference decoded pixels changed")
        need(record["source"]["sha256"] not in {c["source_sha256"] for c in cases}
             and record["source_rgb_sha256"] not in {c["source_decoded_rgb_sha256"] for c in cases}
             and record["crop"]["sha256"] not in {c["sha256"] for c in cases}, "Reference/evaluation source overlap")
        with tempfile.TemporaryDirectory() as temporary:
            prepared = Path(temporary) / "reference.png"
            frozen.vision._prepare_image(crop, prepared, 512)
            with Image.open(prepared) as image:
                need(sha(prepared) == record["prepared_sha256"] and list(image.size) == record["prepared_size"],
                     "Reference 512 preprocessing changed")
        refs[part] = crop
    return refs


def stage_contract(diagnostics, reference_records, expected_target, case_dir, successful):
    """Independent explicit stage roles; full prompts and crop pixels are replayed too."""
    from PIL import Image
    calls = (diagnostics or {}).get("generation_calls", [])
    need(len(calls) <= 3, "Unplanned retry/additional call")
    expected_refs = [reference_records[p]["prepared_sha256"] for p in ("nut", "washer")]
    spatial, identity = 0, 0
    for index, call in enumerate(calls):
        hashes = [im["sha256"] for im in call["images"]]
        if index < 2:
            need(call["schema"] == "SpatialInventory" and hashes[1:] == expected_refs and len(hashes) == 3,
                 "Spatial stage reference order/role mismatch")
            need("reference for nut; do NOT count it" in call["prompt"]
                 and "reference for washer; do NOT count it" in call["prompt"], "Missing reference role instruction")
            spatial += 1
        else:
            need(call["schema"] == "IdentityResponse" and not set(hashes) & set(expected_refs)
                 and "reference for" not in call["prompt"], "Reference leaked into identity stage")
            identity += 1
    if successful:
        need(spatial == 2 and all(c["status"] == "parsed" for c in calls), "Incomplete successful call sequence")
    result = {"spatial_calls": spatial, "identity_calls": identity, "reference_stage_contract_passed": True}
    if not calls:
        return result | {"target_stage_contract_checked": False, "reason": "no generation call preserved"}
    need(calls[0]["images"][0]["sha256"] == expected_target, "Original target differs from historical G")
    with Image.open(inside(case_dir, calls[0]["images"][0]["path"])) as original:
        out = io.BytesIO()
        original.transpose(Image.Transpose.ROTATE_90).save(out, format="PNG")
    rotation = hashlib.sha256(out.getvalue()).hexdigest()
    if len(calls) >= 2:
        need(calls[1]["images"][0]["sha256"] == rotation, "Second target is not exact 90-degree rotation")
    if len(calls) == 3:
        need([r["sha256"] for r in calls[2]["images"]]
             == [expected_target, *[c["crop_sha256"] for c in diagnostics["identity"]["crops"]]], "Identity target/crops differ")
    return result | {"target_stage_contract_checked": True, "original_sha256": expected_target,
                     "rotation_sha256": rotation, "identity_crop_hashes_checked": len(calls) == 3}


def replay(engine, normalized, refs, case_dir, row, frozen):
    calls, counts = H.verify_call_files(case_dir, row.get("observation_diagnostics"), row.get("error"))
    cursor, opaque = 0, []

    def no_model(_self):
        raise AuditError("Model load forbidden during audit")

    def generate(_self, system, prompt, images, schema, *, max_tokens=450):
        nonlocal cursor
        need(cursor < len(calls), "Missing raw call")
        record = calls[cursor]
        cursor += 1
        need((system, prompt, schema.__name__, max_tokens)
             == (record["system"], record["prompt"], record["schema"], record["max_tokens"]), "Frozen prompt/schema/budget mismatch")
        need(len(images) == len(record["images"]), "Replayed image count differs")
        for source, saved in zip(images, record["images"], strict=True):
            need(sha(source) == saved["sha256"], "Frozen target/rotation/reference/identity crop bytes differ")
            target = inside(_self.artifact_dir, saved["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _self._observation_attempt.setdefault("generation_calls", []).append(copy.deepcopy(record))
        _self._last_inference = copy.deepcopy(record["runtime"])
        if record["status"] == "parsed":
            parsed = frozen.vision._parse_json(record["raw_text"].strip(), schema)
            need(parsed.model_dump() == record["parsed"], "Raw response/parsed receipt mismatch")
            return parsed
        if record["raw_text"] is not None:
            try:
                frozen.vision._parse_json(record["raw_text"].strip(), schema)
            except frozen.vision.ModelOutputError:
                need(record["error"].startswith("ModelOutputError:"), "Changed parse exception")
                raise
            raise AuditError("Recorded parse failure has valid raw output")
        opaque.append({"call": cursor, "error": record["error"], "status": "retained_runtime_failure_no_raw_return"})
        raise frozen.vision.ModelUnavailableError("Recorded runtime failure: " + record["error"])

    engine._load = types.MethodType(no_model, engine)
    engine._generate = types.MethodType(generate, engine)
    with tempfile.TemporaryDirectory(prefix="kitguard-reference-replay-") as temporary:
        engine.artifact_dir = Path(temporary)
        observed, error = None, None
        try:
            observed = engine._observe(normalized, refs)
        except AuditError:
            raise
        except Exception as exc:  # noqa: BLE001 -- replay the precise saved failure boundary.
            error = exc
        need(cursor == len(calls), "Extra/unconsumed raw generation")
        original, rebuilt = row["observation_diagnostics"], engine._observation_attempt
        need(original == rebuilt, "Frozen diagnostics differ: " + json.dumps(H.diagnostic_differences(original, rebuilt), ensure_ascii=False))
        if row.get("error"):
            need(error is not None and row.get("observation") is None, "Failure not reproduced at observation boundary")
            if not opaque:
                need(row["error"] == f"{type(error).__name__}: {error}", "Exception differs from raw replay")
            need(type(error).__name__ == original["error_type"], "Replayed exception type differs")
        else:
            need(error is None, f"Successful observation failed replay: {error}")
            actual = frozen.schemas.Observation.model_validate(row["observation"]).model_dump(exclude_none=False)
            expected = frozen.schemas.Observation.model_validate(observed).model_dump(exclude_none=False)
            actual.pop("latency_ms", None)
            expected.pop("latency_ms", None)
            need(actual == expected, "Final observation differs from frozen raw replay")
        need(engine._last_inference == row["observer_status"]["last_inference"], "Aggregate last-inference receipt differs")
        counts["reconstructed_identity_crops"] += len(rebuilt.get("identity", {}).get("crops", []))
    return counts, opaque


def panels(case, row):
    return {key: {k: v for k, v in value.items() if k != "risk_measured"}
            for key, value in H.independent_panels(case, row).items()}


def summarize(items, rows):
    need(len(items) == len({i["case"]["id"] for i in items}) == 51, "Full 51-case plan required")
    indexed = {r["case_id"]: r for r in rows}
    need(len(indexed) == len(rows) and set(indexed) <= {i["case"]["id"] for i in items}, "Duplicate/unplanned ledger row")
    counts, transitions, groups = Counter(), Counter(), {}
    changes, risk, lost, original_wrong = [], [], [], []
    loco_old, loco_kept = 0, 0
    for item in items:
        case, base = item["case"], item["baseline"]
        row = indexed.get(case["id"])
        old = H.derive_outcome(base, case["ground_truth"])
        new = H.derive_outcome(row, case["ground_truth"]) if row else "N"
        counts[new] += 1
        transitions[f"{old}->{new}"] += 1
        groups.setdefault(case["subgroup"], Counter())[new] += 1
        change = {"case_id": case["id"], "baseline": old, "candidate": new}
        changes.append(change)
        if old == "C" and new != "C":
            lost.append(case["id"])
        if old == "W":
            original_wrong.append(change)
        if case["subgroup"] == "loco_normal_222":
            loco_old += old == "C"
            loco_kept += old == new == "C"
        risk.append({"case_id": case["id"], "baseline": panels(case, base),
                     "candidate": panels(case, row or {"error": "not attempted", "observation": None})})
    afr = {p: sum(r["candidate"][p]["any_false_ready"] for r in risk) for p in ("all_four", "source_supported")}
    checks = {"all51_attempted": len(rows) == 51, "zero_W": counts["W"] == 0, "zero_E": counts["E"] == 0,
              "zero_N": counts["N"] == 0, "C_at_least_41": counts["C"] >= 41,
              "zero_all_four_AFR": afr["all_four"] == 0, "all14_loco_C_preserved": loco_old == loco_kept == 14}
    return {"planned": 51, "outcomes": {k: counts[k] for k in "CWUEN"}, "paired_transitions": dict(transitions),
            "changes": changes, "source_groups": {s: {k: c[k] for k in "CWUEN"} for s, c in groups.items()},
            "old_C_lost": lost, "original_wrong_cases": original_wrong, "loco_old_C": loco_old, "loco_C_preserved": loco_kept,
            "panels": risk, "any_false_ready_images": afr, "risk_denominator": 51, "unmeasured_risk": counts["E"] + counts["N"],
            "latency_all_attempted": H.timing([r["latency_ms"] for r in rows]),
            "latency_warm_subset": H.timing([r["latency_ms"] for r in rows if r["loaded_before"]]),
            "baseline_historical_latency": H.timing([i["baseline"]["latency_ms"] for i in items]),
            "concurrent_latency_comparison": False,
            "generation_calls": sum(len((r.get("observation_diagnostics") or {}).get("generation_calls", [])) for r in rows),
            "development_checks": checks, "development_gate_count_conditions_passed": all(checks.values()),
            "independent_audit_required": True, "automatic_promotion": False, "new_holdout": False}


def inventory(run):
    return {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}


def audit(root, run, freeze_path):
    root, run, freeze_path = root.resolve(), run.resolve(), freeze_path.resolve()
    meta = completed_metadata(run)  # Deliberately before any candidate prediction read.
    freeze, snapshot = verify_freeze(root, run, freeze_path, meta)
    runtime_files = snapshot_runtime_files(snapshot, freeze["source_hashes"])
    before = inventory(run)
    need(before["predictions.jsonl"] == meta["predictions_sha256"] and before["analysis.json"] == meta["analysis_sha256"],
         "Run final ledger/report hashes differ")
    ledger = (run / "predictions.jsonl").read_bytes()
    need(ledger.endswith(b"\n"), "Unfinished last prediction")
    rows = [json.loads(line) for line in ledger.decode().splitlines()]
    need(len(rows) == 51 and [(r["index"], r["case_id"], r["mode"]) for r in rows]
         == [(n, i["case"]["id"], MODE) for n, i in enumerate(freeze["cases"], 1)], "51-case execution ledger/order differs")
    need(Counter(i["case"]["subgroup"] for i in freeze["cases"])
         == {"screws_author_safe_crop": 35, "loco_normal_222": 16}, "Source denominators changed")
    frozen = H.load_frozen_modules(snapshot)
    from PIL import Image
    engine = frozen.vision.LocalVision(Path(freeze["model"]["status"]["path"]), observation_mode="spatial_guarded", image_max_side=1536)
    status = engine.status()
    need(all(status[k] == freeze["model"]["status"][k] for k in IDENTITY_KEYS), "Frozen observer identity differs")
    model_files = verify_model(freeze["model"])
    refs = verify_references(root, freeze, frozen)
    totals, attempts, opaque = Counter(), [], []
    previous_loaded = False
    for index, (item, row) in enumerate(zip(freeze["cases"], rows, strict=True), 1):
        case = item["case"]
        need(all(row.get(k) == case.get(k) for k in ("source_id", "image", "sha256", "split", "ground_truth", "subgroup")),
             f"Row source/truth metadata differs at {index}")
        verify_ref(root, item["image"])
        verify_ref(root, item["source"])
        image_path = H.verify_photo(case, root / "datasets", Image)
        expected_normalized = hashlib.sha256(frozen.upload.app_upload_bytes(image_path)).hexdigest()
        need(expected_normalized == item["normalized_sha256"] == item["baseline"]["normalized_sha256"], "Historical upload parity lost")
        H.timing([row["latency_ms"]])
        saved_status = row["observer_status"]
        need(all(saved_status[k] == status[k] for k in IDENTITY_KEYS), "Attempt model/protocol identity differs")
        need(type(row["loaded_before"]) is bool and row["loaded_before"] == previous_loaded, "Cold/warm sequence differs")
        need(type(saved_status["loaded"]) is bool and (not previous_loaded or saved_status["loaded"]), "Model unload/reload unrecorded")
        previous_loaded = saved_status["loaded"]
        directory = run / "cases" / f"{index:03d}-{MODE}"
        normalized = run / "normalized_inputs" / f"{index:03d}.jpg"
        counts = Counter()
        if not row["observation_attempted"]:
            need(row.get("error") and row["observation"] is None and row["observation_diagnostics"] is None,
                 "Pre-observation failure lacks error or retains stale result")
            need(not list(directory.rglob("generation.json")), "Pre-observation failure has hidden model calls")
            opaque.append({"attempt": index, "status": "pre_observation_failure", "error": row["error"]})
            if normalized.exists():
                need(sha(normalized) == expected_normalized, "Partial normalized input differs")
        else:
            need(sha(normalized) == row["normalized_sha256"] == expected_normalized, "Actual normalized input differs")
            diag = row["observation_diagnostics"]
            need(diag == saved_status["last_observation_attempt"] and diag["source_sha256"] == expected_normalized,
                 "Observation diagnostics/status binding differs")
            need(diag["mode"] == "spatial_guarded" and diag["model"] == status["label"], "Attempt observer label differs")
            try:
                counts, missing = replay(engine, normalized, refs, directory, row, frozen)
                opaque.extend({"attempt": index, **failure} for failure in missing)
                expected_stage = stage_contract(diag, freeze["references"],
                    item["baseline"]["observation_diagnostics"]["passes"][0]["input_sha256"], directory, not row["error"])
                need(expected_stage == row["reference_stage_contract"], "Saved stage contract differs")
            except AuditError as exc:
                raise AuditError(f"Attempt {index}/{case['id']}: {exc}") from exc
            raw_ms = sum(c["runtime"]["seconds"] * 1000 for c in diag.get("generation_calls", []) if c.get("runtime"))
            need(raw_ms <= row["latency_ms"] + 50, "Generation time exceeds enclosing timer")
            totals["normalized_inputs_verified"] += 1
        totals.update(counts)
        H.verify_task_receipts(case, row)
        attempts.append({"index": index, "case_id": case["id"], "outcome": H.derive_outcome(row, case["ground_truth"]),
                         "raw_calls": counts["calls"], "actual_input_images": counts["input_images"],
                         "latency_ms": row["latency_ms"], "panels": H.independent_panels(case, row)})
    need({p.name for p in (run / "cases").iterdir()} <= {f"{n:03d}-{MODE}" for n in range(1, 52)}, "Extra/retried case artifacts")
    need({p.name for p in (run / "normalized_inputs").iterdir()} <= {f"{n:03d}.jpg" for n in range(1, 52)}, "Extra normalized inputs")
    result = summarize(freeze["cases"], rows)
    report = read(run / "analysis.json")
    need({k: report.get(k) for k in result} == result, "Independent full-denominator metrics differ: "
         + json.dumps(H.diagnostic_differences({k: report.get(k) for k in result}, result), ensure_ascii=False))
    wall_ms = (datetime.fromisoformat(meta["finished_at"]) - datetime.fromisoformat(meta["started_at"])).total_seconds() * 1000
    need(sum(r["latency_ms"] for r in rows) <= wall_ms + 51, "Sequential timers exceed run duration")
    need(completed_metadata(run) == meta and inventory(run) == before, "Run artifacts changed during audit")
    for name, digest in freeze["source_hashes"].items():
        need(sha(inside(snapshot, name)) == digest, "Frozen source changed during audit")
    need(snapshot_runtime_files(snapshot, freeze["source_hashes"]) == runtime_files, "Runtime snapshot files changed during audit")
    need(not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules), "Audit imported MLX")
    return {"schema": "kitguard.v08.reference-guarded.independent-audit.v1", "status": "passed",
            "checked_at": datetime.now(UTC).isoformat(), "completed_attempts": 51, "source_snapshot_files_verified": len(freeze["source_hashes"]),
            "source_changed": False, "runtime_snapshot_files": runtime_files, "model_payloads_rehashed": model_files, "raw_evidence_checks": dict(totals),
            "retained_failures_without_reproducible_model_return": opaque, "independent_results": result, "attempt_audits": attempts,
            "model_loaded_or_called": False, "automatic_promotion": False, "artifacts_sha256": before,
            "evidence_sha256": {"freeze": FREEZE_SHA, "auditor": sha(Path(__file__)), "helper": HELPER_SHA,
                                "run": before["run.json"], "predictions": before["predictions.jsonl"], "analysis": before["analysis.json"]},
            "limitations": ["51 photos were previously exposed development data, from two existing public domains; not a fresh holdout.",
                            "References aid only two spatial calls; identity is unreferenced and all calls share one correlated VLM.",
                            "LOCO16 has constant counts 2/2/2/0; no bracket-positive or quantity-anomaly coverage.",
                            "Reference labels follow frozen author/project projection and AI crop QA, not human physical identity certification.",
                            "CPU replay verifies saved raw parsing/postprocessing and exact prepared inputs, not model response authenticity.",
                            "Model payload hashes and library versions are checked; external runtime binaries/source are not fully hashed.",
                            "Historical G was not rerun concurrently. Recorded timings do not establish a fair speed advantage.",
                            "Missing raw runtime returns remain unmeasured risk; their internal failure cause cannot be reproduced.",
                            "Pretraining exposure, physical-object/session independence and real-world benefit remain unknown."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--run", type=Path, default=ROOT / "evaluation-runs/v0.8/reference_guarded_v1")
    parser.add_argument("--freeze", type=Path, default=ROOT / FREEZE_REL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists() and not args.output.resolve().is_relative_to(args.run.resolve()), "Audit output must be new/outside run")
    try:
        result = audit(args.project_root, args.run, args.freeze)
    except Exception as exc:  # Preserve audit failure separately; never alter evidence.
        result = {"schema": "kitguard.v08.reference-guarded.independent-audit.v1", "status": "failed",
                  "checked_at": datetime.now(UTC).isoformat(), "error": f"{type(exc).__name__}: {exc}",
                  "auditor_sha256": sha(Path(__file__)), "freeze_sha256": sha(args.freeze), "model_loaded_or_called": False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "outcomes": result["independent_results"]["outcomes"],
                      "output": str(args.output), "sha256": sha(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
