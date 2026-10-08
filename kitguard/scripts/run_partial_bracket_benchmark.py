"""Frozen bracket-only descriptive validation; other categories have no author truth.

Validation uses only the Python standard library. Real inference requires an explicit
CLI flag, and all planned cases remain in the denominator even when execution fails.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import re
import shutil
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

PROTOCOL = "ino_bracket_partial_v1"
LABEL_SCOPE = "author_L_bracket_count_only"
MODEL_PROFILE = "Qwen3.6-27B-4bit"
MODEL_REVISION = "c000ac2c2057d94be3fa931000c31723aac53282"
FIXED_REQUIREMENTS = {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1}
UNLABELED = ["bolt", "nut", "washer"]
RUNNER = Path(__file__).resolve()
PROJECT = RUNNER.parents[1]
SHA_PATTERN = re.compile(r"[a-f0-9]{64}\Z")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(project: Path = PROJECT) -> dict[str, str]:
    """Complete immediate kitguard Python source set; the freeze owns this contract."""
    return {
        path.relative_to(project).as_posix(): file_sha256(path)
        for path in sorted((project / "kitguard").glob("*.py"))
    }


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def json_safe(value, depth=0):
    """Keep invalid observer outputs inspectable without losing the error row."""
    if depth > 50:
        return {"non_json_value": "maximum diagnostic depth exceeded"}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"non_json_float": repr(value)}
    if isinstance(value, dict):
        return {str(key): json_safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item, depth + 1) for item in value]
    return {"non_json_type": type(value).__name__, "representation": repr(value)}


def persist_row(output: Path, row: dict) -> None:
    with (output / "predictions.jsonl").open("a") as stream:
        stream.write(json.dumps(json_safe(row), ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


def read_json(path: Path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=unique_keys)


def checked_image(case: dict, dataset_root: Path) -> Path:
    relative = case.get("image")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Image must be a nonempty relative dataset path")
    root = dataset_root.resolve()
    image = (root / relative).resolve()
    if not image.is_relative_to(root) or not image.is_file():
        raise ValueError(f"Image escapes dataset root or is not a file: {relative}")
    expected = case.get("sha256")
    if not isinstance(expected, str) or SHA_PATTERN.fullmatch(expected) is None:
        raise ValueError(f"Invalid image SHA256: {case.get('id')}")
    if file_sha256(image) != expected:
        raise ValueError(f"Image SHA256 mismatch: {case.get('id')}")
    return image


def validate_manifest(manifest: dict, dataset_root: Path) -> list[Path]:
    if manifest.get("schema_version") != 1 or manifest.get("label_scope") != LABEL_SCOPE:
        raise ValueError("Unsupported bracket-only manifest schema or label scope")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Manifest must contain planned cases")
    seen_ids, seen_sources, paths = set(), set(), []
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("Case must be an object")
        for key, seen in (("id", seen_ids), ("source_id", seen_sources)):
            value = case.get(key)
            if not isinstance(value, str) or not value or value in seen:
                raise ValueError(f"Invalid or duplicate {key}: {value}")
            seen.add(value)
        if case.get("author_group") not in list("ABCDEF"):
            raise ValueError("Unknown author group")
        if case.get("view_kind") not in {"full_image", "author_box_roi"}:
            raise ValueError("Unknown view kind")
        truth = case.get("ground_truth")
        if not isinstance(truth, dict) or set(truth) != {"bracket"}:
            raise ValueError("Ground truth must contain bracket only; never fill unlabeled categories")
        if type(truth["bracket"]) is not int or not 1 <= truth["bracket"] <= 3:
            raise ValueError("Author bracket truth must be a positive integer from 1 to 3")
        if case.get("unlabeled_categories") != UNLABELED:
            raise ValueError("bolt, nut and washer must be explicitly unlabeled")
        paths.append(checked_image(case, dataset_root))
    return paths


def validate_configuration(manifest_path: Path, dataset_root: Path, freeze_path: Path) -> dict:
    manifest, freeze = read_json(manifest_path), read_json(freeze_path)
    validate_manifest(manifest, dataset_root)
    required = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "manifest_sha256": file_sha256(manifest_path),
        "runner_sha256": file_sha256(RUNNER),
        "method_source_hashes": source_hashes(),
        "model": {"profile": MODEL_PROFILE, "revision": MODEL_REVISION},
        "observation_mode": "spatial_guarded",
        "image_max_side": 1536,
        "input_pipeline": "app-upload",
        "label_scope": LABEL_SCOPE,
        "case_ids": [case["id"] for case in manifest["cases"]],
        "expected_cases": len(manifest["cases"]),
        "fixed_observer_requirements": FIXED_REQUIREMENTS,
    }
    for key, value in required.items():
        if freeze.get(key) != value:
            raise ValueError(f"Freeze mismatch: {key}")
    timestamp = freeze.get("frozen_at")
    if not isinstance(timestamp, str):
        raise TypeError("Freeze must include frozen_at")
    parsed = datetime.fromisoformat(timestamp)
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("frozen_at must be an ISO timestamp in UTC")
    return {"manifest": manifest, "freeze": freeze, "verified": required}


def app_upload_bytes(source: Path) -> bytes:
    """Use the actual upload route, isolating both module-level and explicit stores."""
    with TemporaryDirectory(prefix="kitguard-partial-upload-") as temporary:
        previous = os.environ.get("KITGUARD_DATA_DIR")
        os.environ["KITGUARD_DATA_DIR"] = str(Path(temporary) / "import-store")
        try:
            from fastapi.testclient import TestClient

            from kitguard.app import create_app
        finally:
            if previous is None:
                os.environ.pop("KITGUARD_DATA_DIR", None)
            else:
                os.environ["KITGUARD_DATA_DIR"] = previous
        app = create_app(data_dir=Path(temporary) / "upload-store")
        with TestClient(app) as client:
            created = client.post("/api/orders", json={
                "title": "Public photograph preprocessing validation",
                "requirements": dict(FIXED_REQUIREMENTS),
            })
            created.raise_for_status()
            order = created.json()["order"]
            uploaded = client.post(
                f"/api/orders/{order['id']}/photos", data={"expected_revision": 1},
                files={"photo": (source.name, source.read_bytes(), "image/png")},
            )
            uploaded.raise_for_status()
            return app.state.store.photo_path(uploaded.json()["photo"]["id"]).read_bytes()


class GenerationCapture:
    """Retain exact temporary model inputs before LocalVision deletes its directory."""

    def __init__(self, engine):
        self.original = engine._generate
        self.directory: Path | None = None
        self.calls: list[dict] = []
        self.files: dict[str, dict] = {}
        engine._generate = self.generate

    def start(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True)
        self.calls, self.files = [], {}

    def generate(self, system, prompt, images, schema, *, max_tokens=450):
        if self.directory is None:
            raise RuntimeError("Artifact capture has no current case")
        for folder in {Path(path).parent for path in images}:
            for source in sorted(folder.glob("*.png")):
                target = self.directory / source.name
                digest = file_sha256(source)
                if target.exists() and file_sha256(target) != digest:
                    raise ValueError("Prepared image filename was reused with different contents")
                shutil.copyfile(source, target)
                self.files[source.name] = {
                    "file": source.name, "sha256": digest, "bytes": source.stat().st_size,
                }
        call = {
            "call_index": len(self.calls) + 1, "system": system, "prompt": prompt,
            "images": [{"file": Path(path).name, "sha256": file_sha256(Path(path))} for path in images],
            "schema": schema.model_json_schema(), "max_tokens": max_tokens,
            "status": "running",
        }
        self.calls.append(call)
        self.save()
        try:
            result = self.original(system, prompt, images, schema, max_tokens=max_tokens)
            call["status"] = "completed"
            call["parsed_result"] = result.model_dump() if hasattr(result, "model_dump") else result
            return result
        except Exception as exc:
            call["status"] = "error"
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.save()

    def save(self):
        write_json(self.directory / "artifacts.json", {"files": list(self.files.values()), "calls": self.calls})


def make_engine():
    from kitguard.vision import LocalVision

    engine = LocalVision(
        Path.home() / "Downloads" / "AI-Models" / MODEL_PROFILE,
        observation_mode="spatial_guarded", image_max_side=1536,
    )
    status = engine.status()
    if (status["repo_id"] != f"mlx-community/{MODEL_PROFILE}"
            or status["revision"] != MODEL_REVISION
            or status["observation_mode"] != "spatial_guarded" or status["image_max_side"] != 1536):
        raise ValueError("Actual observer configuration differs from the freeze")
    if not status["available"]:
        raise RuntimeError("Real model files are unavailable; predictions are not fabricated")
    return engine


def validated_observation(raw, input_sha256: str):
    from kitguard.schemas import Observation

    result = Observation.model_validate(raw)
    verification = result.verification
    if verification is None or verification.mode != "spatial_consensus":
        raise ValueError("Guarded observation requires the actual spatial passes")
    review = result.identity_verification
    candidates = any(o.part in {"nut", "washer"} for o in verification.passes[0].objects)
    if verification.clear_agreement and candidates and review is None:
        raise ValueError("Guarded clear ring candidates require identity verification")
    if review is not None and review.source_sha256 != input_sha256:
        raise ValueError("Identity review source differs from the normalized input")
    return result.model_dump()


def bracket_outcome(value, truth: int) -> str:
    return "U_b" if value is None else "C_b" if value == truth else "W_b"


def score_partial(case: dict, observation: dict | None, error: str | None) -> dict:
    """Only bracket has truth. Application clarity is never a correctness claim."""
    result = {
        "outcome": "E", "bracket_prediction": None, "app_clear": None,
        "first_pass_bracket": None, "first_pass_outcome": None,
    }
    if observation is None:
        return result
    truth = case["ground_truth"]["bracket"]
    value = observation["observed"]["bracket"]
    first = observation["verification"]["passes"][0]["observed"]["bracket"]
    result.update({
        "outcome": "E" if error else bracket_outcome(value, truth), "bracket_prediction": value,
        "app_clear": None if error else all(observation["observed"][part] is not None for part in FIXED_REQUIREMENTS)
            and not observation["issues"] and observation["action"]["kind"] == "none",
        "first_pass_bracket": first, "first_pass_outcome": bracket_outcome(first, truth),
    })
    return result


def diagnostic_first_pass(diagnostics):
    """Preserve a real successful original pass even if a later pass failed."""
    from kitguard.spatial import SpatialInventory, count_inventory

    try:
        first = diagnostics["passes"][0]
        if first["transform"] != "original":
            return False, None
        inventory = SpatialInventory.model_validate(first["inventory"])
        return True, count_inventory(inventory, "Saved original pass")[0]["observed"]["bracket"]
    except (KeyError, TypeError, ValueError, IndexError):
        return False, None


def summarize_partial(rows: list[dict]) -> dict:
    counts = {key: sum(row["outcome"] == key for row in rows) for key in ("C_b", "W_b", "U_b", "E")}
    cross = {key: {
        "app_clear": sum(row["outcome"] == key and row["app_clear"] is True for row in rows),
        "app_not_clear": sum(row["outcome"] == key and row["app_clear"] is False for row in rows),
    } for key in ("C_b", "W_b", "U_b")}
    paired = [row for row in rows if row["first_pass_outcome"] is not None]
    attempted = [row for row in rows if row.get("execution_status") == "attempted"]
    return {
        "planned_cases": len(rows), "outcomes": counts,
        "author_bracket_count_agreement_fraction": counts["C_b"] / len(rows) if rows else None,
        "outcome_by_application_clarity": cross,
        "paired_first_final": {
            "cases": len(paired),
            "transitions": {f"{a}->{b}": sum(
                row["first_pass_outcome"] == a and row["outcome"] == b for row in paired
            ) for a in ("C_b", "W_b", "U_b") for b in ("C_b", "W_b", "U_b", "E")},
        },
        "constant_one_baseline": {
            "correct": sum(row["ground_truth"]["bracket"] == 1 for row in rows),
            "denominator": len(rows),
            "fraction": sum(row["ground_truth"]["bracket"] == 1 for row in rows) / len(rows) if rows else None,
            "interpretation": "A constant prediction of one matches all single-bracket truths; this set cannot establish counting reasoning.",
        },
        "by_view_kind": {kind: {
            "cases": sum(row["view_kind"] == kind for row in rows),
            "outcomes": {key: sum(row["view_kind"] == kind and row["outcome"] == key for row in rows)
                         for key in ("C_b", "W_b", "U_b", "E")},
        } for kind in ("full_image", "author_box_roi")},
        "median_pipeline_latency_ms": statistics.median(row["elapsed_ms"] for row in attempted) if attempted else None,
        "pipeline_latency_n": len(attempted),
        "interpretation": "Bracket author-count agreement only; app_clear is not four-category correctness or readiness.",
    }


def execute_run(manifest_path: Path, dataset_root: Path, output: Path, freeze_path: Path,
                *, engine_factory=make_engine, normalizer=app_upload_bytes) -> dict:
    configuration = validate_configuration(manifest_path, dataset_root, freeze_path)
    manifest, freeze = configuration["manifest"], configuration["freeze"]
    # mkdir without exist_ok is the final race-safe fresh-output check.
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(manifest_path, output / "manifest.json")
    shutil.copyfile(freeze_path, output / "freeze.json")
    for relative in freeze["method_source_hashes"]:
        target = output / "source_snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / relative, target)
    runner_snapshot = output / "source_snapshot" / "scripts" / RUNNER.name
    runner_snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNNER, runner_snapshot)
    for relative, expected in freeze["method_source_hashes"].items():
        if file_sha256(output / "source_snapshot" / relative) != expected:
            raise ValueError(f"Source changed while taking snapshot: {relative}")
    if (file_sha256(output / "manifest.json") != freeze["manifest_sha256"]
            or file_sha256(runner_snapshot) != freeze["runner_sha256"]):
        raise ValueError("Manifest or runner changed while taking snapshot")
    # A second preflight closes changes made during snapshot collection.
    validate_configuration(manifest_path, dataset_root, freeze_path)
    from kitguard.schemas import Observation

    write_json(output / "observation_schema.json", Observation.model_json_schema())
    metadata = {
        "schema_version": 1, "protocol": PROTOCOL, "label_scope": LABEL_SCOPE,
        "status": "running", "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "manifest_sha256": file_sha256(manifest_path), "freeze_sha256": file_sha256(freeze_path),
        "runner_sha256": file_sha256(RUNNER), "source_hashes": source_hashes(),
        "expected_cases": len(manifest["cases"]), "completed_cases": 0,
        "case_ids": [case["id"] for case in manifest["cases"]],
        "model": freeze["model"], "observation_mode": "spatial_guarded", "image_max_side": 1536,
        "input_pipeline": "app-upload", "fixed_observer_requirements": dict(FIXED_REQUIREMENTS),
        "unlabeled_categories": UNLABELED,
        "view_counts": {kind: sum(case["view_kind"] == kind for case in manifest["cases"])
                        for kind in ("full_image", "author_box_roi")},
        "limitations": [
            "Only author L-bracket counts have truth; bolt, nut and washer remain unlabeled.",
            "Positive-only views, including author-box oracle ROIs; not general detection or false-positive validation.",
            "One case per origin source; no new-factory, independent-scene or multi-bracket claim.",
            "Original-pass counts are paired components of the same run; no independent baseline latency.",
        ],
    }
    write_json(output / "run.json", metadata)
    engine, capture, startup_error = None, None, None
    try:
        engine = engine_factory()
        metadata["model_before"] = copy.deepcopy(engine.status())
        capture = GenerationCapture(engine)
    except Exception as exc:  # noqa: BLE001 -- Initialization failures remain explicit planned errors.
        startup_error = f"{type(exc).__name__}: {exc}"
        metadata["startup_error"] = startup_error
    rows = []
    loop_completed = False
    (output / "normalized_inputs").mkdir()
    try:
        for index, case in enumerate(manifest["cases"], start=1):
            started = time.perf_counter()
            observation, raw, error, diagnostics = None, None, None, None
            source_before = source_after = input_hash = input_after = runtime = None
            normalized = output / "normalized_inputs" / f"{index:03d}.jpg"
            artifacts = output / "case_artifacts" / f"{index:03d}"
            if capture is not None:
                capture.start(artifacts)
            try:
                path = checked_image(case, dataset_root)
                source_before = file_sha256(path)
                if startup_error:
                    raise RuntimeError(startup_error)
                normalized.write_bytes(normalizer(path))
                input_hash = file_sha256(normalized)
                raw = engine.observe(normalized, dict(FIXED_REQUIREMENTS), {})
                diagnostics = copy.deepcopy(engine.status().get("last_observation_attempt"))
                runtime = copy.deepcopy(engine.status().get("last_inference"))
                observation = validated_observation(raw, input_hash)
            except Exception as exc:  # noqa: BLE001 -- Preserve every planned case, without retry.
                error = f"{type(exc).__name__}: {exc}"
                diagnostics = copy.deepcopy(getattr(exc, "observation_diagnostics", diagnostics))
            finally:
                try:
                    source_after = file_sha256((dataset_root / case["image"]).resolve())
                    input_after = file_sha256(normalized) if normalized.exists() else None
                    if source_after != case["sha256"] or input_after != input_hash:
                        error = f"{error + '; ' if error else ''}InputIntegrityError: source or normalized input changed"
                except OSError as exc:
                    error = f"{error + '; ' if error else ''}InputIntegrityError: {exc}"
            elapsed = round((time.perf_counter() - started) * 1000)
            row = {
                "id": case["id"], "source_id": case["source_id"], "author_group": case["author_group"],
                "view_kind": case["view_kind"], "ground_truth": copy.deepcopy(case["ground_truth"]),
                "execution_status": "attempted",
                "unlabeled_categories": UNLABELED, "label_scope": LABEL_SCOPE,
                **score_partial(case, observation, error),
                "error": error, "elapsed_ms": elapsed, "observation": raw,
                "observation_diagnostics": diagnostics, "runtime": runtime,
                "input_pipeline": "app-upload", "source_sha256_before": source_before,
                "source_sha256_after": source_after, "model_input_sha256": input_hash,
                "model_input_sha256_after": input_after,
                "input_changed": source_after != case["sha256"] or input_after != input_hash,
                "normalized_input": normalized.relative_to(output).as_posix() if normalized.exists() else None,
                "case_artifacts": artifacts.relative_to(output).as_posix() if artifacts.exists() else None,
            }
            if row["first_pass_outcome"] is None:
                has_first, first = diagnostic_first_pass(diagnostics)
                if has_first:
                    row["first_pass_bracket"] = first
                    row["first_pass_outcome"] = bracket_outcome(first, case["ground_truth"]["bracket"])
            persist_row(output, row)
            rows.append(row)
            metadata["completed_cases"] = len(rows)
            write_json(output / "run.json", metadata)
            print(json.dumps({"progress": f"{index}/{len(manifest['cases'])}", "id": case["id"],
                              "outcome": row["outcome"], "error": error, "ms": elapsed}), flush=True)
        loop_completed = True
    finally:
        attempted_cases = len(rows)
        # Preserve the fixed denominator after interruption; these are not model predictions.
        for case in manifest["cases"][len(rows):]:
            row = {
                "id": case["id"], "source_id": case["source_id"], "author_group": case["author_group"],
                "view_kind": case["view_kind"], "ground_truth": copy.deepcopy(case["ground_truth"]),
                "unlabeled_categories": UNLABELED, "label_scope": LABEL_SCOPE,
                **score_partial(case, None, "Execution interrupted before case could be recorded"),
                "error": "Execution interrupted before case could be recorded", "elapsed_ms": None,
                "execution_status": "not_executed_or_not_recorded", "observation": None,
                "observation_diagnostics": None,
            }
            persist_row(output, row)
            rows.append(row)
        metadata["status"] = "completed" if loop_completed else "interrupted"
        metadata["completed_cases"] = attempted_cases
        metadata["recorded_cases"] = len(rows)
        metadata["not_executed_or_not_recorded"] = len(rows) - attempted_cases
        metadata["finished_at"] = datetime.now(UTC).isoformat()
        metadata["model_after"] = copy.deepcopy(engine.status()) if engine is not None else None
        metadata["source_hashes_after"] = source_hashes()
        metadata["runner_sha256_after"] = file_sha256(RUNNER)
        metadata["manifest_sha256_after"] = file_sha256(manifest_path)
        metadata["freeze_sha256_after"] = file_sha256(freeze_path)
        metadata["source_changed_during_run"] = (
            metadata["source_hashes_after"] != freeze["method_source_hashes"]
            or metadata["source_hashes"] != freeze["method_source_hashes"]
            or metadata["runner_sha256_after"] != freeze["runner_sha256"]
            or metadata["runner_sha256"] != freeze["runner_sha256"]
            or metadata["manifest_sha256_after"] != freeze["manifest_sha256"]
            or metadata["manifest_sha256"] != freeze["manifest_sha256"]
            or metadata["freeze_sha256_after"] != metadata["freeze_sha256"]
        )
        metadata["summary"] = summarize_partial(rows)
        metadata["input_changed_during_run"] = any(row.get("input_changed", False) for row in rows)
        metadata["valid_frozen_run"] = (
            metadata["status"] == "completed" and not metadata["source_changed_during_run"]
            and not metadata["input_changed_during_run"]
        )
        write_json(output / "run.json", metadata)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--execute-real-model", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output path already exists; retain prior runs and choose a fresh path")
    if args.execute_real_model == args.validate_only:
        parser.error("Select exactly one of --validate-only or --execute-real-model")
    if args.validate_only:
        result = validate_configuration(args.manifest, args.dataset_root, args.freeze)
        print(json.dumps({"status": "validated_without_model_import", **result["verified"]}, indent=2))
        return
    metadata = execute_run(args.manifest, args.dataset_root, args.output, args.freeze)
    print(json.dumps(metadata["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
