"""Completed-only independent CPU audit of the fixed G-only LOCO24 trial.

No candidate analyzer/scorer is called. Math below independently enumerates BOMs.
Only the frozen G observer factory is used to replay saved text; model load is fatal.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import itertools
import json
import math
import os
import re
import shutil
import sys
import tempfile
import types
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE_REL = "docs/v0.8/loco_combined_freeze_v1/freeze.json"
FREEZE_SHA = "513b461a7574e6c68f1bdd6674769fe4b9fa95f3626b1302969f01c70b3deffd"
SELECTION_SHA = "fe6efb0160ac82cce73423494446c793b2ef87bff8c29f0dee91ca6111071114"
RUNNER = "scripts/v08/run_loco_combined.py"
RUNNER_SHA = "16f12bc8ac45cc7536a76bdb5600a5139a447479e8081fcf70d897ca301490cf"
PLAN_SHA = "6348669aeab05e6b8c96a7009312db549302ee9d6376c41451849f1ad4dc5a8b"
SCORER_SHA = "9391920712f523780e099836c54f21024cc2778360c94fdd68a25dc5fef28c94"
PARENT_FREEZE = "docs/v0.8/identity_reference_guarded_freeze_v1/freeze.json"
PARENT_SHA = "2e0ef97133988a2ca00a36a08b82e4a42e2d97f61ae01ef38980fe7d72f8b19e"
HELPER = "scripts/v08/audit_identity_reference_guarded.py"
HELPER_SHA = "a2be00fc3d12583583e03eb06265248550a7f085ee4019d5c88f2b35d4e4ac5c"
SEMANTIC_PATH = "test-results/v0.8-loco-combined-label-semantics-v1.json"
SEMANTIC_SHA = "e15a917d708a4c9edb27a10602d03b5628c423bfb3d593a900bec54af1146484"
SOURCE_PATH = "test-results/v0.8-loco-combined-source-preflight-v1.json"
SOURCE_SHA = "5a099cd576d4014c306beeb9183247953d7dea13303333d1d7e7b020b80e7cf4"
G = "spatial_guarded"
PARTS = ("bolt", "nut", "washer", "bracket")
NORMAL = dict(zip(PARTS, (2, 2, 2, 0), strict=True))
GROUPS = [(2, 0, 4, 0), (2, 1, 3, 0), (2, 3, 1, 0), (2, 4, 0, 0)]
IDENTITY_KEYS = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
STATUS_KEYS = (*IDENTITY_KEYS, "label", "path", "observer_source_hashes", "available")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def helper():
    path = ROOT / HELPER
    if sha(path) != HELPER_SHA:
        raise ValueError("Pinned independent replay helper changed")
    spec = importlib.util.spec_from_file_location("loco_independent_pinned_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = helper()
H = A.H
need, read, inside, AuditError = H.need, H.read, H.inside, H.AuditError


def completed_metadata(run):
    meta = read(run / "run.json")
    need(meta.get("status") == "completed", "Incomplete run; predictions deliberately unread")
    need(meta.get("planned") == meta.get("completed_attempts") == 24, "All 24 G attempts required")
    need(meta.get("source_changed") is False and meta.get("final_integrity_verified") is True,
         "Run integrity failed or unverified")
    need(meta.get("isolated_python") is True and meta.get("model_called_in_setup") is False
         and meta.get("automatic_promotion") is False and meta.get("no_warmup") is True, "Runtime boundary differs")
    need(datetime.fromisoformat(meta["finished_at"]) >= datetime.fromisoformat(meta["observations_finished_at"])
         >= datetime.fromisoformat(meta["started_at"]), "Run timestamps inconsistent")
    return meta


def count_map(value, allow_unknown=False):
    need(isinstance(value, dict) and set(value) == set(PARTS), "Explicit four categories required")
    need(all((allow_unknown and v is None) or (type(v) is int and 0 <= v <= 100) for v in value.values()),
         "Counts must be integer 0..100; no clipping to BOM maximum")
    return dict(value)


def rule_projection(observation):
    need(isinstance(observation, dict), "No observation")
    counts = count_map(observation["observed"], True)
    issues, action = observation["issues"], observation["action"]
    need(isinstance(issues, list) and len(issues) <= 20 and all(isinstance(v, str) for v in issues), "Invalid issues")
    need(action["kind"] in {"none", "recapture", "separate", "manual"}, "Invalid action")
    return {"observed": counts, "issues": issues, "action": {"kind": action["kind"]}}


def clear(observation):
    return all(v is not None for v in observation["observed"].values()) and not observation["issues"] and observation["action"]["kind"] == "none"


def legal(value):
    return any(value.values()) and all(type(v) is int and 0 <= v <= 3 for v in value.values())


def decide(observation, requirements):
    need(legal(requirements), "Invalid BOM")
    if observation["action"]["kind"] == "manual":
        return "manual"
    if not clear(observation):
        return "recapture"
    return "ready" if observation["observed"] == requirements else "correct"


def panel(truth, observation, supported_only=False):
    vectors = itertools.product(range(4), repeat=3 if supported_only else 4)
    orders = [dict(zip(PARTS, v + (0,) if supported_only else v, strict=True)) for v in vectors if any(v)]
    mismatched = [v for v in orders if v != truth]
    wrong = [v for v in mismatched if observation is not None and decide(observation, v) == "ready"]
    return {"legal_orders": len(orders), "mismatched_orders": len(mismatched), "risk_measured": observation is not None,
            "false_ready_orders": wrong if observation is not None else None,
            "any_false_ready": bool(wrong) if observation is not None else None}


def independent_score(case, row):
    truth = count_map(case["ground_truth"])
    observation, error, outcome = None, None, "N"
    if row is not None:
        need(row["case_id"] == case["id"] and row["source_sha256"] == case["source_sha256"], "Source mismatch in scoring")
        need(row["state"] in {"completed", "error", "not_attempted"}, "Unknown row state")
        if row["state"] == "not_attempted":
            need(row.get("observation") is None and not row.get("error"), "Unattempted row contains result")
        elif row["state"] == "error" or row.get("error"):
            error, outcome = str(row.get("error") or "Execution failed"), "E"
        else:
            observation = rule_projection(row["observation"])
            outcome = "U" if not clear(observation) else "C" if observation["observed"] == truth else "W"
    applicable = legal(truth)
    nominal = decide(observation, NORMAL) if observation is not None else None
    return {"case_id": case["id"], "outcome": outcome, "scoring_error": error,
            "counts_exact": observation["observed"] == truth if observation is not None else None,
            "actionable_counts": clear(observation) if observation is not None else None,
            "matched_order": {"applicability": "applicable" if applicable else "not_applicable_due_to_order_limit",
                              "requirements": dict(truth) if applicable else None,
                              "decision": decide(observation, truth) if observation is not None and applicable else None},
            "normal_order": {"requirements": dict(NORMAL), "decision": nominal, "truth_matches": truth == NORMAL,
                             "correct_adjustment": nominal == "correct" and observation["observed"] == truth},
            "all_four_panel": panel(truth, observation), "source_supported_panel": panel(truth, observation, True)}


def summarize(cases, rows):
    need(len(cases) == len({c["id"] for c in cases}) == len({c["source_sha256"] for c in cases}) == 24, "Full24 unique denominator")
    need(Counter(tuple(c["ground_truth"][p] for p in PARTS) for c in cases) == Counter({g: 6 for g in GROUPS}), "Four groups of six")
    indexed = {r["case_id"]: r for r in rows}
    need(len(indexed) == len(rows) and set(indexed) <= {c["id"] for c in cases}, "Duplicate/extra prediction")
    scores = [independent_score(c, indexed.get(c["id"])) for c in cases]
    totals = Counter(s["outcome"] for s in scores)
    groups = []
    for group in GROUPS:
        ids = {c["id"] for c in cases if tuple(c["ground_truth"][p] for p in PARTS) == group}
        groups.append({"counts": dict(zip(PARTS, group, strict=True)), "planned": 6,
                       "outcomes": {k: sum(s["outcome"] == k for s in scores if s["case_id"] in ids) for k in "CWUEN"}})
    def aggregate(key, size):
        return {"correlated_orders_per_image": size, "planned_image_denominator": 24,
                "planned_mismatched_orders": sum(s[key]["mismatched_orders"] for s in scores),
                "measured_images": sum(s[key]["risk_measured"] for s in scores), "unmeasured_images": totals["E"] + totals["N"],
                "observed_any_false_ready_images": sum(s[key]["any_false_ready"] is True for s in scores),
                "observed_false_ready_orders": sum(len(s[key]["false_ready_orders"] or []) for s in scores)}
    return {"schema": "kitguard.v08.loco-combined-score.draft.v1", "protocol_frozen": False, "planned": 24,
            "outcomes": {k: totals[k] for k in "CWUEN"}, "groups": groups,
            "matched_order_applicable": sum(legal(c["ground_truth"]) for c in cases),
            "matched_order_not_applicable": sum(not legal(c["ground_truth"]) for c in cases),
            "matched_order_correct_ready": sum(s["matched_order"]["decision"] == "ready" and s["outcome"] == "C" for s in scores),
            "normal_order_correct_adjustment": sum(s["normal_order"]["correct_adjustment"] for s in scores),
            "all_four_panel": aggregate("all_four_panel", 255), "source_supported_panel": aggregate("source_supported_panel", 63), "cases": scores}



def author_quantity_delta(code, label, definitions):
    """Decode the eight author labels; one is singular, two is plural."""
    match = re.fullmatch(r"([12])_(additional|missing)_(nut|washer)(s?)", label)
    need(match is not None and code in {240, 241, 242, 243, 246, 247, 248, 249}
         and definitions.get(code) == label, "Not an author quantity-only label")
    quantity = int(match[1])
    need(match[4] == ("s" if quantity == 2 else ""), "Author quantity label singular/plural mismatch")
    return match[3], quantity * (1 if match[2] == "additional" else -1)


def independent_cases(root, freeze):
    need(sha(root / SEMANTIC_PATH) == SEMANTIC_SHA and sha(root / SOURCE_PATH) == SOURCE_SHA, "Original semantic/source receipts changed")
    proposal, source_receipt = read(root / SEMANTIC_PATH), read(root / SOURCE_PATH)
    for name, expected in freeze["bindings"].items():
        need(sha(inside(root, name)) == expected, "Metadata binding changed")
    for bound in proposal["sources"]:
        A.verify_ref(root, bound)
    for name, expected in source_receipt["input_sha256"].items():
        need(freeze["bindings"].get(name) == expected, "Missing original source binding")
    need(source_receipt["status"] == "passed_no_exact_overlap_in_bound_registry" and not source_receipt["overlap_candidate_records"]
         and not source_receipt["integrity_errors"] and not source_receipt["metadata_changed_during_check"], "Source preflight incomplete")
    author = {c["id"]: c for c in read(root / "datasets/manifests/mvtec_loco_screw_bag/manifest.json")["images"]}
    definitions = {d["pixel_value"]: d["defect_name"] for d in read(root / "datasets/raw/mvtec_loco_ad/screw_bag/defects_config.json")}
    precases = {c["source_id"]: c for c in source_receipt["records"] if c["role"] == "candidate"}
    records = proposal["records"]
    need({r["source_id"] for r in records} == {f"screw_bag/test/logical_anomalies/{n}" for n in range(113, 137)}, "Exact original24 population changed")
    expected = []
    for record in records:
        original = author[record["source_id"]]
        need(original["label_status"] == "unresolved" and original["kitguard_counts"] is None, "Original truth was rewritten")
        need(original["path"] == record["source_path"] and original["sha256"] == record["source_sha256"], "Author source differs")
        need(len(original["source_masks"]) == len(record["deltas"]) == record["actual_mask_count"] == 2
             and record["other_registered_defects"] == [], "Not exactly two isolated quantity labels")
        masks = {m["path"]: m for m in original["source_masks"]}
        truth, seen = dict(NORMAL), set()
        for delta in record["deltas"]:
            code, label = delta["pixel_value"], delta["defect_name"]
            part, amount = author_quantity_delta(code, label, definitions)
            need(part not in seen and (part, amount) == (delta["part"], delta["delta"]), "Duplicate category or changed delta")
            seen.add(part)
            mask = masks[delta["mask"]]
            need(mask["sha256"] == delta["mask_sha256"] and mask["pixel_values"] == [code] and mask["defect_names"] == [label], "Mask label mapping differs")
            A.verify_ref(root, {"path": delta["mask"], "sha256": delta["mask_sha256"]})
            truth[part] += amount
        need(truth == record["proposed_author_derived_counts_not_frozen"] and record["within_order_scope_0_to_3"] == legal(truth), "Recomputed truth/scope differs")
        source = {"path": record["source_path"], "sha256": record["source_sha256"]}
        A.verify_ref(root, source)
        pre = precases[record["source_id"]]
        need(pre["sha256"] == source["sha256"], "Source receipt differs")
        expected.append({"source_id": record["source_id"], "source": source, "source_sha256": source["sha256"],
                         "ground_truth": truth, "truth_rule": "author_combined_quantity_defect_rule_v1", "deltas": record["deltas"],
                         "source_rgb_sha256": pre["rgb_sha256"]})
    expected.sort(key=lambda c: hashlib.sha256(("kitguard-loco24-v1|"+c["source_sha256"]).encode()).hexdigest())
    for index, case in enumerate(expected, 1):
        case["id"] = f"case-{index:03d}"
    need(freeze["cases"] == expected, "Frozen cases/order/truth differ from independent author derivation")
    return expected


def verify_freeze(root, run, path, meta):
    need(sha(path) == sha(run / "freeze.json") == meta["freeze_sha256"] == FREEZE_SHA, "Pinned LOCO freeze mismatch")
    freeze = read(path)
    need(freeze["schema"] == "kitguard.v08.loco-combined.freeze.v1" and freeze["status"] == "passed", "Wrong freeze")
    snapshot = path.parent / "source_snapshot"
    need(Path(meta["runtime_source_root"]).resolve() == snapshot and Path(freeze["project_root"]).resolve() == root, "Wrong isolated source/data root")
    parent_path = root / PARENT_FREEZE
    need(sha(parent_path) == PARENT_SHA, "Original identity/base freeze changed")
    parent = read(parent_path)
    provenance = read(snapshot / "loco_source_provenance.json")
    need(provenance == {"source_freeze": {"path": PARENT_FREEZE, "sha256": PARENT_SHA}, "source_hashes": parent["source_hashes"],
                        "unused_identity_adapter_may_be_present_in_G_only_bundle": True}, "Legacy provenance changed")
    extra = {RUNNER, "docs/v0.8/LOCO_COMBINED_RUNNER_PLAN.md", "scripts/v08/score_loco_combined.py", "loco_source_provenance.json"}
    need(set(freeze["source_hashes"]) == set(parent["source_hashes"]) | extra and len(freeze["source_hashes"]) == 69,
         "Exactly65 legacy+4 additions required")
    need(all(freeze["source_hashes"][n] == h for n, h in parent["source_hashes"].items()), "Legacy inference source changed")
    need(freeze["source_hashes"][RUNNER] == RUNNER_SHA
         and freeze["source_hashes"]["docs/v0.8/LOCO_COMBINED_RUNNER_PLAN.md"] == PLAN_SHA
         and freeze["source_hashes"]["scripts/v08/score_loco_combined.py"] == SCORER_SHA, "Reviewed protocol/runner/scorer differs")
    A.snapshot_runtime_files(snapshot, freeze["source_hashes"])
    selection = read(A.verify_ref(root, freeze["selection"]))
    need(freeze["selection"]["sha256"] == SELECTION_SHA and selection == freeze["selection_payload"], "Root method choice changed")
    need(selection["status"] == "approved_for_freeze" and selection["methods"] == [G]
         and selection["identity_decision"]["include"] is False and selection["no_loco24_model_results_used"] is True,
         "Only preregistered G included")
    prior_audit = read(A.verify_ref(root, selection["identity51_evidence"]["independent_audit"]))
    need(prior_audit["status"] == "passed" and prior_audit["independent_results"]["development_gate_count_conditions_passed"] is False,
         "Root exclusion basis differs")
    for record in selection["identity51_evidence"].values():
        A.verify_ref(root, record)
    need(datetime.fromisoformat(prior_audit["checked_at"]) <= datetime.fromisoformat(selection["selected_at_utc"])
         <= datetime.fromisoformat(freeze["frozen_at"]) <= datetime.fromisoformat(meta["started_at"]), "Selection/freeze chronology differs")
    need(freeze["model"] == parent["model"] and freeze["references"] == parent["references"]
         and freeze["versions"] == parent["versions"], "Fixed model/reference/runtime differs")
    # Frozen upload/schema replay below checks actual library behavior; package versions also pinned.
    import importlib.metadata
    import platform
    versions = {"python": platform.python_version(), **{p: importlib.metadata.version(p)
                for p in ("mlx", "mlx-vlm", "transformers", "pydantic", "pillow", "fastapi", "httpx")}}
    need(versions == freeze["versions"], "Replay runtime differs")
    preflight = read(A.verify_ref(root, freeze["preflight_receipt"]))
    keys = set(preflight) - {"schema", "runtime_source_root", "inputs"}
    need(all(preflight[k] == freeze[k] for k in keys), "Frozen preflight payload changed")
    for previous, current in zip(preflight["inputs"], freeze["inputs"], strict=True):
        for key in previous:
            if key in {"normalized", "prepared"}:
                need(previous[key]["sha256"] == current[key]["sha256"], "Frozen input copy differs")
            else:
                need(previous[key] == current[key], "Input metadata differs from preflight")
    cases = independent_cases(root, freeze)
    expected_manifest = {"schema": "kitguard.v08.loco-combined.manifest.v1", "truth_rule": "author_combined_quantity_defect_rule_v1", "cases": cases}
    need(read(run / "manifest.json") == read(path.parent / "manifest.json") == expected_manifest
         and sha(run / "manifest.json") == freeze["manifest_sha256"], "Manifest/truth copy differs")
    plan = [{"attempt": i, "case_id": c["id"], "mode": G, "within_case_position": 1, "source_sha256": c["source_sha256"]}
            for i, c in enumerate(cases, 1)]
    need(freeze["schedule"] == plan and len(freeze["methods"]) == 1 and freeze["methods"][0]["mode"] == G,
         "G-only complete schedule differs")
    return freeze, snapshot, cases, plan


def verify_inputs(root, run, freeze, frozen):
    from PIL import Image
    references_sha, references_rgb = set(), set()
    for reference in freeze["references"].values():
        for role in ("source", "crop"):
            path = A.verify_ref(root, reference[role])
            references_sha.add(sha(path))
            with Image.open(path) as image:
                references_rgb.add(A.pixel_sha(image))
        references_sha.add(reference["prepared_sha256"])
    need(len(freeze["inputs"]) == 24, "24 input records required")
    verified, original_seen, normal_seen = {}, set(), set()
    for case, item in zip(freeze["cases"], freeze["inputs"], strict=True):
        need(item["case_id"] == case["id"], "Input order differs")
        source = A.verify_ref(root, case["source"])
        normalized, target = A.verify_ref(root, item["normalized"]), A.verify_ref(root, item["prepared"])
        actual = run / "normalized_inputs" / f"{case['id']}.jpg"
        with Image.open(source) as image:
            pixel = A.pixel_sha(image)
            need(pixel == case["source_rgb_sha256"] and pixel not in original_seen, "Original RGB mismatch/duplicate")
            original_seen.add(pixel)
        expected = hashlib.sha256(frozen.upload.app_upload_bytes(source)).hexdigest()
        need(sha(normalized) == expected, "Frozen normalized bytes differ from canonical upload")
        if actual.exists():
            need(sha(actual) == expected, "Actual normalized bytes differ from frozen app upload")
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "target.png"
            frozen.vision._prepare_image(actual if actual.exists() else normalized, rebuilt, 1536)
            need(sha(rebuilt) == sha(target), "Actual prepared target differs")
        with Image.open(normalized) as image:
            rgb, size = A.pixel_sha(image), list(image.size)
        with Image.open(target) as image:
            prepared_rgb, prepared_size = A.pixel_sha(image), list(image.size)
        need((rgb, size, prepared_rgb, prepared_size) == (item["normalized_rgb_sha256"], item["normalized_size"], item["target_rgb_sha256"], item["target_size"]),
             "Normalized/prepared decoded metadata differs")
        need(rgb not in normal_seen and rgb not in references_rgb and prepared_rgb not in references_rgb
             and expected not in references_sha and sha(target) not in references_sha, "Canonical target duplicate/reference overlap")
        normal_seen.add(rgb)
        verified[case["id"]] = {"normalized": actual, "normalized_sha256": expected, "target_sha256": sha(target)}
    need({p.name for p in (run / "normalized_inputs").iterdir()} <= {f"{c['id']}.jpg" for c in freeze["cases"]}, "Extra normalized input")
    return verified


def replay(engine, normalized, directory, row, frozen):
    calls, counts = H.verify_call_files(directory, row.get("observation_diagnostics"), row.get("error"))
    need(len(calls) <= 3, "No fourth stage/retry")
    cursor, opaque = 0, []
    for call in calls:
        start, end = A.call_flags(call)
        counts["actual_model_calls_started"] += start
        counts["actual_model_calls_completed"] += end
    def no_model(_self):
        raise AuditError("Actual model loading is forbidden during CPU replay")
    def raw_stub(_self, system, prompt, images, schema, *, max_tokens=450):
        nonlocal cursor
        need(cursor < len(calls), "Missing saved generation")
        record = calls[cursor]
        cursor += 1
        need((system, prompt, schema.__name__, max_tokens) == (record["system"], record["prompt"], record["schema"], record["max_tokens"]),
             "Prompt/schema/budget changed")
        need(hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest() == record["json_schema_sha256"], "Complete JSON schema changed")
        need(len(images) == len(record["images"]), "Reference or target input count differs")
        for source, saved in zip(images, record["images"], strict=True):
            need(sha(source) == saved["sha256"], "Exact source/rotation/crop input changed")
            target = inside(_self.artifact_dir, saved["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _self._observation_attempt.setdefault("generation_calls", []).append(copy.deepcopy(record))
        _self._last_inference = copy.deepcopy(record["runtime"])
        if record["status"] == "parsed":
            result = frozen.vision._parse_json(record["raw_text"].strip(), schema)
            need(result.model_dump() == record["parsed"], "Stored raw JSON parses differently")
            return result
        if record["raw_text"] is not None:
            try:
                frozen.vision._parse_json(record["raw_text"].strip(), schema)
            except frozen.vision.ModelOutputError:
                need(record["error"].startswith("ModelOutputError:"), "Parse failure type differs")
                raise
            raise AuditError("Saved parse failure is actually valid")
        opaque.append({"call": cursor, "error": record["error"], "underlying_runtime_cause_not_reproduced": True})
        raise frozen.vision.ModelUnavailableError("Recorded runtime failure: " + record["error"])
    original_generate = type(engine)._generate
    original_recorder = frozen.probe.SelectiveIdentityVision._generate
    def generate(_self, system, prompt, images, schema, *, max_tokens=450):
        start = cursor
        try:
            return original_generate(_self, system, prompt, images, schema, max_tokens=max_tokens)
        finally:
            if cursor == start+1:
                actual = _self._observation_attempt["generation_calls"][-1]
                need(actual["model_call_started"] is False and actual["model_call_completed"] is False, "Replay invoked generate")
                actual.update(model_call_started=calls[start]["model_call_started"], model_call_completed=calls[start]["model_call_completed"])
                need(actual == calls[start], "Actual roles/schema/record changed on replay")
    engine._load = types.MethodType(no_model, engine)
    engine._generate = types.MethodType(generate, engine)
    frozen.probe.SelectiveIdentityVision._generate = raw_stub
    try:
        with tempfile.TemporaryDirectory(prefix="loco-independent-replay-") as temporary:
            engine.artifact_dir = Path(temporary)
            observed = error = None
            try:
                observed = engine._observe(normalized, {})
                validated = frozen.schemas.Observation.model_validate(observed).model_dump(mode="json")
            except AuditError:
                raise
            except Exception as exc:  # noqa: BLE001 -- compare preserved failures
                error = exc
            need(cursor == len(calls), "Unconsumed raw generation record")
            diag = engine._observation_attempt
            need(diag == row["observation_diagnostics"], "Frozen diagnostic replay differs: " + json.dumps(H.diagnostic_differences(row["observation_diagnostics"], diag), ensure_ascii=False))
            if row["state"] == "error":
                need(error is not None and row["observation"] is None, "Failed row replayed successfully")
                if not opaque:
                    need(row["error"] == f"{type(error).__name__}: {error}", "Saved exception differs")
                if observed is not None:
                    saved_invalid, rebuilt_invalid = copy.deepcopy(row.get("raw_observation_before_full_validation")), copy.deepcopy(observed)
                    for value in (saved_invalid, rebuilt_invalid):
                        value.pop("latency_ms", None)
                    need(saved_invalid == rebuilt_invalid, "Invalid full Observation receipt differs")
            else:
                need(error is None and row["state"] == "completed", f"Saved success failed: {error}")
                actual = frozen.schemas.Observation.model_validate(row["observation"]).model_dump(mode="json")
                for value in (actual, validated):
                    value.pop("latency_ms", None)
                need(actual == validated, "Complete Observation differs from raw replay")
            need(engine._last_inference == row["observer_status_after"]["last_inference"], "Historical last-inference receipt differs")
            counts["reconstructed_identity_crops"] += len(diag.get("identity", {}).get("crops", []))
    finally:
        frozen.probe.SelectiveIdentityVision._generate = original_recorder
        engine._generate = types.MethodType(original_generate, engine)
    return counts, opaque


def check_stages(diagnostics, target_sha, directory, successful, frozen):
    import io

    from PIL import Image
    calls = diagnostics.get("generation_calls", [])
    rotation = None
    if calls:
        with Image.open(inside(directory, calls[0]["images"][0]["path"])) as image:
            buffer = io.BytesIO()
            image.transpose(Image.Transpose.ROTATE_90).save(buffer, format="PNG")
            rotation = hashlib.sha256(buffer.getvalue()).hexdigest()
    for index, call in enumerate(calls):
        if index < 2:
            roles = [{"image": 1, "role": "inspection_target"}]
            hashes = [target_sha if index == 0 else rotation]
            system, prompt, budget = frozen.vision.SPATIAL_SYSTEM, frozen.vision.SPATIAL_USER, 900
        else:
            crops = diagnostics["identity"]["crops"]
            roles = [{"image": 1, "role": "inspection_target"}] + [{"image": n, "role": "target_crop", "point_id": c["id"]} for n, c in enumerate(crops, 2)]
            hashes = [target_sha, *[c["crop_sha256"] for c in crops]]
            system, prompt, budget = frozen.vision.IDENTITY_SYSTEM, frozen.vision.build_prompt(crops), 1800
        need(call["input_roles"] == roles and [i["sha256"] for i in call["images"]] == hashes
             and (call["system"], call["prompt"], call["max_tokens"]) == (system, prompt, budget), "G stage images/roles/prompts differ; no references permitted")
    if successful:
        need(len(calls) in {2, 3} and all(c["status"] == "parsed" for c in calls), "Successful G missing parsed stage")
        state = diagnostics["identity"]["status"]
        need((len(calls) == 2 and state in {"skipped_base_unclear", "skipped_no_candidates"})
             or (len(calls) == 3 and state in {"confirmed_candidates", "blocked"}), "Identity skip/execute state differs")
    return {"passed": True, "generation_attempt_records": len(calls), "no_reference_inputs": True}


def timing(values):
    need(all(type(v) is int and v >= 0 for v in values), "Invalid observation timer")
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "p50_ms": None, "p90_ms": None, "total_ms": 0}
    def percentile(q):
        index = (len(ordered)-1)*q
        low, high = math.floor(index), math.ceil(index)
        return ordered[low] + (ordered[high]-ordered[low])*(index-low)
    return {"n": len(values), "p50_ms": percentile(.5), "p90_ms": percentile(.9), "total_ms": sum(values), "max_ms": max(values)}


def normal_results(root, freeze, frozen):
    normal = freeze["historical_normal16"]
    need(normal["historical_exposed_nonconcurrent"] is True and normal["pooled_with_24"] is False
         and normal["planned_per_method"] == 16 and set(normal["records"]) == {G}, "Normal panel cannot be pooled or add excluded I")
    for record in normal["bindings"]:
        A.verify_ref(root, record)
    manifest = read(root / "evaluation-runs/v0.7/public_paired_v1/manifest.json")
    cases = [c for c in manifest["cases"] if c["subgroup"] == "loco_normal_222"]
    need(len(cases) == len({c["source_sha256"] for c in cases}) == 16, "All16 normal sources required")
    old = {r["case_id"]: r for r in map(json.loads, (root / "evaluation-runs/v0.7/public_paired_v1/predictions.jsonl").read_text().splitlines()) if r["mode"] == G}
    need(normal["records"][G] == [{"case": c, "row": old[c["id"]]} for c in cases], "Historical normal row copy changed")
    scores = []
    for case in cases:
        row = old[case["id"]]
        if not row["error"]:
            frozen.schemas.Observation.model_validate(row["observation"])
        scores.append(independent_score(case, {"case_id": case["id"], "source_sha256": case["source_sha256"], "state": "error" if row["error"] else "completed",
                                              "error": row["error"], "observation": row["observation"]}))
    return {"exposed_nonconcurrent_not_pooled": True, "methods": {G: {"planned": 16, "outcomes": {k: sum(s["outcome"] == k for s in scores) for k in "CWUEN"}, "cases": scores}}}


def audit_loaded(root, run, freeze_path):
    root, run, freeze_path = root.resolve(), run.resolve(), freeze_path.resolve()
    meta = completed_metadata(run)
    before = A.inventory(run)
    freeze, snapshot, cases, plan = verify_freeze(root, run, freeze_path, meta)
    need(before["predictions.json"] == meta["predictions_sha256"] and before["analysis.json"] == meta["analysis_sha256"], "Final ledger/report SHA changed")
    rows = read(run / "predictions.json")
    need(len(rows) == 24 and [{k: r.get(k) for k in plan[0]} for r in rows] == plan, "Full24 ledger/order/source/mode differs")
    need(all(r["state"] in {"completed", "error"} for r in rows), "Completed24 cannot silently contain N")
    db = A.runtime_database(run, meta)
    model_files = A.verify_model(freeze["model"])
    frozen = H.load_frozen_modules(snapshot)
    candidate = importlib.import_module("scripts.v08.run_loco_combined")
    need(Path(candidate.__file__).resolve() == snapshot / RUNNER, "Wrong observer factory import")
    engine = candidate.guarded_observer(Path(freeze["model"]["status"]["path"]))
    status = engine.status()
    method = freeze["methods"][0]
    need(all(status[k] == method[k] for k in IDENTITY_KEYS) and status["observation_mode"] == G, "G/model protocol differs")
    inputs = verify_inputs(root, run, freeze, frozen)
    counts, attempts, opaque, previous_loaded = Counter(), [], [], False
    previous_status = status
    for row, case in zip(rows, cases, strict=True):
        directory = run / "cases" / f"{row['attempt']:03d}-{case['id']}-{G}"
        bound = inputs[case["id"]]
        before_status, after_status = row["observer_status_before"], row["observer_status_after"]
        need(all(before_status[k] == after_status[k] == status[k] for k in STATUS_KEYS), "Per-attempt protocol/source/model changed")
        need(before_status == previous_status, "Between-attempt observer/runtime status changed")
        previous_status = after_status
        need(type(row["loaded_before"]) is bool and row["loaded_before"] == before_status["loaded"] == previous_loaded,
             "Cold/warm sequence differs")
        need(type(after_status["loaded"]) is bool and (not previous_loaded or after_status["loaded"]), "Model unload/reload unrecorded")
        previous_loaded = after_status["loaded"]
        timing([row["latency_ms"]])
        if not row["observation_attempted"]:
            need(row["state"] == "error" and row["observation"] is None and row["observation_diagnostics"] is None,
                 "Pre-observation failure contains stale result")
            need(not list(directory.rglob("generation.json")), "Unattempted observation has raw calls")
            opaque.append({"attempt": row["attempt"], "error": row["error"], "pre_observation_failure": True})
            checked = Counter()
        else:
            need(bound["normalized"].is_file() and row["normalized_sha256"] == bound["normalized_sha256"], "Attempt input differs")
            diag = row["observation_diagnostics"]
            need(diag == after_status["last_observation_attempt"] and diag["source_sha256"] == bound["normalized_sha256"]
                 and diag["mode"] == G and diag["model"] == status["label"], "Diagnostics/source/model mismatch")
            need(not any(c.get("model_call_started") for c in diag.get("generation_calls", [])) or after_status["loaded"],
                 "Actual generate started without a loaded runtime receipt")
            checked, failures = replay(engine, bound["normalized"], directory, row, frozen)
            opaque.extend({"attempt": row["attempt"], **failure} for failure in failures)
            expected_stage = check_stages(diag, bound["target_sha256"], directory, row["state"] == "completed", frozen)
            need(expected_stage == row["stage_contract"], "Saved stage contract differs")
            raw_ms = sum(c["runtime"]["seconds"]*1000 for c in diag["generation_calls"] if c.get("runtime"))
            need(raw_ms <= row["latency_ms"]+50, "Generation time exceeds observation")
        counts.update(checked)
        attempts.append({"case_id": case["id"], "source_id": case["source_id"], "outcome": independent_score(case, row)["outcome"],
                         "calls": checked["calls"], "actual_calls_started": checked["actual_model_calls_started"], "actual_calls_completed": checked["actual_model_calls_completed"]})
    allowed_dirs = {f"{p['attempt']:03d}-{p['case_id']}-{G}" for p in plan}
    need({p.name for p in (run / "cases").iterdir()} <= allowed_dirs, "Unplanned/retried observation artifacts")
    report = read(run / "analysis.json")
    scores = summarize(cases, rows)
    expected = {"schema": "kitguard.v08.loco-combined.analysis.v1", "freeze_sha256": FREEZE_SHA, "protocol_frozen": True,
                "scorer_sha256": SCORER_SHA, "embedded_scorer_metadata_is_unchanged_draft_API": True,
                "planned_cases": 24, "planned_observations": 24, "methods": {G: scores}, "paired_changes": [], "paired_transitions": {},
                "historical_normal16": normal_results(root, freeze, frozen),
                "timing": {G: {"all_attempted": timing([r["latency_ms"] for r in rows]), "warm_subset": timing([r["latency_ms"] for r in rows if r["loaded_before"]])}},
                "generation_attempt_records": counts["calls"], "model_calls_started": counts["actual_model_calls_started"],
                "model_calls_completed": counts["actual_model_calls_completed"], "automatic_promotion": False, "independent_audit_required": True,
                "no_general_counting_or_real_world_safety_claim": True}
    controls = {}
    for comparator in ("constant_normal", "always_abstain"):
        controls[comparator] = summarize(cases, [{"case_id": c["id"], "source_sha256": c["source_sha256"], "state": "completed",
            "observation": {"observed": dict(NORMAL) if comparator == "constant_normal" else dict.fromkeys(PARTS),
                            "issues": [] if comparator == "constant_normal" else ["Analytical abstention"],
                            "action": {"kind": "none" if comparator == "constant_normal" else "recapture"}}} for c in cases])
    expected["analytical_comparators_not_model_calls"] = controls
    need(report == expected, "Independent full analysis differs: " + json.dumps(H.diagnostic_differences(report, expected), ensure_ascii=False))
    need(sum(r["latency_ms"] for r in rows) <= (datetime.fromisoformat(meta["observations_finished_at"])-datetime.fromisoformat(meta["started_at"])).total_seconds()*1000+24,
         "Observation timers exceed enclosing run")
    need(A.inventory(run) == before and completed_metadata(run) == meta, "Audit changed or raced original run")
    A.snapshot_runtime_files(snapshot, freeze["source_hashes"])
    need(not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules), "Audit imported MLX")
    return {"schema": "kitguard.v08.loco-combined.independent-audit.v1", "status": "passed", "checked_at": datetime.now(UTC).isoformat(),
            "completed_attempts": 24, "source_snapshot_files_verified": 69, "model_payloads_rehashed": model_files,
            "raw_evidence_checks": dict(counts), "frozen_normalized_inputs_verified": 24,
            "actual_normalized_inputs_verified": sum(i["normalized"].is_file() for i in inputs.values()), "independent_analysis": expected, "attempt_audits": attempts,
            "retained_failures_without_reproducible_model_return": opaque, "empty_runtime_database": db,
            "model_loaded_or_called": False, "run_modified": False, "automatic_promotion": False,
            "evidence_sha256": {"freeze": FREEZE_SHA, "selection": SELECTION_SHA, "auditor": sha(Path(__file__)), "helper": HELPER_SHA,
                                "run": before["run.json"], "predictions": before["predictions.json"], "analysis": before["analysis.json"]},
            "artifacts_sha256": before,
            "limitations": ["Same-domain author global quantity labels, not native instance counting truth or physical/session independence.",
                            "Absence from the bound project exposure registry does not certify never-viewed or pretraining-unseen images.",
                            "Normal16 is historical exposed nonconcurrent and never pooled with24; constant normal counts do not prove quantity skill.",
                            "CPU replay verifies saved bytes/text/schema/postprocessing; it cannot authenticate historical model returns or remeasure latency.",
                            "G repeats the same correlated VLM; no independent confirmation or field safety claim.",
                            "255/63 BOMs per image are correlated rule replays, not additional independent photographs."]}


def audit(root, run, freeze_path):
    with tempfile.TemporaryDirectory(prefix="loco-audit-runtime-") as temporary:
        os.environ["KITGUARD_DATA_DIR"] = temporary
        return audit_loaded(root, run, freeze_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--run", type=Path, default=ROOT / "evaluation-runs/v0.8/loco_combined_v1")
    parser.add_argument("--freeze", type=Path, default=ROOT / FREEZE_REL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists() and not args.output.resolve().is_relative_to(args.run.resolve()), "New external audit output required")
    try:
        result = audit(args.project_root, args.run, args.freeze)
    except Exception as exc:
        result = {"schema": "kitguard.v08.loco-combined.independent-audit.v1", "status": "failed", "checked_at": datetime.now(UTC).isoformat(),
                  "error": f"{type(exc).__name__}: {exc}", "auditor_sha256": sha(Path(__file__)), "freeze_sha256": sha(args.freeze), "model_loaded_or_called": False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"status": result["status"], "outcomes": result["independent_analysis"]["methods"][G]["outcomes"], "output": str(args.output), "sha256": sha(args.output)}))


if __name__ == "__main__":
    main()
