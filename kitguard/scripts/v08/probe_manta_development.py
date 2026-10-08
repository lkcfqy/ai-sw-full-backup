"""Four already-viewed MANTA development views; no test selection or production change."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kitguard.vision import LocalVision
from scripts.probe_selective_identity import SelectiveIdentityVision
from scripts.run_benchmark import app_upload_bytes

PARTS = ("bolt", "nut", "washer", "bracket")
DEV = ROOT / "datasets/derived/v0.8/manta-identity-v1/development_view_check_v1/leftmost_view_v1"
MODEL = Path.home() / "Downloads/AI-Models/Qwen3.6-27B-4bit"


class RecordedVision(LocalVision):
    _generate = SelectiveIdentityVision._generate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def identity(observation, error=None):
    if error:
        return "execution_error"
    counts = observation["observed"]
    if (observation["issues"] or observation["action"]["kind"] != "none"
            or any(counts[p] is None for p in PARTS)):
        return "unknown"
    positive = [p for p in PARTS if counts[p] > 0]
    if len(positive) != 1 or counts[positive[0]] != 1:
        return "non_singleton_inventory"
    return positive[0]


def sources():
    paths = sorted((ROOT / "kitguard").glob("*.py"))
    paths += [Path(__file__), ROOT / "scripts/probe_selective_identity.py", ROOT / "scripts/run_benchmark.py"]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def run(output):
    if output.exists():
        raise FileExistsError("Preserve all prior attempts")
    receipt = json.loads((DEV / "receipt.json").read_text())
    reviewed = json.loads((DEV / "visual_qa.json").read_text())
    if not reviewed["all_four_outputs_viewed"] or reviewed["receipt_sha256"] != sha(DEV / "receipt.json"):
        raise ValueError("Development visual check missing or changed")
    records = receipt["records"]
    expected = {f"mechanics_{category}_{index:05d}.png"
                for category in ("nut", "yellow_green_washer") for index in (1, 2)}
    if len(records) != 4 or {Path(r["output"]).name for r in records} != expected:
        raise ValueError("Only four preselected development views are permitted")
    for record in records:
        path = (ROOT / record["output"]).resolve()
        if path.parent != DEV or sha(path) != record["sha256"] or not record["development_only"]:
            raise ValueError("Development view binding mismatch")
    engine = RecordedVision(MODEL, observation_mode="spatial_guarded", image_max_side=1536)
    status = engine.status()
    if not status["available"]:
        raise ValueError("Pinned local model unavailable")
    output.mkdir(parents=True)
    (output / "inputs").mkdir()
    before = sources()
    protocol = {"schema": "kitguard.v08.manta-development-probe.v1", "started_at": datetime.now(UTC).isoformat(),
                "source_hashes": before, "view_receipt_sha256": sha(DEV / "receipt.json"),
                "visual_qa_sha256": sha(DEV / "visual_qa.json"), "records": records,
                "model_identity": status, "planned": 4, "mode": "spatial_guarded", "references": {},
                "model_input": "Fixed leftmost development crop, then existing app-upload transform",
                "requirements_to_observer": False, "repeat_failures": False,
                "scope": "Already-viewed four single-object identity development checks, not holdout or counting skill",
                "independent_physical_objects_certified": False, "production_change": False}
    write(output / "protocol.json", protocol)
    shutil.copyfile(__file__, output / Path(__file__).name)
    run_state = {"status": "running", "started_at": protocol["started_at"], "planned": 4, "completed": 0}
    write(output / "run.json", run_state)
    rows = []
    try:
        for index, record in enumerate(records, 1):
            if sources() != before:
                raise ValueError("Source changed; stop without replacement")
            observation, error, diagnostics = None, None, None
            target = output / "inputs" / f"{index:03d}.jpg"
            source = ROOT / record["output"]
            start = time.perf_counter()
            loaded_before = engine.status()["loaded"]
            try:
                target.write_bytes(app_upload_bytes(source))
                engine.artifact_dir = output / "cases" / f"{index:03d}"
                # These API-required quantities never enter the observer prompt.
                observation = engine.observe(target, dict.fromkeys(PARTS, 1), {})
                diagnostics = engine.status().get("last_observation_attempt")
            except Exception as exc:  # noqa: BLE001 -- keep every failed attempt in the denominator.
                error = f"{type(exc).__name__}: {exc}"
                diagnostics = getattr(exc, "observation_diagnostics", None)
            predicted = identity(observation, error)
            truth = "nut" if Path(record["source_member"]).parts[0] == "nut" else "washer"
            category = "E" if error else "U" if predicted == "unknown" else "C" if predicted == truth else "W"
            row = {"index": index, "source_member": record["source_member"], "truth_identity": truth,
                   "predicted_identity": predicted, "result": category, "observation": observation,
                   "error": error, "diagnostics": diagnostics, "elapsed_seconds": time.perf_counter() - start,
                   "normalized_sha256": sha(target) if target.exists() else None, "loaded_before": loaded_before}
            rows.append(row)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            run_state["completed"] = len(rows)
            write(output / "run.json", run_state)
            print(json.dumps({k: row[k] for k in ("index", "predicted_identity", "result", "elapsed_seconds", "error")}), flush=True)
        run_state["status"] = "completed"
    except BaseException as exc:
        run_state.update(status="interrupted", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        run_state.update(finished_at=datetime.now(UTC).isoformat(), source_changed=sources() != before)
        write(output / "run.json", run_state)
        counts = Counter(row["result"] for row in rows)
        write(output / "analysis.json", {"planned": 4, "attempted": len(rows),
              "C_W_U_E_N": {key: 4 - len(rows) if key == "N" else counts[key] for key in "CWUEN"},
              "rows": [{k: row[k] for k in ("index", "truth_identity", "predicted_identity", "result")} for row in rows],
              "scope": protocol["scope"], "counting_capability_measured": False, "model_promoted": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
