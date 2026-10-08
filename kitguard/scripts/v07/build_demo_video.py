"""Build a <=180-second, clearly labelled edit of real UI screenshots.

Original capture files are read only. Captions/title cards are separate video layers.
No browser, model, inferred UI state, synthetic result, voice, or failed recording
frame is used. A completed caption plan and its exact capture timeline are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "test-results/browser/public-review-v07/demonstration"
DEFAULT_PLAN = Path(__file__).with_name("demo_video_ko.json")
DEFAULT_FFMPEG = ROOT / ".tools/imageio-ffmpeg/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
DEFAULT_FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
EDIT_LABEL = "실제 실행 화면 편집본 · 대기·조작 구간 축약"
WIDTH, HEIGHT, FPS = 1920, 1080, 24
VIDEO_NAME = "KitGuard_v07_public_photo_walkthrough.mp4"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def run(arguments, **kwargs):
    return subprocess.run([str(a) for a in arguments], capture_output=True, text=True,
                          check=False, **kwargs)


def executable(path, label):
    path = Path(path).resolve()
    result = run([path, "-version"], timeout=15)
    if result.returncode != 0:
        raise ValueError(f"Unavailable {label}: {path}")
    return path, result.stdout.splitlines()[0]


def plain_lines(value, name, maximum=70):
    if (not isinstance(value, list) or not 1 <= len(value) <= 2
            or any(not isinstance(line, str) or not line.strip() or len(line) > maximum
                   or any(token in line for token in ("{", "}", "\\", "\n", "\r")) for line in value)):
        raise ValueError(f"{name} must contain one or two short plain-text lines")
    return value


def source_evidence(source, plan):
    """Bind narrated values to the actual export; do not trust filenames alone."""
    files = {}
    for name in ("order.json", "review-summary.json", "verification.json", "evidence.zip"):
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing original evidence: {name}")
        raw = path.read_bytes()
        files[name] = {"sha256": sha(raw), "bytes": len(raw)}
    order = json.loads((source / "order.json").read_bytes())["order"]
    summary = json.loads((source / "review-summary.json").read_bytes())
    audit = json.loads((source / "verification.json").read_bytes())
    expected = plan["expected_evidence"]
    if not (order["id"] == summary["order_id"] == audit["order_id"] == expected["order_id"]):
        raise ValueError("The source order is not the order narrated in the caption plan")
    if order["demo_source"]["sample_id"] != expected["sample_id"]:
        raise ValueError("The source photo family is not the narrated public example")
    if audit["zip_sha256"] != files["evidence.zip"]["sha256"]:
        raise ValueError("The exported evidence ZIP differs from the capture audit")
    if (audit.get("automation_engineering_trial") is not True
            or audit.get("real_user_validation") is not False
            or audit.get("physical_action_validated") is not False):
        raise ValueError("The capture audit must explicitly retain demonstration scope")
    checks = order["checks"]
    if len(checks) != len(expected["checks"]):
        raise ValueError("Unexpected check history for this video")
    for check, match in zip(checks, expected["checks"], strict=True):
        for key in ("revision", "decision", "latency_ms", "valid"):
            if check[key] != match[key]:
                raise ValueError(f"Narrated check {key} does not match the actual export")
        if (check["observed"] != expected["observed"]
                or check["requirements_snapshot"]["bolt"] != match["required_bolt"]
                or check["backend"] != "mlx"):
            raise ValueError("Actual observation, requirement, or backend differs from the caption plan")
    if (len({check["photo_sha256"] for check in checks}) != 1
            or summary["current_review"]["check_id"] != checks[-1]["id"]):
        raise ValueError("The same-photo recheck or current digital review binding is invalid")
    for field, source_field in (("public_reviews", "public_reviews"), ("public_replays", "public_replays"),
                                ("physical_completions", "completions")):
        if len(order[source_field]) != expected[field] or audit[field] != expected[field]:
            raise ValueError(f"Unexpected {field} count")
    for review in order["public_reviews"]:
        if (review["operator_code"] != "DEMO-AUTOMATION" or review["conclusion"] != "inconclusive"
                or review["physical_completion"] is not False or review["user_validation"] is not False):
            raise ValueError("Digital review scope differs from the automated demonstration")
    return {"artifacts": files, "audit": audit, "source": order["demo_source"],
            "order_id": order["id"], "checks": expected["checks"]}


def load_inputs(source, plan_path):
    source, plan_path = source.resolve(), plan_path.resolve()
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema") != "kitguard.v07.screenshot-narration.v1" or plan.get("ready_for_render") is not True:
        raise ValueError("Caption plan is not complete; wait for the verified final captures")
    timeline_path = source / "timeline.json"
    timeline_bytes = timeline_path.read_bytes()
    timeline = json.loads(timeline_bytes)
    captures = {row["name"]: row for row in timeline}
    if len(captures) != len(timeline):
        raise ValueError("Duplicate capture timeline entries")
    evidence = source_evidence(source, plan)
    audited = {row["name"]: row for row in evidence["audit"]["screenshots"]}
    if set(captures) != set(audited):
        raise ValueError("The capture timeline and original audit differ")
    for key in ("opening_title", "opening_detail", "closing_title", "closing_detail"):
        plain_lines(plan.get(key), key)
    for key in ("opening_seconds", "closing_seconds"):
        if type(plan.get(key)) is not int or not 3 <= plan[key] <= 12:
            raise ValueError("Opening/closing durations must be explicit 3–12 second integers")
    cursor, inputs, shots, previous_capture = plan["opening_seconds"], [], [], None
    seen = set()
    if not isinstance(plan.get("shots"), list) or not plan["shots"]:
        raise ValueError("No verified screenshots were selected")
    for shot in plan["shots"]:
        name, seconds = shot.get("file"), shot.get("seconds")
        if (not isinstance(name, str) or not re.fullmatch(r"[0-9]{2}-[a-z0-9-]+\.png", name)
                or name in seen or name not in captures):
            raise ValueError(f"Screenshot must be unique and explicitly present in the capture timeline: {name}")
        if type(seconds) is not int or not 3 <= seconds <= 18:
            raise ValueError("Screenshot duration must be an explicit 3–18 second integer")
        plain_lines([shot.get("chapter")], "chapter", maximum=55)
        plain_lines(shot.get("caption"), "caption")
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing original capture: {path}")
        captured = datetime.fromisoformat(captures[name]["captured_at"])
        if captured.tzinfo is None or (previous_capture is not None and captured < previous_capture):
            raise ValueError("Screenshots must retain timezone-aware, chronological capture order")
        previous_capture = captured
        raw = path.read_bytes()
        if any(audited[name][key] != captures[name][key] for key in ("captured_at", "url")) or audited[name]["sha256"] != sha(raw):
            raise ValueError(f"Original screenshot or capture metadata changed: {name}")
        with Image.open(path) as image:
            if image.format not in ("PNG", "JPEG") or min(image.size) < 600:
                raise ValueError("Use the original readable UI captures")
            dimensions = list(image.size)
            file_format = image.format
            image.verify()
        inputs.append({"file": name, "source_path": str(path), "sha256": sha(raw), "bytes": len(raw),
                       "dimensions": dimensions, "file_format": file_format, **captures[name]})
        shots.append({**shot, "start_seconds": cursor, "end_seconds": cursor + seconds})
        cursor += seconds
        seen.add(name)
    total = cursor + plan["closing_seconds"]
    if total > 180:
        raise ValueError(f"Planned video is {total}s; keep it at or below 180s")
    if len({tuple(item["dimensions"]) for item in inputs}) != 1:
        raise ValueError("Capture viewport sizes differ; retain consistent original viewport screenshots")
    return {"plan": plan, "plan_bytes": plan_bytes, "plan_sha256": sha(plan_bytes),
            "timeline_bytes": timeline_bytes, "timeline_sha256": sha(timeline_bytes),
            "source": source, "inputs": inputs, "shots": shots, "duration_seconds": total, "evidence": evidence}


def ass_time(seconds):
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}.00"


def srt_time(seconds):
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d},000"


def subtitles(data):
    plan, total = data["plan"], data["duration_seconds"]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: EditLabel,Arial Unicode MS,25,&H00D9E9DD,&H000000FF,&H00152820,&H00152820,0,0,0,0,100,100,0,0,1,0,0,7,55,55,20,1
Style: Chapter,Arial Unicode MS,25,&H00EAF4EE,&H000000FF,&H00152820,&H00152820,0,0,0,0,100,100,0,0,1,0,0,9,55,55,20,1
Style: Caption,Arial Unicode MS,35,&H00FFFFFF,&H000000FF,&H00152820,&H00152820,0,0,0,0,100,100,0,0,1,0,0,2,75,75,35,1
Style: Title,Arial Unicode MS,65,&H00FFFFFF,&H000000FF,&H00152820,&H00152820,0,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: Detail,Arial Unicode MS,31,&H00D5E5DB,&H000000FF,&H00152820,&H00152820,0,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events, captions = [], []

    def add(start, end, style, lines, positioning=""):
        text = positioning + r"\N".join(lines)
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")

    add(0, total, "EditLabel", [EDIT_LABEL])
    add(0, plan["opening_seconds"], "Title", plan["opening_title"], r"{\pos(960,430)}")
    add(0, plan["opening_seconds"], "Detail", plan["opening_detail"], r"{\pos(960,670)}")
    for index, shot in enumerate(data["shots"], 1):
        start, end = shot["start_seconds"], shot["end_seconds"]
        add(start, end, "Chapter", [shot["chapter"]])
        add(start, end, "Caption", shot["caption"])
        captions.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n" + "\n".join(shot["caption"]))
    outro = total - plan["closing_seconds"]
    add(outro, total, "Title", plan["closing_title"], r"{\pos(960,445)}")
    add(outro, total, "Detail", plan["closing_detail"], r"{\pos(960,635)}")
    return header + "\n".join(events) + "\n", "\n\n".join(captions) + "\n"


def concat_text(data, render_inputs=None):
    def file_line(name):
        filename = render_inputs[name] if render_inputs is not None else str(data["source"] / name)
        if "\n" in filename or "\r" in filename:
            raise ValueError("Unsupported newline in capture directory")
        return "file '" + filename.replace("'", "'\\''") + "'"

    shots, plan = data["shots"], data["plan"]
    rows = ["ffconcat version 1.0", file_line(shots[0]["file"]), f"duration {plan['opening_seconds']}"]
    for shot in shots:
        rows += [file_line(shot["file"]), f"duration {shot['seconds']}"]
    rows += [file_line(shots[-1]["file"]), f"duration {plan['closing_seconds']}", file_line(shots[-1]["file"])]
    return "\n".join(rows) + "\n"


def stage_captures(data, output):
    """Use the actual image codec extension without rewriting source pixels or bytes."""
    staged = output / "render-inputs"
    staged.mkdir()
    records = []
    for item in data["inputs"]:
        suffix = {"JPEG": ".jpg", "PNG": ".png"}[item["file_format"]]
        relative = Path("render-inputs") / Path(item["file"]).with_suffix(suffix)
        raw = Path(item["source_path"]).read_bytes()
        if sha(raw) != item["sha256"]:
            raise ValueError("Original screenshot changed before staging")
        with (output / relative).open("xb") as handle:
            handle.write(raw)
        if sha((output / relative).read_bytes()) != item["sha256"]:
            raise ValueError("Staged capture does not match the original bytes")
        records.append({"original_file": item["file"], "path": relative.as_posix(),
                        "file_format": item["file_format"], "sha256": item["sha256"],
                        "bytes": len(raw), "method": "byte_identical_copy_with_codec_extension"})
    return records


def verify_video(path, ffmpeg, ffprobe, total, output):
    decode = run([ffmpeg, "-hide_banner", "-i", path, "-map", "0:v:0", "-f", "null", "-"], timeout=180)
    (output / "ffmpeg-decode.log").write_text(decode.stderr)
    if decode.returncode != 0:
        raise RuntimeError("Full video decode failed; see ffmpeg-decode.log")
    if ffprobe:
        probe = run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], timeout=20)
        if probe.returncode != 0:
            raise RuntimeError(probe.stderr)
        metadata = json.loads(probe.stdout)
        streams = [stream for stream in metadata["streams"] if stream["codec_type"] == "video"]
        if len(streams) != 1:
            raise ValueError("Expected one video stream")
        stream = streams[0]
        actual = {"duration_seconds": float(metadata["format"]["duration"]), "width": stream["width"],
                  "height": stream["height"], "codec": stream["codec_name"], "pixel_format": stream["pix_fmt"]}
        (output / "ffprobe.json").write_bytes(encoded(metadata))
        backend = "ffprobe_json_and_ffmpeg_full_decode"
    else:
        duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", decode.stderr)
        dimensions = re.search(r"Video: h264[^\n]*?\b(1920)x(1080)\b", decode.stderr)
        if not duration or not dimensions or "yuv420p" not in decode.stderr:
            raise ValueError("FFmpeg did not confirm expected duration/H.264/1920x1080/yuv420p")
        actual = {"duration_seconds": int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]),
                  "width": int(dimensions[1]), "height": int(dimensions[2]), "codec": "h264", "pixel_format": "yuv420p"}
        backend = "ffmpeg_metadata_and_full_decode; ffprobe_unavailable"
    if ((actual["width"], actual["height"]) != (WIDTH, HEIGHT) or actual["codec"] != "h264"
            or actual["pixel_format"] != "yuv420p" or abs(actual["duration_seconds"] - total) > .1
            or actual["duration_seconds"] > 180):
        raise ValueError(f"Encoded video properties do not match plan: {actual}")
    return {"backend": backend, "ffprobe_available": bool(ffprobe), "full_decode_passed": True, **actual}


def prepare(data, output):
    """Create inspectable inputs and subtitles without starting any media process."""
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Preserve the earlier edit; choose a new output directory")
    output.mkdir(parents=True)
    (output / "capture-timeline.original.json").write_bytes(data["timeline_bytes"])
    (output / "caption-plan.json").write_bytes(data["plan_bytes"])
    ass, srt = subtitles(data)
    (output / "captions.ass").write_text(ass)
    (output / "captions_ko.srt").write_text(srt)
    render_inputs = stage_captures(data, output)
    (output / "shots.ffconcat").write_text(concat_text(data, {item["original_file"]: item["path"] for item in render_inputs}))
    receipt = {"schema": "kitguard.v07.screenshot-video.v1", "status": "prepared_not_encoded",
               "format": data["plan"]["format"], "continuous_realtime_recording": False,
               "original_capture_files_modified": False,
               "editing": "Whole original screenshots scaled proportionally, letterboxed; independent title/caption layers",
               "waiting_and_operation_intervals_condensed": True, "duration_seconds": data["duration_seconds"],
               "capture_timeline_sha256": data["timeline_sha256"], "caption_plan_sha256": data["plan_sha256"],
               "inputs": data["inputs"], "render_inputs": render_inputs, "edit_timeline": data["shots"],
               "source_evidence": data["evidence"], "builder_sha256": sha(Path(__file__).read_bytes()),
               "unused_material": "Earlier interrupted continuous-capture attempt video/00000.png is not used",
               "claims": "Technical demonstration on existing public development photos; no new holdout scores or genuine user feedback"}
    (output / "video_receipt.json").write_bytes(encoded(receipt))
    attribution = data["evidence"]["source"]
    (output / "README.txt").write_text(
        "KitGuard v0.7 — 실제 실행 화면 편집본\n"
        "실제 공개 사진·로컬 추론, 대기·조작 구간 축약. 연속 실시간 녹화가 아닙니다.\n"
        "검토 입력은 자동화 시연 기록입니다. 실제 사용자 검증이나 실물 완료가 아닙니다.\n\n"
        "Original screenshot files were not modified. The video scales complete screenshots and adds separate captions.\n"
        "The capture filenames end in .png; their actual encoding is recorded per file in video_receipt.json.\n"
        "render-inputs contains byte-identical copies with codec-correct extensions; no image re-encoding is performed.\n"
        "Public photograph attribution (retain with video):\n"
        f"{attribution['sample_id']} — {attribution['source_case_id']}\n"
        f"{attribution['license']}\n{attribution['source_url']}\n"
        "The source photo is used in the recorded KitGuard UI, then proportionally scaled in this edited video.\n"
        "Font software is used from the host system at build time and is not redistributed.\n"
        "See video_receipt.json for exact capture hashes, timings, source artifacts, and verification scope.\n")
    return receipt


def build(source, plan_path, output, ffmpeg_path, font_path, ffprobe_path=None, *, allow_ffmpeg_probe=False):
    data = load_inputs(source, plan_path)
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Preserve the earlier edit; choose a new output directory")
    ffmpeg, ffmpeg_version = executable(ffmpeg_path, "FFmpeg")
    if not font_path.is_file():
        raise ValueError("Korean-capable font file is missing")
    ffprobe, ffprobe_version = (None, None)
    if ffprobe_path:
        ffprobe, ffprobe_version = executable(ffprobe_path, "ffprobe")
    elif not allow_ffmpeg_probe:
        raise ValueError("ffprobe unavailable: provide --ffprobe, or explicitly use --allow-ffmpeg-probe for a labelled fallback")
    receipt = prepare(data, output)
    # Temporary link loads the selected system font without redistributing its software.
    fonts = tempfile.TemporaryDirectory(prefix="kitguard-video-font-")
    (Path(fonts.name) / font_path.name).symlink_to(font_path.resolve())
    total, opening, closing = data["duration_seconds"], data["plan"]["opening_seconds"], data["plan"]["closing_seconds"]
    filters = (f"fps={FPS},scale=1792:850:force_original_aspect_ratio=decrease:flags=lanczos:out_range=tv,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:68:color=0x173A30,setsar=1,"
               f"drawbox=x=0:y=0:w=iw:h=ih:color=0x173A30:t=fill:enable='lt(t,{opening})+gte(t,{total-closing})',"
               f"ass=captions.ass:fontsdir={fonts.name},format=yuv420p")
    movie = output / VIDEO_NAME
    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-n", "-f", "concat", "-safe", "0", "-i", "shots.ffconcat",
               "-vf", filters, "-t", str(total), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-r", str(FPS), "-pix_fmt", "yuv420p", "-color_range", "tv", "-movflags", "+faststart",
               "-metadata", "title=KitGuard public-photo review — edited actual UI screenshots",
               "-metadata", "comment=Not continuous realtime recording; waiting and operation intervals condensed", movie.name]
    receipt.update({"status": "building", "ffmpeg": str(ffmpeg),
               "ffmpeg_version": ffmpeg_version, "ffmpeg_sha256": sha(ffmpeg.read_bytes()),
               "ffprobe": str(ffprobe) if ffprobe else None, "ffprobe_version": ffprobe_version,
               "font": {"source_path": str(font_path), "sha256": sha(font_path.read_bytes())},
               "command": command})
    receipt_path = output / "video_receipt.json"
    receipt_path.write_bytes(encoded(receipt))
    try:
        result = run(command, cwd=output, timeout=600)
        (output / "ffmpeg-encode.log").write_text(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("Video encoding failed; see ffmpeg-encode.log")
        receipt["verification"] = verify_video(movie, ffmpeg, ffprobe, total, output)
        qa = output / "qa"
        qa.mkdir()
        selected = [shot for shot in data["shots"] if shot["file"].startswith(("04-", "07-", "09-", "10-", "12-", "14-"))]
        selected += [data["shots"][-1]]
        times = [("opening", 2), *((Path(s["file"]).stem, s["start_seconds"] + s["seconds"] / 2) for s in selected),
                 ("closing", total - 3)]
        frames = []
        for name, seconds in times:
            target = qa / f"{name}.png"
            frame = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-ss", str(seconds),
                         "-i", movie, "-frames:v", "1", target], timeout=30)
            if frame.returncode != 0:
                raise RuntimeError(frame.stderr)
            frames.append({"path": str(target.relative_to(output)), "video_seconds": seconds,
                           "sha256": sha(target.read_bytes())})
        for item in data["inputs"]:
            if sha(Path(item["source_path"]).read_bytes()) != item["sha256"]:
                raise ValueError("An original capture changed during rendering")
        if sha((data["source"] / "timeline.json").read_bytes()) != data["timeline_sha256"]:
            raise ValueError("Capture timeline changed during rendering")
        for name, item in data["evidence"]["artifacts"].items():
            if sha((data["source"] / name).read_bytes()) != item["sha256"]:
                raise ValueError("Original JSON/ZIP evidence changed during rendering")
        receipt.update(status="encoded_and_decode_verified", video={"path": VIDEO_NAME, "sha256": sha(movie.read_bytes()),
                       "bytes": movie.stat().st_size}, qa_frames=frames,
                       visual_qa="Pending actual inspection of extracted QA frames; frame generation alone is not visual approval")
    except BaseException as error:
        receipt.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        fonts.cleanup()
        receipt_path.write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path(shutil.which("ffmpeg") or DEFAULT_FFMPEG))
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    parser.add_argument("--ffprobe", type=Path, default=Path(shutil.which("ffprobe")) if shutil.which("ffprobe") else None)
    parser.add_argument("--allow-ffmpeg-probe", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Save plan, subtitles and verified input hashes without launching FFmpeg")
    args = parser.parse_args()
    if args.prepare_only:
        receipt = prepare(load_inputs(args.input_dir, args.plan), args.output_dir)
        print(json.dumps({key: receipt[key] for key in ("status", "duration_seconds")}, ensure_ascii=False))
        return
    receipt = build(args.input_dir, args.plan, args.output_dir, args.ffmpeg, args.font, args.ffprobe,
                    allow_ffmpeg_probe=args.allow_ffmpeg_probe)
    print(json.dumps({key: receipt[key] for key in ("status", "duration_seconds", "video", "verification")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
