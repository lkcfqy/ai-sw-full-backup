"""Run frozen engineering text cases through real LocalVision.propose_revision.

No orders are created or completed. This is not a user study. Correct rejection
is a passing clarification case; runtime/model failures are never clarification.
Use --validate-only to validate cases without importing or executing the model.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import traceback
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT / "datasets" / "manifests" / "instructions_v1.json"
PARTS = ("bolt", "nut", "washer", "bracket")
LANGUAGES = {"ko": 8, "zh": 8, "en": 8}
CATEGORIES = {"clear": 9, "out_of_range": 6, "ambiguous": 3, "unrelated": 3, "unauthorized_completion": 3}
KINDS = {"proposal": 9, "clarification": 15}


def utc_now():
    return datetime.now(UTC).isoformat()


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def canonical_hash(value):
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def valid_requirements(value):
    return (
        isinstance(value, dict)
        and set(value) == set(PARTS)
        and all(type(value[part]) is int and 0 <= value[part] <= 3 for part in PARTS)
        and 1 <= sum(value.values()) <= 12
    )


def reject_duplicate_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_nonfinite(value):
    raise ValueError(f"Non-finite JSON constant is not permitted: {value}")


def read_manifest(path):
    raw = Path(path).read_bytes()
    manifest = json.loads(raw, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_nonfinite)
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError("Expected instruction manifest schema_version 1")
    if manifest.get("benchmark_id") != "kitguard-instructions-v1":
        raise ValueError("Unexpected benchmark_id; this runner validates the fixed v1 suite")
    if manifest.get("provenance", {}).get("kind") != "project_authored_engineering_text_cases":
        raise ValueError("Manifest must explicitly identify author-generated engineering text cases")
    if manifest.get("evaluation_phase") != "development_engineering":
        raise ValueError("The v1 suite must be identified as development engineering, not holdout")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 24 or manifest.get("case_count") != 24:
        raise ValueError("The frozen v1 manifest must contain exactly 24 cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("Each case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("Each case needs a unique nonempty id")
        seen.add(case_id)
        if case.get("language") not in LANGUAGES or case.get("category") not in CATEGORIES:
            raise ValueError(f"{case_id}: unknown language/category")
        if not valid_requirements(case.get("initial_requirements")):
            raise ValueError(f"{case_id}: invalid initial requirements")
        instruction = case.get("instruction")
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 500:
            raise ValueError(f"{case_id}: instruction must have 1..500 nonblank characters")
        expected = case.get("expected")
        if not isinstance(expected, dict) or expected.get("kind") not in KINDS:
            raise ValueError(f"{case_id}: expected kind must be proposal or clarification")
        if expected["kind"] == "proposal":
            if set(expected) != {"kind", "requirements"} or not valid_requirements(expected["requirements"]):
                raise ValueError(f"{case_id}: expected proposal must contain valid complete requirements")
        elif set(expected) != {"kind"}:
            raise ValueError(f"{case_id}: clarification must not contain target quantities")
        if (case["category"] == "clear") != (expected["kind"] == "proposal"):
            raise ValueError(f"{case_id}: category and expected kind disagree")
        if not isinstance(case.get("rationale"), str) or not case["rationale"].strip():
            raise ValueError(f"{case_id}: an expectation rationale is required")
        contents = {key: value for key, value in case.items() if key != "content_sha256"}
        if canonical_hash(contents) != case.get("content_sha256"):
            raise ValueError(f"{case_id}: content_sha256 mismatch; do not silently change frozen cases")
    distributions = {
        "languages": dict(Counter(case["language"] for case in cases)),
        "categories": dict(Counter(case["category"] for case in cases)),
        "expected_kinds": dict(Counter(case["expected"]["kind"] for case in cases)),
    }
    required = {"languages": LANGUAGES, "categories": CATEGORIES, "expected_kinds": KINDS}
    if distributions != required or manifest.get("expected_distribution") != required:
        raise ValueError("Case distribution must match the fixed three-language v1 design")
    return manifest, raw


def exception_record(exc):
    return {
        "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


def safe_status(vision):
    try:
        return deepcopy(vision.status())
    except Exception as exc:  # noqa: BLE001 -- Keep status failures in the audit record.
        return {"status_error": exception_record(exc)}


def evaluate_case(vision, case):
    """Call the public real adapter path; injectable object exists only for CPU unit review."""
    output, error = None, None
    interrupted = False
    started_at = utc_now()
    started = time.perf_counter()
    outcome = "execution_error"
    try:
        output = vision.propose_revision(case["instruction"], deepcopy(case["initial_requirements"]))
        if not isinstance(output, dict) or not valid_requirements(output.get("requirements")):
            raise RuntimeError("Public adapter returned an invalid requirements proposal")
        if not isinstance(output.get("explanation"), str) or not output["explanation"].strip():
            raise RuntimeError("Public adapter returned a proposal without a nonblank explanation")
        # Keep the returned dictionary intact, including any future metadata fields.
        outcome = "proposal"
    except KeyboardInterrupt as exc:
        error = exception_record(exc)
        interrupted = True
    except Exception as exc:  # noqa: BLE001 -- Every attempted-case failure stays in the denominator.
        error = exception_record(exc)
        # JSONDecodeError/Pydantic ValidationError are ValueError subclasses and are NOT
        # business clarification. Inputs have already passed strict manifest validation.
        # The current public adapter emits an exact ValueError for requirements:null.
        outcome = "clarification" if type(exc) is ValueError else "execution_error"
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    expected = case["expected"]
    exact = (
        outcome == "proposal"
        and expected["kind"] == "proposal"
        and output["requirements"] == expected["requirements"]
    )
    passed = exact or outcome == "clarification" and expected["kind"] == "clarification"
    reason = (
        "expected_response"
        if passed
        else "execution_error"
        if outcome == "execution_error"
        else "unexpected_clarification"
        if outcome == "clarification"
        else "unexpected_proposal"
        if expected["kind"] == "clarification"
        else "incorrect_requirements"
    )
    return {
        "case_id": case["id"],
        "language": case["language"],
        "category": case["category"],
        "case_content_sha256": case["content_sha256"],
        "instruction": case["instruction"],
        "initial_requirements": case["initial_requirements"],
        "expected": expected,
        "started_at": started_at,
        "finished_at": utc_now(),
        "elapsed_ms": elapsed_ms,
        "returned_output": output,
        "exception": error,
        "outcome": outcome,
        "interrupted": interrupted,
        "requirements_exact": exact if expected["kind"] == "proposal" else None,
        "passed": passed,
        "score_reason": reason,
        # Kept as full post-call state: last_inference can describe a prior case after
        # an early runtime failure, so we never relabel it as this case's token trace.
        "model_status_after_call": safe_status(vision),
    }


def summarize(rows, selected_count):
    def stats(items):
        counts = Counter(row["outcome"] for row in items)
        passed = sum(row["passed"] for row in items)
        return {
            "attempted": len(items),
            "passed": passed,
            "pass_rate_over_attempted": passed / len(items) if items else None,
            "proposal_responses": counts["proposal"],
            "clarification_responses": counts["clarification"],
            "execution_errors": counts["execution_error"],
        }

    return {
        "selected": selected_count,
        "unattempted": selected_count - len(rows),
        "overall": stats(rows),
        "by_language": {lang: stats([r for r in rows if r["language"] == lang]) for lang in LANGUAGES},
        "by_category": {cat: stats([r for r in rows if r["category"] == cat]) for cat in CATEGORIES},
        "by_expected_kind": {
            kind: stats([r for r in rows if r["expected"]["kind"] == kind]) for kind in KINDS
        },
        "interpretation": "Author-generated engineering cases only; expected clarification/rejection is success. Execution errors remain in every attempted-case denominator. No user-study or generalization claim.",
    }


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def model_file_metadata(model_path):
    if not model_path:
        return None
    root = Path(model_path)
    names = [
        "config.json",
        "tokenizer_config.json",
        "generation_config.json",
        "preprocessor_config.json",
        "chat_template.json",
        "chat_template.jinja",
    ]
    files = {}
    for name in names:
        path = root / name
        if path.is_file():
            files[name] = {"bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())}
    return {
        "configuration_files": files,
        "weight_files": [
            {"name": p.name, "bytes": p.stat().st_size} for p in sorted(root.glob("*.safetensors"))
        ],
        "weight_hash_note": "Weight file sizes are inventoried, not SHA-256 verified by this runner.",
    }


def package_versions():
    result = {}
    for package in ("kitguard", "mlx", "mlx-vlm", "pydantic", "transformers", "outlines", "safetensors"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="No GPU call occurs with --validate-only. Run only when the local model worker is available. Exit 1 indicates execution failures; semantic benchmark failures remain in the report.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, help="New run directory; existing paths are never overwritten")
    parser.add_argument(
        "--model-path", type=Path, help="Passed directly to LocalVision; default honors KITGUARD_MODEL_PATH"
    )
    parser.add_argument(
        "--max-cases", type=int, default=0, help="First N manifest cases before inference; 0=all 24"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Check manifest schema, hashes and selection; do not load/import model",
    )
    args = parser.parse_args(argv)
    if args.max_cases < 0:
        parser.error("--max-cases must be nonnegative")
    try:
        manifest, raw_manifest = read_manifest(args.manifest)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Manifest validation failed: {exc}")
    cases = manifest["cases"][: args.max_cases] if args.max_cases else manifest["cases"]
    if args.validate_only:
        print(
            json.dumps(
                {
                    "valid": True,
                    "model_executed": False,
                    "manifest_sha256": sha256_bytes(raw_manifest),
                    "case_count": 24,
                    "selected_cases": len(cases),
                    "partial": len(cases) < 24,
                    "case_ids": [c["id"] for c in cases],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.output is None:
        parser.error("--output is required unless --validate-only is used")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Output path already exists; retain previous runs and choose a new directory")
    # Freeze the complete source and manifest before importing the local model.
    source_dir = args.output / "source_snapshot"
    source_dir.mkdir()
    sources = [
        Path(__file__).resolve(),
        PROJECT / "kitguard" / "vision.py",
        PROJECT / "kitguard" / "schemas.py",
        PROJECT / "kitguard" / "instructions.py",
        PROJECT / "kitguard" / "models.py",
        PROJECT / "pyproject.toml",
    ]
    source_hashes = {}
    for path in sources:
        relative = path.relative_to(PROJECT)
        content = path.read_bytes()
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        source_hashes[str(relative)] = sha256_bytes(content)
    (args.output / "manifest.json").write_bytes(raw_manifest)
    metadata = {
        "benchmark_id": manifest["benchmark_id"],
        "scope": manifest["scope"],
        "evaluation_phase": manifest["evaluation_phase"],
        "started_at": utc_now(),
        "status": "starting",
        "completed_cases": 0,
        "selected_cases": len(cases),
        "partial": len(cases) < 24,
        "case_ids": [case["id"] for case in cases],
        "selection_rule": manifest["selection_rule"],
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": sha256_bytes(raw_manifest),
        "source_hashes": source_hashes,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "package_versions": package_versions(),
        "model_path_argument": str(args.model_path) if args.model_path else None,
        "entrypoint": "kitguard.vision.LocalVision.propose_revision",
        "raw_output_scope": manifest["scoring_policy"]["raw_output_scope"],
        "elapsed_note": "Per-case wall time includes adapter/queue/load time when applicable. No warmup cases are omitted.",
        "model_status_note": "Post-call last_inference may refer to an earlier case after a failure; it is retained as status, not attributed as a case token trace.",
    }
    write_json(args.output / "run.json", metadata)
    rows, vision = [], None
    exit_code = 0
    try:
        # This is the sole production model construction, never replaced by a fake CLI mode.
        sys.path.insert(0, str(PROJECT))
        from kitguard.vision import LocalVision

        vision = LocalVision(args.model_path)
        metadata["model_before"] = safe_status(vision)
        metadata["model_files"] = model_file_metadata(metadata["model_before"].get("path"))
        metadata["status"] = "running"
        write_json(args.output / "run.json", metadata)
        with (args.output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
            for index, case in enumerate(cases, start=1):
                row = evaluate_case(vision, case)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                rows.append(row)
                metadata["completed_cases"] = len(rows)
                metadata["summary"] = summarize(rows, len(cases))
                write_json(args.output / "run.json", metadata)
                print(
                    json.dumps(
                        {
                            "progress": f"{index}/{len(cases)}",
                            "id": case["id"],
                            "outcome": row["outcome"],
                            "passed": row["passed"],
                            "ms": row["elapsed_ms"],
                        }
                    ),
                    flush=True,
                )
                if row["interrupted"]:
                    raise KeyboardInterrupt
        metadata["status"] = "completed"
        exit_code = int(any(row["outcome"] == "execution_error" for row in rows))
    except KeyboardInterrupt:
        metadata["status"] = "interrupted"
        exit_code = 130
    except Exception as exc:  # noqa: BLE001 -- Persist fatal run failures before exiting.
        metadata["status"] = "failed"
        metadata["run_exception"] = exception_record(exc)
        exit_code = 1
    finally:
        metadata["finished_at"] = utc_now()
        metadata["completed_cases"] = len(rows)
        metadata["summary"] = summarize(rows, len(cases))
        metadata["model_after"] = safe_status(vision) if vision else None
        metadata["source_hashes_after_run"] = {
            str(p.relative_to(PROJECT)): sha256_bytes(p.read_bytes()) if p.is_file() else None
            for p in sources
        }
        metadata["source_changed_during_run"] = metadata["source_hashes_after_run"] != source_hashes
        write_json(args.output / "run.json", metadata)
    print(json.dumps(metadata["summary"], ensure_ascii=False, indent=2), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
