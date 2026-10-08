"""Independent completed-only audit of the frozen 51-photo/153-attempt trial.

Never invokes a model. Replays frozen image preparation and observation parsing
against retained raw calls; computes outcome/rule-risk/gates without calling
the trial analyzer or score_case. Inputs and run files are read-only. Temporary
CPU replay files and the new audit output stay outside the run directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import io
import itertools
import json
import math
import shutil
import statistics
import subprocess
import sys
import tempfile
import types
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/v0.7/public_paired_freeze_v1/freeze.json"
FREEZE_SHA = "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7"
PARTS = ("bolt", "nut", "washer", "bracket")
MODES = ("spatial_inventory", "spatial_guarded", "selective_identity_experimental_v1")
IDENTITY_KEYS = ("label", "repo_id", "revision", "observer_protocol_sha256", "observer_source_hashes",
                 "observation_mode", "image_max_side", "path")


class AuditError(ValueError):
    """Missing or inconsistent evidence; never converted into a model failure."""


def need(condition, message):
    if not condition:
        raise AuditError(message)


def diagnostic_differences(saved, replayed, path="$", limit=20):
    """Explain exact mismatches without discarding any diagnostic fields."""
    if saved == replayed:
        return []
    if isinstance(saved, dict) and isinstance(replayed, dict):
        differences = []
        for key in sorted(saved.keys() | replayed.keys()):
            if key not in saved or key not in replayed:
                differences.append({"path": f"{path}.{key}", "saved": saved.get(key),
                                    "replayed": replayed.get(key), "missing": "saved" if key not in saved else "replayed"})
            else:
                differences.extend(diagnostic_differences(saved[key], replayed[key], f"{path}.{key}", limit))
            if len(differences) >= limit:
                return differences[:limit]
        return differences
    if isinstance(saved, (list, tuple)) and isinstance(replayed, (list, tuple)) and len(saved) == len(replayed):
        differences = []
        for i, (a, b) in enumerate(zip(saved, replayed, strict=True)):
            differences.extend(diagnostic_differences(a, b, f"{path}[{i}]", limit))
        if differences:
            return differences[:limit]
    return [{"path": path, "saved": saved, "replayed": replayed,
             "saved_type": type(saved).__name__, "replayed_type": type(replayed).__name__}]


def comparable_diagnostics(diagnostics, row, *, recorded):
    """Check the sole nested wall timer separately; compare all other fields exactly.

    The frozen candidate copies LocalVision's first pass into single_direction_base,
    including its perf_counter latency. CPU raw replay cannot reproduce wall time.
    This is a path-specific exception, not recursive removal of timing fields.
    """
    result = copy.deepcopy(diagnostics)
    if row["mode"] == MODES[2] and "single_direction_base" in result:
        base = result["single_direction_base"]
        need(isinstance(base, dict), "Candidate base diagnostics are not an object")
        elapsed = base.get("latency_ms")
        need(type(elapsed) is int and elapsed >= 0, "Candidate base timer must be a nonnegative integer")
        if recorded:
            total = row.get("latency_ms")
            need(type(total) is int and total >= 0, "Full attempt timer is missing")
            need(elapsed <= total + 1, "Candidate base timer exceeds its enclosing attempt")
            calls = result.get("generation_calls", [])
            need(bool(calls) and calls[0].get("runtime") is not None, "Completed candidate base lost its generation timer")
            # Both recorded timers are rounded to milliseconds; allow only that rounding.
            need(calls[0]["runtime"]["seconds"] * 1000 <= elapsed + 2,
                 "Candidate base timer is shorter than its contained generation")
        del base["latency_ms"]
    return result


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def bytes_sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def inside(root, relative):
    need(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Artifact path must be relative")
    value = (root / relative).resolve()
    need(value.is_relative_to(root.resolve()), "Artifact path escapes its evidence directory")
    need(not (root / relative).is_symlink(), "Evidence symlinks are not accepted")
    return value


def completed_metadata(run):
    metadata = read(run / "run.json")
    # Keep before any prediction-file read; incomplete results cannot be audited.
    need(metadata.get("status") == "completed", "Run is not completed; predictions intentionally unread")
    need(metadata.get("planned_attempts") == metadata.get("completed_attempts") == 153,
         "All 153 planned attempts must remain in the completed run")
    need(metadata.get("source_changed") is False, "Frozen inference source changed or status is unverified")
    need(metadata.get("isolated_python") is True, "Run did not record isolated frozen Python")
    start = datetime.fromisoformat(metadata["started_at"])
    end = datetime.fromisoformat(metadata["finished_at"])
    need(end >= start, "Run timestamps are inconsistent")
    return metadata


def planned_schedule(cases):
    rotations = [MODES[i:] + MODES[:i] for i in range(3)]
    sequences = rotations + [tuple(reversed(s)) for s in rotations]
    return [{"case_id": c["id"], "mode": mode, "order_position": pos}
            for i, c in enumerate(cases) for pos, mode in enumerate(sequences[i % 6], 1)]


def validate_ledger(freeze, manifest, records):
    cases = manifest["cases"]
    need(freeze.get("cases") == len(cases) == 51 and freeze.get("attempts") == 153,
         "Frozen full denominator must be 51 photos and 153 attempts")
    need(tuple(freeze.get("modes", [])) == MODES, "Expected the preregistered three arms")
    need(len({c["id"] for c in cases}) == len({c["source_id"] for c in cases}) == 51,
         "Duplicate photo or original-source identity")
    need(len({c["source_sha256"] for c in cases}) == len({c["source_decoded_rgb_sha256"] for c in cases}) == 51,
         "Duplicate original bytes or decoded pixels")
    plan = planned_schedule(cases)
    need(freeze["schedule"] == plan, "Freeze execution order differs from balanced preregistration")
    need(len(records) == 153, "Prediction ledger does not preserve all 153 attempts")
    observed = [{k: r.get(k) for k in ("case_id", "mode", "order_position")} for r in records]
    need(observed == plan, "Missing, reordered, duplicate or unplanned attempt")
    positions = Counter((r["mode"], r["order_position"]) for r in records)
    need(set(positions.values()) == {17} and len(positions) == 9, "Three arm order positions are not balanced")
    return {c["id"]: c for c in cases}


def rule_decision(observation, requirement, error=None):
    """Independent rule decision for the frozen empty-history order panel."""
    if error or observation is None:
        return "error"
    action = observation["action"]["kind"]
    if action == "manual":
        return "manual"
    if (any(v is None for v in observation["observed"].values())
            or observation["issues"] or action != "none"):
        return "recapture"
    return "ready" if observation["observed"] == requirement else "correct"


def derive_outcome(row, truth):
    observation, error = row.get("observation"), row.get("error")
    if error:
        category, exact, actionable = "E", False, False
    else:
        need(isinstance(observation, dict), "Successful row has no observation")
        exact = observation["observed"] == truth
        actionable = (all(observation["observed"][p] is not None for p in PARTS)
                      and not observation["issues"] and observation["action"]["kind"] == "none")
        category = "C" if exact and actionable else "W" if actionable else "U"
    need(row.get("counts_exact") is exact and row.get("actionable_counts") is actionable,
         "Saved scoring flags differ from independent recomputation")
    return category


def order_panel(parts):
    for vector in itertools.product(range(4), repeat=len(parts)):
        if any(vector):
            yield dict.fromkeys(PARTS, 0) | dict(zip(parts, vector, strict=True))


def independent_panels(case, row):
    results = {}
    for name, parts in (("all_four", PARTS), ("source_supported", case["supported_positive_classes"])):
        orders = [r for r in order_panel(parts) if r != case["ground_truth"]]
        false = [r for r in orders if rule_decision(row.get("observation"), r, row.get("error")) == "ready"]
        results[name] = {"mismatched_orders": len(orders), "false_ready_orders": false,
                         "any_false_ready": bool(false), "risk_measured": not bool(row.get("error"))}
    return results


def verify_task_receipts(case, row):
    truth = case["ground_truth"]
    need(all(type(v) is int and 0 <= v <= 3 for v in truth.values()) and 1 <= sum(truth.values()) <= 12,
         "Selected photo is outside the preregistered product count scope")
    changed = dict(truth)
    for p in PARTS:
        if changed[p] < 3 and sum(changed.values()) < 12:
            changed[p] += 1
            break
        if changed[p] > 0 and sum(changed.values()) > 1:
            changed[p] -= 1
            break
    tasks = [("matched", truth), ("mismatched", changed)]
    if "nominal_requirements" in case:
        tasks.append(("nominal", case["nominal_requirements"]))
    expected = []
    for kind, requirement in tasks:
        decision = rule_decision(row.get("observation"), requirement, row.get("error"))
        exact = not row.get("error") and row["observation"]["observed"] == truth
        expected.append({"kind": kind, "requirements": requirement, "truth_matches_order": requirement == truth,
                         "decision": decision, "false_ready": decision == "ready" and requirement != truth,
                         "correct_ready": decision == "ready" and requirement == truth,
                         "correct_adjustment": decision == "correct" and exact})
    need(row.get("in_product_scope") is True and row.get("tasks") == expected,
         "Saved per-order task decisions differ from independent rules")


def timing(values):
    values = sorted(values)
    need(all(type(x) is int and x >= 0 for x in values), "Invalid elapsed milliseconds")
    return {"measured": len(values), "median_ms": statistics.median(values) if values else None,
            "p90_ms": values[math.ceil(.9 * len(values)) - 1] if values else None,
            "maximum_ms": max(values) if values else None, "total_ms": sum(values)}


def gates(base, candidate, policy):
    c, b = candidate["outcomes"], base["outcomes"]
    checks = {
        "all_planned_complete": b["N"] == c["N"] == 0,
        "zero_execution_errors": c["E"] == policy["guarded_execution_failures"],
        "zero_wrong_actionable": c["W"] == policy["guarded_wrong_actionable"],
        "zero_any_false_ready": candidate["any_false_ready_images"] == policy["guarded_any_false_ready"],
        "coverage_at_least_90_percent": c["C"] / candidate["planned"] >= policy["guarded_correct_actionable_min_rate"],
        "coverage_loss_at_most_three_images": c["C"] >= b["C"] - policy["guarded_coverage_loss_max_images"],
        "median_at_most_60_seconds": candidate["latency_all_attempted"]["median_ms"] is not None
        and candidate["latency_all_attempted"]["median_ms"] <= policy["guarded_median_max_ms"],
    }
    advantage = (c["W"] < b["W"] or candidate["any_false_ready_images"] < base["any_false_ready_images"])
    return {"predeclared_gates": checks, "engineering_acceptance_passed": all(checks.values()),
            "descriptive_safety_advantage_observed": advantage and all(checks.values())}


def summarize_independently(cases, rows, freeze):
    indexed = {(r["case_id"], r["mode"]): r for r in rows}
    summaries = {}
    for mode in MODES:
        groups = {"all": list(cases.values())}
        for case in cases.values():
            groups.setdefault(case["subgroup"], []).append(case)
        summaries[mode] = {}
        for name, group in groups.items():
            selected = [indexed.get((c["id"], mode)) for c in group]
            labels = [derive_outcome(r, c["ground_truth"]) if r else "N" for c, r in zip(group, selected, strict=True)]
            outcomes = dict.fromkeys("CWUEN", 0) | dict(Counter(labels))
            attempted = [r for r in selected if r]
            panels = [independent_panels(c, r) for c, r in zip(group, selected, strict=True) if r]
            summaries[mode][name] = {
                "planned": len(group), "outcomes": outcomes, "correct_actionable_rate": outcomes["C"] / len(group),
                "any_false_ready_images": sum(p["all_four"]["any_false_ready"] for p in panels),
                "source_supported_any_false_ready_images": sum(p["source_supported"]["any_false_ready"] for p in panels),
                "false_ready_denominator": len(group), "unmeasured_risk_images": outcomes["E"] + outcomes["N"],
                "latency_all_attempted": timing([r["latency_ms"] for r in attempted]),
                "latency_loaded_before": timing([r["latency_ms"] for r in attempted if r["loaded_before"]]),
            }
    base = summaries[MODES[0]]["all"]
    comparisons = {mode: gates(base, summaries[mode]["all"], freeze["predeclared_acceptance"]) for mode in MODES[1:]}
    paired = {}
    for before, after in itertools.combinations(MODES, 2):
        transitions = Counter()
        for cid, c in cases.items():
            a, b = indexed.get((cid, before)), indexed.get((cid, after))
            transitions[f"{derive_outcome(a, c['ground_truth']) if a else 'N'}->{derive_outcome(b, c['ground_truth']) if b else 'N'}"] += 1
        paired[f"{before} vs {after}"] = dict(sorted(transitions.items()))
    guarded, candidate = [summaries[m]["all"] for m in MODES[1:]]
    candidate_policy = freeze["selective_identity_further_validation_gate"]
    checks = dict(comparisons[MODES[2]]["predeclared_gates"])
    checks.update({"guarded_comparator_all_attempted": guarded["outcomes"]["N"] == 0,
                   "correct_actionable_no_lower_than_guarded": candidate["outcomes"]["C"] >= guarded["outcomes"]["C"],
                   "median_at_least_20_percent_lower_than_guarded": guarded["latency_all_attempted"]["median_ms"] > 0
                   and candidate["latency_all_attempted"]["median_ms"] <= candidate_policy["median_at_most_guarded_fraction"] * guarded["latency_all_attempted"]["median_ms"]})
    return {"modes": summaries, "comparisons_vs_inventory": comparisons, "paired_outcomes": paired,
            "selective_identity_further_validation_gate": {"checks": checks, "eligible_for_further_validation": all(checks.values()), "automatic_promotion": False}}


def verify_call_files(case_dir, diagnostics, error):
    calls = (diagnostics or {}).get("generation_calls", [])
    paths = sorted(case_dir.glob("call-*/generation.json"))
    need(len(paths) == len(calls), "Generation directory count differs from diagnostics")
    counts = Counter()
    for index, (path, saved) in enumerate(zip(paths, calls, strict=True), 1):
        need(path.parent.name == f"call-{index:02d}", "Raw generation call sequence is not contiguous")
        record = read(path)
        need(record == saved, "Persisted raw generation differs from prediction diagnostics")
        need(record.get("status") in {"parsed", "failed"}, "Completed run retained a pending/returned-only generation")
        need(record.get("schema") in {"SpatialInventory", "IdentityResponse"}, "Unregistered generation schema")
        expected_tokens = 900 if record["schema"] == "SpatialInventory" else 1800
        need(record["max_tokens"] == expected_tokens and record["temperature"] == 0,
             "Generation budget or temperature differs from freeze")
        need(isinstance(record["system"], str) and isinstance(record["prompt"], str), "Missing exact prompt")
        need(isinstance(record["images"], list) and record["images"], "Actual model images are missing")
        need(record["raw_text"] is None or isinstance(record["raw_text"], str), "Invalid raw output type")
        if record["status"] == "parsed":
            need(isinstance(record["raw_text"], str) and isinstance(record.get("parsed"), dict), "Parsed call has no raw output")
        else:
            need(bool(error) and isinstance(record.get("error"), str) and record["error"], "Failure lacks a preserved exception")
        runtime = record.get("runtime")
        if runtime is not None:
            need(isinstance(record["raw_text"], str), "Runtime exists without raw text returned from generate")
            need(type(runtime["seconds"]) in (float, int) and math.isfinite(runtime["seconds"]) and runtime["seconds"] >= 0,
                 "Generation duration is invalid")
            need(all(type(runtime[k]) is int and runtime[k] >= 0 for k in ("prompt_tokens", "generation_tokens")), "Token counters invalid")
            need(runtime["generation_tokens"] <= expected_tokens, "Recorded generation exceeded its frozen token budget")
        expected_images = set()
        for i, image in enumerate(record["images"], 1):
            target = inside(case_dir, image["path"])
            need(target.parent == path.parent and target.stem == f"image-{i:02d}", "Image order/path is inconsistent")
            need(target.is_file() and sha(target) == image["sha256"], "Actual input image bytes changed")
            expected_images.add(target)
        actual_images = {p.resolve() for p in path.parent.iterdir() if p.name != "generation.json"}
        need(actual_images == expected_images, "Call directory has missing or unrecorded input files")
        counts["calls"] += 1
        counts[record["status"]] += 1
        counts["raw_text_returns"] += isinstance(record["raw_text"], str)
        counts["input_images"] += len(record["images"])
    return calls, counts


def replay_observation(engine, normalized, case_dir, row, frozen):
    """Inject saved raw text at generate; prohibit all actual model loading."""
    calls, counts = verify_call_files(case_dir, row.get("observation_diagnostics"), row.get("error"))
    need(len(calls) <= (3 if row["mode"] == MODES[1] else 2 if row["mode"] == MODES[2] else 1), "Arm exceeded call budget")
    cursor = 0
    failures_without_return = []

    def no_model(_self):
        raise AuditError("Model loading is forbidden during evidence replay")

    def generate(_self, system, prompt, images, schema, *, max_tokens=450):
        nonlocal cursor
        need(cursor < len(calls), "Replay requires a raw call missing from the receipt")
        record = calls[cursor]
        cursor += 1
        need((system, prompt, schema.__name__, max_tokens) == (record["system"], record["prompt"], record["schema"], record["max_tokens"]),
             "Prompt, target selection, schema or budget differs on frozen CPU replay")
        need(len(images) == len(record["images"]), "Replayed target/image count differs")
        for source, saved in zip(images, record["images"], strict=True):
            need(sha(source) == saved["sha256"], "Actual model input differs from independently re-prepared pixels")
            target = inside(_self.artifact_dir, saved["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _self._observation_attempt.setdefault("generation_calls", []).append(copy.deepcopy(record))
        _self._last_inference = copy.deepcopy(record["runtime"])
        if record["status"] == "parsed":
            parsed = frozen.vision._parse_json(record["raw_text"].strip(), schema)
            need(parsed.model_dump() == record["parsed"], "Reparsed raw text differs from saved parsed output")
            return parsed
        if record["raw_text"] is not None:
            try:
                frozen.vision._parse_json(record["raw_text"].strip(), schema)
            except frozen.vision.ModelOutputError:
                need(record["error"].startswith("ModelOutputError:"), "Raw parse failure exception was changed")
                raise
            raise AuditError("Failed generation has parseable output; its failure is not reproducible from the saved boundary")
        failures_without_return.append({"call": cursor, "error": record["error"], "status": "retained_runtime_failure_no_raw_return"})
        raise frozen.vision.ModelUnavailableError("Recorded runtime failure: " + record["error"])

    engine._load = types.MethodType(no_model, engine)
    engine._generate = types.MethodType(generate, engine)
    with tempfile.TemporaryDirectory(prefix="kitguard-evidence-replay-") as temp:
        engine.artifact_dir = Path(temp)
        observed, replay_error = None, None
        try:
            observed = engine._observe(normalized, {})
        except AuditError:
            raise
        except Exception as exc:  # noqa: BLE001 -- independently preserve model/parse/contract failures.
            replay_error = exc
        need(cursor == len(calls), "Recorded generation was not consumed by the frozen observation path")
        recorded_diag = comparable_diagnostics(row["observation_diagnostics"], row, recorded=True)
        replayed_diag = comparable_diagnostics(engine._observation_attempt, row, recorded=False)
        if not row.get("error"):
            need(replay_error is None, f"Successful observation failed frozen CPU replay: {replay_error}")
            actual = frozen.schemas.Observation.model_validate(row["observation"]).model_dump(exclude_none=False)
            expected = frozen.schemas.Observation.model_validate(observed).model_dump(exclude_none=False)
            actual.pop("latency_ms", None)
            expected.pop("latency_ms", None)
            need(actual == expected, "Saved final observation differs from retained raw-call replay")
            need(replayed_diag == recorded_diag,
                 "Observation diagnostics differ on frozen replay: " + json.dumps(diagnostic_differences(
                     recorded_diag, replayed_diag), ensure_ascii=False))
            need(engine._last_inference == row["runtime"], "Aggregate inference runtime receipt differs from its component calls")
        elif str(row.get("error", "")).startswith("InvalidObservation:"):
            need(replay_error is None and isinstance(row.get("observation"), dict), "Invalid-output failure lost its returned observation")
            actual, expected = copy.deepcopy(row["observation"]), copy.deepcopy(observed)
            actual.pop("latency_ms", None)
            expected.pop("latency_ms", None)
            need(actual == expected, "Invalid observation differs from raw replay")
            try:
                frozen.schemas.Observation.model_validate(row["observation"])
            except (TypeError, ValueError):
                pass
            else:
                raise AuditError("InvalidObservation receipt now validates without error")
            need(replayed_diag == recorded_diag, "Invalid-output diagnostics differ on replay")
            need(engine._last_inference == row["runtime"], "Invalid-output aggregate runtime changed")
        else:
            need(replay_error is not None, "Failure row replays as successful; failure evidence is incomplete")
            need(row.get("observation") is None and row.get("runtime") is None, "Failure retained a stale success result")
            if not failures_without_return:
                need(row["error"] == f"{type(replay_error).__name__}: {replay_error}", "Recorded exception differs from reproducible raw failure")
            original = row["observation_diagnostics"]
            need(original.get("status") == "failed", "Failed attempt diagnostics are not marked failed")
            need(type(replay_error).__name__ == original.get("error_type"), "Replayed failure type differs from recorded diagnostics")
            # Only a substituted runtime exception's wording may differ. Retain
            # and compare targets, response, crop geometry/hashes and all calls.
            original_diag, replay_diag = recorded_diag, replayed_diag
            if failures_without_return:
                for diag in (original_diag, replay_diag):
                    diag.get("experimental_identity", {}).pop("error", None)
            need(original_diag == replay_diag, "Failure identity/observation diagnostics differ on frozen replay")
        identity = engine._observation_attempt.get("experimental_identity") or engine._observation_attempt.get("identity") or {}
        rebuilt_crops = identity.get("crops", [])
        for crop in rebuilt_crops:
            # Candidate retains pixel originals and resized crops; guarded stores
            # temporary crop metadata, while actual resized inputs remain in call-03.
            if row["mode"] == MODES[2]:
                for key, hashkey in (("crop_file", "crop_sha256"), ("pixel_crop_file", "pixel_crop_sha256")):
                    need(sha(inside(case_dir, crop[key])) == crop[hashkey], "Retained candidate identity crop changed")
        counts["reconstructed_identity_crops"] += len(rebuilt_crops)
    return counts, failures_without_return


def load_frozen_modules(snapshot):
    need(not any(name == "kitguard" or name.startswith("kitguard.") for name in sys.modules),
         "Frozen audit must start before any workspace kitguard import")
    sys.path.insert(0, str(snapshot))
    module = types.SimpleNamespace(
        vision=importlib.import_module("kitguard.vision"), schemas=importlib.import_module("kitguard.schemas"),
        probe=importlib.import_module("scripts.probe_selective_identity"),
        upload=importlib.import_module("scripts.run_benchmark"),
    )
    for module_name, imported in list(sys.modules.items()):
        if module_name == "kitguard" or module_name.startswith("kitguard.") or module_name in {"scripts.probe_selective_identity", "scripts.run_benchmark"}:
            need(Path(imported.__file__).resolve().is_relative_to(snapshot), "CPU replay imported an unfrozen project module")
    need(not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules), "Audit must not import MLX")
    return module


def verify_sources(project_root, freeze_path, run, metadata):
    need(sha(freeze_path) == FREEZE_SHA, "Freeze differs from the preregistered 51-photo three-arm protocol")
    freeze = read(freeze_path)
    need(datetime.fromisoformat(freeze["created_at"]) <= datetime.fromisoformat(metadata["started_at"]),
         "Run started before the recorded protocol freeze")
    need(sha(run / "freeze.json") == metadata["freeze_sha256"] == FREEZE_SHA, "Run freeze copy/hash mismatch")
    snapshot = freeze_path.parent / "source_snapshot"
    need(Path(metadata["runtime_source_root"]).resolve() == snapshot.resolve(), "Run used a different source root")
    need(Path(metadata["data_project_root"]).resolve() == project_root.resolve(), "Run used a different data root")
    for name, expected in freeze["source_hashes"].items():
        need(sha(inside(snapshot, name)) == expected, f"Frozen source snapshot changed: {name}")
    actual_sources = {str(p.relative_to(snapshot)) for p in snapshot.rglob("*.py")}
    expected_sources = {name for name in freeze["source_hashes"] if name.endswith(".py")}
    need(actual_sources == expected_sources, "Frozen snapshot has an unlisted or missing Python source")
    manifest_path = inside(project_root, freeze["manifest"])
    need(sha(manifest_path) == sha(run / "manifest.json") == freeze["manifest_sha256"], "Manifest/input selection changed")
    selection_path = manifest_path.parent / "selection_audit.json"
    need(sha(selection_path) == freeze["selection_audit_sha256"], "Selection audit changed after freeze")
    selection = read(selection_path)
    manifest = read(manifest_path)
    need(not {c["source_sha256"] for c in manifest["cases"]} & selection["exposure"].keys(), "Selected source was already exposed")
    for name, expected in selection["inputs"].items():
        if name.startswith("datasets/manifests/") or name == "datasets/raw/mvtec_screws_v1.0/mvtec_screws.json":
            need(sha(inside(project_root, name)) == expected, f"Truth/selection input changed: {name}")
    return freeze, manifest, snapshot, selection


def verify_photo(case, datasets, image_module):
    image_path = inside(datasets, case["image"])
    source_path = inside(datasets, case.get("source_image", case["image"]))
    need(sha(image_path) == case["sha256"] and sha(source_path) == case["source_sha256"], "Selected image/source hash mismatch")
    with image_module.open(source_path) as opened:
        image = opened.convert("RGB")
        need(bytes_sha(str(image.size).encode() + b"|RGB|" + image.tobytes()) == case["source_decoded_rgb_sha256"],
             "Original decoded pixels differ from selection audit")
        if case["derived_view"]:
            buffer = io.BytesIO()
            image.crop(case["crop_xyxy"]).save(buffer, format="PNG")
            need(bytes_sha(buffer.getvalue()) == case["sha256"], "Derived view no longer equals deterministic source crop")
    return image_path


def cross_check_report(independent, reported):
    """Compare only after independent derivation; never use summary as truth."""
    need(reported["modes"] == independent["modes"], "Runner aggregate differs from independent full-denominator results")
    for mode, comparison in independent["comparisons_vs_inventory"].items():
        for key, expected in comparison.items():
            need(reported["comparisons_vs_inventory"][mode][key] == expected, f"Runner predeclared gate differs: {mode}/{key}")
    for key in ("checks", "eligible_for_further_validation", "automatic_promotion"):
        need(reported["selective_identity_further_validation_gate"][key]
             == independent["selective_identity_further_validation_gate"][key], f"Candidate follow-up gate differs: {key}")


def audit(run, project_root=ROOT, freeze_path=FREEZE):
    run, project_root, freeze_path = run.resolve(), project_root.resolve(), freeze_path.resolve()
    metadata = completed_metadata(run)
    freeze, manifest, snapshot, _selection = verify_sources(project_root, freeze_path, run, metadata)
    ledger_bytes = (run / "predictions.jsonl").read_bytes()
    need(ledger_bytes.endswith(b"\n"), "Last prediction line is not terminated")
    records = [json.loads(line) for line in ledger_bytes.decode().splitlines()]
    cases = validate_ledger(freeze, manifest, records)
    artifacts_before = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    frozen = load_frozen_modules(snapshot)
    from PIL import Image

    engines = {mode: (frozen.probe.SelectiveIdentityVision(Path(freeze["model_identity"][mode]["path"]))
                      if mode == MODES[2] else frozen.vision.LocalVision(Path(freeze["model_identity"][mode]["path"]),
                                                                     observation_mode=mode, image_max_side=1536)) for mode in MODES}
    model_identities = {}
    for mode, engine in engines.items():
        status = engine.status()
        need(all(status[k] == freeze["model_identity"][mode][k] for k in IDENTITY_KEYS), "Frozen observer/model identity cannot be reproduced")
        model_identities[mode] = {k: status[k] for k in IDENTITY_KEYS}
    normalized_expected = {}
    for cid, case in cases.items():
        image_path = verify_photo(case, project_root / "datasets", Image)
        normalized_expected[cid] = bytes_sha(frozen.upload.app_upload_bytes(image_path))
    audits, totals, opaque_failures = [], Counter(), []
    per_mode_raw = {mode: Counter() for mode in MODES}
    used_paths = set()
    for index, row in enumerate(records, 1):
        case = cases[row["case_id"]]
        for key in ("source_id", "image", "sha256", "split", "ground_truth", "subgroup"):
            need(row.get(key) == case.get(key), f"Attempt source/truth metadata differs: {index}/{key}")
        need(type(row.get("loaded_before")) is bool, "Cold/warm indicator missing")
        timing([row["latency_ms"]])
        case_dir = run / "cases" / f"{index:03d}-{row['mode']}"
        normalized = run / "normalized_inputs" / f"{index:03d}-{row['mode']}.jpg"
        used_paths.add(case_dir)
        if row["normalized_sha256"] is None:
            need(bool(row.get("error")) and row.get("observation") is None and row.get("observation_diagnostics") is None,
                 "Missing normalized input without an explicit preprocessing failure")
            need(not list(case_dir.rglob("generation.json")), "Preprocessing failure has unlinked generation records")
            raw_counts = Counter()
            opaque_failures.append({"attempt": index, "status": "pre_observation_failure", "error": row["error"]})
        else:
            need(sha(normalized) == row["normalized_sha256"] == normalized_expected[row["case_id"]],
                 "Normalized actual input differs from fresh frozen app-upload bytes")
            diagnostics = row.get("observation_diagnostics")
            need(isinstance(diagnostics, dict) and diagnostics.get("source_sha256") == row["normalized_sha256"], "Diagnostics lost normalized-source binding")
            need(diagnostics.get("mode") == row["mode"] and diagnostics.get("model") == freeze["model_identity"][row["mode"]]["label"],
                 "Attempt observer/model label differs from freeze")
            try:
                raw_counts, failures = replay_observation(engines[row["mode"]], normalized, case_dir, row, frozen)
            except AuditError as exc:
                raise AuditError(f"Attempt {index} / {row['case_id']} / {row['mode']}: {exc}") from exc
            opaque_failures += [{"attempt": index, **f} for f in failures]
            totals["normalized_inputs_verified"] += 1
            calls = diagnostics.get("generation_calls", [])
            runtime_ms = sum(c["runtime"]["seconds"] * 1000 for c in calls if c.get("runtime"))
            need(runtime_ms <= row["latency_ms"] + 50, "Generation durations exceed the enclosing observation timer")
        totals.update(raw_counts)
        per_mode_raw[row["mode"]].update(raw_counts)
        label = derive_outcome(row, case["ground_truth"])
        verify_task_receipts(case, row)
        audits.append({"attempt": index, "case_id": row["case_id"], "mode": row["mode"], "outcome": label,
                       "raw_calls": raw_counts["calls"], "raw_input_images": raw_counts["input_images"],
                       "recorded_candidate_base_latency_ms": (row.get("observation_diagnostics") or {}).get("single_direction_base", {}).get("latency_ms"),
                       "latency_ms": row["latency_ms"], "panels": independent_panels(case, row)})
    actual_case_dirs = {p for p in (run / "cases").iterdir() if p.is_dir()}
    need(actual_case_dirs <= used_paths, "Run contains unplanned/retried case directories")
    expected_normalized = {run / "normalized_inputs" / f"{i:03d}-{r['mode']}.jpg"
                           for i, r in enumerate(records, 1)}
    need(set((run / "normalized_inputs").iterdir()) <= expected_normalized,
         "Normalized directory includes unplanned/retried inputs")
    wall_ms = (datetime.fromisoformat(metadata["finished_at"]) - datetime.fromisoformat(metadata["started_at"])).total_seconds() * 1000
    need(sum(r["latency_ms"] for r in records) <= wall_ms + 153, "Summed sequential observation times exceed run wall time")
    independent = summarize_independently(cases, records, freeze)
    cross_check_report(independent, read(run / "analysis.json"))
    need(completed_metadata(run) == metadata and bytes_sha((run / "predictions.jsonl").read_bytes()) == bytes_sha(ledger_bytes),
         "Run metadata or prediction ledger changed during audit")
    need(not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules), "CPU audit unexpectedly imported MLX")
    artifacts = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    need(artifacts == artifacts_before, "Run artifacts changed during independent audit")
    for name, expected in freeze["source_hashes"].items():
        need(sha(inside(snapshot, name)) == expected, f"Frozen source changed during audit: {name}")
    return {"schema": "kitguard.v07.public-paired.independent-audit.v1", "checked_at": datetime.now(UTC).isoformat(),
            "status": "passed", "planned_photos": 51, "planned_attempts": 153, "completed_attempts": len(records),
            "source_snapshot_files_verified": len(freeze["source_hashes"]), "source_changed": False,
            "workspace_changed_during_run": metadata.get("workspace_changed_during_run"),
            "selected_originals_verified": 51, "normalization_reexecuted_distinct_sources": 51,
            "raw_evidence_checks": dict(totals), "raw_evidence_by_mode": {m: dict(v) for m, v in per_mode_raw.items()},
            "retained_failures_without_reproducible_model_return": opaque_failures,
            "model_identity": model_identities, "independent_results": independent, "attempt_audits": audits,
            "run_wall_time_ms": wall_ms, "sequential_attempt_time_ms": sum(r["latency_ms"] for r in records),
            "default_change_authorized": False, "model_loaded_or_called": False,
            "evidence_sha256": {"freeze": FREEZE_SHA, "manifest": freeze["manifest_sha256"],
                                "predictions": bytes_sha(ledger_bytes), "auditor": sha(Path(__file__))},
            "artifacts_sha256": artifacts,
            "limitations": ["Raw-call records and file hashes are auditable local evidence, not tamper-proof signatures or proof of inference authenticity.",
                            "Wall-clock observation latency, including candidate single_direction_base.latency_ms, cannot be reproduced by CPU replay; recorded nested values are retained and checked against component/enclosing timers, while other diagnostics compare exactly.",
                            "Generation JSON is overwritten within each call as pending/returned/final; call directories are unique and final raw text remains available.",
                            "Guarded original pixel crops were temporary; source pixels, crop metadata/hashes and retained actual model crop inputs permit CPU reconstruction.",
                            "Model repo/revision/protocol identity is checked; this audit does not rehash multi-gigabyte model weights or prove pretraining exclusion.",
                            "CPU replay checks frozen parsing/postprocessing; it cannot regenerate the model response without a new inference.",
                            "Errors remain in the denominator; missing model returns do not prove safety or zero false-ready risk.",
                            "Public photos share development domains. LOCO16 is constant 2/2/2/0, bracket-positive and fresh LOCO quantity anomalies are absent."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--freeze", type=Path, default=FREEZE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isolated-audit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    need(not args.output.exists(), "Do not overwrite a prior audit")
    need(not args.output.resolve().is_relative_to(args.run.resolve()), "Audit output must be outside the original run")
    completed_metadata(args.run.resolve())
    if not args.isolated_audit:
        command = [sys.executable, "-I", str(Path(__file__).resolve()), "--isolated-audit", "--run", str(args.run.resolve()),
                   "--project-root", str(args.project_root.resolve()), "--freeze", str(args.freeze.resolve()), "--output", str(args.output.resolve())]
        raise SystemExit(subprocess.call(command))
    need(sys.flags.isolated, "Audit replay requires isolated Python")
    result = audit(args.run, args.project_root, args.freeze)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "completed_attempts": result["completed_attempts"],
                      "raw_evidence_checks": result["raw_evidence_checks"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
