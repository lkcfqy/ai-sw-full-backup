"""CPU-only exploratory photometric cue at saved development nut predictions.

No detection, relabelling, deduplication, count correction or production decisions.
The two known development errors motivated this analysis: NOT preregistered.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics import renderSVG
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parents[1]
PARTS = ("bolt", "nut", "washer", "bracket")
DEV_SUFFIXES = (
    "train-good-016",
    "test-logical_anomalies-043",
    "train-good-046",
    "test-logical_anomalies-062",
    "train-good-031",
    "test-logical_anomalies-082",
    "train-good-312",
    "test-logical_anomalies-072",
    "train-good-265",
    "test-logical_anomalies-050",
    "train-good-057",
    "test-logical_anomalies-065",
    "train-good-250",
    "test-logical_anomalies-087",
    "train-good-257",
    "test-logical_anomalies-061",
)
POLICY = {
    "name": "exploratory_dark_center_review_cue_v1",
    "preregistered": False,
    "motivation": "Known development nut overcounts motivated this probe; not independent validation",
    "pixels": "Unmodified saved 1024-max-side model PNGs; no GPU or model inference",
    "luminance": "(0.2126 R + 0.7152 G + 0.0722 B) / 255 on encoded sRGB; not calibrated radiance",
    "center": "The saved model point, without searching or moving toward a favorable pixel",
    "center_radius_fraction_of_long_side": 0.005,
    "center_radius_minimum_pixels": 2.0,
    "annulus_inner_radius_multiple": 2.0,
    "annulus_outer_radius_multiple": 3.0,
    "contrast": "median(annulus luminance) - median(center disk luminance)",
    "review_if_contrast_below": 0.06,
    "bright_center_pixel_threshold": 245 / 255,
    "review_if_bright_center_fraction_at_least": 0.25,
    "incomplete_annulus": "Request review, never infer a missing object",
    "image_rule": "Request review if ANY model-listed nut point requests review",
    "interpretation": "A dark central-hole cue is not supported at this estimated point; NOT proof of no hole",
    "count_policy": "Never delete or relabel any object; original counts and performance stay unchanged",
    "sensitivity_grid": {
        "radius_fractions": [0.003, 0.005, 0.007],
        "contrast_thresholds": [0.03, 0.06, 0.10],
        "purpose": "Report every setting; do not select a winning threshold from these errors",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def point_metrics(rgb: np.ndarray, center: list[float], radius_fraction: float) -> dict:
    """Only image bytes and a model point enter the photometric calculation."""
    height, width = rgb.shape[:2]
    x, y = center[0] * width, center[1] * height
    radius = max(2.0, max(width, height) * radius_fraction)
    outer = radius * 3
    x0, x1 = max(0, math.floor(x - outer)), min(width, math.ceil(x + outer) + 1)
    y0, y1 = max(0, math.floor(y - outer)), min(height, math.ceil(y + outer) + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    distance = (xx + 0.5 - x) ** 2 + (yy + 0.5 - y) ** 2
    gray = rgb[y0:y1, x0:x1] @ np.array([0.2126, 0.7152, 0.0722]) / 255.0
    disk = gray[distance <= radius**2]
    annulus = gray[(distance >= (2 * radius) ** 2) & (distance <= outer**2)]
    complete = x - outer >= 0 and y - outer >= 0 and x + outer < width and y + outer < height
    if disk.size == 0 or annulus.size == 0:
        return {
            "center_px": [x, y],
            "radius_px": radius,
            "complete_annulus": False,
            "center_median": None,
            "annulus_median": None,
            "contrast": None,
            "bright_center_fraction": None,
            "center_pixels": int(disk.size),
            "annulus_pixels": int(annulus.size),
        }
    return {
        "center_px": [x, y],
        "radius_px": radius,
        "complete_annulus": complete,
        "center_median": float(np.median(disk)),
        "annulus_median": float(np.median(annulus)),
        "contrast": float(np.median(annulus) - np.median(disk)),
        "bright_center_fraction": float(np.mean(disk >= 245 / 255)),
        "center_pixels": int(disk.size),
        "annulus_pixels": int(annulus.size),
    }


def reasons(metric: dict, threshold: float) -> list[str]:
    result = []
    if not metric["complete_annulus"]:
        result.append("incomplete_neighborhood")
    if metric["contrast"] is None or metric["contrast"] < threshold:
        result.append("dark_center_cue_not_supported")
    if metric["bright_center_fraction"] is not None and metric["bright_center_fraction"] >= 0.25:
        result.append("bright_center_or_reflection")
    return result


def summarize(rows: list[dict], key: str) -> dict:
    flagged = [row for row in rows if row[key]]
    wrong = [row for row in rows if not row["original_count_exact"]]
    correct = [row for row in rows if row["original_count_exact"]]
    return {
        "images": len(rows),
        "request_review": len(flagged),
        "not_flagged": len(rows) - len(flagged),
        "wrong_images_flagged": sum(row[key] for row in wrong),
        "wrong_images": len(wrong),
        "correct_images_flagged": sum(row[key] for row in correct),
        "correct_images": len(correct),
        "wrong_images_not_flagged": sum(not row[key] for row in wrong),
        "correct_images_not_flagged": sum(not row[key] for row in correct),
        "flagged_case_ids": [row["case_id"] for row in flagged],
        "false_review_case_ids": [row["case_id"] for row in correct if row[key]],
        "uncovered_error_case_ids": [row["case_id"] for row in wrong if not row[key]],
    }


def font(size=14):
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT / "evaluation-runs/loco_development_27b_spatial_v1")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evaluation-runs/nut_visibility_development_probe"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; retain previous exploratory results")
    run = json.loads((args.run / "run.json").read_text())
    rows = [json.loads(line) for line in (args.run / "predictions.jsonl").read_text().splitlines()]
    expected = ["mvtec-loco-screw_bag-" + suffix for suffix in DEV_SUFFIXES]
    if (
        run["status"] != "completed"
        or run["split"] != "development"
        or [r["case_id"] for r in rows] != expected
    ):
        parser.error("Requires exactly the fixed completed 16 development predictions, in order")
    args.output.mkdir(parents=True)
    (args.output / "crops").mkdir()
    save_json(args.output / "policy.json", POLICY)
    # Policy saved before pixel processing, but this remains motivated by known development failures.
    (args.output / "probe_source.py").write_bytes(Path(__file__).read_bytes())
    points, image_rows, tiles = [], [], []
    for image_index, row in enumerate(rows, 1):
        if row["split"] != "development":
            raise ValueError("Nondevelopment row")
        path = (args.run / row["model_input_file"]).resolve()
        if not path.is_relative_to(args.run.resolve()) or sha(path) != row["model_input_sha256"]:
            raise ValueError("Saved model input identity mismatch")
        with Image.open(path) as picture:
            image = picture.convert("RGB")
        rgb = np.asarray(image, dtype=np.float32)
        image_points = []
        for object_index, obj in enumerate(row["inventory"]["objects"], 1):
            if obj["part"] != "nut":
                continue
            metric = point_metrics(rgb, obj["center"], POLICY["center_radius_fraction_of_long_side"])
            point = {
                "case_id": row["case_id"],
                "image_index": image_index,
                "object_index": object_index,
                "model_center": obj["center"],
                "model_input_sha256": sha(path),
                **metric,
            }
            point["review_reasons"] = reasons(metric, POLICY["review_if_contrast_below"])
            point["request_review"] = bool(point["review_reasons"])
            point["scale_metrics"] = {
                str(scale): point_metrics(rgb, obj["center"], scale)
                for scale in POLICY["sensitivity_grid"]["radius_fractions"]
            }
            points.append(point)
            image_points.append(point)
            # Diagram overlay is a derivative diagnostic; source model PNG remains untouched.
            x, y = metric["center_px"]
            half = 40
            box = (round(x) - half, round(y) - half, round(x) + half, round(y) + half)
            crop = image.crop(box).resize((240, 240), Image.Resampling.NEAREST)
            draw = ImageDraw.Draw(crop)
            cx, cy = (x - box[0]) * 3, (y - box[1]) * 3
            for multiple, color in [(1, "#ffdf43"), (2, "#47d9ee"), (3, "#47d9ee")]:
                radius = metric["radius_px"] * multiple * 3
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=2)
            crop_name = f"{image_index:02d}-object-{object_index:02d}.png"
            crop.save(args.output / "crops" / crop_name)
            point["diagnostic_crop"] = "crops/" + crop_name
            tile = Image.new("RGB", (270, 315), "#ffffff")
            tile.paste(crop, (15, 5))
            d = ImageDraw.Draw(tile)
            d.text(
                (8, 249),
                f"{image_index:02d} {DEV_SUFFIXES[image_index - 1]} / obj {object_index}",
                font=font(13),
                fill="black",
            )
            d.text(
                (8, 270),
                f"D={metric['contrast']:.3f} bright={metric['bright_center_fraction']:.2f}",
                font=font(14),
                fill="black",
            )
            d.text(
                (8, 292),
                "REVIEW CUE" if point["request_review"] else "not flagged",
                font=font(14),
                fill="#9c392e" if point["request_review"] else "#20634d",
            )
            tiles.append(tile)
        # Ground truth enters only after photometric features/flags were calculated.
        original_exact = row["observation"]["observed"] == row["ground_truth"] and not row["error"]
        assert original_exact == row["counts_exact"]
        item = {
            "case_id": row["case_id"],
            "image_index": image_index,
            "original_count_exact": original_exact,
            "original_observed": row["observation"]["observed"],
            "ground_truth_for_image_level_scoring_only": row["ground_truth"],
            "nut_points": len(image_points),
            "review_points": sum(p["request_review"] for p in image_points),
            "request_review": any(p["request_review"] for p in image_points),
            "minimum_contrast": min((p["contrast"] for p in image_points), default=None),
            "model_input_file": str(path),
            "model_input_sha256": sha(path),
        }
        for scale in POLICY["sensitivity_grid"]["radius_fractions"]:
            for threshold in POLICY["sensitivity_grid"]["contrast_thresholds"]:
                item[f"sensitivity_{scale}_{threshold}"] = any(
                    reasons(p["scale_metrics"][str(scale)], threshold) for p in image_points
                )
        image_rows.append(item)
    save_json(args.output / "points.json", points)
    save_json(args.output / "images.json", image_rows)
    with (args.output / "images.csv").open("w") as handle:
        fields = [
            "image_index",
            "case_id",
            "original_count_exact",
            "nut_points",
            "review_points",
            "request_review",
            "minimum_contrast",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(image_rows)
    sensitivity = []
    for scale in POLICY["sensitivity_grid"]["radius_fractions"]:
        for threshold in POLICY["sensitivity_grid"]["contrast_thresholds"]:
            sensitivity.append(
                {
                    "radius_fraction": scale,
                    "contrast_threshold": threshold,
                    **summarize(image_rows, f"sensitivity_{scale}_{threshold}"),
                }
            )
    summary = {
        "scope": "Development exploration only; no holdout or model inference",
        "created_at": datetime.now(UTC).isoformat(),
        "source_run": str(args.run.resolve()),
        "source_run_sha256": sha(args.run / "run.json"),
        "source_predictions_sha256": sha(args.run / "predictions.jsonl"),
        "probe_source_sha256": sha(args.output / "probe_source.py"),
        "policy_sha256": sha(args.output / "policy.json"),
        "nut_prediction_points": len(points),
        "points_request_review": sum(p["request_review"] for p in points),
        "primary_rule": summarize(image_rows, "request_review"),
        "sensitivity_grid_not_threshold_selection": sensitivity,
        "original_counts_changed": False,
        "object_level_labels_available": False,
        "limitations": [
            "No visible-hole existence labels or instance annotations",
            "Image-level correct counts do not validate every predicted object center",
            "Dark patches can be screw slots, shadows or texture; bright holes can show the background",
            "Object diameter, pose, bag reflections and imprecise model centers invalidate a universal fixed-radius cue",
            "Flags request review only; not evidence to delete an object or to certify unflagged counts",
            "Known errors motivated the rule; all sensitivity settings are exploratory, no winner selected",
        ],
    }
    save_json(args.output / "summary.json", summary)
    sheet = Image.new("RGB", (5 * 270, math.ceil(len(tiles) / 5) * 315), "#e4e9e8")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % 5) * 270, (index // 5) * 315))
    sheet.save(args.output / "nut_point_contact_sheet.png")
    drawing = Drawing(850, 340)
    chart = LinePlot()
    chart.x = 55
    chart.y = 50
    chart.width = 750
    chart.height = 230
    chart.data = [
        [(row["image_index"], row["minimum_contrast"]) for row in image_rows],
        [(1, 0.06), (16, 0.06)],
    ]
    chart.lines[0].strokeColor = colors.HexColor("#216d78")
    chart.lines[0].strokeWidth = 1.5
    chart.lines[1].strokeColor = colors.HexColor("#bd493a")
    chart.lines[1].strokeDashArray = [5, 3]
    chart.xValueAxis.valueMin = 1
    chart.xValueAxis.valueMax = 16
    chart.xValueAxis.valueStep = 1
    chart.yValueAxis.valueMin = -0.6
    chart.yValueAxis.valueMax = 0.6
    chart.yValueAxis.valueStep = 0.2
    drawing.add(chart)
    drawing.add(
        String(55, 315, "Minimum ring-minus-center luminance per image (development only)", fontSize=14)
    )
    drawing.add(
        String(
            55, 293, "Red dashed: 0.06 review threshold. Near-white centers also trigger review.", fontSize=10
        )
    )
    drawing.add(
        String(
            55,
            20,
            "Image index in frozen 16-case development order; no count correction or holdout claim",
            fontSize=10,
        )
    )
    renderSVG.drawToFile(drawing, str(args.output / "contrast_by_image.svg"))
    print(json.dumps(summary["primary_rule"], indent=2))


if __name__ == "__main__":
    main()
