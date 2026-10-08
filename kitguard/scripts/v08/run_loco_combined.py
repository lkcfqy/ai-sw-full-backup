"""Freezeable, source-isolated LOCO24 runner. No image/model work on import.

Selection precedes preflight/freeze; only an explicit root receipt can select I.
Original sources, scorer and historical evidence are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = "scripts/v08/run_loco_combined.py"
PLAN = "docs/v0.8/LOCO_COMBINED_RUNNER_PLAN.md"
SCORER = "scripts/v08/score_loco_combined.py"
SCORER_SHA = "9391920712f523780e099836c54f21024cc2778360c94fdd68a25dc5fef28c94"
I_FREEZE = "docs/v0.8/identity_reference_guarded_freeze_v1/freeze.json"
I_SHA = "2e0ef97133988a2ca00a36a08b82e4a42e2d97f61ae01ef38980fe7d72f8b19e"
I_RUN = "evaluation-runs/v0.8/identity_reference_guarded_v1"
G = "spatial_guarded"
I = "spatial_guarded_identity_references_v1"
PARTS = ("bolt", "nut", "washer", "bracket")
BINDINGS = {
    "test-results/v0.8-loco-combined-label-semantics-v1.json": "e15a917d708a4c9edb27a10602d03b5628c423bfb3d593a900bec54af1146484",
    "test-results/v0.8-loco-combined-label-peer-review-v1.json": "52adf819d42a68672d637d97c6ff64cfafe4b11501944ed58cc86789048e35eb",
    "test-results/v0.8-loco-combined-source-preflight-v1.json": "5a099cd576d4014c306beeb9183247953d7dea13303333d1d7e7b020b80e7cf4",
    SCORER: SCORER_SHA,
    "docs/v0.8/LOCO_COMBINED_SCORING_DRAFT.md": "01c8bbb0b3482c13d185b38562e53c180c064c63bf9f70002c745f9923bc9250",
    I_FREEZE: I_SHA,
}
SEMANTICS, PEER, SOURCE_CHECK = list(BINDINGS)[:3]
MANIFEST = "datasets/manifests/mvtec_loco_screw_bag/manifest.json"
DEFECTS = "datasets/raw/mvtec_loco_ad/screw_bag/defects_config.json"
DELTA = {249: ("nut", 1), 248: ("nut", 2), 247: ("washer", 1), 246: ("washer", 2),
         243: ("nut", -1), 242: ("nut", -2), 241: ("washer", -1), 240: ("washer", -2)}
GROUPS = {(2, 0, 4, 0): 6, (2, 1, 3, 0): 6, (2, 3, 1, 0): 6, (2, 4, 0, 0): 6}
POLICY = {"population": 24, "truth_rule": "author_combined_quantity_defect_rule_v1",
          "case_order": "sha256(kitguard-loco24-v1|source_sha256), ascending",
          "two_arm_order": "AB,BA alternating by ordered case; 12 first positions per arm",
          "neutral_requirements": dict.fromkeys(PARTS, 1), "image_max_side": 1536,
          "spatial_max_tokens": 900, "identity_max_tokens": 1800, "temperature": 0,
          "retries": 0, "warmup": False, "workers": 1, "automatic_promotion": False,
          "observed_count_max": 100, "order_count_max": 3,
          "normal16": "historical exposed nonconcurrent; never pooled with 24",
          "timing": "per observation includes copy, model load if cold, observation/raw persistence; preprocessing separate"}


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inside(root, name):
    require(isinstance(name, str) and not Path(name).is_absolute() and ".." not in Path(name).parts,
            "Unsafe relative path")
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()), "Path escapes root")
    return path


def ref(root, path):
    return {"path": Path(path).resolve().relative_to(root.resolve()).as_posix(), "sha256": sha(path)}


def verify(root, record):
    path = inside(root, record["path"])
    require(sha(path) == record["sha256"], f"Changed evidence: {record['path']}")
    return path


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def legacy():
    require((ROOT / "loco_source_provenance.json").is_file(), "Isolated immutable source bundle required")
    from scripts.v08 import run_identity_reference_guarded as adapter
    require(Path(adapter.__file__).resolve() == ROOT / "scripts/v08/run_identity_reference_guarded.py",
            "Wrong adapter import")
    return adapter


def prepare_sources(root, destination):
    require(not destination.exists(), "Source bundle cannot be overwritten")
    require(sha(root / I_FREEZE) == I_SHA and sha(root / SCORER) == SCORER_SHA, "Pinned dependency changed")
    frozen = read(root / I_FREEZE)
    original = (root / I_FREEZE).parent / "source_snapshot"
    for name, expected in frozen["source_hashes"].items():
        require(sha(inside(original, name)) == expected, "Immutable legacy source changed")
    destination.mkdir(parents=True)
    for name in frozen["source_hashes"]:
        target = inside(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(original, name), target)
    for name in (ENTRY, PLAN, SCORER):
        target = inside(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(root, name), target)
    write(destination / "loco_source_provenance.json", {
        "source_freeze": {"path": I_FREEZE, "sha256": I_SHA}, "source_hashes": frozen["source_hashes"],
        "unused_identity_adapter_may_be_present_in_G_only_bundle": True})
    return inventory(destination)


def quantity_truth(record, author, defects):
    """Metadata-only distinct-category deltas; masks are not instances."""
    require(record["source_id"] == author["id"] and record["source_path"] == author["path"]
            and record["source_sha256"] == author["sha256"], "Author source mismatch")
    require(author["label_status"] == "unresolved" and author["kitguard_counts"] is None,
            "Do not overwrite or silently adopt different original truth")
    require(record["actual_mask_count"] == len(record["deltas"]) == len(author["source_masks"]) == 2
            and record["other_registered_defects"] == [], "Exactly two quantity defects required")
    result, seen = dict(zip(PARTS, (2, 2, 2, 0), strict=True)), set()
    masks = {m["path"]: m for m in author["source_masks"]}
    require(len(masks) == 2, "Duplicate mask")
    for item in record["deltas"]:
        code = item["pixel_value"]
        require(code in DELTA and DELTA[code] == (item["part"], item["delta"]), "Changed quantity mapping")
        require(item["part"] not in seen, "Repeated category delta cannot be summed")
        seen.add(item["part"])
        source = masks[item["mask"]]
        require(source["sha256"] == item["mask_sha256"] and source["pixel_values"] == [code]
                and source["defect_names"] == [item["defect_name"]]
                and defects[code] == item["defect_name"], "Author mask/config label mismatch")
        result[item["part"]] += item["delta"]
    require(result == record["proposed_author_derived_counts_not_frozen"], "Proposal differs from rederived counts")
    require(tuple(result[p] for p in PARTS) in GROUPS, "Unplanned count group")
    require(record["within_order_scope_0_to_3"] == all(n <= 3 for n in result.values()), "Order scope differs")
    return result


def source_cases(root):
    """Read metadata and raw byte hashes only; never decode candidate images/masks."""
    bindings = dict(BINDINGS)
    for name, expected in bindings.items():
        verify(root, {"path": name, "sha256": expected})
    semantics, peer, receipt = read(root / SEMANTICS), read(root / PEER), read(root / SOURCE_CHECK)
    require(peer["status"] == "supported_for_protocol_preparation_only", "Semantic peer review missing")
    require(receipt["status"] == "passed_no_exact_overlap_in_bound_registry"
            and receipt["planned_candidates"] == receipt["retained_candidates"] == 24
            and not receipt["overlap_candidate_records"] and not receipt["integrity_errors"]
            and not receipt["metadata_changed_during_check"], "Bound source preflight failed")
    for source in semantics["sources"]:
        verify(root, source)
        bindings[source["path"]] = source["sha256"]
    for name, expected in receipt["input_sha256"].items():
        verify(root, {"path": name, "sha256": expected})
        bindings[name] = expected
    author = {c["id"]: c for c in read(root / MANIFEST)["images"]}
    defects = {d["pixel_value"]: d["defect_name"] for d in read(root / DEFECTS)}
    candidates = {r["source_id"]: r for r in receipt["records"] if r["role"] == "candidate"}
    records = semantics["records"]
    require(len(records) == len(candidates) == 24 and len({r["source_sha256"] for r in records}) == 24,
            "Keep all 24 unique sources")
    cases = []
    for record in records:
        truth = quantity_truth(record, author[record["source_id"]], defects)
        source = {"path": record["source_path"], "sha256": record["source_sha256"]}
        verify(root, source)
        for delta in record["deltas"]:
            verify(root, {"path": delta["mask"], "sha256": delta["mask_sha256"]})
        prechecked = candidates[record["source_id"]]
        require(prechecked["sha256"] == source["sha256"], "Preflight/source differs")
        cases.append({"source_id": record["source_id"], "source": source, "source_sha256": source["sha256"],
                      "ground_truth": truth, "truth_rule": POLICY["truth_rule"], "deltas": record["deltas"],
                      "source_rgb_sha256": prechecked["rgb_sha256"]})
    require(Counter(tuple(c["ground_truth"][p] for p in PARTS) for c in cases) == GROUPS, "Four groups of six")
    cases.sort(key=lambda c: hashlib.sha256(("kitguard-loco24-v1|" + c["source_sha256"]).encode()).hexdigest())
    for index, case in enumerate(cases, 1):
        case["id"] = f"case-{index:03d}"
    return cases, bindings


def validate_selection_payload(selection):
    require(selection.get("schema") == "kitguard.v08.loco-combined-method-selection.v1"
            and selection.get("status") == "approved_for_freeze" and selection.get("approved_by") == "root_agent",
            "Explicit root method approval required; draft cannot freeze/run")
    choice = selection.get("identity_decision", {})
    require(choice.get("include") in (True, False) and type(choice.get("include")) is bool
            and isinstance(choice.get("reason"), str) and bool(choice["reason"].strip()), "Explicit include/exclude reason")
    require(choice.get("role") in ({"eligible_candidate", "failed_candidate_comparison"} if choice["include"] else {"excluded"}),
            "Identity arm role must be explicit")
    require(selection.get("methods") == ([G, I] if choice["include"] else [G]), "Methods differ from root choice")
    require(selection.get("no_loco24_model_results_used") is True, "Selection must precede LOCO inference")
    require(isinstance(selection.get("exposure_since_source_preflight"), list), "Explicit subsequent exposure disclosure required")
    return selection["methods"]


def method_selection(root, selection_path):
    selection = read(selection_path)
    methods = validate_selection_payload(selection)
    evidence = selection["identity51_evidence"]
    require(set(evidence) == {"run", "predictions", "independent_audit"}, "Completed identity51 evidence required even if excluded")
    for item in evidence.values():
        verify(root, item)
    require(evidence["run"]["path"] == f"{I_RUN}/run.json" and evidence["predictions"]["path"] == f"{I_RUN}/predictions.jsonl",
            "Wrong prior candidate experiment")
    run, audit = read(verify(root, evidence["run"])), read(verify(root, evidence["independent_audit"]))
    require(run["status"] == "completed" and run["completed_attempts"] == 51 and run["final_integrity_verified"]
            and not run["source_changed"] and run["freeze_sha256"] == I_SHA, "Identity51 must first complete intact")
    require(audit.get("schema") == "kitguard.v08.identity-reference-guarded.independent-audit.v1"
            and audit["status"] == "passed" and audit["completed_attempts"] == 51
            and audit["evidence_sha256"]["freeze"] == I_SHA
            and audit["evidence_sha256"]["run"] == evidence["run"]["sha256"]
            and audit["evidence_sha256"]["predictions"] == evidence["predictions"]["sha256"], "Independent audit binding differs")
    if I in methods:
        gate = audit["independent_results"]["development_gate_count_conditions_passed"]
        expected_role = "eligible_candidate" if gate else "failed_candidate_comparison"
        require(type(gate) is bool and selection["identity_decision"]["role"] == expected_role,
                "Integrity audit passed does not imply candidate quality gate passed")
    selected_at = datetime.fromisoformat(selection["selected_at_utc"])
    require(selected_at.utcoffset() is not None and selected_at >= datetime.fromisoformat(audit["checked_at"]),
            "Selection must occur after completed independent audit")
    for item in selection["exposure_since_source_preflight"]:
        verify(root, item)
    return selection, methods


def normal_regression(root, selection, methods):
    """All 16 historical normal sources; no model re-execution or time comparison."""
    A = legacy()
    bindings = [{"path": f"{A.BASE}/{n}", "sha256": h} for n, h in A.BASE_HASHES.items()]
    bindings.append({"path": A.AUDIT, "sha256": A.AUDIT_SHA})
    for item in bindings:
        verify(root, item)
    cases = [c for c in read(root / A.BASE / "manifest.json")["cases"] if c["subgroup"] == "loco_normal_222"]
    require(len(cases) == len({c["source_sha256"] for c in cases}) == 16, "Complete historical normal16 required")
    rows = [json.loads(line) for line in (root / A.BASE / "predictions.jsonl").read_text().splitlines()]
    indexed = {r["case_id"]: r for r in rows if r["mode"] == G}
    result = {G: [{"case": c, "row": indexed[c["id"]]} for c in cases]}
    if I in methods:
        evidence = selection["identity51_evidence"]
        rows = [json.loads(line) for line in verify(root, evidence["predictions"]).read_text().splitlines()]
        require(len(rows) == len({r["case_id"] for r in rows}) == 51, "Historical I denominator")
        indexed = {r["case_id"]: r for r in rows}
        result[I] = []
        for case in cases:
            row = indexed[case["id"]]
            require(row["mode"] == I and row["source_id"] == case["source_id"]
                    and row["sha256"] == case["sha256"] and row["ground_truth"] == case["ground_truth"], "Normal I source/truth mismatch")
            result[I].append({"case": case, "row": row})
        bindings.extend(evidence.values())
    return {"historical_exposed_nonconcurrent": True, "pooled_with_24": False, "planned_per_method": 16,
            "bindings": bindings, "records": result}


def schedule(cases, methods):
    require(methods in ([G], [G, I]), "Only approved G or G+I supported")
    result = []
    for index, case in enumerate(cases):
        order = methods if index % 2 == 0 else list(reversed(methods))
        for position, mode in enumerate(order, 1):
            result.append({"attempt": len(result) + 1, "case_id": case["id"], "mode": mode,
                           "within_case_position": position, "source_sha256": case["source_sha256"]})
    return result


def guarded_observer(model_path=None):
    """Original G prompts/logic/protocol; only an explicit raw-call recorder added."""
    from kitguard import vision
    from scripts.probe_selective_identity import SelectiveIdentityVision
    require(Path(vision.__file__).resolve() == ROOT / "kitguard/vision.py", "Wrong legacy observer")

    class Recorded(vision.LocalVision):
        artifact_dir = None

        def _observe_passes(self, image_path, references, context=None):
            require(not references and context is None, "Baseline G receives no references/context")
            return super()._observe_passes(image_path, {}, None)

        def _generate(self, system, prompt, images, schema, *, max_tokens=450):
            calls = self._observation_attempt.get("generation_calls", [])
            previous = len(calls)
            roles = [{"image": 1, "role": "inspection_target"}]
            if schema is vision.IdentityResponse:
                roles += [{"image": i, "role": "target_crop", "point_id": crop["id"]}
                          for i, crop in enumerate(self._observation_attempt["identity"]["crops"], 2)]
            actual = {"model_call_started": False, "model_call_completed": False}
            original_load = self._load

            def tracked_load():
                runtime = original_load()

                def generate(*args, **kwargs):
                    actual["model_call_started"] = True
                    call = self._observation_attempt["generation_calls"][-1]
                    call.update(actual)
                    write(self.artifact_dir / f"call-{previous + 1:02d}" / "generation.json", call)
                    response = runtime["generate"](*args, **kwargs)
                    actual["model_call_completed"] = True
                    return response
                return {**runtime, "generate": generate}

            self._load = tracked_load
            try:
                return SelectiveIdentityVision._generate(self, system, prompt, images, schema, max_tokens=max_tokens)
            finally:
                self._load = original_load
                calls = self._observation_attempt.get("generation_calls", [])
                if len(calls) == previous + 1:
                    calls[-1].update(**actual, input_roles=roles,
                                     json_schema_sha256=hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest())
                    write(self.artifact_dir / f"call-{len(calls):02d}" / "generation.json", calls[-1])
    return Recorded(model_path, observation_mode=G, image_max_side=1536)


def methods_identity(frozen, methods):
    A = legacy()
    engines = {mode: (guarded_observer if mode == G else A.observer)(Path(frozen["model"]["status"]["path"])) for mode in methods}
    historical = read(Path(frozen["project_root"]) / A.BASE / "freeze.json")["model_identity"][G]
    table = []
    for mode, engine in engines.items():
        status = engine.status()
        expected = historical if mode == G else frozen["model"]["status"]
        require(all(status[k] == expected[k] for k in A.IDENTITY_KEYS), "Observer/model/protocol identity changed")
        require(status["available"], "Model unavailable")
        table.append({"mode": mode, **{k: status[k] for k in A.IDENTITY_KEYS},
                      "source_freeze": {"path": I_FREEZE, "sha256": I_SHA},
                      "references_in_identity_only": mode == I})
    return engines, table


def preflight(root, selection_path, output):
    require(sys.flags.isolated and "KITGUARD_DATA_DIR" in os.environ, "Isolated preflight with runtime data required")
    A = legacy()
    cases, bindings = source_cases(root)
    selection, methods = method_selection(root, selection_path)
    frozen = read(root / I_FREEZE)
    engines, table = methods_identity(frozen, methods)
    require(all(not e.status()["loaded"] for e in engines.values()), "No warm model in preflight")
    A.verify_model(frozen["model"], full=True)
    require(A.versions() == frozen["versions"], "Pinned runtime versions changed")
    from PIL import Image

    from kitguard.vision import _prepare_image
    from scripts.run_benchmark import app_upload_bytes
    destination = output.with_suffix(".normalized_inputs")
    require(not destination.exists(), "Preflight inputs cannot be overwritten")
    destination.mkdir(parents=True)
    refs = frozen["references"]
    # Reference candidates are fixed irrespective of arm selection; never screen them on results.
    reference_bytes, reference_rgb = set(), set()
    for item in refs.values():
        for key in ("source", "crop"):
            path = verify(root, item[key])
            reference_bytes.add(sha(path))
            with Image.open(path) as image:
                reference_rgb.add(A.pixel_sha(image))
        reference_bytes.add(item["prepared_sha256"])
    input_records, normalized_seen, rgb_seen = [], set(), set()
    preprocessing_started = time.perf_counter()
    for case in cases:
        source = verify(root, case["source"])
        with Image.open(source) as image:
            require(A.pixel_sha(image) == case["source_rgb_sha256"], "Original source pixels changed")
        normalized = destination / f"{case['id']}.jpg"
        normalized.write_bytes(app_upload_bytes(source))
        prepared = destination / f"{case['id']}.png"
        _prepare_image(normalized, prepared, 1536)
        with Image.open(normalized) as image:
            rgb, size = A.pixel_sha(image), list(image.size)
        with Image.open(prepared) as image:
            target_rgb, target_size = A.pixel_sha(image), list(image.size)
        require(sha(normalized) not in reference_bytes and sha(prepared) not in reference_bytes
                and rgb not in reference_rgb and target_rgb not in reference_rgb, "Normalized target/reference exact collision; stop without replacement")
        require(sha(normalized) not in normalized_seen and rgb not in rgb_seen, "Normalized candidates collide; retain denominator and stop")
        normalized_seen.add(sha(normalized))
        rgb_seen.add(rgb)
        input_records.append({"case_id": case["id"], "normalized": ref(root, normalized), "prepared": ref(root, prepared),
                              "normalized_rgb_sha256": rgb, "normalized_size": size,
                              "target_rgb_sha256": target_rgb, "target_size": target_size})
    result = {"schema": "kitguard.v08.loco-combined.preflight.v1", "status": "passed", "created_at": datetime.now(UTC).isoformat(),
              "project_root": str(root), "runtime_source_root": str(ROOT), "source_hashes": inventory(ROOT),
              "policy": POLICY, "bindings": bindings, "selection": ref(root, selection_path), "selection_payload": selection,
              "cases": cases, "inputs": input_records, "methods": table, "schedule": schedule(cases, methods),
              "references": refs, "model": frozen["model"], "versions": frozen["versions"],
              "historical_normal16": normal_regression(root, selection, methods),
              "preprocessing_seconds": time.perf_counter() - preprocessing_started,
              "images_displayed": False, "machine_pixels_decoded": True, "model_called": False,
              "mlx_imported": any(n == "mlx" or n.startswith("mlx.") for n in sys.modules)}
    require(not result["mlx_imported"], "Preflight must not import MLX")
    return result


def verify_inputs(root, cases, inputs, references):
    """Future freeze/run machine check, never invoked by metadata/synthetic tests.

    Reconstructing upload bytes is integrity verification, outside timed observations.
    One persisted normalized copy remains shared by both actual methods.
    """
    from PIL import Image

    from kitguard.vision import _prepare_image
    from scripts.run_benchmark import app_upload_bytes
    A = legacy()
    excluded_sha, excluded_rgb = set(), set()
    for item in references.values():
        for role in ("source", "crop"):
            path = verify(root, item[role])
            excluded_sha.add(sha(path))
            with Image.open(path) as image:
                excluded_rgb.add(A.pixel_sha(image))
        excluded_sha.add(item["prepared_sha256"])
    seen_sha, seen_rgb = set(), set()
    for case, item in zip(cases, inputs, strict=True):
        source = verify(root, case["source"])
        normalized, prepared = verify(root, item["normalized"]), verify(root, item["prepared"])
        with Image.open(source) as image:
            require(A.pixel_sha(image) == case["source_rgb_sha256"], "Source RGB identity changed")
        require(hashlib.sha256(app_upload_bytes(source)).hexdigest() == item["normalized"]["sha256"],
                "Recorded normalized input differs from frozen upload pipeline")
        with tempfile.TemporaryDirectory(prefix="loco-input-check-") as temporary:
            target = Path(temporary) / "target.png"
            _prepare_image(normalized, target, 1536)
            require(sha(target) == item["prepared"]["sha256"], "Prepared model input differs")
        with Image.open(normalized) as image:
            rgb, size = A.pixel_sha(image), list(image.size)
        with Image.open(prepared) as image:
            target_rgb, target_size = A.pixel_sha(image), list(image.size)
        require((rgb, size, target_rgb, target_size) ==
                (item["normalized_rgb_sha256"], item["normalized_size"], item["target_rgb_sha256"], item["target_size"]),
                "Normalized/prepared pixel metadata differs")
        require(sha(normalized) not in excluded_sha and sha(prepared) not in excluded_sha
                and rgb not in excluded_rgb and target_rgb not in excluded_rgb,
                "Prepared target/reference exact collision")
        require(sha(normalized) not in seen_sha and rgb not in seen_rgb, "Prepared target duplicate")
        seen_sha.add(sha(normalized))
        seen_rgb.add(rgb)


def verify_receipt(receipt, source_root):
    require(receipt["schema"] in {"kitguard.v08.loco-combined.preflight.v1", "kitguard.v08.loco-combined.freeze.v1"}
            and receipt["status"] == "passed" and receipt["policy"] == POLICY and receipt["model_called"] is False
            and receipt["mlx_imported"] is False, "Preflight/freeze protocol changed")
    require(inventory(source_root) == receipt["source_hashes"], "Source snapshot changed")
    root = Path(receipt["project_root"])
    cases, bindings = source_cases(root)
    selection, modes = method_selection(root, verify(root, receipt["selection"]))
    require(receipt["cases"] == cases and receipt["bindings"] == bindings and receipt["selection_payload"] == selection,
            "Case/truth/source/selection fields differ from authoritative records")
    original = read(root / I_FREEZE)
    provenance = read(source_root / "loco_source_provenance.json")
    require(provenance == {"source_freeze": {"path": I_FREEZE, "sha256": I_SHA},
                           "source_hashes": original["source_hashes"],
                           "unused_identity_adapter_may_be_present_in_G_only_bundle": True},
            "Legacy source provenance changed")
    require(set(receipt["source_hashes"]) == set(original["source_hashes"]) | {ENTRY, PLAN, SCORER, "loco_source_provenance.json"}
            and all(receipt["source_hashes"][name] == expected for name, expected in original["source_hashes"].items())
            and receipt["source_hashes"][SCORER] == SCORER_SHA,
            "Base observer/adapter/scorer bytes must remain the immutable original versions")
    require(receipt["model"] == original["model"] and receipt["references"] == original["references"]
            and receipt["versions"] == original["versions"], "Model/reference/runtime differs from pinned identity source")
    require(receipt["schedule"] == schedule(cases, modes), "Schedule differs from explicit approved methods")
    require(receipt["historical_normal16"] == normal_regression(root, selection, modes), "Historical normal binding differs")
    _, table = methods_identity(original, modes)
    require(receipt["methods"] == table, "Method/protocol table changed")
    require(len(receipt["inputs"]) == 24 and [i["case_id"] for i in receipt["inputs"]] == [c["id"] for c in cases], "Input population/order changed")
    verify_inputs(root, cases, receipt["inputs"], receipt["references"])
    A = legacy()
    require(A.versions() == receipt["versions"], "Runtime versions changed")
    A.verify_model(receipt["model"], full=True)
    return root


def create_freeze(receipt_path, output):
    require(not output.exists(), "Do not overwrite freeze")
    receipt = read(receipt_path)
    require(receipt["schema"] == "kitguard.v08.loco-combined.preflight.v1", "Preflight receipt required")
    root = verify_receipt(receipt, ROOT)
    output.mkdir(parents=True)
    snapshot = output / "source_snapshot"
    for name, expected in receipt["source_hashes"].items():
        target = inside(snapshot, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(ROOT, name), target)
        require(sha(target) == expected, "Source snapshot copy mismatch")
    frozen = {**receipt, "schema": "kitguard.v08.loco-combined.freeze.v1", "frozen_at": datetime.now(UTC).isoformat(),
              "preflight_receipt": ref(root, receipt_path), "runtime_source_root": str(snapshot)}
    # The final truth is an additive frozen artifact, never a rewrite of author manifest.
    write(output / "manifest.json", {"schema": "kitguard.v08.loco-combined.manifest.v1", "truth_rule": POLICY["truth_rule"], "cases": receipt["cases"]})
    frozen["manifest_sha256"] = sha(output / "manifest.json")
    for item in frozen["inputs"]:
        for key, suffix in (("normalized", ".jpg"), ("prepared", ".png")):
            target = output / "normalized_inputs" / (item["case_id"] + suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(verify(root, item[key]), target)
            item[key] = ref(root, target)
    write(output / "freeze.json", frozen)
    return frozen


def stage_contract(mode, diagnostics, expected_sha, artifact_dir, references, completed):
    A = legacy()
    if mode == I:
        result = A.check_reference_stages(diagnostics, references, artifact_dir, completed)
        return {**result, **A.check_target_stages(diagnostics, expected_sha, artifact_dir, references)}
    from PIL import Image

    from kitguard import vision
    calls = (diagnostics or {}).get("generation_calls", [])
    require(len(calls) <= 3, "No retries/additional stages")
    rotation = None
    if calls:
        require(calls[0]["images"][0]["sha256"] == expected_sha, "Wrong original target")
        with Image.open(inside(artifact_dir, calls[0]["images"][0]["path"])) as image:
            buffer = io.BytesIO()
            image.transpose(Image.Transpose.ROTATE_90).save(buffer, format="PNG")
            rotation = hashlib.sha256(buffer.getvalue()).hexdigest()
    for index, call in enumerate(calls):
        for image in call["images"]:
            verify(artifact_dir, image)
        if index < 2:
            schema, system, prompt, tokens = vision.SpatialInventory, vision.SPATIAL_SYSTEM, vision.SPATIAL_USER, 900
            hashes = [expected_sha if index == 0 else rotation]
            roles = [{"image": 1, "role": "inspection_target"}]
        else:
            crops = diagnostics["identity"]["crops"]
            schema, system, prompt, tokens = vision.IdentityResponse, vision.IDENTITY_SYSTEM, vision.build_prompt(crops), 1800
            hashes = [expected_sha, *[c["crop_sha256"] for c in crops]]
            roles = [{"image": 1, "role": "inspection_target"}] + [
                {"image": i, "role": "target_crop", "point_id": c["id"]} for i, c in enumerate(crops, 2)]
        require(call["schema"] == schema.__name__ and call["system"] == system and call["prompt"] == prompt
                and call["max_tokens"] == tokens and call["temperature"] == 0
                and [v["sha256"] for v in call["images"]] == hashes and call["input_roles"] == roles,
                "G must preserve original prompt/target/crop and have no references")
        require(call["json_schema_sha256"] == hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest(), "Wrong complete JSON schema")
        start, end = call.get("model_call_started"), call.get("model_call_completed")
        require(type(start) is bool and type(end) is bool and (not end or start)
                and (call["status"] != "parsed" or end), "Invalid actual model-call flags")
    if completed:
        require(len(calls) >= 2 and all(c["status"] == "parsed" for c in calls), "Incomplete successful G")
        state = diagnostics["identity"]["status"]
        require((len(calls) == 3 and state in {"blocked", "confirmed_candidates"})
                or (len(calls) == 2 and state in {"skipped_base_unclear", "skipped_no_candidates"}), "G identity stage mismatch")
    return {"passed": True, "generation_attempt_records": len(calls), "no_reference_inputs": True}


def validate_observation(value):
    from kitguard.schemas import Observation
    return Observation.model_validate(value).model_dump(mode="json")


def materialize_rows(cases, methods):
    return [{**s, "state": "not_attempted", "observation": None, "error": None,
             "latency_ms": None, "observation_diagnostics": None} for s in schedule(cases, methods)]


def latency(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "p50_ms": None, "p90_ms": None, "total_ms": 0}
    def percentile(q):
        point = (len(values) - 1) * q
        lower, upper = math.floor(point), math.ceil(point)
        return values[lower] + (values[upper] - values[lower]) * (point - lower)
    return {"n": len(values), "p50_ms": percentile(.5), "p90_ms": percentile(.9), "total_ms": sum(values), "max_ms": max(values)}


def analyze(cases, records, methods, freeze_sha, historical):
    from scripts.v08 import score_loco_combined as score
    require(sha(Path(score.__file__)) == SCORER_SHA, "Frozen scoring helper changed")
    expected = schedule(cases, methods)
    require(len(records) == len(expected), "Materialized full denominator required")
    for row, planned in zip(records, expected, strict=True):
        require(all(row[k] == v for k, v in planned.items()), "Duplicate/unplanned/reordered result")
    reports = {mode: score.summarize(cases, [r for r in records if r["mode"] == mode]) for mode in methods}
    paired = []
    if I in methods:
        by_mode = {m: {r["case_id"]: r for r in reports[m]["cases"]} for m in methods}
        paired = [{"case_id": c["id"], "G": by_mode[G][c["id"]]["outcome"], "I": by_mode[I][c["id"]]["outcome"],
                   "truth": c["ground_truth"]} for c in cases]
    historical_results = {}
    for mode, items in historical["records"].items():
        scores = []
        for item in items:
            c, r = item["case"], item["row"]
            scores.append(score.score_case(c, {"case_id": c["id"], "source_sha256": c["source_sha256"],
                "state": "error" if r.get("error") else "completed", "error": r.get("error"), "observation": r["observation"]}))
        historical_results[mode] = {"planned": 16, "outcomes": {k: sum(r["outcome"] == k for r in scores) for k in "CWUEN"}, "cases": scores}
    calls = [c for row in records for c in (row.get("observation_diagnostics") or {}).get("generation_calls", [])]
    return {"schema": "kitguard.v08.loco-combined.analysis.v1", "freeze_sha256": freeze_sha, "protocol_frozen": True,
            "scorer_sha256": SCORER_SHA, "embedded_scorer_metadata_is_unchanged_draft_API": True,
            "planned_cases": 24, "planned_observations": len(expected), "methods": reports,
            "paired_changes": paired, "paired_transitions": dict(Counter(f"{r['G']}->{r['I']}" for r in paired)),
            "analytical_comparators_not_model_calls": {c: score.summarize(cases, score.comparator_rows(cases, c)) for c in ("constant_normal", "always_abstain")},
            "historical_normal16": {"exposed_nonconcurrent_not_pooled": True, "methods": historical_results},
            "timing": {m: {"all_attempted": latency([r["latency_ms"] for r in records if r["mode"] == m and r["state"] != "not_attempted"]),
                           "warm_subset": latency([r["latency_ms"] for r in records if r["mode"] == m and r.get("loaded_before") and r["state"] != "not_attempted"])} for m in methods},
            "generation_attempt_records": len(calls), "model_calls_started": sum(c.get("model_call_started") is True for c in calls),
            "model_calls_completed": sum(c.get("model_call_completed") is True for c in calls),
            "automatic_promotion": False, "independent_audit_required": True,
            "no_general_counting_or_real_world_safety_claim": True}


def run(freeze_path, output):
    require(sys.flags.isolated and ROOT == freeze_path.parent / "source_snapshot", "Use isolated frozen runtime")
    require(not output.exists(), "Run output cannot be overwritten or resumed")
    output.mkdir(parents=True)
    os.environ["KITGUARD_DATA_DIR"] = str(output / "runtime-app-data")
    started_setup = time.perf_counter()
    frozen = read(freeze_path)
    require(frozen["schema"] == "kitguard.v08.loco-combined.freeze.v1", "Freeze required")
    root = verify_receipt(frozen, ROOT)
    require(sha(freeze_path.parent / "manifest.json") == frozen["manifest_sha256"], "Frozen manifest changed")
    modes = [m["mode"] for m in frozen["methods"]]
    engines, _ = methods_identity(read(root / I_FREEZE), modes)
    require(all(not e.status()["loaded"] for e in engines.values()), "First attempt must begin cold")
    for name in ("freeze.json", "manifest.json"):
        shutil.copy2(freeze_path.parent / name, output / name)
    rows = materialize_rows(frozen["cases"], modes)
    inputs = {i["case_id"]: i for i in frozen["inputs"]}
    metadata = {"schema": "kitguard.v08.loco-combined.run.v1", "status": "running", "started_at": datetime.now(UTC).isoformat(),
                "planned": len(rows), "completed_attempts": 0, "freeze_sha256": sha(freeze_path), "model_called_in_setup": False,
                "runtime_source_root": str(ROOT), "runtime_app_data": os.environ["KITGUARD_DATA_DIR"],
                "shared_model_runtime": True, "no_warmup": True, "isolated_python": True,
                "setup_seconds": time.perf_counter() - started_setup, "automatic_promotion": False}
    write(output / "predictions.json", rows)
    write(output / "run.json", metadata)
    A = legacy()
    try:
        for row in rows:
            require(inventory(ROOT) == frozen["source_hashes"], "Frozen source changed")
            A.verify_model(frozen["model"])
            item, engine = inputs[row["case_id"]], engines[row["mode"]]
            references = {part: verify(root, r["crop"]) for part, r in frozen["references"].items()} if row["mode"] == I else {}
            artifact_dir = output / "cases" / f"{row['attempt']:03d}-{row['case_id']}-{row['mode']}"
            engine.artifact_dir = artifact_dir
            row["loaded_before"] = engine.status()["loaded"]
            row["observer_status_before"] = engine.status()
            started = time.perf_counter()
            observed = diagnostics = contract = pending_interrupt = None
            observation_started = False
            try:
                path = output / "normalized_inputs" / (row["case_id"] + ".jpg")
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    shutil.copy2(verify(root, item["normalized"]), path)
                require(sha(path) == item["normalized"]["sha256"], "Both methods must use identical normalized bytes")
                row["normalized_sha256"] = sha(path)
                observation_started = True
                observed = engine.observe(path, dict.fromkeys(PARTS, 1), references)
                diagnostics = engine.status().get("last_observation_attempt")
                require(diagnostics["source_sha256"] == row["normalized_sha256"], "Wrong diagnostic source")
                try:
                    contract = stage_contract(row["mode"], diagnostics, item["prepared"]["sha256"], artifact_dir, frozen["references"], True)
                except Exception as integrity_error:
                    contract = {"passed": False, "error": f"{type(integrity_error).__name__}: {integrity_error}",
                                "successful_observation_stage_contract_failed": True}
                    raise
                row["observation"] = validate_observation(observed)
                row["state"] = "completed"
            except BaseException as exc:  # noqa: BLE001 -- preserve interruption, then re-raise
                if not isinstance(exc, Exception):
                    pending_interrupt = exc
                row.update(state="error", error=f"{type(exc).__name__}: {exc}", observation=None,
                           raw_observation_before_full_validation=observed)
                diagnostics = getattr(exc, "observation_diagnostics", diagnostics)
                if diagnostics is None and observation_started:
                    diagnostics = engine.status().get("last_observation_attempt")
                try:
                    if not (contract or {}).get("successful_observation_stage_contract_failed"):
                        contract = stage_contract(row["mode"], diagnostics, item["prepared"]["sha256"], artifact_dir, frozen["references"], False)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    contract = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
            row.update(latency_ms=round((time.perf_counter() - started) * 1000), observation_diagnostics=diagnostics,
                       stage_contract=contract, observation_attempted=observation_started,
                       observer_status_after=engine.status())
            metadata["completed_attempts"] += 1
            write(output / "predictions.json", rows)
            write(output / "run.json", metadata)
            print(json.dumps({"completed": metadata["completed_attempts"], "planned": len(rows), "mode": row["mode"], "error": row["error"]}), flush=True)
            if pending_interrupt is not None:
                raise pending_interrupt
        metadata["status"] = "completed"
    except BaseException as exc:
        metadata.update(status="interrupted", interruption=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        metadata["observations_finished_at"] = datetime.now(UTC).isoformat()
        final_started = time.perf_counter()
        metadata["source_changed"] = inventory(ROOT) != frozen["source_hashes"]
        write(output / "predictions.json", rows)
        try:
            verify_receipt(frozen, ROOT)
            require(sha(freeze_path) == metadata["freeze_sha256"], "Freeze changed during run")
            require(not any((r.get("stage_contract") or {}).get("passed") is False for r in rows),
                    "Actual input/prompt/schema/call-stage contract failed")
            metadata["final_integrity_verified"] = True
        except (ValueError, OSError, KeyError) as exc:
            metadata.update(status="failed_integrity", final_integrity_verified=False, integrity_error=str(exc))
        result = analyze(frozen["cases"], rows, modes, metadata["freeze_sha256"], frozen["historical_normal16"])
        write(output / "analysis.json", result)
        metadata.update(predictions_sha256=sha(output / "predictions.json"), analysis_sha256=sha(output / "analysis.json"),
                        final_verification_and_analysis_seconds=time.perf_counter()-final_started, finished_at=datetime.now(UTC).isoformat())
        write(output / "run.json", metadata)
    return metadata


def dispatch(stage, arguments):
    command = [sys.executable, "-I", "-c",
               "import sys;sys.path.insert(0,sys.argv.pop(1));from scripts.v08.run_loco_combined import main;main()",
               str(stage), *arguments, "--isolated-runtime"]
    return subprocess.call(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "freeze", "run"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isolated-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root, output = args.project_root.resolve(), args.output.resolve()
    require(not output.exists(), "Output exists; preserve prior evidence")
    if not args.isolated_runtime:
        if args.command == "preflight":
            require(args.selection is not None, "--selection required")
            stage = output.with_suffix(".source_snapshot")
            prepare_sources(root, stage)
            extra = ["--project-root", str(root), "--selection", str(args.selection.resolve())]
        elif args.command == "freeze":
            require(args.preflight is not None, "--preflight required")
            stage = Path(read(args.preflight)["runtime_source_root"])
            extra = ["--preflight", str(args.preflight.resolve())]
        else:
            require(args.freeze is not None, "--freeze required")
            stage = args.freeze.resolve().parent / "source_snapshot"
            extra = ["--freeze", str(args.freeze.resolve())]
        raise SystemExit(dispatch(stage, [args.command, *extra, "--output", str(output)]))
    require(sys.flags.isolated, "Isolated Python required")
    os.environ["KITGUARD_DATA_DIR"] = str(output.with_suffix(".runtime-app-data") if args.command != "run" else output / "runtime-app-data")
    if args.command == "preflight":
        write(output, preflight(root, args.selection.resolve(), output))
    elif args.command == "freeze":
        create_freeze(args.preflight.resolve(), output)
    else:
        result = run(args.freeze.resolve(), output)
        if result["status"] != "completed":
            raise SystemExit(1)
    print(json.dumps({"status": "completed", "operation": args.command, "output": str(output)}))


if __name__ == "__main__":
    main()
