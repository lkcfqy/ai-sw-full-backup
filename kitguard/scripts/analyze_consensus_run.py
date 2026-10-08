"""Recount completed spatial-consensus runs and their same-run first-pass baseline."""

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from kitguard.evaluation import file_sha256, score_case, summarize
from kitguard.identity import save_crops, select_targets
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory, count_inventory
from kitguard.vision import _prepare_image


def verify_inputs(directory: Path, meta: dict, rows: list[dict]) -> dict:
    """Recreate only deterministic pixel preprocessing; never load a model."""
    if meta["input_pipeline"] != "app-upload":
        return {"verified": False, "reason": "This verifier requires saved app-upload JPEG inputs"}
    checked, crop_checked = 0, 0
    with TemporaryDirectory(prefix="kitguard-input-audit-") as tmp:
        original, rotated = Path(tmp) / "original.png", Path(tmp) / "rotated.png"
        for index, row in enumerate(rows, 1):
            diagnostic = row.get("observation_diagnostics") or row.get("error_diagnostics")
            if not diagnostic:
                if not row["error"]:
                    raise ValueError("Successful row has no current observation trace")
                continue
            uploaded = directory / "normalized_inputs" / f"{index:03d}.jpg"
            digest = file_sha256(uploaded)
            if digest != row["model_input_sha256"] or digest != diagnostic["source_sha256"]:
                raise ValueError("Stored input hash and observation trace do not match this row")
            _prepare_image(uploaded, original, meta["model_before"]["image_max_side"])
            with Image.open(original) as im:
                im.transpose(Image.Transpose.ROTATE_90).save(rotated)
            hashes = {"original": file_sha256(original), "rotate_90_ccw": file_sha256(rotated)}
            for item in diagnostic["passes"]:
                if item["input_sha256"] != hashes[item["transform"]]:
                    raise ValueError("Prepared observation image is not reproducible")
                checked += 1
            review = (row.get("observation") or {}).get("identity_verification")
            if review is not None:
                if review["source_sha256"] != digest or review["full_input_sha256"] != hashes["original"]:
                    raise ValueError("Identity review is not bound to this input")
                observation = row["observation"]
                base = dict(observation)
                base.pop("identity_verification", None)
                base["observed"] = observation["verification"]["passes"][0]["observed"]
                base["issues"] = []
                base["action"] = {"kind": "none", "message": "Reconstructed base", "region": None}
                base["object_evidence"] = {**observation["object_evidence"], "uncertain_parts": []}
                targets = select_targets(base)
                crops = save_crops(uploaded, targets, Path(tmp))
                expected_crops = [{**c, "crop_file": Path(c["crop_file"]).name,
                    "pixel_crop_file": Path(c["pixel_crop_file"]).name} for c in crops]
                if review["crops"] != expected_crops:
                    raise ValueError("Identity crops or their metadata cannot be reproduced")
                crop_checked += 2 * len(crops)
    return {"verified": True, "prepared_inputs_recreated": checked,
            "identity_crop_files_recreated": crop_checked,
            "scope": "Stored upload bytes and both pixel transforms; this does not prove scene authenticity"}


def analyze(directory: Path) -> dict:
    meta = json.loads((directory / "run.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    rows = [json.loads(line) for line in (directory / "predictions.jsonl").read_text().splitlines()]
    if meta["status"] != "completed" or meta["source_changed_during_run"]:
        raise ValueError("Only complete, unchanged-source runs are eligible")
    if [row["case_id"] for row in rows] != meta["case_ids"] or len(rows) != meta["expected_cases"]:
        raise ValueError("Incomplete or reordered prediction set")
    input_audit = verify_inputs(directory, meta, rows)
    cases = {case["id"]: case for case in manifest["cases"]}
    first_rows, final_rows = [], []
    first_model_seconds, second_model_seconds, identity_model_seconds = [], [], []
    transitions = {"correct_retained": 0, "correct_abstained": 0, "wrong_blocked": 0,
                   "wrong_retained": 0, "first_unclear_or_error": 0}
    for row in rows:
        case = cases[row["case_id"]]
        if row["sha256"] != case["sha256"] or row["ground_truth"] != case["ground_truth"]:
            raise ValueError("Prediction identity/truth does not match frozen manifest")
        if row["observation"] is not None:
            Observation.model_validate(row["observation"])
        final = score_case(case, row["observation"], row["latency_ms"], row["error"])
        for key in ("counts_exact", "actionable_counts", "tasks"):
            if row[key] != final[key]:
                raise ValueError(f"Saved score disagrees with independent recount: {key}")
        diagnostic = row.get("observation_diagnostics") or row.get("error_diagnostics") or {}
        passes = diagnostic.get("passes", [])
        first = None
        if passes and passes[0]["transform"] == "original":
            first, _ = count_inventory(SpatialInventory.model_validate(passes[0]["inventory"]), "Same-run first pass")
            for index, destination in [(0, first_model_seconds), (1, second_model_seconds)]:
                if len(passes) > index and "seconds" in passes[index].get("runtime", {}):
                    destination.append(passes[index]["runtime"]["seconds"])
        identity_runtime = (diagnostic.get("identity") or {}).get("runtime", {})
        if "seconds" in identity_runtime:
            identity_model_seconds.append(identity_runtime["seconds"])
        baseline = score_case(case, first, 0, None if first is not None else "First pass unavailable")
        first_rows.append(baseline)
        final_rows.append(final)
        if not baseline["actionable_counts"]:
            transitions["first_unclear_or_error"] += 1
        elif baseline["counts_exact"]:
            transitions["correct_retained" if final["actionable_counts"] else "correct_abstained"] += 1
        else:
            transitions["wrong_retained" if final["actionable_counts"] else "wrong_blocked"] += 1
    first_summary, final_summary = summarize(first_rows), summarize(final_rows)
    first_summary.pop("latency_ms")  # No synthetic 0 ms baseline is presented as actual runtime.
    return {
        "analyzed_at": datetime.now(UTC).isoformat(), "run": str(directory),
        "run_sha256": file_sha256(directory / "run.json"),
        "predictions_sha256": file_sha256(directory / "predictions.jsonl"),
        "manifest_sha256": file_sha256(directory / "manifest.json"),
        "analysis_source_sha256": file_sha256(Path(__file__)),
        "first_pass": first_summary, "final": final_summary, "transitions": transitions,
        "model_only_median_seconds": {
            "first": statistics.median(first_model_seconds) if first_model_seconds else None,
            "second": statistics.median(second_model_seconds) if second_model_seconds else None,
            "identity": statistics.median(identity_model_seconds) if identity_model_seconds else None,
        },
        "correct_actionable": {
            "first_pass": sum(r["counts_exact"] and r["actionable_counts"] for r in first_rows),
            "final": sum(r["counts_exact"] and r["actionable_counts"] for r in final_rows),
            "denominator": len(rows),
        },
        "schema_revalidated": len(rows),
        "input_audit": input_audit,
        "limitations": [
            "First-pass baseline is reconstructed from actual saved original-pass output within the same run, not a separate timed end-to-end deployment.",
            "Digital rotation is not a new photograph; same-model calls are correlated.",
            "Model-only seconds exclude preprocessing/loading/API; final latency includes the benchmark upload/observe path.",
            "Abstentions remain failures for complete count accuracy; lower error among accepted results must be read together with coverage.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve previous analysis; choose a new output path")
    result = analyze(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"transitions": result["transitions"], "final": result["final"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
