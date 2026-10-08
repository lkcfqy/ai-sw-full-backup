"""Predeclared measurements for public, annotated photographs.

Image observations are independent of desired order quantities. Matched and
mismatched order checks derived from one image are correlated and reported as
separate task counts, never as additional independent photographs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from pydantic import ValidationError

from .app import decide
from .schemas import PARTS, Observation, Requirements


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_case_fields(case: dict) -> None:
    if not isinstance(case, dict):
        raise ValueError("Each benchmark case must be an object")  # noqa: TRY004 -- Manifest validation.
    required_keys = {"id", "image", "sha256", "source_id", "split", "ground_truth"}
    if not required_keys <= case.keys():
        raise ValueError(f"Missing case fields: {required_keys - case.keys()}")
    for key in ("id", "source_id", "image"):
        if not isinstance(case[key], str) or not case[key].strip():
            raise ValueError(f"Case {key} must be a nonempty string")
    image = Path(case["image"])
    if image.is_absolute() or ".." in image.parts:
        raise ValueError("Case image must be a relative path within the dataset")
    if not isinstance(case["sha256"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", case["sha256"]):
        raise ValueError("Case sha256 must be a SHA-256 hexadecimal digest")
    if not isinstance(case["split"], str) or case["split"] not in {"development", "holdout"}:
        raise ValueError("A case must have an explicit development/holdout split")
    truth = case["ground_truth"]
    if (
        not isinstance(truth, dict)
        or set(truth) != set(PARTS)
        or any(type(n) is not int or not 0 <= n <= 100 for n in truth.values())
    ):
        raise ValueError("Ground truth must contain four independent integer counts")
    if "nominal_requirements" in case:
        Requirements.model_validate(case["nominal_requirements"])
    if "subgroup" in case and (not isinstance(case["subgroup"], str) or not case["subgroup"].strip()):
        raise ValueError("Subgroup must be a nonempty source-defined string")


def validate_case(case: dict, dataset_root: Path) -> Path:
    _validate_case_fields(case)
    path = (dataset_root / case["image"]).resolve()
    if not path.is_relative_to(dataset_root.resolve()) or not path.is_file():
        raise ValueError("Image must exist inside the stated dataset root")
    if file_sha256(path) != case["sha256"].lower():
        raise ValueError(f"Image hash changed: {case['id']}")
    return path


def order_tasks(truth: dict) -> list[dict]:
    """Create one matched and one mismatched order only inside product scope."""
    if not 1 <= sum(truth.values()) <= 12 or any(n > 3 for n in truth.values()):
        return []
    changed = dict(truth)
    # Fixed, outcome-independent perturbation; no model output is consulted.
    for part in PARTS:
        if changed[part] < 3 and sum(changed.values()) < 12:
            changed[part] += 1
            break
        if changed[part] > 0 and sum(changed.values()) > 1:
            changed[part] -= 1
            break
    assert changed != truth
    return [
        {"kind": "matched", "requirements": dict(truth)},
        {"kind": "mismatched", "requirements": changed},
    ]


def score_case(case: dict, observation: dict | None, elapsed_ms: int, error: str | None = None) -> dict:
    _validate_case_fields(case)
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("Elapsed milliseconds must be a nonnegative integer")
    truth = case["ground_truth"]
    tasks = order_tasks(truth)
    if "nominal_requirements" in case:
        tasks.append({"kind": "nominal", "requirements": dict(case["nominal_requirements"])})
    parsed = None
    # Model failures must become rows, not escape the runner and truncate its denominator.
    # An explicit error takes precedence over a partial/stale observation.
    if error:
        error = str(error)
    elif observation is None:
        error = "MissingObservation: no model observation was returned"
    else:
        try:
            parsed = Observation.model_validate(observation)
        except (ValidationError, TypeError, ValueError) as exc:
            error = f"InvalidObservation: {exc}"
    result = {
        "case_id": case["id"],
        "source_id": case["source_id"],
        "image": case["image"],
        "sha256": case["sha256"],
        "split": case["split"],
        "ground_truth": truth,
        "subgroup": case.get("subgroup", "unspecified"),
        "latency_ms": elapsed_ms,
        "error": error,
        "observation": observation,
        "counts_exact": False,
        "actionable_counts": False,
        "in_product_scope": bool(tasks),
        "tasks": [],
    }
    if parsed:
        counts = parsed.observed.model_dump()
        result["counts_exact"] = counts == truth
        result["actionable_counts"] = (
            all(count is not None for count in counts.values())
            and not parsed.issues
            and parsed.action.kind == "none"
        )
    for task in tasks:
        snapshot = {"id": case["id"], "revision": 1, "requirements": task["requirements"], "checks": []}
        check = decide(snapshot, parsed, case["id"], elapsed_ms) if parsed else None
        result["tasks"].append(
            {
                **task,
                "truth_matches_order": task["requirements"] == truth,
                "decision": check["decision"] if check else "error",
                "false_ready": bool(check and check["decision"] == "ready" and task["requirements"] != truth),
                "correct_ready": bool(
                    check and check["decision"] == "ready" and task["requirements"] == truth
                ),
                "correct_adjustment": bool(check and check["decision"] == "correct" and counts == truth),
            }
        )
    return result


def rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def wilson_interval(successes: int, count: int) -> list[float] | None:
    """Approximate 95% binomial interval; assumes independent sampled images."""
    if type(successes) is not int or type(count) is not int or not 0 <= successes <= count:
        raise ValueError("Wilson counts require integers with 0 <= successes <= count")
    if count == 0:
        return None
    z = 1.959963984540054
    p = successes / count
    divisor = 1 + z * z / count
    center = (p + z * z / (2 * count)) / divisor
    margin = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / divisor
    return [max(0, center - margin), min(1, center + margin)]


def summarize(rows: list[dict], *, independent_sample: bool = False) -> dict:
    n = len(rows)
    exact = sum(row["counts_exact"] for row in rows)
    actionable = sum(row["actionable_counts"] for row in rows)
    covered_wrong = sum(row["actionable_counts"] and not row["counts_exact"] for row in rows)
    tasks = [task for row in rows for task in row["tasks"]]
    matched = [task for task in tasks if task["kind"] == "matched"]
    mismatched = [task for task in tasks if task["kind"] == "mismatched"]
    nominal = [task for task in tasks if task["kind"] == "nominal"]
    nominal_matches = [task for task in nominal if task["truth_matches_order"]]
    nominal_anomalies = [task for task in nominal if not task["truth_matches_order"]]
    subgroups = {}
    for group in sorted({row.get("subgroup", "unspecified") for row in rows}):
        subset = [row for row in rows if row.get("subgroup", "unspecified") == group]
        group_actionable = sum(row["actionable_counts"] for row in subset)
        subgroups[group] = {
            "images": len(subset),
            "count_exact": rate(sum(row["counts_exact"] for row in subset), len(subset)),
            "actionable_coverage": rate(group_actionable, len(subset)),
            "wrong_actionable_count": rate(
                sum(row["actionable_counts"] and not row["counts_exact"] for row in subset), group_actionable
            ),
            "errors": rate(sum(bool(row["error"]) for row in subset), len(subset)),
        }
    times = sorted(row["latency_ms"] for row in rows)
    median = None if not times else (times[(n - 1) // 2] + times[n // 2]) / 2
    unique_images = len({row["sha256"].lower() for row in rows})
    unique_sources = len({row["source_id"] for row in rows})
    splits = {split: sum(row["split"] == split for row in rows) for split in {r["split"] for r in rows}}
    interval_eligible = (
        independent_sample and n == unique_images == unique_sources and set(splits) == {"holdout"}
    )
    return {
        "images": n,
        "unique_image_hashes": unique_images,
        "unique_source_images": unique_sources,
        "splits": splits,
        "order_eligible_images": sum(bool(row["tasks"]) for row in rows),
        "order_out_of_scope_images": sum(not row["tasks"] for row in rows),
        "count_exact": {
            **rate(exact, n),
            "wilson_95": wilson_interval(exact, n) if interval_eligible else None,
            "interval_note": (
                "Explicit independent holdout sampling assumption; not a deployment guarantee."
                if interval_eligible
                else "Descriptive benchmark only; independent holdout sampling is not established."
            ),
        },
        "actionable_coverage": rate(actionable, n),
        "wrong_actionable_count": rate(covered_wrong, actionable),
        "errors": rate(sum(bool(row["error"]) for row in rows), n),
        "matched_order_ready": rate(sum(t["correct_ready"] for t in matched), len(matched)),
        "mismatched_order_false_ready": rate(sum(t["false_ready"] for t in mismatched), len(mismatched)),
        "mismatched_order_correct_adjustment": rate(
            sum(t["correct_adjustment"] for t in mismatched), len(mismatched)
        ),
        "nominal_order": {
            "matching_images_ready": rate(
                sum(t["correct_ready"] for t in nominal_matches), len(nominal_matches)
            ),
            "quantity_anomalies_false_ready": rate(
                sum(t["false_ready"] for t in nominal_anomalies), len(nominal_anomalies)
            ),
            "quantity_anomalies_correct_adjustment": rate(
                sum(t["correct_adjustment"] for t in nominal_anomalies), len(nominal_anomalies)
            ),
            "constant_nominal_baseline": {
                "label": "Always return the author-defined normal composition; no visual input",
                "count_exact": rate(len(nominal_matches), len(nominal)),
                "quantity_anomalies_false_ready": rate(len(nominal_anomalies), len(nominal_anomalies)),
            },
        },
        "subgroups": subgroups,
        "latency_ms": {"median": median, "maximum": max(times) if times else None},
        "limitations": [
            "Public photographs, broad category mapping; no SKU/size or physical action verification.",
            "Order tasks from the same photograph are correlated, not additional image samples.",
            "Refusals and errors remain in the image denominator; no exclusion after model output.",
            "Intervals require an explicit independent holdout sampling assumption and unique sources.",
            "Development and first-N benchmark results are descriptive, not population performance estimates.",
            "Mismatched-order rates cover one fixed perturbation per eligible image, not every possible mismatch.",
            "Unknown overlap with the pretrained model's training data limits generalization claims.",
        ],
    }


def read_manifest(path: Path) -> dict:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate manifest JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite manifest JSON value: {value}")

    manifest = json.loads(path.read_text(), object_pairs_hook=unique_keys, parse_constant=invalid_constant)
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or not isinstance(manifest.get("cases"), list)
    ):
        raise ValueError("Unsupported benchmark manifest")
    for case in manifest["cases"]:
        _validate_case_fields(case)
    ids = [case["id"] for case in manifest["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate benchmark case IDs")
    splits: dict[tuple[str, str], set[str]] = {}
    image_hashes: set[str] = set()
    image_paths: set[str] = set()
    for case in manifest["cases"]:
        for identity in (
            ("source", case["source_id"]),
            ("hash", case["sha256"].lower()),
            ("path", str(Path(case["image"]))),
        ):
            splits.setdefault(identity, set()).add(case["split"])
    if any(len(values) > 1 for values in splits.values()):
        raise ValueError("Source image/hash/path leaks across development and holdout")
    for case in manifest["cases"]:
        digest, image = case["sha256"].lower(), str(Path(case["image"]))
        if digest in image_hashes or image in image_paths:
            raise ValueError("Duplicate benchmark image hash/path would inflate the image denominator")
        image_hashes.add(digest)
        image_paths.add(image)
    return manifest
