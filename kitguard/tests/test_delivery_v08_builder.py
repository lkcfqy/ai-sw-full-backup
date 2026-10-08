"""CPU-only packaging contracts: synthetic files/archives, no model or image decode."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.v08 import build_delivery as b


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b.encoded(value))


def file(path, data=b"synthetic receipt\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def plan(tmp_path):
    paths = dict(b.FIXED)
    paths.update(report="output/report/preview/report.pdf", technical="output/report/preview/technical.pdf",
                 slides="output/slides/preview/slides.pptx", source="output/source-preview.zip",
                 source_smoke="output/source-preview.zip.verification.json")
    rows = []
    for role, name in paths.items():
        p = file(tmp_path / name, (role + "\n").encode())
        prefix = "materials" if role in b.PRIMARY else "evidence"
        rows.append({"role": role, "path": name, "sha256": b.sha(p), "destination": f"{prefix}/{role}/{p.name}", "title": role})
    return {"schema": b.SCHEMA, "version": b.VERSION, "preview": True, "output_directory": "output/delivery-preview-fixture",
                "output_zip": "output/delivery-preview-fixture.zip", "files": rows}


def test_explicit_plan_all_inputs_bound_without_collecting_neighbors(tmp_path, plan):
    file(tmp_path / "output/private.sqlite3", b"must not be scanned or copied")
    rows, paths, _, _ = b.validate_plan(plan, tmp_path)
    assert set(rows) == b.REQUIRED == set(paths)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "duplicate", "hash", "pending_hash", "outside", "symlink",
                                     "destination_traversal", "destination_collision", "wrong_version", "not_preview",
                                     "old_output", "zip_inside", "private_swap", "extension_swap", "wrong_smoke"])
def test_plan_refuses_unsafe_or_incomplete_inputs(tmp_path, plan, mutation):
    first = plan["files"][0]
    if mutation == "missing":
        plan["files"].pop()
    elif mutation == "unknown":
        plan["files"].append({**first, "role": "arbitrary_attachment"})
    elif mutation == "duplicate":
        plan["files"].append(dict(first))
    elif mutation == "hash":
        first["sha256"] = "0" * 64
    elif mutation == "pending_hash":
        first["sha256"] = "pending"
    elif mutation == "outside":
        first["path"] = "../outside.md"
    elif mutation == "symlink":
        p = tmp_path / first["path"]
        other = file(tmp_path / "synthetic.md")
        p.unlink()
        p.symlink_to(other)
    elif mutation == "destination_traversal":
        first["destination"] = "evidence/../private.md"
    elif mutation == "destination_collision":
        plan["files"][1]["destination"] = first["destination"].upper()
    elif mutation == "wrong_version":
        plan["version"] = "0.7.0"
    elif mutation == "not_preview":
        plan["preview"] = False
    elif mutation == "old_output":
        (tmp_path / plan["output_directory"]).mkdir(parents=True)
    elif mutation == "zip_inside":
        plan["output_zip"] = plan["output_directory"] + "/delivery-preview.zip"
    elif mutation == "private_swap":
        p = file(tmp_path / "data/private.md")
        first.update(path="data/private.md", sha256=b.sha(p))
    elif mutation == "extension_swap":
        first["destination"] += ".jpg"
    else:
        row = next(r for r in plan["files"] if r["role"] == "source_smoke")
        p = file(tmp_path / "wrong.json")
        row.update(path="wrong.json", sha256=b.sha(p))
    with pytest.raises(ValueError):
        b.validate_plan(plan, tmp_path)


def test_old_video_requires_matching_pair_and_disclosure(tmp_path, plan):
    p = file(tmp_path / b.OPTIONAL["historical_video"])
    row = {"role": "historical_video", "path": b.OPTIONAL["historical_video"], "sha256": b.sha(p),
               "destination": "materials/old.mp4", "title": "New feature demo"}
    plan["files"].append(row)
    with pytest.raises(ValueError, match="requires its receipt"):
        b.validate_plan(plan, tmp_path)
    p2 = file(tmp_path / b.OPTIONAL["historical_video_receipt"])
    plan["files"].append({"role": "historical_video_receipt", "path": b.OPTIONAL["historical_video_receipt"],
                              "sha256": b.sha(p2), "destination": "evidence/video.json", "title": "Historical receipt"})
    with pytest.raises(ValueError, match="label"):
        b.validate_plan(plan, tmp_path)
    row["title"] = b.VIDEO_LABEL
    b.validate_plan(plan, tmp_path)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links += [v for k, v in attrs if k == "href"]


def test_synthetic_build_every_offline_link_hash_and_zip_member(tmp_path, plan, monkeypatch):
    # Packaging is exercised end-to-end; semantic domain checks have separate tests below.
    monkeypatch.setattr(b, "validate_evidence", lambda paths, root: {"synthetic_fixture_only": True})
    plan["files"][0]["title"] = '<script>alert("x")</script> & 文档'
    p = tmp_path / "synthetic-plan.json"
    save(p, plan)
    result = b.build(p, tmp_path)
    folder = Path(result["output_directory"])
    manifest = b.read(folder / "BUILD_MANIFEST.json")
    assert manifest["plan_sha256"] == b.sha(p)
    assert (folder / "PLAN.json").read_bytes() == p.read_bytes()
    assert manifest["published_or_submitted"] is False
    markup = (folder / "START_HERE.html").read_text()
    assert "&lt;script&gt;" in markup and '<script>alert' not in markup
    assert "41C / 3W / 7U" in markup and "23C / 0W / 1U" in markup and b.VIDEO_LABEL in markup
    parser = Links()
    parser.feed(markup)
    assert len(parser.links) == len(plan["files"]) + 4
    assert all((folder / unquote(link)).is_file() for link in parser.links)
    assert b.verify_bundle(folder, Path(result["output_zip"]))["status"] == "passed"
    with pytest.raises(ValueError, match="never overwritten"):
        b.build(p, tmp_path)
    (folder / plan["files"][0]["destination"]).write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        b.verify_bundle(folder, Path(result["output_zip"]))


def test_source_race_stops_before_output_creation(tmp_path, plan, monkeypatch):
    def validation(paths, root):
        paths["readme"].write_text("changed after verification")
        return {}
    monkeypatch.setattr(b, "validate_evidence", validation)
    p = tmp_path / "plan.json"
    save(p, plan)
    with pytest.raises(ValueError, match="changed during"):
        b.build(p, tmp_path)
    assert not (tmp_path / plan["output_directory"]).exists()


@pytest.fixture
def loco(tmp_path, monkeypatch):
    paths = {k: tmp_path / v for k, v in b.FIXED.items() if k.startswith("loco_")}
    outcomes = {"C": 23, "W": 0, "U": 1, "E": 0, "N": 0}
    group = {"planned": 24, "outcomes": outcomes, "groups": [{"planned": 6}] * 4,
             "matched_order_applicable": 12, "matched_order_not_applicable": 12, "matched_order_correct_ready": 11,
             **{k: {"planned_image_denominator": 24, "observed_any_false_ready_images": 0, "unmeasured_images": 0}
                for k in ("all_four_panel", "source_supported_panel")}}
    analysis = {"methods": {"spatial_guarded": group}, "planned_cases": 24, "planned_observations": 24,
                "historical_normal16": {"exposed_nonconcurrent_not_pooled": True, "methods": {"spatial_guarded": {"planned": 16}}}}
    for k in ("freeze", "selection", "failure", "repair", "result"):
        save(paths["loco_" + k], {"synthetic": k})
    freeze_sha = b.sha(paths["loco_freeze"])
    monkeypatch.setattr(b, "LOCO_FREEZE", freeze_sha)
    save(paths["loco_run"], {"status": "completed", "planned": 24, "completed_attempts": 24,
                                "final_integrity_verified": True, "source_changed": False, "freeze_sha256": freeze_sha})
    save(paths["loco_predictions"], [{"case_id": str(n)} for n in range(24)])
    save(paths["loco_analysis"], analysis)
    audit = {"status": "passed", "completed_attempts": 24, "model_loaded_or_called": False, "independent_analysis": analysis,
                 "evidence_sha256": {k: b.sha(paths["loco_" + k]) for k in ("freeze", "run", "analysis", "predictions", "selection")}}
    save(paths["loco_audit"], audit)
    monkeypatch.setattr(b, "LOCO_AUDIT", b.sha(paths["loco_audit"]))
    save(paths["loco_decision"], {"outcomes": outcomes, "production_unchanged": True, "automatic_promotion": False,
                                    "evidence": [{"path": b.FIXED[k], "sha256": b.sha(paths[k])} for k in
                                              ("loco_result", "loco_audit", "loco_failure", "loco_repair")]})
    return paths


def test_loco_exact_audit_and_separate_historical_population(loco):
    result = b.loco_evidence(loco)
    assert result["population"] == 24 and result["outcomes"]["C"] == 23
    assert "never pooled" in result["historical_normal16"]


@pytest.mark.parametrize("key", ["run", "analysis", "predictions", "selection", "freeze", "audit", "result", "failure", "repair"])
def test_loco_same_json_new_bytes_rejected(loco, key):
    with loco["loco_" + key].open("ab") as f:
        f.write(b" \n")
    with pytest.raises(ValueError):
        b.loco_evidence(loco)


def test_loco_incomplete_stops_before_reading_predictions(loco):
    run = b.read(loco["loco_run"])
    run.update(status="running", completed_attempts=23)
    save(loco["loco_run"], run)
    loco["loco_predictions"].unlink()
    with pytest.raises(ValueError, match="complete"):
        b.loco_evidence(loco)


@pytest.fixture
def api(tmp_path, monkeypatch):
    paths = {k: tmp_path / v for k, v in b.FIXED.items() if k.startswith("api_")}
    raw = b"synthetic jpg payload, no decode"
    monkeypatch.setattr(b, "API_STORAGE", b.digest(raw))
    for k in ("api_source_before", "api_source_after", "api_model_receipt"):
        save(paths[k], {"synthetic": True})
    plan = {"purpose": "real_mlx_photo_document_api_integration", "source_sha256": b.API_SOURCE,
                "source_already_exposed": True, "human_participants": 0, "physical_completion": False, "accuracy_evaluation": False,
                "source_before_sha256": b.sha(paths["api_source_before"])}
    save(paths["api_plan"], plan)
    for n in (1, 2):
        save(paths[f"api_observer_r{n}"], {"loaded": True, "observation_mode": "spatial_guarded",
             "last_observation_attempt": {"generation_calls": [{"status": "parsed", "model_call_started": True,
                       "model_call_completed": True, "raw_text": '{"synthetic":true}'}] * 3}})
    photos = [{"revision": n, "source_sha256": b.API_SOURCE, "sha256": b.API_STORAGE, "physical_capture": False,
                   "archive_path": f"photos/synthetic-{n}.jpg"} for n in (1, 2)]
    evidence = {"photos": photos, "order": {"document_source": {"source_sha256": b.API_SOURCE,
                    "verification": "user_declared_unverified", "physical_completion_allowed": False,
                    "license_note": "MVTec · CC BY-NC-SA 4.0"}, "checks": [{}, {}], "completions": []}}
    payload = {p["archive_path"]: raw for p in photos} | {"evidence.json": b.encoded(evidence), "OPEN_ME.html": b"synthetic"}
    payload["SHA256.json"] = b.encoded([{"path": k, "bytes": len(v), "sha256": b.digest(v)} for k, v in payload.items()])
    payload["README.txt"] = b"synthetic"
    paths["api_zip"].parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(paths["api_zip"], "w", ZIP_DEFLATED) as z:
        for k, v in payload.items():
            z.writestr(k, v)
    receipt = {"status": "passed", "inspect_attempts": 2, "human_participants": 0, "model_calls_started": 6,
                   "model_calls_completed": 6, "source_unchanged": True, "replay_model_calls": 0,
                   "physical_completion_rejections": 2, "physical_completion": False,
                   "source_after_sha256": b.sha(paths["api_source_after"]),
                   "full_model_sha256_receipt": b.sha(paths["api_model_receipt"]), "evidence_zip_sha256": b.sha(paths["api_zip"])}
    save(paths["api_receipt"], receipt)
    return paths


def test_actual_call_boundaries_and_two_image_api_scope(api):
    assert b.api_evidence(api)["real_generation_calls"] == 6


@pytest.mark.parametrize("mutation", ["human", "model_calls", "source_changed", "call_not_completed", "source_bytes", "extra_image"])
def test_api_cannot_relabel_synthetic_or_add_private_picture(api, mutation):
    r = b.read(api["api_receipt"])
    if mutation == "human":
        r["human_participants"] = 1
    elif mutation == "model_calls":
        r["model_calls_completed"] = 5
    elif mutation == "source_changed":
        r["source_unchanged"] = False
    elif mutation == "call_not_completed":
        o = b.read(api["api_observer_r1"])
        o["last_observation_attempt"]["generation_calls"][0]["model_call_completed"] = False
        save(api["api_observer_r1"], o)
    elif mutation == "source_bytes":
        save(api["api_source_after"], {"changed": True})
    else:
        with ZipFile(api["api_zip"], "a") as z:
            z.writestr("photos/private.jpg", b"not authorized")
        r["evidence_zip_sha256"] = b.sha(api["api_zip"])
    save(api["api_receipt"], r)
    with pytest.raises(ValueError):
        b.api_evidence(api)


def test_zip_rejects_traversal_and_symlink(tmp_path):
    from zipfile import ZipInfo
    for kind in ("path", "symlink"):
        p = tmp_path / (kind + ".zip")
        with ZipFile(p, "w") as z:
            info = ZipInfo("../escape" if kind == "path" else "link")
            if kind == "symlink":
                info.external_attr = 0o120777 << 16
            z.writestr(info, b"target")
        with ZipFile(p) as z, pytest.raises(ValueError):
            b.zip_members(z)


def test_import_is_cpu_only():
    import sys
    assert not any(n == "mlx" or n.startswith("mlx.") for n in sys.modules)


@pytest.fixture
def source_zip(tmp_path, monkeypatch):
    from scripts.v07 import package_source as old
    from scripts.v08 import package_source as new
    samples = [{"sample_id": name, "archive_path": f"datasets/raw/demo/{name}.jpg",
                "source_sha256": b.digest(name.encode()), "license": "MVTec · CC BY-NC-SA 4.0",
                "source_url": "https://www.mvtec.com/synthetic-fixture"}
               for name in sorted(old.DEMO_IDS)]
    monkeypatch.setattr(old, "public_samples", lambda root: samples)
    payload = {name: b"" for name in new.REQUIRED}
    payload["pyproject.toml"] = f'[project]\nversion="{b.VERSION}"\n'.encode()
    payload["kitguard/__init__.py"] = f'__version__ = "{b.VERSION}"\n'.encode()
    payload.update({s["archive_path"]: s["sample_id"].encode() for s in samples})
    paths = {"source": tmp_path / "source.zip", "source_smoke": tmp_path / "source.zip.verification.json"}

    def rebuild():
        records = [{"path": name, "bytes": len(data), "sha256": b.digest(data)} for name, data in payload.items()]
        manifest = {"schema": "kitguard.v08.source-package.v1", "version": b.VERSION, "preview": True,
                    "full_experiment_reproduction_self_contained": False, "public_samples": samples, "files": records}
        with ZipFile(paths["source"], "w") as z:
            for name, data in payload.items():
                z.writestr("KitGuard/" + name, data)
            z.writestr("KitGuard/SOURCE_MANIFEST.json", b.encoded(manifest))
        smoke = {"status": "passed", "archive_sha256": b.sha(paths["source"]), "version": b.VERSION,
                 "preview": True, "shell_syntax": "passed", "runtime": {
                     "version": b.VERSION, "synthetic": True, "model_calls": 0, "human_participants": 0,
                     "mlx_imported": False, "multipart_create": 201, "root_replace": 409,
                     "physical_complete": 409, "zip_manifest_verified": True}}
        save(paths["source_smoke"], smoke)
    rebuild()
    return paths, payload, rebuild


def test_source_exact_preview_version_three_demos_and_extracted_smoke(source_zip, tmp_path):
    paths, _, _ = source_zip
    assert b.source_evidence(paths, tmp_path)["demo_images"] == 3


@pytest.mark.parametrize("mutation", ["database", "raw_tree", "extra_photo", "other_binary", "missing_module",
                                     "actual_version", "false_smoke", "wrong_zip_smoke", "runtime", "secret", "raw_text", "large_text"])
def test_source_extra_data_old_version_or_unbound_smoke_rejected(source_zip, tmp_path, mutation):
    paths, payload, rebuild = source_zip
    if mutation == "database":
        payload["data/kitguard.sqlite3"] = b"private"
    elif mutation == "raw_tree":
        payload["docs/v0.8/source_snapshot/secret.py"] = b""
    elif mutation == "extra_photo":
        payload["datasets/raw/manta/unapproved.jpg"] = b"extra image"
    elif mutation == "other_binary":
        payload["docs/private.pdf"] = b"other binary"
    elif mutation == "missing_module":
        del payload["kitguard/photo_documents.py"]
    elif mutation == "runtime":
        payload["docs/fixture.runtime-app-data/state.json"] = b"{}"
    elif mutation == "secret":
        payload["docs/secrets.json"] = b"{}"
    elif mutation == "raw_text":
        payload["datasets/raw/manta/annotation.txt"] = b"not a declared demo"
    elif mutation == "large_text":
        payload["docs/too-large.txt"] = b"0" * (b.MAX_SMALL + 1)
    elif mutation == "actual_version":
        payload["kitguard/__init__.py"] = b'__version__ = "0.7.0"\n'
    rebuild()
    if mutation in {"false_smoke", "wrong_zip_smoke"}:
        smoke = b.read(paths["source_smoke"])
        if mutation == "false_smoke":
            smoke["runtime"]["multipart_create"] = 422
        else:
            smoke["archive_sha256"] = "0" * 64
        save(paths["source_smoke"], smoke)
    with pytest.raises(ValueError):
        b.source_evidence(paths, tmp_path)


def test_primary_browser_cannot_point_to_synthetic_fixture(tmp_path, plan):
    row = next(x for x in plan["files"] if x["role"] == "browser_receipt")
    wrong = b.SYNTHETIC_BROWSER_BASE + "browser-receipt.json"
    p = file(tmp_path / wrong)
    row.update(path=wrong, sha256=b.sha(p))
    with pytest.raises(ValueError, match="Unapproved source"):
        b.validate_plan(plan, tmp_path)


def test_real_browser_fields_are_not_a_synthetic_or_new_inference_claim(tmp_path):
    paths = {k: tmp_path / v for k, v in b.FIXED.items() if k.startswith(("browser_", "tests_")) or k in {"ruff_log", "api_receipt"}}
    file(paths["tests_xml"], ('<testsuites><testsuite>' + '<testcase name="fixture"/>' * 1530 + '</testsuite></testsuites>').encode())
    file(paths["tests_log"], b"1530 passed, 2 warnings in 42.49s\n")
    file(paths["ruff_log"], b"All checks passed!\n")
    save(paths["api_receipt"], {"order_id": "synthetic-contract"})
    for role in ("browser_ko", "browser_zh"):
        file(paths[role])
    download = {"order_equals_original_api_export": True, "checks": 2, "public_reviews": 2, "public_replays": 1,
                "completions": 0, "all_reviews_engineering_agent_zero_humans": True, "zip_sha256": "1" * 64}
    save(paths["browser_download_receipt"], download)
    receipt = {"schema": "kitguard.v08.photo-document-live-browser.v1", "status": "passed_read_only_display_and_download",
               "human_participants": 0, "saved_order_unchanged": True, "production_source_changed_since_real_api_run": [],
               "limitations": ["upload and file:// not verified"], "order_id": "synthetic-contract",
               "prior_real_api_run": {"receipt_sha256": b.sha(paths["api_receipt"])}, "browser_scope": {
                   "http_request_methods_observed": ["GET"], "http_request_count": 31, "get_only_service_enforced": True,
                   "additional_model_calls": 0, "new_review_or_mutation_requests": 0, "mlx_imported": False, "actual_zip_download": True},
               "artifacts_sha256": {b.FIXED[k]: b.sha(paths[k]) for k in ("browser_ko", "browser_zh", "browser_download_receipt")}}
    receipt["artifacts_sha256"][b.BROWSER_BASE + "browser-download-evidence.zip"] = "1" * 64
    save(paths["browser_receipt"], receipt)
    assert "31 GET" in b.engineering_evidence(paths)["browser"]
    receipt["browser_scope"]["additional_model_calls"] = 1
    save(paths["browser_receipt"], receipt)
    with pytest.raises(ValueError, match="zero new model"):
        b.engineering_evidence(paths)


def test_pdf_sources_and_visual_qa_bind_exact_primary_bytes(tmp_path, monkeypatch):
    paths = {"report": file(tmp_path / "output/report.pdf", b"fakepdf5"),
             "technical": file(tmp_path / "output/technical.pdf", b"fakepdf1"),
             "slides": tmp_path / "output/slides.pptx"}
    monkeypatch.setattr(b, "pdf_pages", lambda p: 5 if p == paths["report"] else 1)
    with ZipFile(paths["slides"], "w") as z:
        z.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst>'
                   + '<p:sldId/>' * 8 + '</p:sldIdLst></p:presentation>')
    sources = {}
    for i in range(1, 18):
        p = file(tmp_path / f"evidence/{i}.json", b"synthetic numeric evidence")
        paths[f"source{i}"] = p
        sources[f"E{i}"] = {"path": p.relative_to(tmp_path).as_posix(), "sha256": b.sha(p)}
    paths.update(report_sources=tmp_path / "sources.json", report_qa=tmp_path / "qa.json", slides_qa=tmp_path / "slideqa.json")
    save(paths["report_sources"], {"sources": sources})
    save(paths["report_qa"], {"status": "passed", "version": b.VERSION,
         "release_status": "development_preview_not_released_or_submitted", "source_evidence_sha256": b.sha(paths["report_sources"]),
         "pdf_documents": [{"path": paths[k].relative_to(tmp_path).as_posix(), "sha256": b.sha(paths[k]), "pages": n}
                           for k, n in (("report", 5), ("technical", 1))]})
    save(paths["slides_qa"], {"status": "passed", "preview": True, "version": b.VERSION, "slide_count": 8,
         "output": {"sha256": b.sha(paths["slides"]), "path": paths["slides"].relative_to(tmp_path).as_posix()},
         "visual_qa": {"all_final_slides_rendered_and_individually_viewed": True}})
    assert b.presentation_evidence(paths, tmp_path)["pdf_cited_sources_copied"] == 17
    paths["source17"].write_text("edited source after PDF QA")
    with pytest.raises(ValueError, match="PDF cited source"):
        b.presentation_evidence(paths, tmp_path)


def test_source_all14_registered_model_notices_are_text_not_weights(source_zip, tmp_path):
    paths, payload, rebuild = source_zip
    assert len(b.MODEL_NOTICE_SHA256) == 14
    for name, expected in b.MODEL_NOTICE_SHA256.items():
        blob = (b.ROOT / name).read_bytes()  # Existing licensed text only; no model payload or image.
        assert b.digest(blob) == expected and "\x00" not in blob.decode("utf-8")
        payload[name] = blob
    rebuild()
    assert b.source_evidence(paths, tmp_path)["extracted_smoke"] == "passed"


@pytest.mark.parametrize("kind", ["unknown_notice", "changed_notice", "weights", "other_models_dir"])
def test_source_model_notice_exception_is_not_a_general_models_allowance(source_zip, tmp_path, kind):
    paths, payload, rebuild = source_zip
    if kind == "unknown_notice":
        payload["third_party/models/unregistered/README.md"] = b"Not registered"
    elif kind == "changed_notice":
        payload[next(iter(b.MODEL_NOTICE_SHA256))] = b"Changed registered notice"
    elif kind == "weights":
        payload["third_party/models/Qwen3.6-27B/model.safetensors"] = b"weights"
    else:
        payload["docs/models/README.md"] = b"Different models directory"
    rebuild()
    with pytest.raises(ValueError, match="registered exact model notice"):
        b.source_evidence(paths, tmp_path)
