"""Check final guarded observer, decision code, and all 51 upload bytes against the freeze.

This is a CPU compatibility check, not another recognition experiment. Run only
after the complete paired study and final application changes, before packaging.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE_SHA = "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7"
UNCHANGED = (
    "vision.py", "spatial.py", "consensus.py", "identity.py", "models.py",
    "schemas.py", "feedback.py", "regions.py",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def function_tree(path, name):
    tree = ast.parse(path.read_text())
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError(f"Missing or duplicate top-level function: {name}")
    return ast.dump(matches[0], include_attributes=False)


def verify(run, freeze_path, root=ROOT):
    metadata = read(run / "run.json")
    if (metadata.get("status") != "completed" or metadata.get("completed_attempts") != 153
            or metadata.get("source_changed") is not False):
        raise ValueError("Wait for the complete unchanged paired study")
    if sha(freeze_path.read_bytes()) != FREEZE_SHA or metadata["freeze_sha256"] != FREEZE_SHA:
        raise ValueError("Unexpected experiment freeze")
    freeze = read(freeze_path)
    snapshot = freeze_path.parent / "source_snapshot"
    current_hashes = {}
    for name in UNCHANGED:
        relative = f"kitguard/{name}"
        expected = freeze["source_hashes"][relative]
        actual = sha((root / relative).read_bytes())
        if actual != expected or sha((snapshot / relative).read_bytes()) != expected:
            raise ValueError(f"Recognition dependency changed: {relative}")
        current_hashes[relative] = actual
    frozen_decide = function_tree(snapshot / "kitguard/app.py", "decide")
    current_decide = function_tree(root / "kitguard/app.py", "decide")
    if current_decide != frozen_decide:
        raise ValueError("The decision function changed after evaluation")

    # Imports are delayed until completed-state and source checks succeed.
    from kitguard import __version__
    from kitguard.vision import LocalVision
    from scripts.run_benchmark import app_upload_bytes

    expected_identity = freeze["model_identity"]["spatial_guarded"]
    engine = LocalVision(Path(expected_identity["path"]), observation_mode="spatial_guarded", image_max_side=1536)
    status = engine.status()
    identity_keys = ("label", "repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
    if any(status[key] != expected_identity[key] for key in identity_keys):
        raise ValueError("Final guarded observer identity differs from evaluated observer")
    source_manifest = root / freeze["manifest"]
    if sha(source_manifest.read_bytes()) != freeze["manifest_sha256"]:
        raise ValueError("Selected images changed after evaluation")
    cases = read(source_manifest)["cases"]
    records = [json.loads(line) for line in (run / "predictions.jsonl").read_text().splitlines()]
    expected_inputs = {}
    for row in records:
        expected_inputs.setdefault(row["case_id"], set()).add(row["normalized_sha256"])
    if len(cases) != 51 or len(records) != 153 or any(len(values) != 1 or None in values for values in expected_inputs.values()):
        raise ValueError("A complete common normalized input is required for all 51 cases")
    photos = []
    for case in cases:
        path = root / "datasets" / case["image"]
        if sha(path.read_bytes()) != case["sha256"]:
            raise ValueError(f"Selected photograph changed: {case['id']}")
        actual = sha(app_upload_bytes(path))
        if {actual} != expected_inputs[case["id"]]:
            raise ValueError(f"Final app upload differs from the evaluated pixels: {case['id']}")
        photos.append({"case_id": case["id"], "normalized_sha256": actual})
    if any(name == "mlx" or name.startswith("mlx.") for name in sys.modules):
        raise ValueError("CPU compatibility verification unexpectedly imported MLX")
    return {
        "schema": "kitguard.v07.release-method-compatibility.v1", "status": "passed",
        "checked_at": datetime.now(UTC).isoformat(), "application_version": __version__,
        "freeze_sha256": FREEZE_SHA, "model_loaded_or_called": False,
        "production_mode_verified": "spatial_guarded",
        "model_identity": {key: status[key] for key in identity_keys},
        "unchanged_recognition_dependencies": current_hashes,
        "unchanged_decide_ast_sha256": sha(current_decide.encode()),
        "current_app_sha256": sha((root / "kitguard/app.py").read_bytes()),
        "current_store_sha256": sha((root / "kitguard/store.py").read_bytes()),
        "current_upload_harness_sha256": sha((root / "scripts/run_benchmark.py").read_bytes()),
        "run_metadata_sha256": sha((run / "run.json").read_bytes()),
        "normalized_inputs_reexecuted": len(photos), "photos": photos,
        "limitations": [
            "This checks frozen observer dependencies, the decision AST, and actual final-app upload bytes; it does not repeat inference.",
            "Workflow/UI changes are separate from this method-compatibility check and require their own regression and browser validation.",
            "References, user-selected regions and earlier-photo context are not covered by the no-reference full-image paired study.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new verification path; preserve earlier evidence")
    result = verify(args.run.resolve(), args.freeze.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "application_version", "normalized_inputs_reexecuted")}))


if __name__ == "__main__":
    main()
