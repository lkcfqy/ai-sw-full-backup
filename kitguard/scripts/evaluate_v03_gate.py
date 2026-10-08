"""CPU-only recomputation of the predeclared v0.3 research selection gates.

No images are opened and no model is loaded. Run with --run RUN --stage
development|holdout --output NEW.json. Holdout additionally requires the passing
development report. The saved source snapshot is hashed, never executed.
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from kitguard.evaluation import file_sha256, rate, read_manifest, score_case
from kitguard.schemas import PARTS, Observation
from kitguard.spatial import SpatialInventory, count_inventory

DEFAULT_PROTOCOL = PROJECT / "docs/v0.3/HOLDOUT_GATES_V1.json"
LABELS = ("C", "W", "U", "E")
SCORER_FILES = (
    "evaluation.py",
    "schemas.py",
    "spatial.py",
    "identity.py",
    "consensus.py",
    "app.py",
    "feedback.py",
)


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def valid_panel_counts(counts: dict) -> bool:
    """All 255 legal BOMs: each class 0..3 and total 1..12."""
    return (
        set(counts) == set(PARTS)
        and all(type(counts[p]) is int and 0 <= counts[p] <= 3 for p in PARTS)
        and 1 <= sum(counts.values()) <= 12
    )


def bom_panel() -> list[dict]:
    return [
        dict(zip(PARTS, values, strict=True))
        for values in itertools.product(range(4), repeat=4)
        if 1 <= sum(values) <= 12
    ]


def classification(row: dict) -> str:
    if row["error"]:
        return "E"
    if not row["actionable_counts"]:
        return "U"
    return "C" if row["counts_exact"] else "W"


def panel_result(row: dict) -> dict:
    # decide == ready iff no unknown/issues/action AND observed == requirements.
    # Thus at most one of all 255 legal BOMs can be ready; no need to generate
    # 255 random check IDs or count correlated order pairs as extra images.
    counts = row["observation"].get("observed", {}) if row["observation"] else {}
    ready_bom = counts if row["actionable_counts"] and valid_panel_counts(counts) else None
    return {
        "orders_per_image": 255,
        "ready_requirements": ready_bom,
        "any_false_ready": bool(ready_bom is not None and ready_bom != row["ground_truth"]),
    }


def first_pass_observation(raw: dict) -> tuple[dict | None, str | None]:
    """Recover the real original pass even if a later call failed; no fallback."""
    diagnostic = raw.get("observation_diagnostics") or raw.get("error_diagnostics") or {}
    passes = diagnostic.get("passes", [])
    if not passes or passes[0].get("transform") != "original":
        return None, "UnavailableFirstPass: no saved original inventory"
    try:
        inventory = SpatialInventory.model_validate(passes[0]["inventory"])
        observation, _ = count_inventory(inventory, "Same-run actual original pass (correlated ablation)")
        # Validate independently of any final guarded observation or scoring flags.
        Observation.model_validate(observation)
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"InvalidFirstPass: {type(exc).__name__}: {exc}"
    return observation, None


def rescore(case: dict, raw: dict) -> tuple[dict, dict]:
    candidate = score_case(case, raw.get("observation"), raw["latency_ms"], raw.get("error"))
    first, error = first_pass_observation(raw)
    # score_case requires an integer duration. This zero is an internal sentinel,
    # never presented as a baseline latency or used by a gate.
    baseline = score_case(case, first, 0, error)
    baseline["latency_ms"] = None
    for row in (candidate, baseline):
        row["classification"] = classification(row)
        row["panel"] = panel_result(row)
    return candidate, baseline


def metrics(rows: list[dict], *, latency: bool) -> dict:
    n = len(rows)
    counts = {label: sum(row["classification"] == label for row in rows) for label in LABELS}
    assert sum(counts.values()) == n
    tasks = [task for row in rows for task in row["tasks"]]
    perturb = [t for t in tasks if t["kind"] == "mismatched"]
    nominal_abnormal = [t for t in tasks if t["kind"] == "nominal" and not t["truth_matches_order"]]
    nominal_normal = [t for t in tasks if t["kind"] == "nominal" and t["truth_matches_order"]]
    matched = [t for t in tasks if t["kind"] == "matched"]
    answer_n = counts["C"] + counts["W"]
    times = sorted(r["latency_ms"] for r in rows) if latency else []
    return {
        "images": n,
        **counts,
        "correct_actionable": rate(counts["C"], n),
        "wrong_actionable_all_images": rate(counts["W"], n),
        "actionable_coverage": rate(answer_n, n),
        "wrong_given_actionable": rate(counts["W"], answer_n),
        "abstention": rate(counts["U"], n),
        "errors": rate(counts["E"], n),
        "counts_exact_including_nonactionable": rate(sum(r["counts_exact"] for r in rows), n),
        "matched_correct_ready": rate(sum(t["correct_ready"] for t in matched), len(matched)),
        "fixed_perturbation_false_ready": rate(sum(t["false_ready"] for t in perturb), len(perturb)),
        "nominal_anomaly_false_ready": rate(
            sum(t["false_ready"] for t in nominal_abnormal), len(nominal_abnormal)
        ),
        "nominal_normal_ready": rate(sum(t["correct_ready"] for t in nominal_normal), len(nominal_normal)),
        "panel_any_false_ready": rate(sum(r["panel"]["any_false_ready"] for r in rows), n),
        "latency_ms": {
            "median": statistics.median(times),
            "maximum": max(times),
            "scope": "Observed complete candidate call including app-upload; first/cold row retained",
        }
        if latency and times
        else None,
        "latency_note": None
        if latency
        else "No separately measured end-to-end baseline latency; same-run first-pass ablation only",
    }


def compare(candidates: list[dict], baselines: list[dict]) -> dict:
    matrix = {a: {b: 0 for b in LABELS} for a in LABELS}
    for candidate, baseline in zip(candidates, baselines, strict=True):
        matrix[baseline["classification"]][candidate["classification"]] += 1
    old_wrong = sum(r["classification"] == "W" for r in baselines)
    new_wrong = sum(r["classification"] == "W" for r in candidates)
    introduced = sum(matrix[x]["W"] for x in LABELS if x != "W")
    return {
        "paired_matrix_baseline_rows_candidate_columns": matrix,
        "baseline_wrong": old_wrong,
        "candidate_wrong": new_wrong,
        "blocked_baseline_wrong": sum(matrix["W"][x] for x in LABELS if x != "W"),
        "introduced_wrong": introduced,
        "correct_to_abstention": matrix["C"]["U"],
        "demonstrated_error_blocking_benefit": old_wrong > 0 and new_wrong < old_wrong and introduced == 0,
        "zero_wrong_both_note": "No demonstrated error-blocking benefit"
        if old_wrong == new_wrong == 0
        else None,
    }


def evaluate_rows(cases: list[dict], raw_rows: list[dict], stage_config: dict) -> dict:
    pairs = [rescore(case, raw) for case, raw in zip(cases, raw_rows, strict=True)]
    candidates, baselines = [pair[0] for pair in pairs], [pair[1] for pair in pairs]
    groups = {}
    for name, gate in stage_config["groups"].items():
        indices = [i for i, case in enumerate(cases) if case["subgroup"] in gate["subgroups"]]
        candidate = metrics([candidates[i] for i in indices], latency=True)
        baseline = metrics([baselines[i] for i in indices], latency=False)
        passed = (
            candidate["images"] == gate["images"]
            and candidate["C"] >= gate["correct_actionable_min"]
            and candidate["W"] == candidate["E"] == 0
            and candidate["latency_ms"] is not None
            and candidate["latency_ms"]["median"] <= stage_config["median_latency_ms_max"]
        )
        groups[name] = {"candidate": candidate, "baseline": baseline, "gate": gate, "passed": passed}
    overall = metrics(candidates, latency=True)
    false_ready_gates = {}
    for name, denominator in stage_config.get("zero_false_ready_gates", {}).items():
        value = overall[name]
        false_ready_gates[name] = {
            **value,
            "expected_denominator": denominator,
            "passed": value["denominator"] == denominator and value["numerator"] == 0,
        }
    return {
        "candidate": overall,
        "baseline": metrics(baselines, latency=False),
        "groups": groups,
        "false_ready_gates": false_ready_gates,
        "comparison": compare(candidates, baselines),
        "stage_passed": all(group["passed"] for group in groups.values())
        and all(gate["passed"] for gate in false_ready_gates.values()),
        "cases": [
            {
                "case_id": case["id"],
                "source_id": case["source_id"],
                "subgroup": case["subgroup"],
                "ground_truth": case["ground_truth"],
                "candidate": c,
                "baseline": b,
            }
            for case, c, b in zip(cases, candidates, baselines, strict=True)
        ],
    }


def verify_provenance(
    run_dir: Path, metadata: dict, manifest: dict, config: dict, protocol: dict, stage: str
) -> list[dict]:
    selected = [case for case in manifest["cases"] if case["split"] == stage]
    expected = config["case_ids"]
    if [case["id"] for case in selected] != expected or metadata.get("case_ids") != expected:
        raise ValueError("Run/manifest case sequence differs from the full frozen selection")
    if (
        metadata.get("manifest_sha256") != config["manifest_sha256"]
        or file_sha256(run_dir / "manifest.json") != config["manifest_sha256"]
    ):
        raise ValueError("Run manifest differs from frozen manifest")
    if (
        metadata.get("status") != "completed"
        or metadata.get("expected_cases") != len(expected)
        or metadata.get("completed_cases") != len(expected)
    ):
        raise ValueError(f"Incomplete run: planned denominator remains {len(expected)}")
    before, after = metadata.get("source_hashes", {}), metadata.get("source_hashes_after", {})
    if metadata.get("source_changed_during_run") is not False or not before or before != after:
        raise ValueError("Run sources changed or no final source-integrity record exists")
    required = set(protocol["method_source_hashes"])
    if not required <= set(before):
        raise ValueError("Required source files absent from run snapshot")
    for name, digest in before.items():
        if Path(name).name != name or file_sha256(run_dir / "source_snapshot" / name) != digest:
            raise ValueError(f"Source snapshot hash mismatch: {name}")
    if stage == "holdout" and any(
        before[name] != digest for name, digest in protocol["method_source_hashes"].items()
    ):
        raise ValueError("Holdout method differs from predeclared source freeze")
    if metadata.get("input_pipeline") != "app-upload" or metadata.get("split") != stage:
        raise ValueError("Wrong input pipeline or split")
    for point in ("model_before", "model_after"):
        model = metadata.get(point, {})
        for key, value in protocol["required_model_status"].items():
            if model.get(key) != value:
                raise ValueError(f"Model configuration mismatch: {point}.{key}")
    if stage == "holdout" and datetime.fromisoformat(metadata["started_at"]) <= datetime.fromisoformat(
        protocol["created_at"]
    ):
        raise ValueError("Gate was not frozen before holdout started")
    return selected


def evaluate_run(
    run_dir: Path, stage: str, protocol_path: Path = DEFAULT_PROTOCOL, development_report: Path | None = None
) -> dict:
    protocol = strict_json(protocol_path.read_text())
    for name, digest in protocol["scoring_source_hashes"].items():
        if Path(name).name != name or file_sha256(PROJECT / "kitguard" / name) != digest:
            raise ValueError("Current scoring implementation differs from the frozen scoring source")
    config = protocol["stages"][stage]
    metadata = strict_json((run_dir / "run.json").read_text())
    manifest = read_manifest(run_dir / "manifest.json")
    cases = verify_provenance(run_dir, metadata, manifest, config, protocol, stage)
    raw_rows = [
        strict_json(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines() if line.strip()
    ]
    if [r.get("case_id") for r in raw_rows] != config["case_ids"]:
        raise ValueError(
            f"Predictions incomplete, duplicated or out of order; planned denominator {len(cases)} retained"
        )
    for index, (case, row) in enumerate(zip(cases, raw_rows, strict=True), 1):
        for field in ("source_id", "image", "sha256", "split", "ground_truth", "subgroup"):
            if row.get(field) != case.get(field):
                raise ValueError(f"Prediction/manifest metadata mismatch: {case['id']} {field}")
        if row.get("input_pipeline") != "app-upload":
            raise ValueError("Prediction pipeline mismatch")
        photo = run_dir / "normalized_inputs" / f"{index:03d}.jpg"
        if row.get("model_input_sha256") is not None:
            if file_sha256(photo) != row["model_input_sha256"]:
                raise ValueError("Saved normalized input hash mismatch")
        elif not row.get("error"):
            raise ValueError("Successful prediction lacks its input hash")
    report = evaluate_rows(cases, raw_rows, config)
    development_passed = False
    if stage == "holdout" and development_report is not None:
        prior = strict_json(development_report.read_text())
        development_passed = (
            prior.get("stage") == "development"
            and prior.get("stage_passed") is True
            and prior.get("protocol_sha256") == file_sha256(protocol_path)
            and prior.get("planned_images") == 28
            and prior.get("complete") is True
        )
        if not development_passed:
            raise ValueError("Development gate evidence does not match this frozen protocol or did not pass")
    report.update(
        {
            "schema_version": 1,
            "stage": stage,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "run_path": str(run_dir.resolve()),
            "complete": True,
            "planned_images": len(cases),
            "completed_images": len(raw_rows),
            "protocol_sha256": file_sha256(protocol_path),
            "run_json_sha256": file_sha256(run_dir / "run.json"),
            "predictions_sha256": file_sha256(run_dir / "predictions.jsonl"),
            "manifest_sha256": file_sha256(run_dir / "manifest.json"),
            "run_source_hashes": metadata["source_hashes"],
            "evaluator_sha256": file_sha256(Path(__file__)),
            "scoring_source_hashes": {
                name: file_sha256(PROJECT / "kitguard" / name) for name in SCORER_FILES
            },
            "development_gate_passed": development_passed if stage == "holdout" else None,
            "development_report_sha256": file_sha256(development_report) if development_report else None,
            "default_adoption_eligible": stage == "holdout"
            and report["stage_passed"]
            and report["comparison"]["demonstrated_error_blocking_benefit"]
            and development_passed,
            "scope": "Research benchmark gate only; not contest ranking, field validity, shipping safety or release authorization",
            "limitations": protocol["limitations"],
        }
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--stage", choices=["development", "holdout"], required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--development-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; keep previous evidence")
    try:
        report = evaluate_run(args.run, args.stage, args.protocol, args.development_report)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Gate not evaluated: {exc}. No passing report created.\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {k: report[k] for k in ("stage", "planned_images", "stage_passed", "default_adoption_eligible")}
        )
    )


if __name__ == "__main__":
    main()
