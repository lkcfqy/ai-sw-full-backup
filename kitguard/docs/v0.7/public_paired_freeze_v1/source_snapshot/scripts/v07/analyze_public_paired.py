"""Recompute paired public-photo results, retaining all planned photographs."""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
from collections import Counter
from pathlib import Path

from kitguard.app import decide
from kitguard.evaluation import score_case
from kitguard.schemas import Observation

MODES = ("spatial_inventory", "spatial_guarded")
CANDIDATE_MODE = "selective_identity_experimental_v1"
PARTS = ("bolt", "nut", "washer", "bracket")


def orders(parts):
    for values in itertools.product(range(4), repeat=len(parts)):
        if any(values):
            yield dict.fromkeys(PARTS, 0) | dict(zip(parts, values, strict=True))


def false_ready_panel(case, observation, error):
    panels = {}
    parsed = Observation.model_validate(observation) if observation is not None and not error else None
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        wrong = []
        total = 0
        for requirement in orders(parts):
            if requirement == case["ground_truth"]:
                continue
            total += 1
            if parsed and decide({"id": case["id"], "revision": 1, "requirements": requirement, "checks": []},
                                 parsed, case["id"], 0)["decision"] == "ready":
                wrong.append(requirement)
        panels[name] = {"mismatched_orders": total, "false_ready_orders": wrong, "any_false_ready": bool(wrong)}
    return panels


def classify(row):
    if row is None:
        return "N"
    if row["error"]:
        return "E"
    if not row["actionable_counts"]:
        return "U"
    return "C" if row["counts_exact"] else "W"


def latency(values):
    ordered = sorted(values)
    return {"measured": len(ordered), "median_ms": statistics.median(ordered) if ordered else None,
            "p90_ms": ordered[max(0, (9 * len(ordered) + 9) // 10 - 1)] if ordered else None,
            "maximum_ms": max(ordered) if ordered else None,
            "total_ms": sum(ordered)}


def acceptance(base, candidate):
    checks = {
        "all_planned_complete": all(s["outcomes"]["N"] == 0 for s in (base, candidate)),
        "zero_execution_errors": candidate["outcomes"]["E"] == 0,
        "zero_wrong_actionable": candidate["outcomes"]["W"] == 0,
        "zero_any_false_ready": candidate["any_false_ready_images"] == 0,
        "coverage_at_least_90_percent": candidate["correct_actionable_rate"] >= 0.9,
        "coverage_loss_at_most_three_images": candidate["outcomes"]["C"] >= base["outcomes"]["C"] - 3,
        "median_at_most_60_seconds": candidate["latency_all_attempted"]["median_ms"] is not None and candidate["latency_all_attempted"]["median_ms"] <= 60000,
    }
    improved = (candidate["outcomes"]["W"] < base["outcomes"]["W"]
                or candidate["any_false_ready_images"] < base["any_false_ready_images"])
    return {"predeclared_gates": checks, "engineering_acceptance_passed": all(checks.values()),
            "descriptive_safety_advantage_observed": improved and all(checks.values())}


def analyze(manifest, records, *, modes=MODES):
    if tuple(modes) not in (MODES, (*MODES, CANDIDATE_MODE)):
        raise ValueError("Only the predeclared two or three methods are supported")
    cases = {c["id"]: c for c in manifest["cases"]}
    if len(cases) != len(manifest["cases"]):
        raise ValueError("Duplicate manifest case")
    indexed = {}
    for record in records:
        key = (record["case_id"], record["mode"])
        if key in indexed or key[0] not in cases or key[1] not in modes:
            raise ValueError("Duplicate or unplanned prediction")
        case = cases[key[0]]
        if record["sha256"] != case["sha256"] or record["source_id"] != case["source_id"]:
            raise ValueError("Prediction source does not match manifest")
        row = score_case(case, record.get("observation"), record["latency_ms"], record.get("error"))
        row["loaded_before"] = record.get("loaded_before", False)
        row["order_position"] = record.get("order_position")
        row["panel"] = false_ready_panel(case, row["observation"], row["error"])
        indexed[key] = row
    summaries = {}
    for mode in modes:
        groups = {"all": list(cases)}
        for case_id, case in cases.items():
            groups.setdefault(case["subgroup"], []).append(case_id)
        summaries[mode] = {}
        for group, ids in groups.items():
            rows = [indexed.get((case_id, mode)) for case_id in ids]
            measured = [r for r in rows if r is not None]
            outcomes = dict.fromkeys(("C", "W", "U", "E", "N"), 0)
            outcomes.update(Counter(classify(r) for r in rows))
            summaries[mode][group] = {
                "planned": len(ids), "outcomes": outcomes,
                "correct_actionable_rate": outcomes["C"] / len(ids),
                "any_false_ready_images": sum(r["panel"]["all_four"]["any_false_ready"] for r in measured),
                "source_supported_any_false_ready_images": sum(r["panel"]["source_supported"]["any_false_ready"] for r in measured),
                "false_ready_denominator": len(ids), "unmeasured_risk_images": outcomes["N"] + outcomes["E"],
                "latency_all_attempted": latency([r["latency_ms"] for r in measured]),
                "latency_loaded_before": latency([r["latency_ms"] for r in measured if r["loaded_before"]]),
            }
    pair_counts = Counter()
    differences = []
    paired = []
    for case_id in cases:
        first, guarded = [indexed.get((case_id, m)) for m in MODES]
        a, b = classify(first), classify(guarded)
        pair_counts[f"{a}->{b}"] += 1
        if first is not None and guarded is not None:
            differences.append(guarded["latency_ms"] - first["latency_ms"])
        paired.append({"case_id": case_id, "inventory": a, "guarded": b})
    base, guarded = [summaries[m]["all"] for m in MODES]
    comparisons = {mode: acceptance(base, summaries[mode]["all"]) for mode in modes[1:]}
    for mode in modes[1:]:
        transitions = Counter(f"{classify(indexed.get((case_id, MODES[0])))}->{classify(indexed.get((case_id, mode)))}" for case_id in cases)
        comparisons[mode]["paired_outcomes_vs_inventory"] = dict(sorted(transitions.items()))
    candidate_followup = None
    if CANDIDATE_MODE in modes:
        candidate = summaries[CANDIDATE_MODE]["all"]
        baseline_time = guarded["latency_all_attempted"]["median_ms"]
        candidate_time = candidate["latency_all_attempted"]["median_ms"]
        checks = dict(comparisons[CANDIDATE_MODE]["predeclared_gates"])
        checks.update({
            "guarded_comparator_all_attempted": guarded["outcomes"]["N"] == 0,
            "correct_actionable_no_lower_than_guarded": candidate["outcomes"]["C"] >= guarded["outcomes"]["C"],
            "median_at_least_20_percent_lower_than_guarded": (
                baseline_time is not None and baseline_time > 0 and candidate_time is not None
                and candidate_time <= .8 * baseline_time
            ),
        })
        candidate_followup = {
            "checks": checks, "eligible_for_further_validation": all(checks.values()),
            "median_reduction_fraction_vs_guarded": (1 - candidate_time / baseline_time
                if baseline_time and candidate_time is not None else None),
            "paired_outcomes_vs_guarded": dict(sorted(Counter(
                f"{classify(indexed.get((case_id, 'spatial_guarded')))}->{classify(indexed.get((case_id, CANDIDATE_MODE)))}"
                for case_id in cases).items())),
            "automatic_promotion": False,
        }
    nominal_cases = [c for c in cases.values() if "nominal_requirements" in c]
    return {
        "schema": "kitguard.v07.public-paired.analysis.v1", "modes": summaries,
        "classification": {"C": "correct actionable", "W": "wrong actionable", "U": "uncertain/non-actionable", "E": "execution/invalid-output failure", "N": "not attempted"},
        "paired_outcomes": dict(sorted(pair_counts.items())), "paired_cases": paired,
        "paired_latency_guarded_minus_inventory": latency(differences),
        **comparisons["spatial_guarded"], "comparisons_vs_inventory": comparisons,
        "selective_identity_further_validation_gate": candidate_followup,
        "constant_nominal_nonvisual_baseline": {
            "eligible_images": len(nominal_cases),
            "count_exact_images": sum(c["nominal_requirements"] == c["ground_truth"] for c in nominal_cases),
            "physical_quantity_anomaly_images": sum(c["nominal_requirements"] != c["ground_truth"] for c in nominal_cases),
            "note": "Always return the author normal composition without viewing the image; all-normal LOCO alone cannot show visual advantage.",
        },
        "default_change_authorized_by_this_report": False,
        "limitations": ["51 source photos are descriptive same-domain evidence, not statistically independent factory samples.",
                        "No new bracket positives or real LOCO quantity-anomaly images.",
                        "Synthetic order panels do not create additional image samples or actual warehouse orders.",
                        "Missing/failing predictions have unmeasured false-ready risk, not proven safe outcomes.",
                        "Latency includes each isolated upload and model attempt; cold model loading remains in all-attempted times.",
                        "No inference from this static study about physical task efficiency or human accuracy."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists")
    records = [json.loads(line) for line in (args.run / "predictions.jsonl").read_text().splitlines() if line]
    frozen = json.loads((args.run / "freeze.json").read_text())
    result = analyze(json.loads(args.manifest.read_text()), records, modes=tuple(frozen.get("modes", MODES)))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"gates": result["predeclared_gates"], "modes": result["modes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
