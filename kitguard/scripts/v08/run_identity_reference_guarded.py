"""Freeze/run one identity-only reference guarded observation on each exposed source.

Preflight only reads bytes/pixels and LocalVision.status; no MLX import/model load.
Run dispatches isolated Python into the frozen snapshot. Never modifies production.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = "docs/v0.8/IDENTITY_REFERENCE_GUARDED_PLAN.md"
APPROVAL = "datasets/derived/v0.8/class_reference_dev_v1/approved_references.json"
APPROVAL_SHA = "9eded7727cf624d812b3b4ed03598c7d82afe93bd6a9a630935afa3d318961fe"
BASE = "evaluation-runs/v0.7/public_paired_v1"
BASE_HASHES = {
    "run.json": "98d26a66c384466fc85f2e6c3f9c2266d2be89b8a2a3d3ad034da6fae2789661",
    "manifest.json": "efe4633e873d45032101a26e035c23d267bafa6605d147d3d2f7fcb51b697643",
    "freeze.json": "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7",
    "predictions.jsonl": "9b525702cb2665274c37a7d7740c1d93c05562ab5fb5a17e171e31b75a6859ee",
}
AUDIT = "test-results/v0.7/public-paired-audit-v1.json"
AUDIT_SHA = "94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9"
MODE = "spatial_guarded_identity_references_v1"
PARTS = ("bolt", "nut", "washer", "bracket")
REF_PARTS = ("nut", "washer")
BASE_SOURCE_FREEZE = "docs/v0.7/public_paired_freeze_v1/freeze.json"
BASE_SOURCE_SHA = "cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7"
ENTRY = "scripts/v08/run_identity_reference_guarded.py"
PREPARED_REFS = {
    "nut": "097a0da4cdd05c725cab6f2e871cfb4f55e153d0125d25d548c4534969ce5137",
    "washer": "845922352509f55cfe294ec2f2ec2a4218d251a140f302323dfc08c146a76d88",
}
IDENTITY_KEYS = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
POLICY = {"cases": 51, "mode": MODE, "observer": "spatial_guarded", "image_max_side": 1536,
          "spatial_reference_parts": [], "reference_max_side": 512, "identity_reference_parts": list(REF_PARTS),
          "identity_references": True, "count_change_policy": "existing unknown-only identity veto",
          "spatial_max_tokens": 900, "identity_max_tokens": 1800, "temperature": 0,
          "retries": 0, "warmup": False, "concurrency": 1, "new_holdout": False,
          "historical_baseline_only": True, "concurrent_latency_comparison": False, "automatic_promotion": False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def inside(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts,
            "Unsafe evidence path")
    result = (root / relative).resolve()
    require(result.is_relative_to(root.resolve()), "Evidence escapes project")
    return result


def reference(root, path):
    return {"path": Path(path).resolve().relative_to(root.resolve()).as_posix(), "sha256": sha(path)}


def case_source_ref(case):
    return {"path": "datasets/" + case.get("source_image", case["image"]), "sha256": case["source_sha256"]}


def verify(root, ref):
    path = inside(root, ref["path"])
    require(sha(path) == ref["sha256"], f"Changed evidence: {ref['path']}")
    return path


def versions():
    return {"python": platform.python_version(), **{p: importlib.metadata.version(p)
            for p in ("mlx", "mlx-vlm", "transformers", "pydantic", "pillow", "fastapi", "httpx")}}


def sources(root):
    require((root / "base_source_manifest.json").is_file(), "Isolated v0.7 source bundle required")
    files = [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return {str(p.relative_to(root)): sha(p) for p in sorted(files)}


def prepare_sources(root, destination):
    """Copy only manifest-listed legacy files; never copy its incidental SQLite DB."""
    require(not destination.exists(), "Source staging destination already exists")
    freeze = inside(root, BASE_SOURCE_FREEZE)
    require(sha(freeze) == BASE_SOURCE_SHA, "Original v0.7 source freeze changed")
    frozen = read(freeze)
    snapshot = freeze.parent / "source_snapshot"
    for relative, expected in frozen["source_hashes"].items():
        require(sha(inside(snapshot, relative)) == expected, "Original frozen source changed")
    destination.mkdir(parents=True)
    for relative, expected in frozen["source_hashes"].items():
        output = inside(destination, relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(snapshot, relative), output)
        require(sha(output) == expected, "Base source copy differs")
    for relative in (ENTRY, PLAN):
        output = inside(destination, relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(root, relative), output)
    write(destination / "base_source_manifest.json", {
        "freeze": {"path": BASE_SOURCE_FREEZE, "sha256": BASE_SOURCE_SHA},
        "source_hashes": frozen["source_hashes"], "model_called": False,
    })
    return sources(destination)


def observer(model_path=None):
    require((ROOT / "base_source_manifest.json").is_file(), "Observer requires prepared legacy source bundle")
    from kitguard import vision
    from kitguard.vision import LocalVision
    from scripts.probe_selective_identity import SelectiveIdentityVision
    require(Path(vision.__file__).resolve() == ROOT / "kitguard/vision.py",
            "Do not import workspace production observer into this experiment")

    class RecordedGuarded(LocalVision):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.base_protocol_sha256 = self.protocol_sha256
            self.protocol_sources = {**self.protocol_sources, ENTRY: sha(Path(__file__))}
            self.protocol_sha256 = hashlib.sha256(json.dumps({
                "base": self.base_protocol_sha256, "sources": self.protocol_sources,
                "policy": POLICY,
            }, sort_keys=True).encode()).hexdigest()
            self.artifact_dir = None
            self._identity_reference_paths = {}

        def status(self):
            return {**super().status(), "observation_mode": MODE,
                    "base_observation_mode": "spatial_guarded",
                    "base_observer_protocol_sha256": self.base_protocol_sha256,
                    "identity_references": True, "production_selected": False}

        def _observe_passes(self, image_path, references, context=None):
            require(set(references) == set(REF_PARTS) and context is None,
                    "Exactly fixed nut/washer references and no previous context required")
            self._identity_reference_paths = dict(references)
            self._observation_attempt.update(
                experimental_mode=MODE, experiment_protocol_sha256=self.protocol_sha256,
                experimental_reference_inputs={"spatial_reference_indices": [],
                                               "identity_reference_indices": [],
                                               "identity_generation_status": "not_called"})
            try:
                return super()._observe_passes(image_path, {}, None)
            finally:
                self._observation_attempt["experimental_reference_inputs"]["identity_stage_status"] = (
                    self._observation_attempt.get("identity", {}).get("status", "not_reached"))

        def _generate(self, system, prompt, images, schema, *, max_tokens=450):
            roles = [{"image": 1, "role": "inspection_target"}]
            with tempfile.TemporaryDirectory(prefix="identity-reference-") as temporary:
                if schema is vision.IdentityResponse:
                    require(max_tokens == 1800 and system == vision.IDENTITY_SYSTEM,
                            "Identity base system/schema/budget differs")
                    crops = self._observation_attempt["identity"]["crops"]
                    require(len(images) == 1 + len(crops), "Identity target/crop prefix differs")
                    roles += [{"image": i, "role": "target_crop", "point_id": c["id"]}
                              for i, c in enumerate(crops, 2)]
                    system, prompt = identity_messages(system, prompt, len(images))
                    images = list(images)
                    for part in REF_PARTS:
                        path = Path(temporary) / f"reference-{part}.png"
                        vision._prepare_image(self._identity_reference_paths[part], path, 512)
                        images.append(str(path))
                        roles.append({"image": len(images), "role": "category_reference",
                                      "part": part, "counted": False})
                    self._observation_attempt["experimental_reference_inputs"].update(
                        identity_generation_status="started", identity_reference_indices=[len(images)-1, len(images)])
                else:
                    require(schema is vision.SpatialInventory and len(images) == 1
                            and system == vision.SPATIAL_SYSTEM and prompt == vision.SPATIAL_USER
                            and max_tokens == 900, "Spatial observation must equal original reference-free G")
                previous = len(self._observation_attempt.get("generation_calls", []))
                actual = {"model_call_started": False, "model_call_completed": False}
                original_load = self._load

                def tracked_load():
                    runtime = original_load()

                    def tracked_generate(*args, **kwargs):
                        actual["model_call_started"] = True
                        call = self._observation_attempt["generation_calls"][-1]
                        call.update(actual)
                        write(self.artifact_dir / f"call-{previous+1:02d}" / "generation.json", call)
                        result = runtime["generate"](*args, **kwargs)
                        actual["model_call_completed"] = True
                        return result

                    return {**runtime, "generate": tracked_generate}

                self._load = tracked_load
                try:
                    return SelectiveIdentityVision._generate(
                        self, system, prompt, images, schema, max_tokens=max_tokens)
                finally:
                    self._load = original_load
                    calls = self._observation_attempt.get("generation_calls", [])
                    if len(calls) == previous + 1:
                        call = calls[-1]
                        call.update(**actual, input_roles=roles, experiment_protocol_sha256=self.protocol_sha256,
                                    json_schema_sha256=hashlib.sha256(json.dumps(
                                        schema.model_json_schema(), sort_keys=True).encode()).hexdigest())
                        write(self.artifact_dir / f"call-{len(calls):02d}" / "generation.json", call)
                        if schema is vision.IdentityResponse:
                            self._observation_attempt["experimental_reference_inputs"]["identity_generation_status"] = call["status"]
    return RecordedGuarded(model_path, observation_mode="spatial_guarded", image_max_side=1536)


def identity_messages(system, point_prompt, prefix_count):
    """Only describe image roles; preserve every category/uncertainty instruction."""
    original = "Image 1 is the full photograph. Each later image is an unmarked crop of the same photograph."
    require(system.count(original) == 1 and prefix_count >= 2, "Unexpected identity prompt contract")
    roles = (f"Image 1 is the full inspection photograph. Images 2 through {prefix_count} are unmarked "
             "crops of that same photograph. "
             f"Images {prefix_count + 1} and {prefix_count + 2} are category reference examples only. "
             "Never classify or count an object in a reference as an inspection target.")
    prompt = (point_prompt + f"\nImage {prefix_count + 1}: reference for nut; do NOT count it"
              + f"\nImage {prefix_count + 2}: reference for washer; do NOT count it"
              + "\nReturn only the supplied point IDs; reference images create no additional IDs.")
    return system.replace(original, roles), prompt
def model_receipt(model_path, status):
    manifest_path = model_path.parent / (model_path.name + ".manifest.json")
    manifest = read(manifest_path)
    require(manifest["repo_id"] == status["repo_id"] == "mlx-community/Qwen3.6-27B-4bit", "27B model required")
    require(manifest["revision"] == status["revision"] == "c000ac2c2057d94be3fa931000c31723aac53282", "Model revision")
    files = []
    for item in manifest["files"]:
        path = model_path / item["path"]
        require(path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], f"Model file differs: {path.name}")
        stat = path.stat()
        files.append({"path": str(path.resolve()), "sha256": item["sha256"], "bytes": stat.st_size,
                      "mtime_ns": stat.st_mtime_ns, "inode": stat.st_ino})
    return {"manifest_path": str(manifest_path), "manifest_sha256": sha(manifest_path), "files": files,
            "weight_payloads_rehashed": True, "status": status}


def verify_model(receipt, full=False):
    require(sha(receipt["manifest_path"]) == receipt["manifest_sha256"], "Model manifest changed")
    for item in receipt["files"]:
        stat = Path(item["path"]).stat()
        require(stat.st_size == item["bytes"] and stat.st_mtime_ns == item["mtime_ns"] and stat.st_ino == item["inode"],
                "Model file identity changed")
        if full:
            require(sha(item["path"]) == item["sha256"], "Model content changed")


def pixel_sha(image):
    return hashlib.sha256(str(image.size).encode() + b"|RGB|" + image.convert("RGB").tobytes()).hexdigest()


def validate_approval(approval):
    require(approval.get("schema") == "kitguard.v08.class-references-approved.v1"
            and approval.get("status") == "approved_for_development_inference", "Missing approved references")
    require(approval.get("selected_without_candidate_predictions") is True
            and approval.get("no_count_or_order_overlays") is True, "Reference selection/content approval missing")
    require(len(approval["items"]) == 2 and {i["part"] for i in approval["items"]} == set(REF_PARTS), "Exactly nut/washer refs")
    for item in approval["items"]:
        require(item["single_object_ai_reviewed"] is True and item["label_basis"] and item["notes"], "Reference QA missing")
        require(len(item["crop_xyxy"]) == 4 and all(type(x) is int for x in item["crop_xyxy"]), "Crop must be original pixels")


def reference_receipts(root, approval_path, cases):
    from PIL import Image

    from kitguard.vision import _prepare_image
    approval = read(approval_path)
    validate_approval(approval)
    source_hashes = {c["source_sha256"] for c in cases}
    source_paths = {inside(root / "datasets", c.get("source_image", c["image"])) for c in cases}
    source_pixels = {c["source_decoded_rgb_sha256"] for c in cases}
    case_bytes = {c["sha256"] for c in cases}
    references = {}
    for item in approval["items"]:
        source, crop = inside(root, item["source"]), inside(root, item["crop"])
        require(sha(source) == item["source_sha256"] and sha(crop) == item["crop_sha256"], "Reference file hash")
        require(source not in source_paths and item["source_sha256"] not in source_hashes
                and item["crop_sha256"] not in case_bytes, "Reference source overlaps evaluation")
        with Image.open(source) as image, Image.open(crop) as target:
            image, target = image.convert("RGB"), target.convert("RGB")
            rect = item["crop_xyxy"]
            require(0 <= rect[0] < rect[2] <= image.width and 0 <= rect[1] < rect[3] <= image.height, "Reference crop outside source")
            extracted = image.crop(rect)
            require(extracted.size == target.size and extracted.tobytes() == target.tobytes(), "Reference crop is not original pixels")
            require(pixel_sha(image) not in source_pixels, "Reference decoded source overlaps evaluation")
            if "size" in item:
                require(list(target.size) == item["size"], "Approved reference size changed")
            source_rgb, crop_rgb, size = pixel_sha(image), pixel_sha(target), list(target.size)
        with tempfile.TemporaryDirectory() as temporary:
            prepared = Path(temporary) / "reference.png"
            _prepare_image(crop, prepared, 512)
            with Image.open(prepared) as image:
                prepared_size = list(image.size)
            prepared_sha = sha(prepared)
        references[item["part"]] = {"approval": item, "source": reference(root, source), "crop": reference(root, crop),
                                     "source_rgb_sha256": source_rgb, "crop_rgb_sha256": crop_rgb, "crop_size": size,
                                     "prepared_sha256": prepared_sha, "prepared_size": prepared_size}
    require(references["nut"]["source"]["sha256"] != references["washer"]["source"]["sha256"], "Distinct reference sources required")
    training = read(root / "datasets/derived/public_detector_v1/train.json")
    require(references["nut"]["source"]["sha256"] in {r["source_sha256"] for r in training["images"]},
            "Nut reference must remain from original Screws training source")
    require({p: r["prepared_sha256"] for p, r in references.items()} == PREPARED_REFS,
            "Only the previously approved nut297/washer057 references are permitted")
    return references


def preflight(root, approval_path, model_path=None):
    require((ROOT / "base_source_manifest.json").is_file() and sys.flags.isolated, "Isolated legacy snapshot required")
    require("KITGUARD_DATA_DIR" in os.environ, "Set runtime app data before imports")
    from kitguard.evaluation import validate_case
    from scripts.run_benchmark import app_upload_bytes
    root = root.resolve()
    require(sha(approval_path) == APPROVAL_SHA, "Use the unchanged previously approved reference pair")
    baseline_files = []
    for name, digest in BASE_HASHES.items():
        path = root / BASE / name
        require(sha(path) == digest, "Historical baseline changed")
        baseline_files.append(reference(root, path))
    require(sha(root / AUDIT) == AUDIT_SHA and read(root / AUDIT)["status"] == "passed", "Original audit changed")
    baseline_files.append(reference(root, root / AUDIT))
    baseline = read(root / BASE / "run.json")
    require(baseline["status"] == "completed", "Baseline incomplete")
    manifest = read(root / BASE / "manifest.json")
    cases = manifest["cases"]
    require(len(cases) == len({c["id"] for c in cases}) == 51, "Exactly original 51 required")
    require(Counter(c["subgroup"] for c in cases) == {"screws_author_safe_crop": 35, "loco_normal_222": 16}, "Source denominator")
    base_rows = {r["case_id"]: r for r in [json.loads(x) for x in (root / BASE / "predictions.jsonl").read_text().splitlines()]
                 if r["mode"] == "spatial_guarded"}
    require(set(base_rows) == {c["id"] for c in cases}, "Baseline case set mismatch")
    refs = reference_receipts(root, approval_path, cases)
    engine = observer(model_path)
    status = engine.status()
    require(status["available"] and not status["loaded"], "Fresh available observer required; no model loading in preflight")
    historical = read(root / BASE / "freeze.json")["model_identity"]["spatial_guarded"]
    base_status = {**status, "observer_protocol_sha256": status["base_observer_protocol_sha256"],
                   "observation_mode": status["base_observation_mode"]}
    require(all(base_status[k] == historical[k] for k in IDENTITY_KEYS), "Historical guarded method/model identity differs")
    identity = model_receipt(Path(status["path"]), status)
    bound_cases = []
    for case in cases:
        path = validate_case(case, root / "datasets")
        source = inside(root / "datasets", case.get("source_image", case["image"]))
        require(sha(source) == case["source_sha256"], "Source photo changed")
        normalized = app_upload_bytes(path)
        digest = hashlib.sha256(normalized).hexdigest()
        require(digest == base_rows[case["id"]]["normalized_sha256"], "Current app upload differs from historical G")
        bound_cases.append({"case": case, "image": reference(root, path), "source": reference(root, source),
                            "normalized_sha256": digest, "baseline": base_rows[case["id"]]})
    return {"schema": "kitguard.v08.identity-reference-guarded.preflight.v1", "status": "passed",
            "created_at": datetime.now(UTC).isoformat(), "project_root": str(root), "policy": POLICY,
            "approval": reference(root, approval_path), "references": refs, "cases": bound_cases,
            "baseline_files": baseline_files, "model": identity, "versions": versions(), "source_hashes": sources(ROOT), "runtime_source_root": str(ROOT),
            "base_provenance": read(ROOT / "base_source_manifest.json"),
            "model_called": False, "mlx_imported": "mlx.core" in sys.modules, "cases_preprocessed": 51}


def create_freeze(receipt, output):
    require(not output.exists(), "Freeze cannot be overwritten")
    require(receipt.get("schema") == "kitguard.v08.identity-reference-guarded.preflight.v1"
            and receipt.get("policy") == POLICY, "Preflight schema/policy changed")
    require(receipt["status"] == "passed" and receipt["mlx_imported"] is False, "Preflight must not load MLX")
    root = Path(receipt["project_root"])
    source_root = Path(receipt["runtime_source_root"])
    require(sources(source_root) == receipt["source_hashes"], "Source changed since preflight")
    for ref in [receipt["approval"], *receipt["baseline_files"]]:
        verify(root, ref)
    require(receipt["approval"] == {"path": APPROVAL, "sha256": APPROVAL_SHA}, "Preflight approval changed")
    baseline_refs = [{"path": f"{BASE}/{name}", "sha256": digest} for name, digest in BASE_HASHES.items()]
    require(receipt["baseline_files"] == [*baseline_refs, {"path": AUDIT, "sha256": AUDIT_SHA}],
            "Preflight baseline bindings changed")
    cases = read(root / BASE / "manifest.json")["cases"]
    baseline_rows = {r["case_id"]: r for r in (json.loads(line) for line in
                     (root / BASE / "predictions.jsonl").read_text().splitlines()) if r["mode"] == "spatial_guarded"}
    require(len(receipt["cases"]) == len(cases) == len(baseline_rows) == 51, "Preflight requires original full 51")
    for item, case in zip(receipt["cases"], cases, strict=True):
        require(item["case"] == case and item["baseline"] == baseline_rows[case["id"]]
                and item["normalized_sha256"] == baseline_rows[case["id"]]["normalized_sha256"],
                "Preflight case/order/truth/baseline differs from immutable originals")
        require(item["image"] == {"path": "datasets/" + case["image"], "sha256": case["sha256"]}
                and item["source"] == case_source_ref(case),
                "Preflight target/source binding changed")
    base_provenance = read(source_root / "base_source_manifest.json")
    require(receipt["base_provenance"] == base_provenance and
            base_provenance["freeze"] == {"path": BASE_SOURCE_FREEZE, "sha256": BASE_SOURCE_SHA},
            "Preflight base provenance changed")
    require(sha(root / BASE_SOURCE_FREEZE) == BASE_SOURCE_SHA, "Original base freeze changed")
    require(base_provenance["source_hashes"] == read(root / BASE_SOURCE_FREEZE)["source_hashes"]
            and all(receipt["source_hashes"].get(p) == h for p, h in base_provenance["source_hashes"].items()),
            "Only unchanged original base sources are permitted")
    approved = {i["part"]: i for i in read(root / APPROVAL)["items"]}
    require(set(receipt["references"]) == set(REF_PARTS), "Preflight must retain exactly two fixed references")
    for part, item in receipt["references"].items():
        original = approved[part]
        require(item["approval"] == original and item["prepared_sha256"] == PREPARED_REFS[part]
                and item["source"] == {"path": original["source"], "sha256": original["source_sha256"]}
                and item["crop"] == {"path": original["crop"], "sha256": original["crop_sha256"]},
                "Preflight reference binding differs from fixed approval")
        verify(root, item["source"])
        verify(root, item["crop"])
    for item in receipt["cases"]:
        verify(root, item["source"])
        verify(root, item["image"])
    verify_model(receipt["model"], full=True)
    output.mkdir(parents=True)
    snapshot = output / "source_snapshot"
    for relative, expected in receipt["source_hashes"].items():
        path = snapshot / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, path)
        require(sha(path) == expected, "Source snapshot changed while copying")
    frozen = {**receipt, "schema": "kitguard.v08.identity-reference-guarded.freeze.v1"}
    write(output / "freeze.json", frozen)
    return frozen


def verify_frozen(freeze_path, full_model=False):
    frozen = read(freeze_path)
    require(frozen["schema"] == "kitguard.v08.identity-reference-guarded.freeze.v1" and frozen["policy"] == POLICY, "Freeze protocol differs")
    require(sources(ROOT) == frozen["source_hashes"], "Execute unchanged frozen source snapshot")
    require(versions() == frozen["versions"], "Runtime versions changed")
    root = Path(frozen["project_root"])
    for ref in [frozen["approval"], *frozen["baseline_files"]]:
        verify(root, ref)
    for item in frozen["references"].values():
        verify(root, item["source"])
        verify(root, item["crop"])
    verify_model(frozen["model"], full=full_model)
    return frozen, root


def check_reference_stages(diagnostics, refs, artifact_dir, completed):
    from kitguard import vision
    calls = (diagnostics or {}).get("generation_calls", [])
    expected = [refs[p]["prepared_sha256"] for p in REF_PARTS]
    require(len(calls) <= 3, "Unexpected retry or added model call")
    identity = 0
    for index, call in enumerate(calls):
        hashes = [i["sha256"] for i in call["images"]]
        for im in call["images"]:
            require(sha(inside(artifact_dir, im["path"])) == im["sha256"], "Saved raw input differs")
        if index < 2:
            schema = vision.SpatialInventory
            require(call["schema"] == schema.__name__ and len(hashes) == 1,
                    "Spatial stage must have exactly one target and no references")
            require(call["system"] == vision.SPATIAL_SYSTEM and call["prompt"] == vision.SPATIAL_USER
                    and call["max_tokens"] == 900, "Spatial reference-free G prompt/budget differs")
            roles = [{"image": 1, "role": "inspection_target"}]
        else:
            identity += 1
            schema = vision.IdentityResponse
            crops = diagnostics["identity"]["crops"]
            prefix_count = 1 + len(crops)
            system, prompt = identity_messages(vision.IDENTITY_SYSTEM, vision.build_prompt(crops), prefix_count)
            require(call["schema"] == schema.__name__ and len(hashes) == prefix_count + 2
                    and hashes[-2:] == expected, "Identity references missing, reordered or changed")
            require(call["system"] == system and call["prompt"] == prompt and call["max_tokens"] == 1800,
                    "Identity role prompt/budget differs")
            roles = ([{"image": 1, "role": "inspection_target"}]
                     + [{"image": i, "role": "target_crop", "point_id": c["id"]}
                        for i, c in enumerate(crops, 2)]
                     + [{"image": prefix_count+i, "role": "category_reference", "part": part, "counted": False}
                        for i, part in enumerate(REF_PARTS, 1)])
        require(call.get("input_roles") == roles, "Actual image roles differ")
        require(call.get("experiment_protocol_sha256") == diagnostics.get("experiment_protocol_sha256"),
                "Generation protocol not bound to experiment")
        schema_sha = hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode()).hexdigest()
        require(call.get("json_schema_sha256") == schema_sha, "Actual model JSON schema differs")
        require(call["temperature"] == 0, "Sampling temperature changed")
        require(type(call.get("model_call_started")) is bool and type(call.get("model_call_completed")) is bool
                and (not call["model_call_completed"] or call["model_call_started"]),
                "Actual model invocation boundary missing")
        require(call["status"] != "parsed" or call["model_call_completed"], "Parsed output needs returned model call")
    if completed:
        require(len(calls) >= 2 and all(c["status"] == "parsed" for c in calls), "Successful call sequence incomplete")
        state = diagnostics["identity"]["status"]
        require((identity == 1 and state in {"blocked", "confirmed_candidates"})
                or (identity == 0 and state in {"skipped_base_unclear", "skipped_no_candidates"}),
                "Identity execution/skip status differs")
    trace = diagnostics.get("experimental_reference_inputs", {}) if diagnostics else {}
    if diagnostics:
        require(trace.get("identity_stage_status") == diagnostics.get("identity", {}).get("status", "not_reached"),
                "Experimental trace must preserve identity validation/skip/failure status")
        require(trace.get("identity_generation_status") == (calls[2]["status"] if identity else "not_called"),
                "Experimental identity generation status differs")
        require(trace.get("identity_reference_indices") == (
            [len(calls[2]["images"])-1, len(calls[2]["images"])] if identity else []),
            "Experimental trace must distinguish identity references from skipped identity")
    return {"spatial_calls": min(2, len(calls)), "identity_calls": identity,
            "spatial_reference_indices": [],
            "identity_reference_indices": list(range(len(calls[-1]["images"])-1, len(calls[-1]["images"])+1)) if identity else [],
            "reference_stage_contract_passed": True}


def check_target_stages(diagnostics, expected_target_sha, artifact_dir, refs):
    from PIL import Image
    calls = (diagnostics or {}).get("generation_calls", [])
    if not calls:
        return {"target_stage_contract_checked": False, "reason": "no generation call preserved"}
    first = calls[0]
    require(first["schema"] == "SpatialInventory" and first["images"][0]["sha256"] == expected_target_sha,
            "Candidate original target differs from historical G actual input")
    with Image.open(artifact_dir / first["images"][0]["path"]) as image:
        rotated = image.transpose(Image.Transpose.ROTATE_90)
        buffer = io.BytesIO()
        rotated.save(buffer, format="PNG")
    rotation_sha = hashlib.sha256(buffer.getvalue()).hexdigest()
    if len(calls) >= 2:
        require(calls[1]["schema"] == "SpatialInventory" and calls[1]["images"][0]["sha256"] == rotation_sha,
                "Second target is not exact original-input 90-degree rotation")
    if len(calls) == 3:
        crop_hashes = [c["crop_sha256"] for c in diagnostics["identity"]["crops"]]
        require(calls[2]["schema"] == "IdentityResponse"
                and [i["sha256"] for i in calls[2]["images"]] == [expected_target_sha, *crop_hashes, *[refs[p]["prepared_sha256"] for p in REF_PARTS]],
                "Identity image list differs from target, saved crops and appended references")
    return {"target_stage_contract_checked": True, "original_sha256": expected_target_sha,
            "rotation_sha256": rotation_sha, "identity_crop_hashes_checked": len(calls) == 3}


def analyze(items, records):
    from kitguard.evaluation import score_case
    from scripts.v07.analyze_public_paired import classify, false_ready_panel, latency
    require(len(items) == len({i["case"]["id"] for i in items}) == 51, "Complete frozen 51-case denominator required")
    indexed = {r["case_id"]: r for r in records}
    require(len(indexed) == len(records) and set(indexed) <= {i["case"]["id"] for i in items}, "Duplicate/unplanned result")
    counts, transitions, groups, changes, panels = Counter(), Counter(), {}, [], []
    lost, loco_old, loco_kept, original_wrong = [], 0, 0, []
    for item in items:
        case, base = item["case"], item["baseline"]
        row = indexed.get(case["id"])
        if row is not None:
            require(row["sha256"] == case["sha256"] and row["source_id"] == case["source_id"]
                    and row["ground_truth"] == case["ground_truth"] and row["mode"] == MODE, "Result source/truth/mode mismatch")
            rescored = score_case(case, row["observation"], row["latency_ms"], row["error"])
            row = {**row, **rescored}
        old, new = classify(base), classify(row)
        counts[new] += 1
        transitions[f"{old}->{new}"] += 1
        groups.setdefault(case["subgroup"], Counter())[new] += 1
        change = {"case_id": case["id"], "baseline": old, "candidate": new}
        changes.append(change)
        if old == "C" and new != "C":
            lost.append(case["id"])
        if old == "W":
            original_wrong.append(change)
        if case["subgroup"] == "loco_normal_222":
            loco_old += old == "C"
            loco_kept += old == new == "C"
        panels.append({"case_id": case["id"], "baseline": false_ready_panel(case, base["observation"], base["error"]),
                       "candidate": false_ready_panel(case, row["observation"] if row else None,
                                                       row["error"] if row else "not attempted")})
    afr = {name: sum(p["candidate"][name]["any_false_ready"] for p in panels) for name in ("all_four", "source_supported")}
    checks = {"all51_attempted": len(records) == 51, "zero_W": counts["W"] == 0, "zero_E": counts["E"] == 0,
              "zero_N": counts["N"] == 0, "C_at_least_41": counts["C"] >= 41,
              "zero_all_four_AFR": afr["all_four"] == 0, "all14_loco_C_preserved": loco_old == loco_kept == 14}
    return {"schema": "kitguard.v08.identity-reference-guarded.analysis.v1", "planned": 51,
            "outcomes": {k: counts[k] for k in "CWUEN"}, "paired_transitions": dict(transitions), "changes": changes,
            "source_groups": {s: {k: ct[k] for k in "CWUEN"} for s, ct in groups.items()}, "old_C_lost": lost,
            "original_wrong_cases": original_wrong, "loco_old_C": loco_old, "loco_C_preserved": loco_kept,
            "panels": panels, "any_false_ready_images": afr, "risk_denominator": 51, "unmeasured_risk": counts["E"] + counts["N"],
            "latency_all_attempted": latency([r["latency_ms"] for r in records]),
            "latency_warm_subset": latency([r["latency_ms"] for r in records if r["loaded_before"]]),
            "baseline_historical_latency": latency([i["baseline"]["latency_ms"] for i in items]),
            "concurrent_latency_comparison": False,
            "generation_attempt_records": sum(len((r.get("observation_diagnostics") or {}).get("generation_calls", [])) for r in records),
            "model_calls_started": sum(c.get("model_call_started", False) for r in records
                                       for c in (r.get("observation_diagnostics") or {}).get("generation_calls", [])),
            "model_calls_completed": sum(c.get("model_call_completed", False) for r in records
                                         for c in (r.get("observation_diagnostics") or {}).get("generation_calls", [])),
            "development_checks": checks, "development_gate_count_conditions_passed": all(checks.values()),
            "independent_audit_required": True, "automatic_promotion": False, "new_holdout": False}


def run(freeze_path, output):
    require(not output.exists(), "Preserve previous results; output must be new")
    output.mkdir(parents=True)
    os.environ["KITGUARD_DATA_DIR"] = str(output / "runtime-app-data")
    from kitguard.evaluation import score_case
    from scripts.run_benchmark import app_upload_bytes
    setup_started = time.perf_counter()
    frozen, root = verify_frozen(freeze_path, full_model=True)
    snapshot = freeze_path.parent / "source_snapshot"
    require(ROOT == snapshot and sys.flags.isolated, "Runtime must use isolated frozen source")
    engine = observer(Path(frozen["model"]["status"]["path"]))
    status = engine.status()
    require(status["available"] and not status["loaded"], "Run must begin cold without loading in setup")
    require(all(status[k] == frozen["model"]["status"][k] for k in IDENTITY_KEYS), "Observer identity changed")
    refs = {part: inside(root, item["crop"]["path"]) for part, item in frozen["references"].items()}
    (output / "normalized_inputs").mkdir()
    shutil.copy2(freeze_path, output / "freeze.json")
    write(output / "manifest.json", {"cases": [i["case"] for i in frozen["cases"]]})
    metadata = {"schema": "kitguard.v08.identity-reference-guarded.run.v1", "status": "running",
                "started_at": datetime.now(UTC).isoformat(), "planned": 51, "completed_attempts": 0,
                "freeze_sha256": sha(freeze_path), "runtime_source_root": str(ROOT), "project_root": str(root),
                "isolated_python": True, "setup_verification_seconds": time.perf_counter() - setup_started,
                "model_called_in_setup": False, "automatic_promotion": False,
                "runtime_app_data": os.environ["KITGUARD_DATA_DIR"],
                "experiment_protocol_sha256": status["observer_protocol_sha256"],
                "base_observer_protocol_sha256": status["base_observer_protocol_sha256"],
                "cold_first_attempt_included": True}
    write(output / "run.json", metadata)
    records = []
    try:
        for index, item in enumerate(frozen["cases"], 1):
            require(sources(ROOT) == frozen["source_hashes"], "Frozen source changed")
            verify_model(frozen["model"])
            for ref in frozen["references"].values():
                verify(root, ref["crop"])
            loaded = engine.status()["loaded"]
            artifact_dir = output / "cases" / f"{index:03d}-{MODE}"
            engine.artifact_dir = artifact_dir
            normalized = output / "normalized_inputs" / f"{index:03d}.jpg"
            observed = diagnostics = stage_contract = None
            error = normalized_sha = None
            observe_started = False
            started = time.perf_counter()
            try:
                path = verify(root, item["image"])
                normalized.write_bytes(app_upload_bytes(path))
                normalized_sha = sha(normalized)
                require(normalized_sha == item["normalized_sha256"], "Upload differs from historical G input")
                observe_started = True
                observed = engine.observe(normalized, dict.fromkeys(PARTS, 1), refs)
                diagnostics = engine.status().get("last_observation_attempt")
                require(diagnostics["source_sha256"] == normalized_sha, "Diagnostics bound to another input")
                stage_contract = check_reference_stages(diagnostics, frozen["references"], artifact_dir, True)
                stage_contract.update(check_target_stages(diagnostics, item["baseline"]["observation_diagnostics"]["passes"][0]["input_sha256"], artifact_dir, frozen["references"]))
            except Exception as exc:  # noqa: BLE001 -- retain every failed case, no retry
                error = f"{type(exc).__name__}: {exc}"
                diagnostics = getattr(exc, "observation_diagnostics", diagnostics)
                if diagnostics is None and observe_started:
                    diagnostics = engine.status().get("last_observation_attempt")
                try:
                    stage_contract = check_reference_stages(diagnostics, frozen["references"], artifact_dir, False)
                    stage_contract.update(check_target_stages(diagnostics, item["baseline"]["observation_diagnostics"]["passes"][0]["input_sha256"], artifact_dir, frozen["references"]))
                except (ValueError, OSError) as stage_error:
                    stage_contract = {"reference_stage_contract_passed": False, "error": str(stage_error)}
            elapsed = round((time.perf_counter() - started) * 1000)
            row = score_case(item["case"], observed, elapsed, error)
            row.update(mode=MODE, index=index, normalized_sha256=normalized_sha, loaded_before=loaded,
                       observation_diagnostics=diagnostics, reference_stage_contract=stage_contract,
                       observation_attempted=observe_started, observer_status=engine.status())
            records.append(row)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
            metadata["completed_attempts"] = len(records)
            write(output / "run.json", metadata)
            print(json.dumps({"completed": len(records), "planned": 51, "case_id": item["case"]["id"], "error": error,
                              "latency_ms": elapsed}), flush=True)
        metadata["status"] = "completed"
    except BaseException as exc:
        metadata.update(status="interrupted", interruption=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        metadata["finished_at"] = datetime.now(UTC).isoformat()
        metadata["source_changed"] = sources(ROOT) != frozen["source_hashes"]
        try:
            verify_frozen(freeze_path, full_model=True)
            require(sha(freeze_path) == metadata["freeze_sha256"], "Freeze changed during run")
            metadata["final_integrity_verified"] = True
        except (ValueError, OSError) as exc:
            metadata.update(status="failed_integrity", final_integrity_verified=False, integrity_error=str(exc))
        analysis = analyze(frozen["cases"], records)
        write(output / "analysis.json", analysis)
        metadata["analysis_sha256"] = sha(output / "analysis.json")
        metadata["predictions_sha256"] = sha(output / "predictions.jsonl") if records else None
        write(output / "run.json", metadata)
    return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("preflight", "freeze", "run"))
    p.add_argument("--project-root", type=Path, default=ROOT)
    p.add_argument("--approval", type=Path)
    p.add_argument("--model-path", type=Path)
    p.add_argument("--preflight", type=Path)
    p.add_argument("--freeze", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--frozen-runtime", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    require(not args.output.exists(), "Output already exists")
    if args.command == "preflight":
        if not args.frozen_runtime:
            stage = args.output.resolve().with_suffix(".source_snapshot")
            prepare_sources(args.project_root.resolve(), stage)
            entry = ("import sys; sys.path.insert(0,sys.argv.pop(1)); "
                     "from scripts.v08.run_identity_reference_guarded import main; main()")
            command = [sys.executable, "-I", "-c", entry, str(stage), "preflight", "--frozen-runtime",
                       "--project-root", str(args.project_root.resolve()), "--output", str(args.output.resolve())]
            if args.approval:
                command += ["--approval", str(args.approval.resolve())]
            if args.model_path:
                command += ["--model-path", str(args.model_path.resolve())]
            raise SystemExit(subprocess.call(command))
        os.environ["KITGUARD_DATA_DIR"] = str(args.output.resolve().with_suffix(".runtime-app-data"))
        write(args.output, preflight(args.project_root.resolve(), args.approval or args.project_root / APPROVAL, args.model_path))
        print(json.dumps({"status": "passed", "output": str(args.output), "model_called": False}))
    elif args.command == "freeze":
        require(args.preflight is not None, "--preflight required")
        result = create_freeze(read(args.preflight), args.output.resolve())
        print(json.dumps({"status": "frozen", "cases": len(result["cases"]), "sha256": sha(args.output / "freeze.json")}))
    else:
        require(args.freeze is not None, "--freeze required")
        if args.frozen_runtime:
            result = run(args.freeze.resolve(), args.output.resolve())
            if result["status"] != "completed":
                p.exit(1, "Run preserved an integrity/interruption failure; inspect run.json\n")
        else:
            snapshot = args.freeze.resolve().parent / "source_snapshot"
            entry = "import sys; sys.path.insert(0,sys.argv.pop(1)); from scripts.v08.run_identity_reference_guarded import main; main()"
            command = [sys.executable, "-I", "-c", entry, str(snapshot), "run", "--frozen-runtime",
                       "--freeze", str(args.freeze.resolve()), "--output", str(args.output.resolve())]
            raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
