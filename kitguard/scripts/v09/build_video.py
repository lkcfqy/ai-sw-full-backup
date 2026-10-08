"""Assemble real browser screenshots with separate captions and local TTS.

No source screenshot is edited. The result is labelled as an edited engineering
walkthrough with waiting omitted, not a continuous screen recording or user test.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/competition-v0.9"
BUILD = ROOT / "tmp/v09-video"
FF = ROOT / ".tools/imageio-ffmpeg/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
SCENES = [
    ("08-final-workspace.jpg", "KitGuard / 사진과 주문의 디지털 검토", "기존 M5 Pro 64GB에서 실행 / 새 실물·외부 GPU 없이 시연", "킷가드는 사진과 주문 수량을 함께 검토하는 로컬 에이전트입니다. 기존 맥과 공개 사진으로 실행했습니다. 지금 보시는 영상은 실제 화면을 편집한 기능 리허설이며, 대기 시간은 생략했습니다. 목소리는 합성 음성입니다."),
    ("01-real-r1.jpg", "01  R1 사진 관찰과 수량 대조", "요구 3/2/2/0  관찰 2/2/2/0 / 실제 관찰 55.052초", "첫 주문은 나사류 세 개, 너트 두 개, 와셔 두 개입니다. 로컬 모델은 각각 두 개를 관찰했습니다. 프로그램이 주문과 비교하여 나사류 한 개의 차이를 안내합니다. 저장된 실제 관찰 시간은 약 오십오 초입니다."),
    ("02-point-review-r1.jpg", "02  위치를 표시하고 검토 결론 저장", "표시를 계수해 차이를 계산 / AI 원관찰은 그대로 유지", "검토자는 사진에서 물체의 위치와 종류를 표시합니다. 시스템은 표시를 세어 주문과 비교하고, 원래 에이아이 결과와 별도로 결론을 저장합니다. 모호한 사진은 추가 자료 요청으로 남길 수 있습니다."),
    ("03-revision-input.jpg", "03  명시적으로 주문 수량 변경", "R1 필요 3개에서 R2 필요 2개로 변경 / 부품 보충 없음", "이제 사전에 정한 시나리오에 따라 필요한 나사류를 세 개에서 두 개로 바꿉니다. 사진 속 부품은 변하지 않았습니다. 주문이 바뀌면 이전 검사와 검토 결론은 현재 근거에서 제외됩니다."),
    ("04-r2-marked.jpg", "04  같은 사진으로 새 검사와 복검", "R2 새 관찰 49.773초 / 새 위치 6개와 요구 수량 일치", "같은 사진도 명시적으로 다시 연결한 뒤 새로 추론합니다. 두 번째 관찰은 약 오십 초였고, 새 검토에서 표시한 여섯 개도 바뀐 요구 수량과 일치했습니다. 이전 버전의 차이 기록은 계속 남습니다."),
    ("06-offline-current.jpg", "05  결과와 근거를 증거 ZIP으로 전달", "원 AI / 주문 / 복검 / 차이 / 버전과 이력 보존", "결론을 저장한 뒤 증거 파일을 내려받습니다. 파일에는 주문과 버전, 원래 에이아이 값, 복검 수량, 사진과 표시 위치가 함께 들어갑니다. 다운로드한 파일의 해시를 확인하고 로컬 화면에서 실제 기록을 검토했습니다."),
    ("07-offline-points.jpg", "현재 완성도: 디지털 작업 MVP", "소프트웨어 회귀 1,826 통과 / 실제 참여자 0명 / 실물 완료 0건", "소프트웨어 회귀 천팔백이십육 개가 통과했습니다. 이번 기록은 자동화 기능 리허설로 실제 참여자는 없습니다. 모델의 기존 오류도 유지하여 공개했습니다. 다음 단계는 담당자의 독립적인 업무 검증입니다."),
]


def run(args, name):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=600, check=False)
    (BUILD / f"{name}.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"{name} failed: {result.stderr[-1000:]}")
    return result.stdout + result.stderr


def duration(path, name):
    result = subprocess.run([str(FF), "-hide_banner", "-i", str(path)], capture_output=True, text=True, check=False)
    text = result.stdout + result.stderr
    (BUILD / f"{name}.log").write_text(text)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if not m:
        raise ValueError("No duration")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def subtitles(title, caption):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,Arial Unicode MS,32,&H00353D12,&H000000FF,&H00F2F8F8,&H00F2F8F8,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for x, y, size, text in [
        (52, 18, 24, "실제 화면 편집본 / 대기 생략 / ENGINEERING-AGENT 기능 리허설 / 합성 음성"),
        (52, 67, 46, title),
        (52, 954, 32, caption),
        (52, 1019, 20, "Photo: MVTec LOCO AD screw_bag/train/good/016.png / CC BY-NC-SA 4.0 / 2026.10.03 / KitGuard 0.9.0.dev1"),
    ]:
        assert not any(c in text for c in "{}\\\n")
        events.append(f"Dialogue: 0,0:00:00.00,0:03:00.00,Text,,0,0,0,,{{\\pos({x},{y})\\fs{size}}}" + text)
    return header + "\n".join(events) + "\n"


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "fonts").mkdir(exist_ok=True)
    link = BUILD / "fonts/font.ttf"
    if not link.exists():
        link.symlink_to(FONT)
    evidence = json.loads((ROOT / "test-results/v0.9/ACCEPTANCE.json").read_text())
    timeline = []; total = 0
    for i, (capture, title, caption, narration) in enumerate(SCENES, 1):
        shot = ROOT / "test-results/v0.9/browser" / capture
        digest = hashlib.sha256(shot.read_bytes()).hexdigest()
        assert evidence["sources"][str(shot.relative_to(ROOT))] == digest
        voice = BUILD / f"{i}.aiff"; words = BUILD / f"{i}.txt"
        words.write_text(narration)
        run(["say", "-v", "Yuna", "-r", "185", "-f", words, "-o", voice], f"voice-{i}")
        voice_seconds = duration(voice, f"voice-info-{i}")
        seconds = max(14, voice_seconds + 1.0)
        ass = BUILD / f"{i}.ass"; ass.write_text(subtitles(title, caption))
        segment = BUILD / f"{i}.mp4"
        filters = f"[1:v]scale=1560:780:force_original_aspect_ratio=decrease[shot];[0:v][shot]overlay=(W-w)/2:138,ass='{ass}':fontsdir='{BUILD / 'fonts'}'[v];[2:a]apad[a]"
        run([FF, "-y", "-f", "lavfi", "-i", "color=c=0xf8f8f2:s=1920x1080:r=24", "-loop", "1", "-i", shot, "-i", voice, "-filter_complex", filters, "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", segment], f"encode-{i}")
        timeline.append({"scene": i, "start": total, "seconds": seconds, "capture": str(shot.relative_to(ROOT)), "sha256": digest, "title": title, "caption": caption, "narration": narration, "voice_seconds": voice_seconds})
        total += seconds
    assert total < 180, total
    concat = BUILD / "concat.txt"
    concat.write_text("".join(f"file '{BUILD / f'{i}.mp4'}'\n" for i in range(1, len(SCENES) + 1)))
    video = OUT / "KitGuard_demo_ko.mp4"
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", "-movflags", "+faststart", video], "concat")
    actual_seconds = duration(video, "final-info")
    assert actual_seconds < 180
    run([FF, "-v", "error", "-i", video, "-f", "null", "-"], "full-decode")
    for row in timeline:
        run([FF, "-y", "-ss", str(row["start"] + 2), "-i", video, "-frames:v", "1", BUILD / f"qa-{row['scene']}.png"], f"qa-{row['scene']}")
    result = {"format": "actual screenshot edit, not continuous screen recording", "voice": "local macOS Yuna TTS, synthetic", "human_participants": 0, "seconds": actual_seconds, "timeline": timeline, "full_decode": "passed", "visual_qa": "pending", "sha256": hashlib.sha256(video.read_bytes()).hexdigest()}
    (OUT / "video-build.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"video": str(video), "seconds": actual_seconds, "decode": "passed"}))


if __name__ == "__main__":
    main()
