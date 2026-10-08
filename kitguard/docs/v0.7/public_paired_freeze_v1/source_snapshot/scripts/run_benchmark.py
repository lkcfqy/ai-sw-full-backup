"""Run a frozen, hash-verified set of public photographs through the real local model."""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from kitguard.evaluation import file_sha256, read_manifest, score_case, summarize, validate_case
from kitguard.vision import LocalVision


def app_upload_bytes(source: Path) -> bytes:
    """Exercise the actual upload route in an isolated store; do not duplicate resizing code."""
    from fastapi.testclient import TestClient

    from kitguard.app import create_app

    with TemporaryDirectory(prefix="kitguard-benchmark-upload-") as temporary:
        app = create_app(data_dir=Path(temporary))
        with TestClient(app) as client:
            created = client.post(
                "/api/orders",
                json={
                    "title": "Public photograph preprocessing benchmark",
                    "requirements": {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1},
                },
            )
            created.raise_for_status()
            order = created.json()["order"]
            uploaded = client.post(
                f"/api/orders/{order['id']}/photos",
                data={"expected_revision": 1},
                files={"photo": (source.name, source.read_bytes(), "image/png")},
            )
            uploaded.raise_for_status()
            photo = uploaded.json()["photo"]
            return app.state.store.photo_path(photo["id"]).read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument(
        "--max-cases", type=int, default=0, help="First N manifest cases, selected before inference; 0=all"
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument(
        "--observation-mode", choices=["single", "dual_orientation", "spatial_inventory", "spatial_consensus", "spatial_guarded"], default="single"
    )
    parser.add_argument("--input-pipeline", choices=["original", "app-upload"], default="original")
    parser.add_argument("--image-max-side", type=int, choices=[1024, 1536, 2048], default=1024)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output path already exists; retain previous runs and choose a new path")
    if args.max_cases < 0:
        raise SystemExit("--max-cases must be nonnegative")
    manifest = read_manifest(args.manifest)
    cases = [case for case in manifest["cases"] if case["split"] == args.split]
    if args.max_cases:
        cases = cases[: args.max_cases]
    if not cases:
        raise SystemExit("No selected cases")
    paths = [validate_case(case, args.dataset_root) for case in cases]
    project = Path(__file__).resolve().parents[1]
    source_files = [
        project / "kitguard" / name
        for name in [
            "__init__.py",
            "public_demo_catalog.py",
            "vision.py",
            "app.py",
            "schemas.py",
            "evaluation.py",
            "feedback.py",
            "store.py",
            "models.py",
            "instructions.py",
            "evidence.py",
            "spatial.py",
            "consensus.py", "identity.py",
        ]
    ]
    source_files.append(Path(__file__).resolve())
    args.output.mkdir(parents=True)
    source_dir = args.output / "source_snapshot"
    source_dir.mkdir()
    for path in source_files:
        (source_dir / path.name).write_bytes(path.read_bytes())
    vision = LocalVision(
        args.model_path, observation_mode=args.observation_mode, image_max_side=args.image_max_side
    )
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "expected_cases": len(cases),
        "completed_cases": 0,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": file_sha256(args.manifest),
        "split": args.split,
        "input_pipeline": args.input_pipeline,
        "selection": "Manifest order fixed before inference, first N only when explicitly requested",
        "case_ids": [case["id"] for case in cases],
        "source_hashes": {path.name: file_sha256(path) for path in source_files},
        "model_before": vision.status(),
    }
    (args.output / "manifest.json").write_bytes(args.manifest.read_bytes())
    (args.output / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    if not metadata["model_before"]["available"]:
        raise SystemExit("Real model files are unavailable; no predictions fabricated")
    rows = []
    for index, (case, path) in enumerate(zip(cases, paths, strict=True), start=1):
        started = time.perf_counter()
        observation, error = None, None
        error_diagnostics = None
        observation_diagnostics = None
        model_input_sha256 = None
        try:
            model_input = path
            if args.input_pipeline == "app-upload":
                inputs = args.output / "normalized_inputs"
                inputs.mkdir(exist_ok=True)
                model_input = inputs / f"{index:03d}.jpg"
                model_input.write_bytes(app_upload_bytes(path))
            model_input_sha256 = file_sha256(model_input)
            # Fixed valid quantities are deliberately unrelated to each image's truth.
            # The model adapter does not send quantities to the observer.
            observation = vision.observe(model_input, {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1}, {})
            observation_diagnostics = vision.status().get("last_observation_attempt")
        except Exception as exc:  # noqa: BLE001 -- Model failures must stay in the evaluation denominator.
            error = f"{type(exc).__name__}: {exc}"
            error_diagnostics = getattr(exc, "observation_diagnostics", None)
            observation_diagnostics = error_diagnostics
        elapsed = round((time.perf_counter() - started) * 1000)
        row = score_case(case, observation, elapsed, error)
        row["runtime"] = None if error else vision.status().get("last_inference")
        row["error_diagnostics"] = error_diagnostics
        # Preserve every prepared-input hash and both lists, not only the last case.
        row["observation_diagnostics"] = observation_diagnostics
        row["input_pipeline"] = args.input_pipeline
        row["model_input_sha256"] = model_input_sha256
        rows.append(row)
        with (args.output / "predictions.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    "progress": f"{index}/{len(cases)}",
                    "id": case["id"],
                    "exact": row["counts_exact"],
                    "error": error,
                    "ms": elapsed,
                }
            ),
            flush=True,
        )
    metadata["status"] = "completed"
    metadata["completed_cases"] = len(rows)
    metadata["finished_at"] = datetime.now(UTC).isoformat()
    metadata["model_after"] = vision.status()
    metadata["source_hashes_after"] = {path.name: file_sha256(path) for path in source_files}
    metadata["source_changed_during_run"] = metadata["source_hashes_after"] != metadata["source_hashes"]
    metadata["summary"] = summarize(rows)
    (args.output / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metadata["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
