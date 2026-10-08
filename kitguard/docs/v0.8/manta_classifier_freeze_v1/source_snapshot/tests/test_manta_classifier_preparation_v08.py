"""CPU contracts use synthetic pixels only; real MANTA use is metadata-only."""
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manta_classifier_prepare", ROOT / "scripts/v08/prepare_manta_classifier.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def real_metadata():
    return [json.loads(s) for s in (ROOT / m.META).read_text().splitlines()]


def png(mode="RGB", size=(500, 100), color=80, exif=None):
    image = Image.new(mode, size, color)
    if mode == "RGB":
        # Distinct synthetic panels, never actual data.
        for i in range(5):
            image.paste((20 + 30 * i, 40 + 30 * i, 70 + 20 * i), (i * (size[0] // 5), 0, (i + 1) * (size[0] // 5), size[1]))
    stream = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(stream, format="PNG", **kwargs)
    return stream.getvalue()


def row(i, role="validation", name="nut", block=None, duplicate=None, exposed=False):
    return {"index": i, "input_id": f"record-{i:04d}", "class_name": name,
            "proxy_block": block or f"{name}:{i}", "initial_role": role, "previously_exposed": exposed,
            "status": "prepared", "member_sha256": duplicate or f"raw-{i}",
            "composite_rgb_sha256": f"composite-{i}", "panel_rgb_sha256": [f"rgb-{i}-{j}" for j in range(5)],
            "panel_gray_sha256": [f"gray-{i}-{j}" for j in range(5)], "input_pixel_sha256": f"inp-{i}"}


def proposal():
    return {"source_image_sha256": "a" * 64, "source_width": 960, "source_height": 720,
            "proposal_id": "p1", "bbox_xyxy": [1, 2, 30, 40], "proposer_model_sha256": "b" * 64,
            "proposer_config_sha256": "c" * 64, "proposal_score": 0.7,
            "proposal_origin": "independent_detector"}


def test_actual_metadata_selection_reproducible_and_bounded():
    rows = real_metadata()
    selected, blocks = m.select_records(rows)
    reversed_selected, reversed_blocks = m.select_records(list(reversed(rows)))
    assert (selected, blocks) == (reversed_selected, reversed_blocks)
    assert len(selected) == 1024 and len(blocks) == 32
    assert sum(r["initial_role"] == "validation" for r in selected) == 256
    assert all("/train/good/" in r["member_path"] for r in selected)
    assert sum(r["previously_exposed"] for r in selected) == 4
    assert all(r["initial_role"] == "train" for r in selected if r["previously_exposed"])


def test_fixed_qa_covers_every_block_and_discloses_validation_exposure():
    selected, blocks = m.select_records(real_metadata())
    qa = [r for r in selected if r["visual_qa_selected"]]
    assert len(qa) == 36
    assert len({r["proxy_block"] for r in qa}) == len(blocks)
    assert sum(r["initial_role"] == "validation" for r in qa) == 8
    assert all(r["previously_exposed"] or (r["record_number"] - 1) % 32 == 15 for r in qa)


@pytest.mark.parametrize("edit", ["missing", "duplicate", "wrong_train_path", "oversized"])
def test_metadata_census_or_path_tamper_rejected(edit):
    rows = real_metadata()
    i = next(i for i, r in enumerate(rows) if r["split"] == "train")
    if edit == "missing":
        rows.pop(i)
    elif edit == "duplicate":
        rows.append(copy.deepcopy(rows[i]))
    elif edit == "wrong_train_path":
        rows[i]["image_path"] = rows[i]["image_path"].replace("train/good", "test/good")
    else:
        rows[i]["image_bytes"] = 32 * 1024 * 1024
    with pytest.raises(ValueError):
        m.select_records(rows)


def test_first_view_and_gray_bytes_reconstruct_exactly():
    data = png()
    facts, encoded, rgb, prepared = m.prepare_pixels(data)
    assert facts["crop_xyxy"] == [0, 0, 100, 100]
    assert len(facts["panel_rgb_sha256"]) == 5 and len(set(facts["panel_rgb_sha256"])) == 5
    assert facts["input_size"] == [224, 224] and m.digest(encoded) == facts["input_sha256"]
    assert prepared.getpixel((112, 112)) == rgb.crop((0, 0, 100, 100)).convert("L").convert("RGB").getpixel((50, 50))
    r, g, b = prepared.split()
    assert r.tobytes() == g.tobytes() == b.tobytes()
    assert m.pixel_sha(prepared) == facts["input_pixel_sha256"]


@pytest.mark.parametrize("data", [png(mode="RGBA"), png(size=(503, 100)), png(size=(100, 100)), png(size=(500, 300))])
def test_unsupported_layout_never_guesses(data):
    with pytest.raises(ValueError):
        m.prepare_pixels(data)


def test_exif_rejected_instead_of_silent_rotation():
    exif = Image.Exif()
    exif[274] = 6
    with pytest.raises(ValueError, match="EXIF"):
        m.prepare_pixels(png(exif=exif))


def test_pixel_hash_includes_dimensions():
    a = Image.new("RGB", (10, 20), "black")
    b = Image.new("RGB", (20, 10), "black")
    assert a.tobytes() == b.tobytes() and m.pixel_sha(a) != m.pixel_sha(b)


def test_proxy_blocks_and_transitive_duplicates_cannot_cross_roles():
    rows = [row(0, "train", block="nut:0"), row(1, "validation", duplicate="shared"),
            row(2, "validation", block="nut:2", duplicate="shared"), row(3, "validation", block="nut:2")]
    rows[0]["panel_rgb_sha256"][4] = rows[1]["panel_rgb_sha256"][0]
    result = m.group_records(rows)
    assert len(result["groups"]) == 1
    assert {r["role"] for r in rows} == {"train"}
    assert len(result["duplicate_edges"]) >= 2


def test_exposure_forces_train_even_if_initial_partition_corrupted():
    rows = [row(0, exposed=True), row(1, duplicate="same")]
    rows[0]["member_sha256"] = "same"
    m.group_records(rows)
    assert {r["role"] for r in rows} == {"train"}


def test_cross_class_input_duplicate_quarantines_entire_proxy_component():
    rows = [row(0, "train", block="nut:0"), row(1, "validation", block="nut:0"),
            row(2, "validation", name="yellow_green_washer")]
    rows[0]["input_pixel_sha256"] = rows[2]["input_pixel_sha256"] = "identical-gray-input"
    result = m.group_records(rows)
    assert result["label_conflict_groups"] == 1
    assert {r["role"] for r in rows} == {"quarantined_label_conflict"}


def test_failed_and_not_attempted_rows_stay_in_population():
    rows = [row(0), row(1), row(2)]
    rows[1]["status"] = "failed"
    rows[2]["status"] = "not_attempted"
    result = m.group_records(rows)
    assert sum(len(g["members"]) for g in result["groups"]) == 3
    assert rows[1]["status"] == "failed" and rows[2]["status"] == "not_attempted"


def tar_fixture(path, entries):
    with tarfile.open(path, "w:gz") as stream:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.type = kind
            stream.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)


def test_extractor_never_requests_test_or_mask_payload(tmp_path, monkeypatch):
    wanted = "nut/train/good/mechanics_nut_00001.png"
    p = tmp_path / "archive.tar.gz"
    tar_fixture(p, [("nut/test/good/never.png", b"not decoded", tarfile.REGTYPE),
                    ("nut/ground_truth/a/mask.png", b"not decoded", tarfile.REGTYPE),
                    (wanted, b"selected", tarfile.REGTYPE)])
    calls = []
    original = tarfile.TarFile.extractfile

    def spy(self, member):
        calls.append(member.name)
        return original(self, member)
    monkeypatch.setattr(tarfile.TarFile, "extractfile", spy)
    items = list(m.extract_selected(p, {wanted: {"member_bytes": 8}}))
    assert calls == [wanted] and items[0][1] == b"selected"


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_selected_links_rejected(tmp_path, kind):
    name = "nut/train/good/mechanics_nut_00001.png"
    p = tmp_path / "archive.tar.gz"
    tar_fixture(p, [(name, b"", kind)])
    with pytest.raises(ValueError, match="regular"):
        list(m.extract_selected(p, {name: {"member_bytes": 0}}))


def test_duplicate_or_missing_selected_member_rejected(tmp_path):
    name = "nut/train/good/mechanics_nut_00001.png"
    p = tmp_path / "archive.tar.gz"
    tar_fixture(p, [(name, b"x", tarfile.REGTYPE), (name, b"x", tarfile.REGTYPE)])
    with pytest.raises(ValueError, match="Repeated"):
        list(m.extract_selected(p, {name: {"member_bytes": 1}}))
    with pytest.raises(ValueError, match="Missing"):
        list(m.extract_selected(p, {name.replace("00001", "00002"): {"member_bytes": 1}}))


def test_immutable_json_never_overwrites(tmp_path):
    p = tmp_path / "receipt.json"
    m.dump_new(p, {"original": True})
    with pytest.raises(FileExistsError):
        m.dump_new(p, {"original": False})
    assert m.read(p) == {"original": True}


@pytest.mark.parametrize("key,value", [("proposal_origin", "vlm_point"), ("proposal_origin", "author_ground_truth"),
                                      ("bbox_xyxy", [0, 0, 961, 10]), ("bbox_xyxy", [0, 0, float("nan"), 10]),
                                      ("proposal_score", True), ("ground_truth", {"nut": 1}), ("bom", {"nut": 1})])
def test_proposal_boundary_rejects_nonindependent_or_invalid(key, value):
    p = proposal()
    p[key] = value
    with pytest.raises(ValueError):
        m.validate_proposal(p)


def test_proposal_contract_accepts_original_pixel_coordinates():
    assert m.validate_proposal(proposal()) is True


def test_module_import_does_not_import_models_or_pillow():
    code = f"import runpy,sys;runpy.run_path({str(ROOT / m.SCRIPT)!r});assert 'torch' not in sys.modules;assert 'PIL.Image' not in sys.modules;assert not any(k.startswith('mlx') for k in sys.modules)"
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_interrupted_decode_preserves_failed_attempt_and_remaining_not_attempted(tmp_path, monkeypatch):
    records = []
    for i in range(3):
        r = row(i)
        r.update(member_path=f"nut/train/good/mechanics_nut_{i+1:05d}.png", visual_qa_selected=False)
        records.append(r)
    protocol = {"records": records, "archives": [{"class_name": "nut", "path": "fake.tar.gz"}]}
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    m.dump_new(frozen / "protocol.json", protocol)
    m.dump_new(frozen / "freeze.json", {})
    monkeypatch.setattr(m, "verify_freeze", lambda *a, **k: protocol)
    monkeypatch.setattr(m, "extract_selected", lambda archive, targets: ((r, b"payload") for r in targets.values()))

    def interrupt(data):
        raise KeyboardInterrupt("synthetic stop")
    monkeypatch.setattr(m, "prepare_pixels", interrupt)
    out = tmp_path / "prepared"
    with pytest.raises(KeyboardInterrupt):
        m.prepare(tmp_path, frozen / "freeze.json", "test-only", out)
    saved = m.read(out / "records.json")
    assert [r["status"] for r in saved] == ["failed", "not_attempted", "not_attempted"]
    assert saved[0]["error"]["type"] == "KeyboardInterrupt"
    receipt = m.read(out / "preparation.json")
    assert receipt["status"] == "blocked" and receipt["training_authorized"] is False
    assert receipt["processing_error"]["message"] == "synthetic stop"
    assert len((out / "attempts.jsonl").read_text().splitlines()) == 1
