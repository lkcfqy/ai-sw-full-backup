"""After frozen audit passes, replay the same raw calls against a workspace snapshot.

This is CPU behavioral compatibility, never a second MLX experiment. Only new
reference_evidence and protocol/source hashes may differ; generated prompts,
schemas, actual input bytes, counts, actions and other diagnostics must match.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITOR_PATH = ROOT / "scripts/v08/audit_reference_guarded.py"
spec = importlib.util.spec_from_file_location("frozen_reference_independent_auditor", AUDITOR_PATH)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
need = a.need


def semantic_copy(value):
    result = copy.deepcopy(value)
    result.pop("reference_evidence", None)
    return result


def sources(root):
    files = list((root / "kitguard").glob("*.py"))
    files += [p for p in (root / "kitguard/static").rglob("*") if p.is_file()]
    files += [root / p for p in ("scripts/run_benchmark.py", "scripts/probe_selective_identity.py")]
    return {str(p.relative_to(root)): a.sha(p) for p in sorted(files)}


def prior_schemas(snapshot):
    code = ("import sys,json;sys.path.insert(0,sys.argv[1]);"
            "from kitguard.vision import SpatialInventory,IdentityResponse;"
            "print(json.dumps({x.__name__:x.model_json_schema() for x in (SpatialInventory,IdentityResponse)}));"
            "assert not any(n=='mlx' or n.startswith('mlx.') for n in sys.modules)")
    proc = subprocess.run([sys.executable, "-I", "-c", code, str(snapshot)], capture_output=True, text=True, check=False)
    need(proc.returncode == 0, "Unable to read original frozen response schemas: " + proc.stderr)
    return json.loads(proc.stdout)


def check_metadata(evidence, freeze, row, status):
    need(evidence["protocol"] == "reference_inputs_v1" and evidence["observer_protocol_sha256"] == status["observer_protocol_sha256"],
         "Workspace metadata protocol binding differs")
    need(evidence["observation_mode"] == "spatial_guarded" and evidence["max_side"] == 512
         and evidence["guarded_identity_uses_references"] is False and evidence["prepared_bytes_retained"] is False,
         "Workspace reference role/retention metadata differs")
    need(evidence["preprocessing"] == "exif_transpose_rgb_thumbnail_lanczos_png_v1"
         and evidence["pillow_version"] == freeze["versions"]["pillow"], "Reference preprocessing metadata differs")
    expected = [{"part": part, "stored_sha256": freeze["references"][part]["crop"]["sha256"],
                 "prepared_sha256": freeze["references"][part]["prepared_sha256"],
                 "prepared_size": freeze["references"][part]["prepared_size"], "image_index": n}
                for n, part in enumerate(("nut", "washer"), 2)]
    need(evidence["images"] == expected, "New reference metadata differs from saved actual inputs")
    calls = row["observation_diagnostics"].get("generation_calls", [])
    stages = [{"stage": ("original", "rotate_90_ccw", "identity")[n],
               "reference_image_indices": [2, 3] if n < 2 else [],
               "status": "completed" if call["status"] == "parsed" else "failed"}
              for n, call in enumerate(calls)]
    if len(calls) == 2 and not row["error"]:
        stages.append({"stage": "identity", "reference_image_indices": [],
                       "status": row["observation_diagnostics"]["identity"]["status"]})
    need(evidence["stages"] == stages, "New stage metadata contradicts actual recorded call sequence")


def compatible_engine(frozen, schema_receipt, model_path):
    class WorkspaceObserver(frozen.vision.LocalVision):
        def __setattr__(self, name, value):
            if name == "_generate":
                injected = value

                def checked(system, prompt, images, schema, *, max_tokens=450):
                    need(schema.model_json_schema() == schema_receipt[schema.__name__], "Model response JSON schema changed")
                    return injected(system, prompt, images, schema, max_tokens=max_tokens)
                value = checked
            super().__setattr__(name, value)

        def _observe(self, *args, **kwargs):
            try:
                observation = super()._observe(*args, **kwargs)
                # Validate the complete new schema BEFORE omitting allowed metadata
                # for comparison with the pre-patch result.
                frozen.schemas.Observation.model_validate(observation)
                self.compat_observation = copy.deepcopy(observation)
                return semantic_copy(observation)
            finally:
                self.compat_diagnostics = copy.deepcopy(self._observation_attempt)
                self._observation_attempt = semantic_copy(self._observation_attempt)
    return WorkspaceObserver(model_path, observation_mode="spatial_guarded", image_max_side=1536)


def run(root, run_dir, audit_path, output):
    need(not output.exists() and not output.resolve().is_relative_to(run_dir.resolve()), "Use a new compatibility output outside original run")
    # Passing independent audit is required before looking at candidate records.
    audited = a.read(audit_path)
    need(audited.get("status") == "passed" and audited["completed_attempts"] == 51
         and audited["evidence_sha256"]["freeze"] == a.FREEZE_SHA
         and audited["evidence_sha256"]["auditor"] == a.sha(AUDITOR_PATH), "Pinned frozen independent audit must pass first")
    meta = a.completed_metadata(run_dir)
    need(a.inventory(run_dir) == audited["artifacts_sha256"], "Original evidence changed since independent audit")
    freeze_path = root / a.FREEZE_REL
    freeze, original_snapshot = a.verify_freeze(root, run_dir, freeze_path, meta)
    schemas = prior_schemas(original_snapshot)
    before_sources = sources(root)
    output.mkdir(parents=True)
    snapshot = output / "workspace_snapshot"
    for relative, digest in before_sources.items():
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
        need(a.sha(destination) == digest, "Workspace changed during snapshot copy")
    # Separate process and no prior kitguard import; all CPU behavior comes from
    # this exact new workspace snapshot, while project data remains original.
    os.environ["KITGUARD_DATA_DIR"] = str(output / "runtime-app-data")
    frozen = a.H.load_frozen_modules(snapshot.resolve())
    engine = compatible_engine(frozen, schemas, Path(freeze["model"]["status"]["path"]))
    status = engine.status()
    identity_keys = [k for k in a.IDENTITY_KEYS if k not in {"observer_protocol_sha256", "observer_source_hashes"}]
    need(all(status[k] == freeze["model"]["status"][k] for k in identity_keys), "Workspace model/method identity changed beyond source protocol metadata")
    refs = a.verify_references(root, freeze, frozen)
    rows = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    receipts = []
    for n, (item, row) in enumerate(zip(freeze["cases"], rows, strict=True), 1):
        need(row["index"] == n and row["case_id"] == item["case"]["id"], "Row schedule differs")
        need(row["observation_attempted"] is True, "Pre-observation failure has no model behavior to establish compatibility")
        actual = run_dir / "normalized_inputs" / f"{n:03d}.jpg"
        source = a.verify_ref(root, item["image"])
        need(a.H.bytes_sha(frozen.upload.app_upload_bytes(source)) == a.sha(actual) == row["normalized_sha256"],
             "Workspace upload preprocessing changed")
        counts, opaque = a.replay(engine, actual, refs, run_dir / "cases" / f"{n:03d}-{a.MODE}", row, frozen)
        evidence = engine.compat_diagnostics["reference_evidence"]
        check_metadata(evidence, freeze, row, status)
        receipts.append({"index": n, "case_id": row["case_id"], "behavior_and_all_model_inputs_equal": True,
                         "new_reference_evidence": evidence, "raw_calls": counts["calls"],
                         "opaque_failures": opaque, "new_mlx_observation": False})
    need(len(receipts) == 51 and sources(root) == before_sources, "Workspace changed during compatibility replay")
    need(a.inventory(run_dir) == audited["artifacts_sha256"], "Original evidence changed during compatibility replay")
    need(not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules), "Compatibility replay imported MLX")
    return {"schema": "kitguard.v08.reference-workspace-cpu-compatibility.v1", "status": "passed",
            "checked_at": datetime.now(UTC).isoformat(), "observations_replayed": len(receipts),
            "model_loaded_or_called": False, "new_mlx_observations": 0,
            "frozen_experiment_audit_replaced": False, "behavior_and_prompts_schemas_inputs_equal": True,
            "allowed_difference": ["new reference_evidence fields", "observer protocol/source hashes", "top-level wall-clock latency_ms"],
            "runtime_app_data_files_sha256": a.inventory(output / "runtime-app-data"),
            "workspace_source_sha256": before_sources, "workspace_observer_status": {k: status[k] for k in a.IDENTITY_KEYS},
            "original_observer_protocol_sha256": freeze["model"]["status"]["observer_protocol_sha256"],
            "model_response_schemas": schemas, "attempts": receipts,
            "evidence_sha256": {"original_freeze": a.FREEZE_SHA, "original_run": a.sha(run_dir / "run.json"),
                                "original_predictions": a.sha(run_dir / "predictions.jsonl"), "independent_audit": a.sha(audit_path),
                                "independent_auditor": a.sha(AUDITOR_PATH), "compatibility_script": a.sha(Path(__file__))},
            "limitations": ["CPU reuses old raw responses; it does not establish new-model inference repeatability or new accuracy results.",
                            "This batch demonstrates behavior preservation only for these saved inputs/returns, not all possible inputs.",
                            "The new product persists reference metadata hashes, not prepared PNG bytes; original experimental call artifacts remain separately retained.",
                            "Original 51 photos remain exposed development data; no production promotion or physical safety inference follows."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--run", type=Path, default=ROOT / "evaluation-runs/v0.8/reference_guarded_v1")
    parser.add_argument("--audit", type=Path, default=ROOT / "test-results/v0.8-reference-guarded-independent-audit-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.project_root.resolve(), args.run.resolve(), args.audit.resolve(), args.output.resolve())
    except Exception as exc:
        if args.output.is_dir() and not (args.output / "compatibility.json").exists():
            (args.output / "compatibility.json").write_text(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                                                                      "model_called": False}, ensure_ascii=False, indent=2) + "\n")
        raise
    path = args.output / "compatibility.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": "passed", "replayed": len(result["attempts"]), "output": str(path), "sha256": a.sha(path)}))


if __name__ == "__main__":
    main()
