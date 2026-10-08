"""Draft, stdlib-only LOCO combined-label scoring; no images or model runner.

Truth 4 is legal observation data, not a request to create an illegal BOM.
Only projected count/action semantics are validated here. A future runner must
also validate the complete production Observation and bind source/input SHA.
"""
from __future__ import annotations

import itertools
import re
from collections import Counter

PARTS = ("bolt", "nut", "washer", "bracket")
NORMAL = dict(zip(PARTS, (2, 2, 2, 0), strict=True))
COMBINED_GROUPS = ((2, 0, 4, 0), (2, 1, 3, 0), (2, 3, 1, 0), (2, 4, 0, 0))


def counts(value, *, unknown=False):
    if not isinstance(value, dict) or set(value) != set(PARTS):
        raise ValueError("Four explicit count categories are required")
    if any(not (unknown and n is None) and (type(n) is not int or not 0 <= n <= 100)
           for n in value.values()):
        raise ValueError("Observation counts must be integers 0..100, or explicit unknown")
    return {p: value[p] for p in PARTS}


def legal_order(value):
    try:
        value = counts(value)
    except ValueError:
        return False
    return any(value.values()) and all(n <= 3 for n in value.values())


def legal_orders(parts=PARTS):
    return [dict.fromkeys(PARTS, 0) | dict(zip(parts, v, strict=True))
            for v in itertools.product(range(4), repeat=len(parts)) if any(v)]


def projection(observation):
    if not isinstance(observation, dict):
        raise TypeError("Missing observation")
    observed = counts(observation.get("observed"), unknown=True)
    issues, action = observation.get("issues"), observation.get("action")
    if not isinstance(issues, list) or len(issues) > 20 or any(not isinstance(i, str) for i in issues):
        raise ValueError("Invalid issues")
    if not isinstance(action, dict) or action.get("kind") not in {"none", "separate", "recapture", "manual"}:
        raise ValueError("Invalid original observation action")
    return {"observed": observed, "issues": list(issues), "action": {"kind": action["kind"]}}


def actionable(observation):
    return (all(v is not None for v in observation["observed"].values())
            and not observation["issues"] and observation["action"]["kind"] == "none")


def decision(observation, requirement):
    """Fresh first inspection, no previous recapture episode or region context."""
    if not legal_order(requirement):
        raise ValueError("BOM must be nonzero with each category 0..3")
    if observation["action"]["kind"] == "manual":
        return "manual"
    if not actionable(observation):
        return "recapture"
    return "ready" if observation["observed"] == requirement else "correct"


def order_panel(truth, observed, parts):
    orders = legal_orders(parts)
    mismatched = [order for order in orders if order != truth]
    wrong = [order for order in mismatched if observed and decision(observed, order) == "ready"]
    measured = observed is not None
    return {"legal_orders": len(orders), "mismatched_orders": len(mismatched), "risk_measured": measured,
            "false_ready_orders": wrong if measured else None,
            "any_false_ready": bool(wrong) if measured else None}


def score_case(case, row=None):
    if not isinstance(case.get("id"), str) or not case["id"]:
        raise ValueError("Planned case ID required")
    if not isinstance(case.get("source_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", case["source_sha256"]):
        raise ValueError("Planned source SHA-256 required")
    truth = counts(case["ground_truth"])
    observed, error, outcome = None, None, "N"
    if row is not None:
        if row.get("case_id") != case["id"] or row.get("source_sha256") != case["source_sha256"]:
            raise ValueError("Prediction is not bound to this planned case/source SHA")
        state = row.get("state")
        if state not in {"completed", "error", "not_attempted"}:
            raise ValueError("Explicit attempt state required")
        if state == "not_attempted" and (row.get("observation") is not None or row.get("error")):
            raise ValueError("Unattempted row cannot contain a result or execution error")
        if state == "error" or row.get("error"):
            error, outcome = str(row.get("error") or "Execution failed"), "E"
        elif state == "completed":
            try:
                observed = projection(row.get("observation"))
            except (TypeError, ValueError) as exc:
                error, outcome = str(exc), "E"
            else:
                outcome = "U" if not actionable(observed) else "C" if observed["observed"] == truth else "W"
    applicable = legal_order(truth)
    measured = observed is not None
    nominal_decision = decision(observed, NORMAL) if measured else None
    return {
        "case_id": case["id"], "outcome": outcome, "scoring_error": error,
        "counts_exact": observed["observed"] == truth if measured else None,
        "actionable_counts": actionable(observed) if measured else None,
        "matched_order": {
            "applicability": "applicable" if applicable else "not_applicable_due_to_order_limit",
            "requirements": dict(truth) if applicable else None,
            "decision": decision(observed, truth) if measured and applicable else None,
        },
        "normal_order": {"requirements": dict(NORMAL), "decision": nominal_decision,
                         "truth_matches": truth == NORMAL,
                         "correct_adjustment": nominal_decision == "correct" and observed["observed"] == truth},
        "all_four_panel": order_panel(truth, observed, PARTS),
        "source_supported_panel": order_panel(truth, observed, PARTS[:3]),
    }


def summarize(cases, rows):
    """Only the full four-by-six new cohort; historical normal stays separate."""
    identifiers = [c["id"] for c in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate planned case")
    if len({c["source_sha256"] for c in cases}) != len(cases):
        raise ValueError("Duplicate planned source")
    groups = Counter(tuple(counts(c["ground_truth"])[p] for p in PARTS) for c in cases)
    if groups != Counter({g: 6 for g in COMBINED_GROUPS}):
        raise ValueError("Draft combined cohort requires all 24 cases, four groups of six")
    row_ids = [r["case_id"] for r in rows]
    if len(set(row_ids)) != len(row_ids) or set(row_ids) - set(identifiers):
        raise ValueError("Duplicate or unplanned prediction")
    by_id = {r["case_id"]: r for r in rows}
    result = [score_case(c, by_id.get(c["id"])) for c in cases]
    totals = Counter(r["outcome"] for r in result)
    strata = []
    for group in COMBINED_GROUPS:
        ids = {c["id"] for c in cases if tuple(c["ground_truth"][p] for p in PARTS) == group}
        group_counts = Counter(r["outcome"] for r in result if r["case_id"] in ids)
        strata.append({"counts": dict(zip(PARTS, group, strict=True)), "planned": 6,
                       "outcomes": {k: group_counts[k] for k in "CWUEN"}})
    def panel_summary(name, size):
        return {
            "correlated_orders_per_image": size, "planned_image_denominator": 24,
            "planned_mismatched_orders": sum(r[name]["mismatched_orders"] for r in result),
            "measured_images": sum(r[name]["risk_measured"] for r in result),
            "unmeasured_images": totals["E"] + totals["N"],
            "observed_any_false_ready_images": sum(r[name]["any_false_ready"] is True for r in result),
            "observed_false_ready_orders": sum(len(r[name]["false_ready_orders"] or []) for r in result),
        }
    return {
        "schema": "kitguard.v08.loco-combined-score.draft.v1", "protocol_frozen": False,
        "planned": 24, "outcomes": {k: totals[k] for k in "CWUEN"}, "groups": strata,
        "matched_order_applicable": 12, "matched_order_not_applicable": 12,
        "matched_order_correct_ready": sum(r["matched_order"]["decision"] == "ready" and r["outcome"] == "C" for r in result),
        "normal_order_correct_adjustment": sum(r["normal_order"]["correct_adjustment"] for r in result),
        "all_four_panel": panel_summary("all_four_panel", 255),
        "source_supported_panel": panel_summary("source_supported_panel", 63), "cases": result,
    }


def comparator_rows(cases, comparator):
    if comparator not in {"constant_normal", "always_abstain"}:
        raise ValueError("Unknown analytical comparator")
    return [{"case_id": c["id"], "source_sha256": c["source_sha256"], "state": "completed",
             "analytical_comparator_not_model": comparator,
             "observation": {"observed": dict(NORMAL) if comparator == "constant_normal" else dict.fromkeys(PARTS),
                             "issues": [] if comparator == "constant_normal" else ["Analytical abstention"],
                             "action": {"kind": "none" if comparator == "constant_normal" else "recapture"}}}
            for c in cases]
