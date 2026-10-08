"""Video provenance guards with synthetic fixtures, no inference or FFmpeg encoding."""

import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.v07 import build_demo_video as video


def write_json(path, value):
    path.write_bytes(video.encoded(value))


@pytest.fixture
def captures(tmp_path):
    source = tmp_path / "captures"
    source.mkdir()
    plan = json.loads(video.DEFAULT_PLAN.read_bytes())
    plan["shots"] = [plan["shots"][0], plan["shots"][-1]]
    plan_path = tmp_path / "plan.json"
    write_json(plan_path, plan)
    timeline = []
    for index, shot in enumerate(plan["shots"]):
        path = source / shot["file"]
        # The real capture tool used JPEG bytes with .png filenames; preserve this case.
        Image.new("RGB", (800, 600), (index * 20, 30, 40)).save(path, format="JPEG")
        timeline.append({"name": path.name, "captured_at": f"2026-10-01T21:2{index}:00+00:00", "url": "http://localhost/fixture"})
    write_json(source / "timeline.json", timeline)
    expected = plan["expected_evidence"]
    checks = [{**{k: v for k, v in match.items() if k != "required_bolt"}, "id": f"check-{index}",
               "requirements_snapshot": {"bolt": match["required_bolt"]}, "observed": expected["observed"],
               "backend": "mlx", "photo_sha256": "synthetic-family"}
              for index, match in enumerate(expected["checks"])]
    order = {"id": expected["order_id"], "demo_source": {"sample_id": "bag-revision", "source_case_id": "synthetic",
             "license": "synthetic fixture, not a photograph", "source_url": "https://example.invalid/fixture"},
             "checks": checks, "public_reviews": [{"operator_code": "DEMO-AUTOMATION", "conclusion": "inconclusive",
             "physical_completion": False, "user_validation": False}] * 2, "public_replays": [{}], "completions": []}
    write_json(source / "order.json", {"order": order})
    write_json(source / "review-summary.json", {"order_id": order["id"], "current_review": {"check_id": checks[-1]["id"]}})
    (source / "evidence.zip").write_bytes(b"Synthetic evidence bytes, never a real export")
    write_json(source / "verification.json", {"order_id": order["id"], "automation_engineering_trial": True,
               "real_user_validation": False, "physical_action_validated": False, "public_reviews": 2,
               "public_replays": 1, "physical_completions": 0,
               "zip_sha256": video.sha((source / "evidence.zip").read_bytes()),
               "screenshots": [{**row, "sha256": video.sha((source / row["name"]).read_bytes())} for row in timeline]})
    return source, plan_path


def test_preparation_preserves_bytes_and_does_not_launch_media_process(captures, tmp_path, monkeypatch):
    source, plan_path = captures
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    monkeypatch.setattr(video, "run", lambda *a, **k: pytest.fail("Preparation must not launch processes"))
    output = tmp_path / "prepared"
    receipt = video.prepare(video.load_inputs(source, plan_path), output)
    assert receipt["status"] == "prepared_not_encoded"
    assert receipt["continuous_realtime_recording"] is False
    assert receipt["original_capture_files_modified"] is False
    assert all(row["file_format"] == "JPEG" for row in receipt["inputs"])
    for item in receipt["render_inputs"]:
        assert item["path"].endswith(".jpg")
        assert (output / item["path"]).read_bytes() == (source / item["original_file"]).read_bytes()
        assert video.sha((output / item["path"]).read_bytes()) == item["sha256"]
    assert "render-inputs/01-public-library.jpg" in (output / "shots.ffconcat").read_text()
    assert ".png'" not in (output / "shots.ffconcat").read_text()
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert not list(output.glob("*.mp4"))
    assert video.EDIT_LABEL in (output / "captions.ass").read_text()
    with pytest.raises(FileExistsError):
        video.prepare(video.load_inputs(source, plan_path), output)


def test_input_mutation_after_preflight_cannot_be_staged(captures, tmp_path):
    source, plan_path = captures
    data = video.load_inputs(source, plan_path)
    next(source.glob("*.png")).write_bytes(b"changed after preflight")
    output = tmp_path / "staging"
    output.mkdir()
    with pytest.raises(ValueError, match="changed before staging"):
        video.stage_captures(data, output)


@pytest.mark.parametrize("mutation", ["screenshot_bytes", "timeline", "source_order", "latency", "model_backend",
                                    "different_photo", "user_validation", "stale_review", "evidence_zip"])
def test_provenance_mismatch_rejected_before_render(captures, mutation):
    source, plan_path = captures
    order = json.loads((source / "order.json").read_bytes())
    if mutation == "screenshot_bytes":
        next(source.glob("*.png")).write_bytes(b"changed capture")
    elif mutation == "timeline":
        rows = json.loads((source / "timeline.json").read_bytes())
        rows[0]["url"] = "http://localhost/other-order"
        write_json(source / "timeline.json", rows)
    elif mutation == "evidence_zip":
        (source / "evidence.zip").write_bytes(b"other export")
    elif mutation == "stale_review":
        summary = json.loads((source / "review-summary.json").read_bytes())
        summary["current_review"]["check_id"] = "check-0"
        write_json(source / "review-summary.json", summary)
    else:
        if mutation == "source_order":
            order["order"]["id"] = "other-order"
        elif mutation == "latency":
            order["order"]["checks"][0]["latency_ms"] = 24100
        elif mutation == "model_backend":
            order["order"]["checks"][0]["backend"] = "fixture"
        elif mutation == "different_photo":
            order["order"]["checks"][0]["photo_sha256"] = "other-family"
        elif mutation == "user_validation":
            order["order"]["public_reviews"][0]["user_validation"] = True
        write_json(source / "order.json", order)
    with pytest.raises(ValueError):
        video.load_inputs(source, plan_path)


@pytest.mark.parametrize("mutation", ["unready", "duplicate", "escape", "ass_injection", "too_long"])
def test_unsafe_or_incomplete_edit_plan_rejected(captures, mutation):
    source, plan_path = captures
    plan = json.loads(plan_path.read_bytes())
    if mutation == "unready":
        plan["ready_for_render"] = False
    elif mutation == "duplicate":
        plan["shots"].append(plan["shots"][0])
    elif mutation == "escape":
        plan["shots"][0]["file"] = "../private.png"
    elif mutation == "ass_injection":
        plan["shots"][0]["caption"] = [r"{\pos(0,0)} inserted"]
    elif mutation == "too_long":
        plan["shots"][0]["seconds"] = 181
    write_json(plan_path, plan)
    with pytest.raises(ValueError):
        video.load_inputs(source, plan_path)


def test_ffmpeg_only_verification_is_explicit_and_checks_full_decode(tmp_path, monkeypatch):
    class Result:
        returncode = 0
        stderr = "Duration: 00:02:23.00, start: 0.00\nStream #0:0: Video: h264 (High), yuv420p, 1920x1080, 24 fps"

    calls = []

    def decode(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(video, "run", decode)
    result = video.verify_video(Path("synthetic.mp4"), Path("ffmpeg"), None, 143, tmp_path)
    assert calls[0][-3:] == ["-f", "null", "-"]
    assert result["duration_seconds"] == 143
    assert result["ffprobe_available"] is False
    assert result["full_decode_passed"] is True
    Result.returncode = 1
    with pytest.raises(RuntimeError, match="decode failed"):
        video.verify_video(Path("synthetic.mp4"), Path("ffmpeg"), None, 143, tmp_path)


def test_build_receipt_is_serializable_and_visual_qa_stays_pending(captures, tmp_path, monkeypatch):
    """Exercise media orchestration with a fake process, never present it as real video."""
    from types import SimpleNamespace

    source, plan_path = captures
    binary, font = tmp_path / "fake-ffmpeg", tmp_path / "fake-font.ttf"
    binary.write_bytes(b"synthetic binary")
    font.write_bytes(b"synthetic font")

    def fake_process(command, **kwargs):
        if "-version" in command:
            return SimpleNamespace(returncode=0, stdout="Synthetic ffmpeg, not real media\n", stderr="")
        target = Path(command[-1])
        if not target.is_absolute():
            target = kwargs["cwd"] / target
        target.write_bytes(b"synthetic media orchestration fixture")
        return SimpleNamespace(returncode=0, stderr="Synthetic process fixture\n")

    monkeypatch.setattr(video, "run", fake_process)
    monkeypatch.setattr(video, "verify_video", lambda *a: {"fixture_only": True})
    out = tmp_path / "render"
    result = video.build(source, plan_path, out, binary, font, allow_ffmpeg_probe=True)
    saved = json.loads((out / "video_receipt.json").read_bytes())
    assert all(isinstance(arg, str) for arg in saved["command"])
    assert result["status"] == "encoded_and_decode_verified"
    assert result["visual_qa"].startswith("Pending actual inspection")
    assert result["video"]["sha256"] == video.sha((out / video.VIDEO_NAME).read_bytes())
