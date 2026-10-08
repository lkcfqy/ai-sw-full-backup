# v0.7 actual-screen demonstration edit

`scripts/v07/build_demo_video.py` builds a Korean-captioned, 143-second edit of the
15 captured screens in `test-results/browser/public-review-v07/demonstration/`.
This is an **edited explanation of actual screenshots**, not a continuous realtime
screen recording. The title, persistent video label and receipt say that waiting
and operation intervals are condensed. No audio narration is generated.

The captured example is `bag-revision`, order `ord_01a0e1e0cd8f49b3bb67`:
R1 observes two bolts against a requirement of three; the natural-language change
proposal is approved as R2; the old evidence becomes invalid; an explicit reuse of
the same public photo precedes another real model check. The recorded inference
latencies are 51.488 s and 46.614 s. The two digital review records are automated
engineering demonstration entries, with `inconclusive` conclusions. They are not
real user opinions, accuracy measurements, physical completion or new holdout results.

The source photograph is MVTec LOCO `screw_bag/train/good/016.png`,
[CC BY-NC-SA 4.0](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad).
Retain the generated README attribution with the video. The UI screenshots are
used intact, proportionally scaled and letterboxed. Separate title/subtitle layers
are added in the video. Original files are not rewritten. The capture tool saved
JPEG bytes under `.png` filenames; the builder records actual format, dimensions
and SHA-256 without renaming or converting the source files. The interrupted
`video/00000.png` capture attempt is excluded.

For FFmpeg input, `render-inputs/` contains byte-identical copies with extensions
matching the detected codec (`.jpg` for the current JPEG captures). The concat
list uses those copies, and their hashes are recorded in `render_inputs`. This
avoids relying on image demuxer behavior for a misleading `.png` extension.
No pixel decode/re-encode occurs during this preparation step.

## Prepare without media load

```sh
.venv/bin/python -m scripts.v07.build_demo_video \
  --prepare-only --output-dir tmp/v07-video-preparation/new-check
```

This checks capture hashes against `verification.json`, binds the captions to
`order.json`, `review-summary.json` and the evidence ZIP, and writes the ASS/SRT
captions, original capture timeline, edit timeline and provenance receipt. It does
not call FFmpeg, a browser or a model. Existing output directories are rejected.
`prepared_not_encoded` is not a completed video.

## Build after timed model experiments finish

```sh
.venv/bin/python -m scripts.v07.build_demo_video \
  --output-dir output/demo/v0.7/public-photo-edit-01 --allow-ffmpeg-probe
```

The default local FFmpeg fallback is the existing imageio-ffmpeg 7.1 binary under
`.tools/`. A portable installation may instead pass `--ffmpeg /path/to/ffmpeg`,
`--ffprobe /path/to/ffprobe`, and `--font /path/to/korean-capable-font`. Use an
Arial Unicode MS-compatible font or adjust the ASS style's font family when using
a different family. Font software is loaded through a temporary link and is not
redistributed. The source package excludes `.tools/`, model weights and captured
demonstration outputs; rebuilding this video requires those external inputs.

This host has no ffprobe. The explicit `--allow-ffmpeg-probe` option permits a
labelled fallback: FFmpeg reads the video metadata and decodes the entire video.
It does not claim ffprobe ran. The receipt records the tool binary hash/version,
exact command, input hashes, real duration, codec and dimensions. Selected video
frames are extracted for separate visual inspection; generation alone does not
mark them visually approved.

## Delivery receipt contract

- `status`: `prepared_not_encoded`, `building`, `failed`, or
  `encoded_and_decode_verified`.
- `video.path`: MP4 path relative to the receipt directory; `video.sha256` and
  `video.bytes` identify the produced bytes.
- `duration_seconds`: planned duration. `verification.duration_seconds`: measured
  output duration, required to match the plan within 0.1 s and be at most 180 s.
- `verification.full_decode_passed`, `verification.ffprobe_available`, and
  `verification.backend`: validation scope. Current fallback is
  `ffmpeg_metadata_and_full_decode; ffprobe_unavailable`.
- `verification.width`, `height`, `codec`, `pixel_format`: 1920, 1080, h264, yuv420p.
- `qa_frames`: extracted frame paths, hashes and video times. `visual_qa` is pending
  until those exact frames have actually been inspected.
- `inputs`, `source_evidence`, `capture_timeline_sha256`, `caption_plan_sha256`,
  `edit_timeline`: provenance and reproducible edit plan.

The output directory also retains encode/decode logs, editable subtitles and a
source/license README. The script neither loads MLX nor calls application inference.
