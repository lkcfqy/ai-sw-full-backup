"""Train-only MANTA component preparation. No Torch, inference, network, or test pixels.

freeze commits the complete selection/policy and executable source before image reads.
prepare must run from that exact source snapshot. All planned records remain in records.json.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
import platform
import re
import shutil
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "scripts/v08/prepare_manta_classifier.py"
DOC = "docs/v0.8/MANTA_CLASSIFIER_PROTOCOL_V1.md"
TEST = "tests/test_manta_classifier_preparation_v08.py"
META = "datasets/manifests/v0.8/manta-identity-v1/record_metadata.jsonl"
META_SHA = "0758a4a35caed254e0de9d0d8c60cbdf301f2d9bbfc373f9d808680c869f7dbc"
SOURCE = "datasets/manifests/v0.8/manta-identity-v1/source_manifest.json"
SOURCE_SHA = "7164d37e7ac6b716983bb081243d0e471deb6bbaf16d18c6dfa7a5ac3008b46b"
DEV = "datasets/derived/v0.8/manta-identity-v1/development_view_check_v1"
WEIGHT_NAME = "fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth"
WEIGHT_SHA = "907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5"
CLASSES = {"nut": 0, "yellow_green_washer": 1}
TRAIN_COUNTS = {"nut": 2148, "yellow_green_washer": 2072}
POLICY = {
    "version": 1, "purpose": "two-class identity component research only",
    "seed": "kitguard-manta-classifier-v1-20261002", "block_size": 32,
    "blocks_per_class": 16, "validation_blocks_per_class": 4, "maximum_records": 1024,
    "selection": "block zero plus 15 complete blocks by SHA256(seed|select|class|block); no replacements",
    "initial_partition": "4 nonzero selected blocks by SHA256(seed|partition|class|block) are validation",
    "grouping": "union same class consecutive-ID block plus exact raw/composite/all-panel/input pixel duplicates",
    "duplicate_role": "train wins on mixed partition; cross-class duplicate component quarantined and blocks readiness",
    "physical_identity_verified": False, "session_identity_verified": False,
    "views_per_record": 5, "view_index": 0, "camera_position": None,
    "layout": "RGB single-frame PNG; empty EXIF; width divisible by 5; 64<=panel width,height<=2048; ratio 0.5..2",
    "layout_claim": "structural checks plus fixed 36-record visual QA; not full-corpus semantic verification",
    "preprocessing": "leftmost [0,0,width/5,height]; RGB->L->RGB; aspect-fit LANCZOS pad black to 224x224",
    "duplicate_scope": "selected 1024 only; exact bytes and dimension-bound pixels, not perceptual/physical identity",
    "test_policy": "metadata and archive stream headers only; never extract/decode author test or masks",
    "failures": "preserve all planned rows; no replacement/retry; any failure/conflict blocks training readiness",
    "minimum_partition": "each class train>=256/validation>=64 and each role>=2 final groups; else blocked",
    "qa_selection": "both previously exposed records plus record16 of each selected32 block, per class; 8 validation records exposed only to layout QA",
    "license": "author CC BY-NC-SA 4.0; conflicting Figshare CC BY metadata unresolved; local noncommercial research",
    "pretraining_exposure": "unknown", "new_holdout_claim": False,
    "old51": "exposed development stress regression only; no tuning on new LOCO24",
    "training": {
        "initialization": "existing original COCO Faster R-CNN MobileNetV3 strict state, then backbone.body only",
        "weights_sha256": WEIGHT_SHA, "feature": "body output key 1 (960 channels), global adaptive average pool",
        "head": "Linear(960,2), only head trainable; backbone eval including normalization",
        "normalization_mean": [0.485, 0.456, 0.406], "normalization_std": [0.229, 0.224, 0.225],
        "epochs": 10, "selection": "final epoch 10 only; no best-epoch/threshold search",
        "optimizer": "SGD", "learning_rate": 0.01, "momentum": 0.9, "weight_decay": 0.0001,
        "batch_size": 32, "seed": 20261002, "device": "mps", "precision": "float32",
        "workers": 0, "augmentation": "none", "probability_threshold": 0.9,
        "confidence_claim": "softmax is not calibrated correctness or open-set confidence",
        "requires_separate_root_review_and_training_command": True,
    },
    "component_gate": {"validation_each_class_correct_coverage_min": 0.75, "W": 0, "E": 0, "N": 0,
                       "scope": "continuation gate only, no production promotion"},
    "later_exposed51_gate": {"C_min": 41, "W": 0, "E": 0, "N": 0, "all_four_AFR": 0,
                             "all_14_old_loco_correct_retained": True},
}
PROPOSAL_INTERFACE = {
    "schema": "kitguard.v08.independent-identity-proposals.v1",
    "required": ["source_image_sha256", "source_width", "source_height", "proposal_id", "bbox_xyxy",
                 "proposer_model_sha256", "proposer_config_sha256", "proposal_score", "proposal_origin"],
    "coordinate_space": "original source-image pixels, finite 0<=x0<x1<=width and 0<=y0<y1<=height",
    "allowed_origin": "independent_detector", "forbidden_origin": ["vlm_point", "author_ground_truth"],
    "recall_evaluation": "one-to-one IoU>=0.5 against author target boxes on exposed development source groups",
    "required_report": ["proposal_recall_by_class_and_source", "unmatched_truth", "unmatched_proposals",
                        "duplicate_proposals", "all_raw_proposals", "classification_C_W_U_E_N", "added_latency"],
    "limitations": "LOCO lacks author instance boxes; any added labels require separate provenance/QA",
    "integration": "not implemented; conflict may only become unknown, never auto-correct/add counts",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for b in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read(path):
    return json.loads(Path(path).read_text())


def dump_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def now():
    return datetime.now(UTC).isoformat()


def rank(purpose, class_name, block):
    return digest(f"{POLICY['seed']}|{purpose}|{class_name}|{block}".encode())


def record_number(row):
    name = row["class_name"]
    match = re.fullmatch(rf"mechanics_{re.escape(name)}_(\d{{5}})", row["record_id_from_filename"])
    require(match and int(match[1]) > 0, "Invalid record identifier")
    number = int(match[1])
    expected = f"{name}/train/good/mechanics_{name}_{number:05d}.png"
    require(row["split"] == "train" and row["author_condition_label"] == "good"
            and row["image_path"] == expected, "Only exact author train/good members are eligible")
    require(type(row["image_bytes"]) is int and 0 < row["image_bytes"] <= 16 * 1024 * 1024,
            "Invalid/oversized member")
    return number


def select_records(rows):
    selected, block_table = [], []
    for name, label in CLASSES.items():
        subset = [r for r in rows if r["class_name"] == name and r["split"] == "train"]
        numbers = [record_number(r) for r in subset]
        require(len(numbers) == TRAIN_COUNTS[name] and len(set(numbers)) == len(numbers), "Train census changed")
        require(set(numbers) == set(range(1, TRAIN_COUNTS[name] + 1)), "Train IDs not contiguous")
        blocks = defaultdict(list)
        for row in subset:
            blocks[(record_number(row) - 1) // POLICY["block_size"]].append(row)
        complete = [b for b, members in blocks.items() if len(members) == POLICY["block_size"]]
        require(0 in complete and len(complete) >= 16, "Insufficient complete blocks")
        chosen = [0] + sorted((b for b in complete if b), key=lambda b: (rank("select", name, b), b))[:15]
        val = set(sorted(chosen[1:], key=lambda b: (rank("partition", name, b), b))[:4])
        for b in sorted(chosen):
            role = "validation" if b in val else "train"
            block_table.append({"class_name": name, "block": b, "initial_role": role,
                                "selection_rank": rank("select", name, b), "count": 32})
            for row in sorted(blocks[b], key=lambda r: r["image_path"]):
                n = record_number(row)
                selected.append({"class_name": name, "label": label, "member_path": row["image_path"],
                                 "member_bytes": row["image_bytes"], "archive_sha256": row["archive_sha256"],
                                 "record_id": row["record_id_from_filename"], "record_number": n,
                                 "record_group": row["five_view_record_key"], "proxy_block": f"{name}:{b:04d}",
                                 "initial_role": role, "previously_exposed": n in (1, 2),
                                 "visual_qa_selected": n in (1, 2) or n == b * 32 + 16,
                                 "author_split": "train", "author_condition": "good",
                                 "physical_object_id": None, "capture_session_id": None})
    selected.sort(key=lambda r: r["member_path"])
    for index, row in enumerate(selected):
        row["index"] = index
        row["input_id"] = f"record-{index:04d}"
    require(len(selected) == 1024 and len({r["member_path"] for r in selected}) == 1024, "Population not 1024")
    require(sum(r["visual_qa_selected"] for r in selected) == 36, "QA population changed")
    require(all(r["initial_role"] == "train" for r in selected if r["previously_exposed"]), "Old exposure leaked into validation")
    return selected, block_table


def runtime_bindings():
    """Hash installed implementations without importing Torch/Torchvision/PIL."""
    result = {"python": sys.version, "executable": str(Path(sys.executable).resolve()),
              "platform": platform.platform(), "packages": {}, "files": {}}
    for package, module, paths in (
        ("Pillow", "PIL", ["Image.py", "ImageOps.py", "PngImagePlugin.py", "ImageFile.py"]),
        ("torch", "torch", ["nn/modules/linear.py", "optim/sgd.py"]),
        ("torchvision", "torchvision", ["models/mobilenetv3.py", "models/detection/backbone_utils.py",
                                       "models/detection/faster_rcnn.py", "models/_utils.py", "ops/misc.py"]),
    ):
        result["packages"][package] = importlib.metadata.version(package)
        base = Path(importlib.util.find_spec(module).origin).parent
        for rel in paths:
            p = base / rel
            result["files"][str(p.resolve())] = sha(p)
        if module == "PIL":
            for p in sorted(base.glob("_imaging*.so")):
                result["files"][str(p.resolve())] = sha(p)
    return result


def create_freeze(root, output, weights):
    root, output, weights = Path(root).resolve(), Path(output).resolve(), Path(weights).resolve()
    require(not output.exists(), "Freeze output already exists")
    require(sha(root / META) == META_SHA and sha(root / SOURCE) == SOURCE_SHA, "Original metadata changed")
    require(sha(weights) == WEIGHT_SHA, "Wrong or changed original COCO weights")
    source = read(root / SOURCE)
    rows = [json.loads(line) for line in (root / META).read_text().splitlines()]
    selected, blocks = select_records(rows)
    downloads = {d["file_metadata"]["name"].removesuffix(".tar.gz"): d for d in source["downloads"]}
    archives = []
    for name in CLASSES:
        d = downloads[name]
        require(d["status"] == "verified" and sha(root / d["path"]) == d["sha256"], "Archive integrity failed")
        require(all(r["archive_sha256"] == d["sha256"] for r in selected if r["class_name"] == name),
                "Member/archive lineage mismatch")
        archives.append({"class_name": name, "path": d["path"], "sha256": d["sha256"], "bytes": d["bytes"]})
    bindings = [META, SOURCE, f"{DEV}/selection.json", f"{DEV}/preparation.json", f"{DEV}/layout_review.json",
                f"{DEV}/leftmost_view_v1/receipt.json", "docs/v0.8/MANTA_LICENSE_CHECK.md",
                "datasets/manifests/v0.8/manta-license/source_receipt.json"]
    for name in CLASSES:
        bindings += [f"datasets/manifests/v0.8/manta-identity-v1/{name}_archive_entries.jsonl"]
    protocol = {"schema": "kitguard.v08.manta-classifier.protocol.v1", "created_at_utc": now(),
                "policy": POLICY, "proposal_interface": PROPOSAL_INTERFACE, "records": selected, "blocks": blocks,
                "archives": archives, "weights": {"path": str(weights), "sha256": WEIGHT_SHA, "bytes": weights.stat().st_size},
                "bindings": {p: sha(root / p) for p in bindings}, "runtime": runtime_bindings(),
                "selection_before_pixels": True, "pixels_read_by_freeze": 0, "model_called": False}
    output.mkdir(parents=True, exist_ok=False)
    dump_new(output / "protocol.json", protocol)
    snapshots = {}
    for rel in (SCRIPT, DOC, TEST):
        target = output / "source_snapshot" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, target)
        snapshots[rel] = sha(target)
        require(snapshots[rel] == sha(root / rel), "Source changed during freeze")
    freeze = {"schema": "kitguard.v08.manta-classifier.freeze.v1", "created_at_utc": now(),
              "protocol_sha256": sha(output / "protocol.json"), "source_snapshot": snapshots,
              "selection_count": 1024, "model_called": False, "training_authorized_by_this_artifact": False}
    dump_new(output / "freeze.json", freeze)
    return {"freeze": str(output / "freeze.json"), "sha256": sha(output / "freeze.json"),
            "selected": len(selected), "initial_partitions": dict(Counter(r["initial_role"] for r in selected)),
            "torch_imported": "torch" in sys.modules, "pillow_imported": "PIL.Image" in sys.modules}


def verify_freeze(root, freeze_path, expected, require_snapshot=True):
    root, freeze_path = Path(root).resolve(), Path(freeze_path).resolve()
    require(sha(freeze_path) == expected, "Freeze SHA mismatch")
    freeze, base = read(freeze_path), freeze_path.parent
    require(freeze["schema"] == "kitguard.v08.manta-classifier.freeze.v1", "Wrong freeze schema")
    require(sha(base / "protocol.json") == freeze["protocol_sha256"], "Protocol changed")
    for rel, expected_sha in freeze["source_snapshot"].items():
        require(sha(base / "source_snapshot" / rel) == expected_sha, "Frozen source changed")
    if require_snapshot:
        require(Path(__file__).resolve() == base / "source_snapshot" / SCRIPT, "Run prepare from frozen source")
    p = read(base / "protocol.json")
    require(p["policy"] == POLICY and p["proposal_interface"] == PROPOSAL_INTERFACE, "Policy mismatch")
    for rel, expected_sha in p["bindings"].items():
        require(sha(root / rel) == expected_sha, f"Input binding changed: {rel}")
    require(runtime_bindings() == p["runtime"], "Runtime changed")
    selected, blocks = select_records([json.loads(s) for s in (root / META).read_text().splitlines()])
    require(selected == p["records"] and blocks == p["blocks"], "Frozen population differs from deterministic selection")
    require(sha(p["weights"]["path"]) == WEIGHT_SHA, "Weights changed")
    for a in p["archives"]:
        require(sha(root / a["path"]) == a["sha256"], "Archive changed")
    return p


def pixel_sha(image):
    return digest(canonical({"mode": image.mode, "size": list(image.size)}).encode() + b"\0" + image.tobytes())


def prepare_pixels(data):
    """Only selected train bytes reach this function. No model import."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as original:
        require(original.format == "PNG" and original.mode == "RGB" and getattr(original, "n_frames", 1) == 1,
                "Require single-frame RGB PNG")
        require(not dict(original.getexif()), "EXIF unsupported; do not infer orientation")
        w, h = original.size
        require(w % 5 == 0 and 64 <= w // 5 <= 2048 and 64 <= h <= 2048 and 0.5 <= (w // 5) / h <= 2,
                "Unsupported five-panel geometry; no alternative slicing")
        original.load()
        rgb = original.copy()
    pw = w // 5
    panels = [rgb.crop((i * pw, 0, (i + 1) * pw, h)) for i in range(5)]
    grays = [p.convert("L").convert("RGB") for p in panels]
    inp = ImageOps.pad(grays[0], (224, 224), method=Image.Resampling.LANCZOS,
                       color=(0, 0, 0), centering=(0.5, 0.5))
    encoded = io.BytesIO()
    inp.save(encoded, format="PNG", optimize=False, compress_level=6)
    facts = {"source_size": [w, h], "source_mode": "RGB", "frames": 1, "exif": {},
             "crop_xyxy": [0, 0, pw, h], "view_size": [pw, h], "view_index": 0,
             "composite_rgb_sha256": pixel_sha(rgb), "panel_rgb_sha256": [pixel_sha(p) for p in panels],
             "panel_gray_sha256": [pixel_sha(p) for p in grays], "input_pixel_sha256": pixel_sha(inp),
             "input_sha256": digest(encoded.getvalue()), "input_size": [224, 224],
             "structural_layout_check": "passed", "full_object_semantics_verified": False}
    return facts, encoded.getvalue(), rgb, inp


def duplicate_keys(row):
    if row["status"] != "prepared":
        return []
    keys = [("raw", row["member_sha256"]), ("composite", row["composite_rgb_sha256"]),
            ("input", row["input_pixel_sha256"])]
    keys += [("panel_rgb", s) for s in row["panel_rgb_sha256"]]
    keys += [("panel_gray", s) for s in row["panel_gray_sha256"]]
    return sorted(set(keys))


def group_records(rows):
    """Conservative connected components. Never silently train contradictory labels."""
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    blocks, seen, duplicate_edges = {}, {}, []
    for i, row in enumerate(rows):
        block = row["proxy_block"]
        if block in blocks:
            union(i, blocks[block])
        else:
            blocks[block] = i
        for key in duplicate_keys(row):
            if key in seen:
                j = seen[key]
                union(i, j)
                duplicate_edges.append({"a": rows[j]["input_id"], "b": row["input_id"],
                                        "kind": key[0], "sha256": key[1]})
            else:
                seen[key] = i
    grouped = defaultdict(list)
    for i, row in enumerate(rows):
        grouped[find(i)].append(row)
    groups = []
    for members in grouped.values():
        ids = sorted(m["input_id"] for m in members)
        conflict = len({m["class_name"] for m in members}) != 1
        role = "quarantined_label_conflict" if conflict else (
            "train" if any(m["initial_role"] == "train" or m["previously_exposed"] for m in members) else "validation")
        gid = digest(canonical(ids).encode())
        for m in members:
            m["final_group"] = gid
            m["role"] = role
        groups.append({"group_id": gid, "members": ids, "proxy_blocks": sorted({m["proxy_block"] for m in members}),
                       "role": role, "cross_class_label_conflict": conflict,
                       "physical_identity_verified": False})
    return {"groups": sorted(groups, key=lambda g: g["members"]), "duplicate_edges": duplicate_edges,
            "label_conflict_groups": sum(g["cross_class_label_conflict"] for g in groups),
            "pixel_comparison_scope": "selected records/all five panels only; no test, other train, or perceptual comparison"}


def extract_selected(archive, targets):
    """Do not call extractfile for any nonselected member, including all test/masks."""
    seen = set()
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            if member.name not in targets:
                continue
            require(member.name not in seen, "Repeated selected member")
            require(member.isfile() and not member.issym() and not member.islnk(), "Selected member not regular")
            parts = PurePosixPath(member.name).parts
            require(len(parts) == 4 and parts[0] in CLASSES and parts[1:3] == ("train", "good"),
                    "Forbidden archive payload")
            row = targets[member.name]
            require(member.size == row["member_bytes"], "Selected member size changed")
            seen.add(member.name)
            payload = stream.extractfile(member).read()
            require(len(payload) == member.size, "Truncated selected payload")
            yield row, payload
    require(seen == set(targets), "Missing selected members")


def make_qa_sheet(items, target):
    from PIL import Image, ImageDraw, ImageOps
    sheet = Image.new("RGB", (1120, len(items) * 240), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (row, rgb, inp) in enumerate(items):
        y = i * 240
        draw.text((12, y + 8), f"{row['input_id']} {row['record_id']} | fixed layout QA | RGB composite -> gray view0", fill="black")
        thumb = ImageOps.contain(rgb, (860, 196))
        sheet.paste(thumb, (12, y + 35 + (196 - thumb.height) // 2))
        draw.line((880, y + 30, 880, y + 236), fill="gray")
        sheet.paste(inp, (890, y + 16))
    sheet.save(target, format="PNG")


def prepare(root, freeze_path, expected, output):
    root, freeze_path, output = Path(root).resolve(), Path(freeze_path).resolve(), Path(output).resolve()
    protocol = verify_freeze(root, freeze_path, expected)
    require(not output.exists(), "Preparation output exists; never overwrite or resume")
    output.mkdir(parents=True, exist_ok=False)
    (output / "inputs").mkdir()
    (output / "qa").mkdir()
    started = now()
    rows = [{**r, "status": "not_attempted", "error": None} for r in protocol["records"]]
    dump_new(output / "started.json", {"schema": "kitguard.v08.manta-classifier.preparation-start.v1",
             "started_at_utc": started, "freeze_path": str(freeze_path), "freeze_sha256": expected,
             "population": 1024, "torch_imported": "torch" in sys.modules, "model_called": False})
    qa, interruption, processing_error = [], None, None
    with (output / "attempts.jsonl").open("x") as log:
        try:
            for archive in protocol["archives"]:
                targets = {r["member_path"]: r for r in rows if r["class_name"] == archive["class_name"]}
                for row, data in extract_selected(root / archive["path"], targets):
                    row["payload_read_at_utc"] = now()
                    row["member_sha256"] = digest(data)
                    try:
                        facts, png, rgb, inp = prepare_pixels(data)
                        row.update(facts)
                        target = output / "inputs" / f"{row['input_id']}.png"
                        with target.open("xb") as destination:
                            destination.write(png)
                        row.update(status="prepared", input_path=str(target.relative_to(output)))
                        if row["visual_qa_selected"]:
                            qa.append((row, rgb, inp))
                    except BaseException as error:  # noqa: BLE001 -- persist failures and re-raise interruption
                        row.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                        if not isinstance(error, Exception):
                            interruption = error
                    finally:
                        log.write(canonical(row) + "\n")
                        log.flush()
                    if interruption:
                        raise interruption
        except BaseException as error:  # noqa: BLE001 -- persist failures and re-raise interruption
            processing_error = {"type": type(error).__name__, "message": str(error)}
            if not isinstance(error, Exception):
                interruption = error
    grouped = group_records(rows)
    dump_new(output / "records.json", rows)
    dump_new(output / "grouping.json", grouped)
    qa_files = []
    for name in CLASSES:
        chosen = sorted((x for x in qa if x[0]["class_name"] == name), key=lambda x: x[0]["index"])
        for offset in range(0, len(chosen), 6):
            page = chosen[offset:offset + 6]
            target = output / "qa" / f"{name}-{offset // 6 + 1:02d}.png"
            make_qa_sheet(page, target)
            qa_files.append({"path": str(target.relative_to(output)), "sha256": sha(target),
                             "record_ids": [x[0]["input_id"] for x in page]})
    final_integrity_error = None
    try:
        verify_freeze(root, freeze_path, expected)
        for row in rows:
            if row["status"] == "prepared":
                require(sha(output / row["input_path"]) == row["input_sha256"], "Prepared input changed")
    except Exception as error:  # noqa: BLE001 -- record integrity failure
        final_integrity_error = {"type": type(error).__name__, "message": str(error)}
    counts = dict(Counter(r["status"] for r in rows))
    adequate_roles = all(
        sum(r["role"] == role and r["class_name"] == name for r in rows) >= minimum
        and len({r["final_group"] for r in rows if r["role"] == role and r["class_name"] == name}) >= 2
        for name in CLASSES for role, minimum in (("train", 256), ("validation", 64))
    )
    ready = (counts == {"prepared": 1024} and not grouped["label_conflict_groups"] and not processing_error
             and not final_integrity_error and adequate_roles)
    result = {"schema": "kitguard.v08.manta-classifier.preparation.v1", "started_at_utc": started,
              "finished_at_utc": now(), "status": "prepared_pending_visual_review" if ready else "blocked",
              "freeze_path": str(freeze_path), "freeze_sha256": expected,
              "protocol_sha256": sha(freeze_path.parent / "protocol.json"), "population": 1024,
              "status_counts": counts, "role_counts": dict(Counter(r["role"] for r in rows)),
              "by_class_role": {name: dict(Counter(r["role"] for r in rows if r["class_name"] == name)) for name in CLASSES},
              "records_sha256": sha(output / "records.json"), "grouping_sha256": sha(output / "grouping.json"),
              "attempts_sha256": sha(output / "attempts.jsonl"), "group_count": len(grouped["groups"]),
              "duplicate_edges": len(grouped["duplicate_edges"]), "label_conflict_groups": grouped["label_conflict_groups"],
              "qa_sheets": qa_files, "visual_review_status": "pending", "training_authorized": False, "adequate_partitions": adequate_roles,
              "processing_error": processing_error, "final_integrity_error": final_integrity_error,
              "test_payloads_extracted": 0, "test_images_decoded": 0, "model_called": False,
              "torch_imported": "torch" in sys.modules, "new_holdout_claim": False,
              "limitations": ["32-record adjacent blocks are proxies, not certified physical/session groups",
                              "Exact duplicates checked only within selected records, not all archive/test/pretraining",
                              "Geometry/PNG checks cannot prove full object isolation in every image",
                              "Training requires separate root review and an additional training implementation"]}
    dump_new(output / "preparation.json", result)
    if interruption:
        raise interruption
    return result


def validate_proposal(proposal):
    require(all(k in proposal for k in PROPOSAL_INTERFACE["required"]), "Incomplete proposal provenance")
    require(proposal["proposal_origin"] == "independent_detector", "Not independent localization")
    for key in ("source_image_sha256", "proposer_model_sha256", "proposer_config_sha256"):
        require(isinstance(proposal[key], str) and re.fullmatch(r"[a-f0-9]{64}", proposal[key]), "Invalid SHA")
    w, h = proposal["source_width"], proposal["source_height"]
    require(type(w) is int and type(h) is int and w > 0 and h > 0, "Invalid source size")
    box = proposal["bbox_xyxy"]
    require(isinstance(box, list) and len(box) == 4
            and all(type(v) in (int, float) and math.isfinite(v) for v in box), "Invalid box")
    require(0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h, "Box outside original pixels")
    score = proposal["proposal_score"]
    require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1, "Invalid proposal score")
    require(isinstance(proposal["proposal_id"], str) and proposal["proposal_id"], "Empty proposal id")
    require(not any(k in proposal for k in ("vlm_point", "ground_truth", "bom", "expected_counts")), "Forbidden answer/point fields")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "prepare"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--weights", type=Path, default=Path.home() / ".cache/torch/hub/checkpoints" / WEIGHT_NAME)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--expected-freeze-sha256")
    args = parser.parse_args()
    if args.command == "freeze":
        result = create_freeze(args.project_root, args.output, args.weights)
    else:
        require(args.freeze and args.expected_freeze_sha256, "prepare requires pinned freeze path and SHA")
        result = prepare(args.project_root, args.freeze, args.expected_freeze_sha256, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    raise SystemExit(main())
