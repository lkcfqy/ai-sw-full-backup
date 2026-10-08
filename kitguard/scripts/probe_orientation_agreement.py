"""Development-only orientation probe; no holdout data or invented model answers."""

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from kitguard.evaluation import file_sha256, read_manifest, score_case, summarize, validate_case
from kitguard.vision import LocalVision

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/manifests/mvtec_loco_screw_bag_pending/benchmark_v2.json"
BASELINE = ROOT / "evaluation-runs/loco_development_8b_v1/predictions.jsonl"
OUTPUT = ROOT / "evaluation-runs/loco_orientation_development_probe_v1"


def combine(first, second):
    unknown = [
        p
        for p in first["observed"]
        if first["observed"][p] is None
        or second["observed"][p] is None
        or first["observed"][p] != second["observed"][p]
    ]
    obstacle = (
        unknown
        or first["issues"]
        or second["issues"]
        or first["action"]["kind"] != "none"
        or second["action"]["kind"] != "none"
    )
    return {
        "observed": {p: None if p in unknown else first["observed"][p] for p in first["observed"]},
        "issues": (
            ["두 방향 관찰이 일치하지 않습니다. 실제 부품을 분리해 재촬영하세요."] if obstacle else []
        ),
        "action": {
            "kind": "recapture" if obstacle else "none",
            "message": "서로 다른 방향의 관찰 수량을 대조했습니다.",
            "region": None,
        },
        "backend": "mlx",
        "model_label": "Qwen3-VL-8B-Instruct, two orientations (same model)",
    }


def main():
    if OUTPUT.exists():
        raise SystemExit("Preserve previous probe; output exists")
    OUTPUT.mkdir(parents=True)
    original = {row["case_id"]: row for row in map(json.loads, BASELINE.read_text().splitlines())}
    cases = [c for c in read_manifest(MANIFEST)["cases"] if c["split"] == "development"]
    v = LocalVision()
    rows = []
    raw_rows = []
    for c in cases:
        path = validate_case(c, ROOT / "datasets")
        t = time.perf_counter()
        with TemporaryDirectory(prefix="kitguard-orientation-probe-") as d:
            rotated = Path(d) / "rotation.png"
            with Image.open(path) as image:
                image.transpose(Image.Transpose.ROTATE_90).save(rotated)
            observation = v.observe(rotated, {"bolt": 1, "nut": 1, "washer": 1, "bracket": 1}, {})
            transform_hash = file_sha256(rotated)
        elapsed = round((time.perf_counter() - t) * 1000)
        raw = score_case(c, observation, elapsed)
        raw["transform"] = "90 degree counterclockwise rotation; no crop/composite"
        raw["model_input_sha256"] = transform_hash
        raw_rows.append(raw)
        combined = combine(original[c["id"]]["observation"], observation)
        row = score_case(c, combined, elapsed + original[c["id"]]["latency_ms"])
        rows.append(row)
        with (OUTPUT / "rotated_predictions.jsonl").open("a") as f:
            f.write(json.dumps(raw, ensure_ascii=False) + "\n")
        with (OUTPUT / "agreement_predictions.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    "id": c["id"],
                    "rotated_exact": raw["counts_exact"],
                    "agreement_exact": row["counts_exact"],
                    "actionable": row["actionable_counts"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    result = {
        "development_only": True,
        "same_model_correlated_calls": True,
        "manifest_sha256": file_sha256(MANIFEST),
        "baseline_sha256": file_sha256(BASELINE),
        "script_sha256": file_sha256(Path(__file__)),
        "timing": "sum of two separately run process invocations; not an integrated endpoint latency",
        "rotated_summary": summarize(raw_rows),
        "agreement_summary": summarize(rows),
    }
    (OUTPUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
