"""Prepare, explicitly freeze, serve, then run two bounded real-MLX region checks.

prepare/verify never load a model. freeze/serve/run require an explicit execution
flag, to be used only after root confirms stable sources and exclusive GPU access.
These are previously exposed development inputs, not new accuracy or human trials.
"""
# ruff: noqa: BLE001 -- Recorder must preserve every failure and finalize evidence, never retry inference.

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import math
import os
import socket
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image, ImageOps
from PIL import __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "test-results/browser/inspection-region-real-v05"
URL = "http://127.0.0.1:8791"
MODEL_PATH = Path.home() / "Downloads/AI-Models/Qwen3.6-27B-4bit"
REPO = "mlx-community/Qwen3.6-27B-4bit"
REVISION = "c000ac2c2057d94be3fa931000c31723aac53282"
SCRIPT = Path(__file__).resolve().relative_to(ROOT).as_posix()
NOTE = "SCRIPTED AUTHOR-TRUTH PUBLIC REPLAY; NOT HUMAN TIMING OR FIELD EVIDENCE. 自动录入作者真值，非真人计时、非现场。"


def stamp():
    return datetime.now(UTC).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    with path.open("x" if exclusive else "w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def normalize(raw):
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95)
        return output.getvalue(), image.size


def crop_bytes(root_raw, rectangle):
    with Image.open(io.BytesIO(root_raw)) as source:
        output = io.BytesIO()
        source.convert("RGB").crop(rectangle).save(output, format="JPEG", quality=95)
        return output.getvalue()


def source_plan():
    """Read author coordinates independently; never use product crop/score helpers."""
    image = ROOT / "datasets/raw/ino-10-190/data/origin/A/41_color.png"
    annotation = image.with_suffix(".txt")
    require(file_sha(image) == "0633cf4178aada2611ec46d8df34ee0f6c7452a549c8e6bd67fc4c456e299695",
            "A41 source differs from the v0.4 frozen author image")
    require(file_sha(annotation) == "e3be445b2cbe2a01373329cd7447e7ccf01bf6441a2574d8abf95cbce32b0d38",
            "A41 annotation differs from the v0.4 frozen author label")
    lines = [line.split() for line in annotation.read_text().splitlines() if line.strip()]
    require(len(lines) == 1 and lines[0][0] == "0", "A41 must retain exactly one author class0 row")
    _, center_x, center_y, width, height = map(float, lines[0])
    with Image.open(image) as opened:
        w, h = opened.size
    require((w, h) == (1280, 720), "Unexpected A41 origin size")
    box = [(center_x-width/2)*w, (center_y-height/2)*h,
           (center_x+width/2)*w, (center_y+height/2)*h]
    margin = min(width*w, height*h)*0.1
    rectangle = [math.floor(box[0]-margin), math.floor(box[1]-margin),
                 math.ceil(box[2]+margin), math.ceil(box[3]+margin)]
    require(0 <= rectangle[0] < rectangle[2] <= w and 0 <= rectangle[1] < rectangle[3] <= h,
            "A41 ROI outside source")
    root, size = normalize(image.read_bytes())
    require(size == (w, h), "A41 normalization changes coordinate dimensions")
    a41 = {"id": "ino-A41-author-region", "image": str(image.relative_to(ROOT)),
           "image_sha256": file_sha(image), "annotation": str(annotation.relative_to(ROOT)),
           "annotation_sha256": file_sha(annotation), "author_bbox_xyxy": box, "margin_px": margin,
           "region_xyxy": rectangle, "root_size": list(size), "expected_root_sha256": sha(root),
           "expected_view_sha256": sha(crop_bytes(root, rectangle)),
           "requirements": {"bolt": 0, "nut": 0, "washer": 0, "bracket": 1},
           "ground_truth": {"bracket": 1}, "unlabeled_categories": ["bolt", "nut", "washer"],
           "label_scope": "author_class0_count_only", "field_registration": False,
           "interpretation": "Previously exposed A41, author-position ROI; no four-category scoring or accuracy-improvement claim."}
    manifest_path = ROOT / "datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json"
    case = next(c for c in read_json(manifest_path)["cases"] if c["id"] == "v03-screws-screws_344-8d389e404b12")
    catalog_source = (ROOT / "kitguard/public_demo_catalog.py").read_text()
    assignment = next(n for n in ast.parse(catalog_source).body if isinstance(n, ast.Assign))
    spec = next(c for c in ast.literal_eval(assignment.value) if c["sample_id"] == "mixed-screws")
    derived = ROOT / "datasets" / case["image"]
    source = ROOT / "datasets" / case["source_image"]
    annotations = ROOT / case["annotation_source"]
    require(file_sha(derived) == case["sha256"] == spec["source_sha256"], "Mixed derived SHA mismatch")
    require(file_sha(source) == case["source_sha256"], "Mixed author image SHA mismatch")
    require(file_sha(annotations) == case["annotation_sha256"], "Mixed author annotation SHA mismatch")
    require(case["split"] == "development", "Only existing development sample allowed")
    with Image.open(source) as opened:
        rebuilt = opened.convert("RGB").crop(case["crop_xyxy"])
        with Image.open(derived) as cropped:
            require(rebuilt.size == cropped.size and rebuilt.tobytes() == cropped.convert("RGB").tobytes(),
                    "Mixed sample does not match author source pixels")
    data = read_json(annotations)
    image_record = next(i for i in data["images"] if i["file_name"] == source.name)
    left, top, right, bottom = case["crop_xyxy"]
    included, counts = [], {"bolt": 0, "nut": 0, "washer": 0, "bracket": 0}
    geometry = []
    for item in (a for a in data["annotations"] if a["image_id"] == image_record["id"]):
        # Author README: (row, col, width, height, phi), not common COCO xywh.
        row, col, aw, ah, phi = item["bbox"]
        dx = abs(aw*math.cos(phi))/2 + abs(ah*math.sin(phi))/2
        dy = abs(aw*math.sin(phi))/2 + abs(ah*math.cos(phi))/2
        pad = case["bbox_margin_px"]
        bounds = [col-dx-pad, row-dy-pad, col+dx+pad, row+dy+pad]
        inside = left <= bounds[0] and top <= bounds[1] and right >= bounds[2] and bottom >= bounds[3]
        outside = bounds[2] < left or bounds[3] < top or bounds[0] > right or bounds[1] > bottom
        require(inside or outside, "Mixed crop touches/cuts an author padded box")
        if inside:
            require(item["category_id"] in {4, 8, 12}, "Unexpected mixed sample category; do not invent a mapping")
            included.append(item["id"])
            counts["bolt"] += 1
        geometry.append({"annotation_id": item["id"], "category_id": item["category_id"],
                         "padded_aabb_xyxy": bounds, "inside": inside, "outside": outside})
    require(sorted(included) == sorted(case["included_annotation_ids"]), "Mixed included author IDs differ")
    require(counts == case["ground_truth"] == spec["requirements"] == {"bolt": 3, "nut": 0, "washer": 0, "bracket": 0},
            "Mixed source truth differs")
    root, size = normalize(derived.read_bytes())
    full_rectangle = [0, 0, *size]
    mixed = {"id": "mixed-screws-full-region", "sample_id": "mixed-screws",
             "image": str(derived.relative_to(ROOT)), "image_sha256": file_sha(derived),
             "source_image": str(source.relative_to(ROOT)), "source_sha256": file_sha(source),
             "annotation": str(annotations.relative_to(ROOT)), "annotation_sha256": file_sha(annotations),
             "truth_manifest": str(manifest_path.relative_to(ROOT)), "truth_manifest_sha256": file_sha(manifest_path),
             "source_crop_xyxy": case["crop_xyxy"], "author_annotation_geometry": geometry,
             "included_annotation_ids": included, "ground_truth": counts, "requirements": counts,
             "label_scope": "existing_author_taxonomy_four_categories", "field_registration": True,
             "root_size": list(size), "region_xyxy": full_rectangle, "expected_root_sha256": sha(root),
             "expected_view_sha256": sha(crop_bytes(root, full_rectangle)),
             "interpretation": "Previously exposed development sample; full-frame region integration; scripted author counts, not a human baseline."}
    return {"schema_version": 1, "status": "prepared_not_frozen_not_executed", "base_url": URL,
            "planned_inspections": 2, "retry_inference": False, "human_participants": 0,
            "model_path": str(MODEL_PATH), "repo_id": REPO, "model_revision": REVISION,
            "observation_mode": "spatial_guarded", "image_max_side": 1536,
            "pillow_version": pillow_version, "cases": [a41, mixed],
            "scope": "Two exposed development inputs, one HTTP inspect each, all failures retained, no physical completion, no new accuracy samples."}


def sources():
    paths = list((ROOT / "kitguard").glob("*.py"))
    paths += [p for p in (ROOT / "kitguard/static").rglob("*") if p.is_file()]
    paths += [ROOT / SCRIPT, ROOT / "scripts/verify_study_export.py", ROOT / "requirements-lock.txt", ROOT / "pyproject.toml"]
    return sorted(p for p in set(paths) if p.is_file())


def verify_freeze(base):
    freeze = read_json(base / "PLAN_FREEZE.json")
    require(file_sha(base / "SOURCE_PLAN.json") == freeze["source_plan_sha256"], "Prepared plan changed")
    require(source_plan() == read_json(base / "SOURCE_PLAN.json"), "Author inputs/geometry changed")
    for name, expected in freeze["source_sha256"].items():
        require(file_sha(ROOT / name) == expected, "Source differs from freeze: " + name)
        require(file_sha(base / "source_snapshot" / name) == expected, "Snapshot differs: " + name)
    return freeze


def freeze_sources(base):
    require(not (base / "PLAN_FREEZE.json").exists(), "Freeze already exists; preserve earlier attempt")
    require(source_plan() == read_json(base / "SOURCE_PLAN.json"), "Prepared source metadata changed")
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 8791))
    hashes = {}
    for path in sources():
        name = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        target = base / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as out:
            out.write(raw)
        hashes[name] = sha(raw)
    prior = read_json(ROOT / "docs/v0.4/INO_TWO_BRACKET_FREEZE_V1.json")["method_source_hashes"]
    for name in ("kitguard/vision.py", "kitguard/spatial.py", "kitguard/consensus.py", "kitguard/identity.py"):
        require(hashes[name] == prior[name], "Frozen v0.4 visual method changed: " + name)
    value = {"schema_version": 1, "frozen_at": stamp(), "source_plan_sha256": file_sha(base / "SOURCE_PLAN.json"),
             "source_sha256": hashes, "gpu_exclusive_access": "Root explicitly authorizes and reserves before execution; not proven by this hash.",
             "python": sys.version, "pillow_version": pillow_version}
    write_json(base / "PLAN_FREEZE.json", value, exclusive=True)
    verify_freeze(base)
    print(json.dumps({"status": "frozen_not_executed", "source_count": len(hashes)}, ensure_ascii=False))


def serve(base):
    verify_freeze(base)
    require(not (base / "data").exists(), "Server data already exists; never resume a real attempt")
    os.environ["KITGUARD_DATA_DIR"] = str(base / "import-state")
    os.environ["KITGUARD_OBSERVATION_MODE"] = "spatial_guarded"
    os.environ["KITGUARD_MODEL_PATH"] = str(MODEL_PATH)
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(ROOT))
    import uvicorn

    from kitguard.app import create_app
    from kitguard.vision import LocalVision

    engine = LocalVision(model_path=MODEL_PATH, observation_mode="spatial_guarded", image_max_side=1536)
    status = engine.status()
    require(status["available"] and not status["loaded"], "Real model must be available and initially unloaded")
    require(status["repo_id"] == REPO and status["revision"] == REVISION, "Unexpected model identity")
    write_json(base / "server.json", {"pid": os.getpid(), "started_at": stamp(), "base_url": URL,
                                    "freeze_sha256": file_sha(base / "PLAN_FREEZE.json"), "model_before": status}, exclusive=True)
    app = create_app(data_dir=base / "data", analyzer=engine, inference_timeout=300, demo_dataset_root=ROOT / "datasets")
    try:
        uvicorn.run(app, host="127.0.0.1", port=8791, access_log=True)
    finally:
        write_json(base / "server-exit.json", {"exited_at": stamp(), "pid": os.getpid(), "model_final": engine.status()})


class HTTP:
    def __init__(self, base):
        self.base = base
        self.folder = base / "http"
        self.folder.mkdir(exist_ok=False)
        self.records = []

    def request(self, name, endpoint, body=None, *, raw_body=None, content_type=None, binary=False):
        raw = raw_body if raw_body is not None else (json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        headers = {"Content-Type": content_type or "application/json"} if raw is not None else {}
        method = "POST" if raw is not None else "GET"
        prefix = self.folder / f"{len(self.records)+1:03d}-{name}"
        record = {"name": name, "method": method, "endpoint": endpoint, "started_at": stamp(),
                  "headers": headers, "body": body, "request_body_sha256": sha(raw or b"")}
        prefix.with_suffix(".request.body").write_bytes(raw or b"")
        write_json(prefix.with_suffix(".request.json"), record)
        self.records.append(record)
        started, data, status = time.monotonic(), b"", None
        try:
            with urlopen(Request(URL+endpoint, data=raw, headers=headers, method=method), timeout=360) as response:
                status, data = response.status, response.read()
                record["response_headers"] = dict(response.headers)
        except HTTPError as exc:
            status, data = exc.code, exc.read()
            record["response_headers"] = dict(exc.headers)
        except Exception as exc:
            record["transport_error"] = str(exc)
        finally:
            record.update({"status": status, "elapsed_ms": round((time.monotonic()-started)*1000),
                           "response_sha256": sha(data), "response_bytes": len(data)})
            prefix.with_suffix(".response.body").write_bytes(data)
            write_json(prefix.with_suffix(".receipt.json"), record)
            write_json(self.base / "http-index.json", self.records)
        require(status is not None and status < 400, f"{name}: HTTP {status}: {data[:500]!r}")
        return data if binary else json.loads(data)


def uploaded_a41(http, spec):
    order = http.request("create-a41", "/api/orders", {"title": "PUBLIC InO A41 AUTHOR REGION · development integration",
                         "requirements": spec["requirements"]})["order"]
    boundary = "KitGuardV05IndependentFixedBoundary"
    raw = (ROOT / spec["image"]).read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"expected_revision\"\r\n\r\n1\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"A41.png\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode()+raw+f"\r\n--{boundary}--\r\n".encode()
    return http.request("upload-a41", f"/api/orders/{order['id']}/photos", raw_body=body,
                        content_type=f"multipart/form-data; boundary={boundary}")


def select_and_verify(http, base, spec, uploaded):
    order, root = uploaded["order"], uploaded["photo"]
    selected = http.request("select-"+spec["id"], f"/api/orders/{order['id']}/inspection-region", {
        "expected_revision": order["revision"], "expected_photo_id": root["id"],
        "expected_evidence_epoch": order["evidence_epoch"], "root_photo_id": root["id"],
        "mode": "region", "region_xyxy": spec["region_xyxy"], "confirmed_all_items_inside": True})
    folder = base / spec["id"]
    folder.mkdir(exist_ok=False)
    for label, photo in (("root", root), ("view", selected["photo"])):
        raw = http.request(f"{label}-"+spec["id"], photo["url"], binary=True)
        (folder / f"{label}.jpg").write_bytes(raw)
        require(sha(raw) == photo["sha256"] == spec[f"expected_{label}_sha256"], label+" image mismatch")
    require(root["source_sha256"] == spec["image_sha256"], "Root original-upload SHA differs")
    require(crop_bytes((folder / "root.jpg").read_bytes(), spec["region_xyxy"]) == (folder / "view.jpg").read_bytes(),
            "Independent region reconstruction differs")
    write_json(folder / "selected.json", selected)
    return selected


def runtime_check(status):
    require(status["repo_id"] == REPO and status["revision"] == REVISION, "Wrong real model identity")
    require(status["observation_mode"] == "spatial_guarded" and status["image_max_side"] == 1536,
            "Wrong model observation protocol")


def run(base):
    freeze = verify_freeze(base)
    require(not (base / "result.json").exists(), "Attempt exists; never retry or overwrite")
    require(read_json(base / "server.json")["freeze_sha256"] == file_sha(base / "PLAN_FREEZE.json"), "Wrong server freeze")
    plan = read_json(base / "SOURCE_PLAN.json")
    result = {"status": "running", "started_at": stamp(), "scope": plan["scope"], "planned_inspections": 2,
              "attempted_inspections": 0, "cases": [{"id": s["id"], "status": "not_started"} for s in plan["cases"]],
              "errors": [], "human_field_samples": 0}
    write_json(base / "result.json", result, exclusive=True)
    http = HTTP(base)
    study = None
    bindings = []

    def save():
        write_json(base / "result.json", result)

    def keep_error(stage, exc):
        result["errors"].append({"stage": stage, "error": str(exc), "at": stamp()})
        save()

    try:
        health = http.request("health-before", "/api/health")
        runtime_check(health["model"])
        require(not health["model"]["loaded"], "Run must start unloaded")
        require(not http.request("orders-before", "/api/orders")["orders"], "Real run database must be empty")
        write_json(base / "model-before.json", health)
        for spec in plan["cases"]:
            uploaded = (uploaded_a41(http, spec) if not spec["field_registration"] else
                        http.request("create-mixed", "/api/public-demos/mixed-screws/orders", {}))
            bindings.append(select_and_verify(http, base, spec, uploaded))
        mixed = plan["cases"][1]
        order, photo = bindings[1]["order"], bindings[1]["photo"]
        study = http.request("create-study", "/api/studies", {"title": "PUBLIC DEVELOPMENT REGION · actual MLX",
                 "source_kind": "public_replay", "planned_cases": 1, "participant_code": "scripted_replay", "note": NOTE})["study"]
        result["study_id"] = study["id"]
        study = http.request("register-mixed", f"/api/studies/{study['id']}/cases", {
            "label": "mixed-screws · scripted author truth · full-frame region", "order_id": order["id"],
            "expected_revision": order["revision"], "photo_id": photo["id"], "truth": mixed["ground_truth"],
            "truth_repeat": mixed["ground_truth"], "confirmed_independent": True, "source_note": NOTE})["study"]
        study = http.request("freeze-study", f"/api/studies/{study['id']}/freeze", {"confirmed": True})["study"]
        result["protocol_sha256"] = study["protocol_sha256"]
        save()
        for index, (spec, selected) in enumerate(zip(plan["cases"], bindings, strict=True)):
            item = result["cases"][index]
            order, photo = selected["order"], selected["photo"]
            item.update({"order_id": order["id"], "photo_id": photo["id"], "status": "running"})
            trial = None
            try:
                if spec["field_registration"]:
                    case = study["cases"][0]
                    manual = http.request("manual-start", f"/api/studies/{study['id']}/cases/{case['id']}/start", {"method": "manual"})["trial"]
                    http.request("manual-scripted", f"/api/studies/{study['id']}/trials/{manual['id']}/finish", {
                        "outcome": "completed", "manual_counts": spec["ground_truth"], "note": NOTE})
                    trial = http.request("ai-start", f"/api/studies/{study['id']}/cases/{case['id']}/start", {"method": "kitguard"})["trial"]
                result["attempted_inspections"] += 1
                item["inspect_attempted"] = True
                save()
                observed = http.request("inspect-"+spec["id"], f"/api/orders/{order['id']}/inspect", {
                    "photo_id": photo["id"], "expected_revision": order["revision"]})
                item["check"] = observed["check"]  # Preserve returned evidence before validation/finish.
                save()
                check = item["check"]
                require(check["backend"] == "mlx", "Real MLX only; no test/fallback check")
                runtime_check(check["runtime_identity"])
                item["internal_observation_passes"] = len(check.get("observation_verification", {}).get("passes", []))
                item["identity_review_status"] = check.get("identity_verification", {}).get("status")
                require(check["inspection_scope"]["region_xyxy"] == spec["region_xyxy"]
                        and check["inspection_scope"]["root_photo_sha256"] == spec["expected_root_sha256"]
                        and check["photo_sha256"] == spec["expected_view_sha256"], "Check scope/input binding differs")
                if trial:
                    http.request("ai-finish", f"/api/studies/{study['id']}/trials/{trial['id']}/finish", {
                        "outcome": "completed", "check_id": check["id"]})
                else:
                    item["author_bracket_count_only"] = {"expected": 1, "observed": check["observed"]["bracket"],
                                                         "four_category_evaluation": False}
                item["status"] = "completed"
            except Exception as exc:
                item.update({"status": "failed", "error": str(exc)})
                keep_error(spec["id"], exc)
                if trial:
                    try:
                        http.request("ai-failed", f"/api/studies/{study['id']}/trials/{trial['id']}/finish", {
                            "outcome": "failed", "note": ("NO RETRY: "+str(exc))[:1000]})
                    except Exception as finish_error:
                        keep_error("record-ai-failure", finish_error)
            finally:
                try:
                    saved = http.request("order-after-"+spec["id"], f"/api/orders/{order['id']}")
                    write_json(base / spec["id"] / "order.json", saved)
                    require(not saved["order"]["completions"], "Physical completion was unexpectedly recorded")
                    raw = http.request("order-zip-"+spec["id"], f"/api/orders/{order['id']}/evidence.zip", binary=True)
                    (base / spec["id"] / "order-evidence.zip").write_bytes(raw)
                except Exception as export_error:
                    keep_error("order-export-"+spec["id"], export_error)
                save()
                print(json.dumps({"case": spec["id"], "status": item["status"],
                                  "decision": item.get("check", {}).get("decision")}), flush=True)
    except BaseException as exc:
        result["fatal_error"] = traceback.format_exc()
        keep_error("setup_or_execution", exc)
    finally:
        if study:
            try:
                result["study"] = http.request("close-study", f"/api/studies/{study['id']}/close", {"confirmed": True})["study"]
                for endpoint, filename in (("export", "public-replay.json"), ("report.html", "public-replay.html"),
                                           ("evidence.zip", "public-replay-evidence.zip")):
                    raw = http.request("study-export-"+endpoint.replace(".", "-"), f"/api/studies/{study['id']}/{endpoint}", binary=True)
                    (base / filename).write_bytes(raw)
            except Exception as exc:
                keep_error("study-close-export", exc)
        try:
            result["model_after"] = http.request("health-after", "/api/health")["model"]
        except Exception as exc:
            keep_error("final-health", exc)
        after = {name: file_sha(ROOT / name) if (ROOT / name).is_file() else None for name in freeze["source_sha256"]}
        result.update({"finished_at": stamp(), "source_sha256_after": after,
                       "source_changed": after != freeze["source_sha256"],
                       "status": "completed_with_errors" if result["errors"] else "completed"})
        if result["source_changed"]:
            result["status"] = "invalid_source_changed"
        save()
    return 0 if result["status"] == "completed" else 1


def verify_outputs(base):
    """Independent HTTP/file/ZIP consistency checks; never runs model inference."""
    plan, result = read_json(base / "SOURCE_PLAN.json"), read_json(base / "result.json")
    checks = []
    for row in read_json(base / "http-index.json"):
        prefix = next((base / "http").glob(f"*-{row['name']}.receipt.json")).with_suffix("").with_suffix("")
        require(file_sha(prefix.with_suffix(".request.body")) == row["request_body_sha256"], "HTTP request SHA differs")
        require(file_sha(prefix.with_suffix(".response.body")) == row["response_sha256"], "HTTP response SHA differs")
    inspections = [r for r in read_json(base / "http-index.json") if r["endpoint"].endswith("/inspect")]
    require(len(inspections) == result["attempted_inspections"] <= 2, "Inference request count differs")
    require(not result["source_changed"], "Sources changed during execution")
    for spec in plan["cases"]:
        folder = base / spec["id"]
        root, view = (folder / "root.jpg").read_bytes(), (folder / "view.jpg").read_bytes()
        require(sha(root) == spec["expected_root_sha256"] and sha(view) == spec["expected_view_sha256"], "Saved image SHA differs")
        require(crop_bytes(root, spec["region_xyxy"]) == view, "Saved derived bytes do not reconstruct")
        checks.append({"case": spec["id"], "root_sha256": sha(root), "view_sha256": sha(view), "region_xyxy": spec["region_xyxy"]})
    archives = []
    for path in sorted(base.rglob("*.zip")):
        with ZipFile(path) as archive:
            require(archive.testzip() is None, "ZIP CRC failure")
            files = read_json_bytes(archive.read("SHA256.json")) if "SHA256.json" in archive.namelist() else read_json_bytes(archive.read("MANIFEST.json"))["files"]
            for entry in files:
                raw = archive.read(entry["path"])
                require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], "ZIP member mismatch")
            hashes = {sha(archive.read(name)) for name in archive.namelist() if name.endswith(".jpg")}
            spec = plan["cases"][0] if path.parent.name == plan["cases"][0]["id"] else plan["cases"][1]
            require({spec["expected_root_sha256"], spec["expected_view_sha256"]} <= hashes, "ZIP misses root/view")
        archives.append({"path": str(path.relative_to(base)), "sha256": file_sha(path)})
    require(len(archives) == 3, "Expected two order ZIPs and one closed-study ZIP")
    verified = subprocess.run([sys.executable, str(ROOT / "scripts/verify_study_export.py"), str(base / "public-replay.json"),
                               "--output", str(base / "study-export-verification.json")], capture_output=True, text=True, check=False)
    write_json(base / "independent-verifier-process.json", {"returncode": verified.returncode, "stdout": verified.stdout, "stderr": verified.stderr})
    require(verified.returncode == 0, "Independent closed-study verifier failed")
    receipt = {"verified_at": stamp(), "status": "verified", "attempted_inspections": len(inspections),
               "result_sha256": file_sha(base / "result.json"),
               "source_plan_sha256": file_sha(base / "SOURCE_PLAN.json"),
               "plan_freeze_sha256": file_sha(base / "PLAN_FREEZE.json"),
               "http_index_sha256": file_sha(base / "http-index.json"),
               "study_export_sha256": file_sha(base / "public-replay.json"),
               "study_verifier_receipt_sha256": file_sha(base / "study-export-verification.json"),
               "inputs": checks, "archives": archives, "scope": "Internal consistency only; no human, physical-completeness or new-accuracy certification."}
    write_json(base / "verification.json", receipt, exclusive=True)
    print(json.dumps(receipt, ensure_ascii=False))


def read_json_bytes(value):
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "freeze", "serve", "run", "verify"))
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument("--execute-real-model", action="store_true", help="Use only after explicit root start authorization")
    args = parser.parse_args()
    base = args.output.resolve()
    require(base.is_relative_to(ROOT / "test-results/browser"), "Use a dedicated project browser evidence directory")
    if args.phase in {"freeze", "serve", "run"}:
        require(args.execute_real_model, "Root authorization and --execute-real-model required; preparation does not grant it")
    if args.phase == "prepare":
        base.mkdir(parents=True, exist_ok=True)
        plan = source_plan()
        write_json(base / "SOURCE_PLAN.json", plan, exclusive=True)
        print(json.dumps({"status": plan["status"], "cases": [{"id": c["id"], "region_xyxy": c["region_xyxy"]} for c in plan["cases"]]}, ensure_ascii=False))
    elif args.phase == "freeze":
        freeze_sources(base)
    elif args.phase == "serve":
        serve(base)
    elif args.phase == "run":
        return run(base)
    else:
        verify_outputs(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
