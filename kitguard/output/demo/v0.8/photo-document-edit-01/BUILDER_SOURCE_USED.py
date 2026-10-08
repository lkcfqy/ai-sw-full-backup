"""Build a silent, explicitly edited video of five existing real-history screenshots.

prepare: validate original JSON/captures; render separate captioned scene layers.
encode: require a hash-bound peer approval, encode, fully decode, extract QA frames.
No browser, model, source-image modification, or new research data is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PLAN = Path(__file__).with_name("demo_video_ko.json")
CAPTURES = ROOT / "test-results/browser/photo-document-live-v08"
FFMPEG = ROOT / ".tools/imageio-ffmpeg/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
VIDEO = "KitGuard_v08_photo_document_edit_ko.mp4"
EXPECTED_CAPTURES = {"r2-ko.jpg", "r2-zh.jpg", "r1-history-zh.jpg", "reviews-ko.jpg", "reviews-zh.jpg"}
W, H, FPS = 1920, 1080, 24


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load(path):
    return json.loads(Path(path).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_index(plan):
    """Validate narrated facts against both original API history and browser audit."""
    files = {k: ROOT / v for k, v in plan["source_paths"].items()}
    for path in files.values():
        require(path.is_file() and not path.is_symlink() and path.is_relative_to(ROOT), "Unsafe source")
    data = {k: load(v) for k, v in files.items()}
    api, browser, order, download = (data[k] for k in ("api", "browser", "order", "download"))
    order = order["order"]
    require(api["status"] == "passed" and browser["status"] == "passed_read_only_display_and_download", "Source run not passed")
    require(api["order_id"] == browser["order_id"] == order["id"] == plan["order_id"], "Wrong order")
    require(browser["prior_real_api_run"]["receipt_sha256"] == digest(files["api"]), "API binding mismatch")
    for key in ("order", "download"):
        require(browser["artifacts_sha256"][str(files[key].relative_to(ROOT))] == digest(files[key]), "Browser source binding mismatch")
    require(api["model_calls_started"] == api["model_calls_completed"] == 6 and api["inspect_attempts"] == 2, "Unexpected calls")
    require(api["human_participants"] == browser["human_participants"] == 0 and api["accuracy_claim"] is False, "Scope mismatch")
    require(api["revision_invalidates_previous_check_and_review"] is True and api["replay_model_calls"] == 0, "Replay facts mismatch")
    require(browser["browser_scope"]["additional_model_calls"] == 0 and browser["browser_scope"]["new_review_or_mutation_requests"] == 0, "Not read-only captures")
    require(order["document_source"]["verification"] == "user_declared_unverified" and order["document_source"]["physical_completion_allowed"] is False, "Source scope mismatch")
    require(data["api_plan"]["references"] == {} and "Preset explicit" in data["api_plan"]["revision_authority"], "Wrong revision authority")
    require(len(order["checks"]) == 2, "Wrong check history")
    for check, result, rev, ms, decision, bolt in zip(order["checks"], api["inspection_results"], [1, 2], [50909, 47728], ["correct", "ready"], [3, 2], strict=True):
        require(check["revision"] == result["revision"] == rev and check["latency_ms"] == result["latency_ms"] == ms, "Wrong revision/timing")
        require(check["decision"] == result["decision"] == decision and check["backend"] == "mlx", "Wrong actual decision")
        require(check["observed"] == result["observed"] == {"bolt": 2, "nut": 2, "washer": 2, "bracket": 0}, "Wrong observation")
        require(check["requirements_snapshot"] == {"bolt": bolt, "nut": 2, "washer": 2, "bracket": 0} and check["valid"] is (rev == 2), "Wrong BOM/currentness")
        evidence = check["reference_evidence"]
        require(evidence["images"] == [] and [(s["stage"], s["status"], s["reference_image_indices"]) for s in evidence["stages"]] == [(s, "completed", []) for s in ["original", "rotate_90_ccw", "identity"]], "Wrong actual tool stages")
    require(len({c["photo_sha256"] for c in order["checks"]}) == 1, "Not same photo")
    require(len(order["public_reviews"]) == 2 and len(order["public_replays"]) == 1 and not order["completions"], "Wrong record counts")
    for review in order["public_reviews"]:
        require(review["operator_code"] == "ENGINEERING-AGENT" and review["conclusion"] == "inconclusive" and review["user_validation"] is False and review["physical_completion"] is False, "Opinion scope mismatch")
    require(download["transport"].startswith("Actual Chrome download") and len(download["verified_payload_entries"]) == 4 and api["zip_members_verified"] == 6, "Download evidence mismatch")
    require(download["order_equals_original_api_export"] is True and download["all_reviews_engineering_agent_zero_humans"] is True, "Download history mismatch")
    inputs = [{"role": k, "path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": digest(p)} for k, p in files.items()]
    selected = [s["screenshot"] for s in plan["scenes"] if s["screenshot"]]
    require(set(selected) == EXPECTED_CAPTURES and len(selected) == 5, "Use exactly five authorized original captures")
    for name in selected:
        path = CAPTURES / name
        require(not path.is_symlink(), "Capture symlink")
        require(browser["artifacts_sha256"][str(path.relative_to(ROOT))] == digest(path), "Capture changed")
        with Image.open(path) as im:
            require(im.format == "JPEG" and im.size == (1713, 899), "Unexpected actual image format or size")
            im.verify()
        inputs.append({"role": "original_capture", "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path), "format": "JPEG", "dimensions": [1713, 899]})
    return {"schema": "kitguard.v08.video-source-index.v1", "inputs": inputs, "exact_capture_times": "Not recorded per screenshot; all display completed API history. Edit order is narrative order, not capture chronology.", "source_photo": order["document_source"], "browser_checked_at": browser["checked_at"], "api_started_at": api["started_at"], "api_finished_at": api["finished_at"], "human_participants": 0, "additional_model_calls": 0, "audio": "none", "limitations": browser["limitations"]}


def validate_plan(plan):
    require(plan["schema"] == "kitguard.v08.real-history-video-plan.v1" and len(plan["scenes"]) == 6, "Unexpected plan")
    require([s["seconds"] for s in plan["scenes"]] == [20, 25, 25, 25, 20, 20], "Unexpected timeline")
    for scene in plan["scenes"]:
        require(len(scene["facts"]) == 3 and len(scene["caption"]) == 2, "Incomplete scene")
        strings = [scene["title"], scene["source_note"], *scene["caption"], *(line for group in scene["facts"] for line in group)]
        require(all(isinstance(s, str) and s and not any(c in s for c in "{}\\\n\r") for s in strings), "Unsafe caption")
    return 135


def ass(scene, plan):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,Arial Unicode MS,32,&H00353D12,&H000000FF,&H00F2F8F8,&H00F2F8F8,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    def text(x, y, size, lines, color="123D35", bold=False):
        color = color[4:6] + color[2:4] + color[:2]
        tags = rf"{{\pos({x},{y})\fs{size}\c&H{color}&\b{int(bold)}}}"
        events.append("Dialogue: 0,0:00:00.00,0:03:00.00,Text,,0,0,0,," + tags + r"\N".join(lines))

    text(55, 20, 24, [plan["persistent_label"]])
    text(1500, 20, 24, ["KitGuard · " + plan["version"]])
    text(55, 65, 44, [scene["title"]], bold=True)
    if scene["screenshot"]:
        for y, lines in zip([185, 415, 645], scene["facts"], strict=True):
            text(55, y, 30, lines, bold=True)
        text(448, 900, 22, [scene["source_note"]], "566B64")
    else:
        for x, lines in zip([60, 700, 1310], scene["facts"], strict=True):
            text(x, 260, 31, lines, bold=True)
        text(60, 580, 48, ["입력 → 판단 → 도구 실행 → 기록 전달"], bold=True)
        text(60, 680, 30, ["자료의 요구 일치와 증거 이력 관리", "실물 보충·출고·사용자 만족을 주장하지 않음"], "17725C")
        text(60, 840, 24, [scene["source_note"]], "566B64")
    text(55, 944, 29, scene["caption"])
    text(55, 1038, 19, [plan["credit"]], "566B64")
    return header + "\n".join(events) + "\n"


def command(args, out, name, timeout=600):
    with (out / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps([str(x) for x in args], ensure_ascii=False) + "\n")
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout, check=False)
    (out / (name + ".log")).write_text(p.stdout + p.stderr)
    require(p.returncode == 0, f"{name} failed; see log")
    return p.stdout + p.stderr


def prepare(out):
    require(not out.exists(), "Refuse to overwrite an existing output")
    plan = load(PLAN)
    total = validate_plan(plan)
    index = source_index(plan)
    out.mkdir(parents=True)
    (out / "scenes").mkdir()
    (out / "qa").mkdir()
    (out / "fonts").mkdir()
    (out / "fonts/font.ttf").symlink_to(FONT)
    try:
        version = command([FFMPEG, "-version"], out, "ffmpeg-version", 20).splitlines()[0]
        command([FFMPEG, "-L"], out, "ffmpeg-license", 20)
        shutil.copyfile(PLAN, out / "EDIT_PLAN.json")
        save(out / "SOURCE_INDEX.json", index)
        cursor, timeline = 0, []
        for n, scene in enumerate(plan["scenes"], 1):
            ass_path = out / f"scenes/scene-{n:02}.ass"
            ass_path.write_text(ass(scene, plan))
            output = out / f"scenes/scene-{n:02}.png"
            if scene["screenshot"]:
                input_args = ["-i", CAPTURES / scene["screenshot"]]
                base_filter = "scale=1440:-1:flags=lanczos,pad=1920:1080:448:132:color=0xF8F8F2,setsar=1,"
            else:
                input_args = ["-f", "lavfi", "-i", "color=c=0xF8F8F2:s=1920x1080:r=24"]
                base_filter = ""
            filt = base_filter + f"ass='{ass_path}':fontsdir='{out / 'fonts'}'"
            command([FFMPEG, "-hide_banner", "-nostdin", *input_args, "-vf", filt, "-frames:v", "1", "-threads", "1", output], out, f"render-scene-{n:02}")
            timeline.append({"scene": n, "start_seconds": cursor, "end_seconds": cursor + scene["seconds"], "original_screenshot": scene["screenshot"], "rendered_frame": str(output.relative_to(out)), "frame_sha256": digest(output), "ass_sha256": digest(ass_path)})
            cursor += scene["seconds"]
        save(out / "TIMELINE.json", timeline)
        save(out / "PREPARATION.json", {"schema": "kitguard.v08.video-preparation.v1", "status": "prepared_for_independent_review", "created_at": datetime.now(UTC).isoformat(), "source_script": str(Path(__file__).relative_to(ROOT)), "script_sha256": digest(__file__), "plan_sha256": digest(PLAN), "source_index_sha256": digest(out / "SOURCE_INDEX.json"), "timeline_sha256": digest(out / "TIMELINE.json"), "duration_seconds": total, "ffmpeg": {"path": str(FFMPEG.relative_to(ROOT)), "sha256": digest(FFMPEG), "version": version}, "font": {"path": str(FONT), "sha256": digest(FONT)}, "audio_tracks": 0, "visual_qa": "pending; captions are independent composition layers and originals are unchanged"})
    finally:
        (out / "fonts/font.ttf").unlink(missing_ok=True)
        (out / "fonts").rmdir()


def encode(out, approval):
    prepared = load(out / "PREPARATION.json")
    require(digest(__file__) == prepared["script_sha256"] and digest(PLAN) == prepared["plan_sha256"], "Builder/plan changed since preparation")
    require(digest(out / "SOURCE_INDEX.json") == prepared["source_index_sha256"] and digest(out / "TIMELINE.json") == prepared["timeline_sha256"], "Preparation changed")
    require(source_index(load(PLAN)) == load(out / "SOURCE_INDEX.json"), "Original input changed")
    peer = load(approval)
    require(peer["status"] == "approved_for_encode" and peer["preparation_sha256"] == digest(out / "PREPARATION.json"), "Missing exact peer approval")
    require(not (out / VIDEO).exists() and not (out / "receipt.json").exists(), "Refuse to overwrite video/receipt")
    timeline = load(out / "TIMELINE.json")
    for row in timeline:
        require(digest(out / row["rendered_frame"]) == row["frame_sha256"], "Prepared scene changed")
    concat = out / "concat.txt"
    concat.write_text("".join(f"file '{(out / row['rendered_frame']).as_posix()}'\nduration {row['end_seconds'] - row['start_seconds']}\n" for row in timeline) + f"file '{(out / timeline[-1]['rendered_frame']).as_posix()}'\n")
    command([FFMPEG, "-hide_banner", "-nostdin", "-f", "concat", "-safe", "0", "-i", concat, "-t", "135", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-movflags", "+faststart", "-an", out / VIDEO], out, "encode")
    decoded = command([FFMPEG, "-hide_banner", "-nostdin", "-i", out / VIDEO, "-map", "0:v:0", "-f", "null", "-"], out, "full-decode")
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", decoded)
    require(match is not None, "Missing measured duration")
    measured = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    require(abs(measured - 135) < .05 and "1920x1080" in decoded and "yuv420p" in decoded and "Video: h264" in decoded, "Unexpected encoded stream")
    require("Audio:" not in decoded, "Unexpected audio")
    frames = [int(n) for n in re.findall(r"frame=\s*(\d+)", decoded)]
    require(frames and max(frames) == 135 * FPS, "Full decoded frame count differs")
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        command([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", out / VIDEO], out, "ffprobe")
    samples = {0, 135 * FPS - 1}
    for row in timeline:
        samples.add(int((row["start_seconds"] + row["end_seconds"]) / 2 * FPS))
        if row["start_seconds"]:
            samples.update([int(row["start_seconds"] * FPS) - 1, int(row["start_seconds"] * FPS)])
    qa = []
    for n in sorted(samples):
        path = out / f"qa/frame-{n:04}.png"
        command([FFMPEG, "-hide_banner", "-nostdin", "-ss", f"{n / FPS:.8f}", "-i", out / VIDEO, "-frames:v", "1", "-threads", "1", path], out, f"extract-frame-{n:04}")
        qa.append({"frame": n, "seconds": n / FPS, "path": str(path.relative_to(out)), "sha256": digest(path)})
    require(source_index(load(PLAN)) == load(out / "SOURCE_INDEX.json"), "Original input changed during encode")
    save(out / "receipt.json", {"schema": "kitguard.v08.real-history-video-receipt.v1", "status": "encoded_and_full_decode_verified_pending_visual_qa", "finished_at": datetime.now(UTC).isoformat(), "video": {"path": str((out / VIDEO).relative_to(ROOT)), "sha256": digest(out / VIDEO), "bytes": (out / VIDEO).stat().st_size}, "duration_seconds": measured, "resolution": [W, H], "fps": FPS, "decoded_frames": max(frames), "full_decode_passed": True, "ffprobe_available": bool(ffprobe), "metadata_verifier": "ffprobe and FFmpeg full decode" if ffprobe else "FFmpeg stream metadata and full decode; ffprobe unavailable", "audio_tracks": 0, "silent": True, "original_inputs_unchanged": True, "human_participants": 0, "new_model_calls": 0, "continuous_screen_recording": False, "preparation_sha256": digest(out / "PREPARATION.json"), "peer_approval": {"path": str(approval.relative_to(ROOT)), "sha256": digest(approval)}, "qa_frames": qa, "visual_qa": "pending; record separately without rewriting this stage receipt"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "encode"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / "output/demo/v0.8") and not out.is_symlink(), "Use a new v0.8 video output")
    if args.action == "prepare":
        prepare(out)
    else:
        require(args.approval is not None, "Peer approval required")
        encode(out, args.approval.resolve())


if __name__ == "__main__":
    main()
