"""Freeze or run independent, alternating paired MLX observations on new sources."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from kitguard.evaluation import file_sha256, read_manifest, score_case, validate_case
from kitguard.vision import LocalVision
from scripts.run_benchmark import app_upload_bytes
from scripts.v07.analyze_public_paired import CANDIDATE_MODE, MODES, analyze
from scripts.v07.prepare_public_evaluation import ROOT, SEED


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def schedule(cases, modes=MODES):
    """Alternate two methods, or balance three methods across six permutations."""
    if tuple(modes) == MODES:
        sequences = [MODES, tuple(reversed(MODES))]
    elif tuple(modes) == (*MODES, CANDIDATE_MODE):
        sequences = [tuple(modes[i:]) + tuple(modes[:i]) for i in range(3)]
        sequences += [tuple(reversed(s)) for s in sequences]
    else:
        raise ValueError("Unregistered method sequence")
    return [(case, mode, position) for index, case in enumerate(cases)
            for position, mode in enumerate(sequences[index % len(sequences)], 1)]


def engine_factory(modes, model_path=None):
    # All arms share the same raw-generation recording boundary and logging cost.
    from scripts.probe_selective_identity import SelectiveIdentityVision

    class RecordedLocalVision(LocalVision):
        _generate = SelectiveIdentityVision._generate

    return {mode: (SelectiveIdentityVision(model_path) if mode == CANDIDATE_MODE
                   else RecordedLocalVision(model_path, observation_mode=mode, image_max_side=1536))
            for mode in modes}


def source_hashes(root=ROOT):
    files = list((root / "kitguard").glob("*.py")) + list((root / "scripts/v07").glob("*.py"))
    files += [p for p in (root / "kitguard/static").rglob("*") if p.is_file()]
    files += [root / "scripts/run_benchmark.py"]
    files += [root / "scripts/probe_selective_identity.py"]
    return {str(p.relative_to(root)): file_sha256(p) for p in sorted(files)}


def create_freeze(manifest_path, freeze_path, model_path=None, *, modes=MODES):
    if freeze_path.exists():
        raise ValueError("Freeze already exists; do not overwrite it")
    manifest = read_manifest(manifest_path)
    cases = manifest["cases"]
    for case in cases:
        validate_case(case, ROOT / "datasets")
    engines = engine_factory(modes, model_path)
    identities = {mode: engine.status() for mode, engine in engines.items()}
    if not all(status["available"] for status in identities.values()):
        raise ValueError("Expected local model files are unavailable")
    freeze = {
        "schema": "kitguard.v07.public-paired.freeze.v1", "created_at": datetime.now(UTC).isoformat(),
        "selection_seed": SEED, "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": file_sha256(manifest_path), "cases": len(cases), "attempts": len(modes) * len(cases),
        "modes": list(modes),
        "selection_audit_sha256": file_sha256(manifest_path.parent / "selection_audit.json"),
        "source_hashes": source_hashes(), "model_identity": identities,
        "schedule": [{"case_id": c["id"], "mode": mode, "order_position": pos} for c, mode, pos in schedule(cases, modes)],
        "protocol": {"input_pipeline": "independent app-upload per method; identical normalized bytes required",
                     "image_max_side": 1536, "references": {}, "order_quantities_sent_to_observer": False,
                     "temperature": 0, "spatial_output_tokens_per_orientation": 900, "guarded_identity_tokens": 1800,
                     "time_measure": "each upload preprocessing + independent observation; includes first cold load",
                     "warmup": "none; mark loaded_before and report warm subset in addition to all attempts",
                     "logging": "All arms use identical raw generation/image recorder from frozen probe_selective_identity.py; production observer protocols unchanged",
                     "repeat_failed_cases": False, "inference_concurrency": 1},
        "predeclared_acceptance": {"guarded_wrong_actionable": 0, "guarded_any_false_ready": 0,
                                   "guarded_execution_failures": 0, "guarded_correct_actionable_min_rate": 0.9,
                                   "guarded_coverage_loss_max_images": 3, "guarded_median_max_ms": 60000,
                                   "complete_planned_denominator_required": True,
                                   "safety_advantage_requires": "strict reduction of wrong actionable or any-false-ready images, plus all gates",
                                   "no_automatic_model_or_default_promotion": True},
        "selective_identity_further_validation_gate": {
            "applies_when_predeclared": CANDIDATE_MODE in modes,
            "all_standard_acceptance_conditions": True,
            "correct_actionable_at_least_guarded": True,
            "median_at_most_guarded_fraction": 0.8,
            "all_planned_guarded_attempts_required": True,
            "effect": "eligible for further validation only; no automatic promotion/default change",
        },
    }
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    write(freeze_path, freeze)
    snapshot = freeze_path.parent / "source_snapshot"
    snapshot.mkdir()
    for relative in freeze["source_hashes"]:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return freeze


def run(freeze_path, output, model_path=None, *, project_root=ROOT):
    if output.exists():
        raise ValueError("Output exists; preserve all attempts, including failures")
    freeze = json.loads(freeze_path.read_text())
    manifest_path = project_root / freeze["manifest"]
    if file_sha256(manifest_path) != freeze["manifest_sha256"] or source_hashes() != freeze["source_hashes"]:
        raise ValueError("Manifest or source changed after freeze")
    if file_sha256(manifest_path.parent / "selection_audit.json") != freeze["selection_audit_sha256"]:
        raise ValueError("Selection audit changed after freeze")
    manifest = read_manifest(manifest_path)
    cases = manifest["cases"]
    modes = tuple(freeze["modes"])
    paths = {c["id"]: validate_case(c, project_root / "datasets") for c in cases}
    engines = engine_factory(modes, model_path)
    for mode, engine in engines.items():
        status = engine.status()
        for key in ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side"):
            if status[key] != freeze["model_identity"][mode][key]:
                raise ValueError(f"Model identity changed: {mode}/{key}")
    planned = schedule(cases, modes)
    if [{"case_id": c["id"], "mode": m, "order_position": p} for c, m, p in planned] != freeze["schedule"]:
        raise ValueError("Frozen execution order changed")
    output.mkdir(parents=True)
    (output / "normalized_inputs").mkdir()
    (output / "manifest.json").write_bytes(manifest_path.read_bytes())
    (output / "freeze.json").write_bytes(freeze_path.read_bytes())
    metadata = {"status": "running", "started_at": datetime.now(UTC).isoformat(),
                "freeze_sha256": file_sha256(freeze_path), "planned_attempts": len(planned),
                "completed_attempts": 0, "python": platform.python_version(), "platform": platform.platform(),
                "runtime_source_root": str(ROOT), "data_project_root": str(project_root),
                "isolated_python": bool(sys.flags.isolated),
                "workspace_source_hashes_before": source_hashes(project_root)}
    write(output / "run.json", metadata)
    rows, input_hashes = [], {}
    try:
        for index, (case, mode, position) in enumerate(planned, 1):
            if source_hashes() != freeze["source_hashes"]:
                raise ValueError("Source changed during run; stop and preserve remaining denominator")
            engine = engines[mode]
            loaded = engine.status()["loaded"]
            start = time.perf_counter()
            observation, error, diagnostics = None, None, None
            normalized_sha = None
            try:
                engine.artifact_dir = output / "cases" / f"{index:03d}-{mode}"
                normalized = output / "normalized_inputs" / f"{index:03d}-{mode}.jpg"
                normalized.write_bytes(app_upload_bytes(paths[case["id"]]))
                normalized_sha = file_sha256(normalized)
                if case["id"] in input_hashes and input_hashes[case["id"]] != normalized_sha:
                    raise ValueError("Paired normalized input differs")
                input_hashes[case["id"]] = normalized_sha
                observation = engine.observe(normalized, dict.fromkeys(("bolt", "nut", "washer", "bracket"), 1), {})
                diagnostics = engine.status().get("last_observation_attempt")
            except Exception as exc:  # noqa: BLE001 -- every failed attempt remains visible.
                error = f"{type(exc).__name__}: {exc}"
                diagnostics = getattr(exc, "observation_diagnostics", None)
            elapsed = round((time.perf_counter() - start) * 1000)
            row = score_case(case, observation, elapsed, error)
            row.update({"mode": mode, "order_position": position, "loaded_before": loaded,
                        "normalized_sha256": normalized_sha, "observation_diagnostics": diagnostics,
                        "runtime": engine.status().get("last_inference") if not error else None})
            rows.append(row)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
            metadata["completed_attempts"] = len(rows)
            write(output / "run.json", metadata)
            print(json.dumps({"progress": f"{index}/{len(planned)}", "case": case["id"], "mode": mode,
                              "exact": row["counts_exact"], "actionable": row["actionable_counts"], "error": error,
                              "latency_ms": elapsed}), flush=True)
        metadata["status"] = "completed"
    except BaseException as exc:
        metadata["status"] = "interrupted"
        metadata["interruption"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        metadata["finished_at"] = datetime.now(UTC).isoformat()
        metadata["source_changed"] = source_hashes() != freeze["source_hashes"]
        metadata["workspace_source_hashes_after"] = source_hashes(project_root)
        metadata["workspace_changed_during_run"] = metadata["workspace_source_hashes_after"] != metadata["workspace_source_hashes_before"]
        write(output / "run.json", metadata)
        write(output / "analysis.json", analyze(manifest, rows, modes=modes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--create-freeze", action="store_true")
    parser.add_argument("--include-selective-identity", action="store_true", help="Only when selected using prior development data, before holdout inference")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--frozen-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.include_selective_identity and not args.create_freeze:
        parser.error("--include-selective-identity is only allowed while creating the pre-inference freeze")
    if args.create_freeze:
        if args.manifest is None:
            parser.error("--create-freeze requires --manifest")
        modes = (*MODES, CANDIDATE_MODE) if args.include_selective_identity else MODES
        freeze = create_freeze(args.manifest.resolve(), args.freeze.resolve(), args.model_path, modes=modes)
        print(json.dumps({"frozen_cases": freeze["cases"], "attempts": freeze["attempts"], "sha256": file_sha256(args.freeze)}))
    else:
        if args.output is None:
            parser.error("Running requires --output")
        if args.frozen_runtime:
            expected_snapshot = args.freeze.resolve().parent / "source_snapshot"
            if ROOT != expected_snapshot or not sys.flags.isolated:
                raise ValueError("Frozen runtime requires isolated Python importing the freeze snapshot")
            run(args.freeze.resolve(), args.output.resolve(), args.model_path, project_root=args.project_root.resolve())
        else:
            snapshot = args.freeze.resolve().parent / "source_snapshot"
            # -I excludes CWD/PYTHONPATH; the snapshot alone supplies project modules.
            entry = "import sys; sys.path.insert(0, sys.argv.pop(1)); from scripts.v07.run_public_paired import main; main()"
            command = [sys.executable, "-I", "-c", entry, str(snapshot), "--frozen-runtime",
                       "--freeze", str(args.freeze.resolve()), "--output", str(args.output.resolve()),
                       "--project-root", str(args.project_root.resolve())]
            if args.model_path:
                command.extend(["--model-path", str(args.model_path.expanduser().resolve())])
            raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
