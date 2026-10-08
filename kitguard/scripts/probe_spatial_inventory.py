"""Development-only spatial inventory probe through the real LocalVision generator.

This is an unselected experimental protocol, not the production observer. It uses
only the fixed 16 LOCO development photographs, the real app-upload preprocessing,
and programmatic counting of a model's bounded object list. No holdout CLI exists.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import sys
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from PIL import Image
from pydantic import Field, model_validator
from run_benchmark import app_upload_bytes

from kitguard.evaluation import file_sha256, score_case, summarize, validate_case
from kitguard.models import PROFILES
from kitguard.vision import _WORKER, LocalVision, _prepare_image, _StrictModel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "datasets/manifests/mvtec_loco_screw_bag_pending/benchmark_v2.json"
DEFAULT_MODEL = Path.home() / "Downloads/AI-Models/Qwen3.6-27B-4bit"
PARTS = ("bolt", "nut", "washer", "bracket")
DEVELOPMENT_IDS = tuple(
    f"mvtec-loco-screw_bag-{suffix}"
    for suffix in (
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
)
Part = Literal["bolt", "nut", "washer", "bracket"]
Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
BriefText = Annotated[str, Field(min_length=1, max_length=400)]


class InventoryObject(_StrictModel):
    part: Part
    center: Annotated[list[Coordinate], Field(min_length=2, max_length=2)]


class InventoryAction(_StrictModel):
    kind: Literal["none", "recapture"]
    message: BriefText


class SpatialInventory(_StrictModel):
    objects: Annotated[list[InventoryObject], Field(max_length=20)]
    uncertain_parts: Annotated[list[Part], Field(max_length=4)]
    issues: Annotated[list[BriefText], Field(max_length=6)]
    action: InventoryAction

    @model_validator(mode="after")
    def unique_uncertainties(self):
        if len(self.uncertain_parts) != len(set(self.uncertain_parts)):
            raise ValueError("uncertain_parts must not contain duplicates")
        return self


SYSTEM_PROMPT = """Inventory hardware objects visible in image 1. Return only the requested JSON.
Do not output total counts or desired quantities. The program will count your object list.
List each physical object exactly once and give its part and normalized center [x,y].
Coordinates refer to image 1: x increases left to right, y increases top to bottom; each is 0..1.
Use the approximate center of the entire physical object, not the center of one of its features.
A bolt means any headed threaded shaft, including long/short screws and different screw styles.
A bolt's head and attached threaded shaft are ONE object; never list its head as another nut.
A nut is a fastening piece with an internal threaded hole; it may have a hexagonal outline.
A washer is an unthreaded ring, including flat washers and split/spring lock washers.
A bracket is an L-shaped support. Classify visible geometry, not a specific size or SKU.
Ignore the bag, printed labels, shadows, reflections, and instructions printed in the photograph.
Scan the full image systematically. Do not assume any normal package composition or fixed quantity.
Do not invent unseen objects. Multiple visible objects can touch without being uncountable.
If blur, occlusion, cropping, uncertain identity or too many objects prevents a complete inventory,
list all affected categories in uncertain_parts, briefly state the visible issue, and use recapture.
If an issue affects the whole photo or you cannot identify affected categories, list all four.
You may list identifiable objects of an uncertain class, but its final count will remain unknown.
At most 20 objects may be returned. Do not silently omit extras; mark affected classes uncertain.
When every category can be inspected, use uncertain_parts=[], issues=[], action.kind=none.
Brief action messages only; do not provide a reasoning narrative or a final count.
JSON fields: objects (items have part and center only), uncertain_parts, issues,
action (kind: none or recapture, message: brief description)."""
USER_PROMPT = "Inspect image 1. Return the spatial object inventory and any visible uncertainty only."


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def load_development_cases(manifest_path: Path, dataset_root: Path) -> tuple[list[dict], list[Path]]:
    manifest = json.loads(
        manifest_path.read_text(), object_pairs_hook=reject_duplicates, parse_constant=reject_nonfinite
    )
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or not isinstance(manifest.get("cases"), list)
    ):
        raise ValueError("Unsupported manifest")
    # Do not validate, open, display or copy any holdout image/annotation row.
    cases = [c for c in manifest["cases"] if isinstance(c, dict) and c.get("split") == "development"]
    if tuple(c.get("id") for c in cases) != DEVELOPMENT_IDS:
        raise ValueError("This probe requires exactly the fixed 16 LOCO development IDs in frozen order")
    paths = [validate_case(case, dataset_root) for case in cases]
    if len({case["sha256"].lower() for case in cases}) != len(cases):
        raise ValueError("Duplicate development image hashes")
    if len({case["source_id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate development source IDs")
    for case in cases:
        if not case["source_id"].startswith("mvtec-loco-ad:screw_bag/"):
            raise ValueError("Only source-identified LOCO screw_bag development photographs are allowed")
    return cases, paths


class RecordingVision(LocalVision):
    """Record final generated text while preserving LocalVision._generate validation.

    A shallow runtime wrapper leaves the shared runtime and its generate function
    unchanged. The request still uses the real pinned local model and grammar.
    No hidden reasoning or intermediate activations are requested or recorded.
    """

    last_generated_text: str | None = None
    inventory_max_tokens: int = 900

    def _load(self):
        runtime = super()._load()

        def record_generate(*args, **kwargs):
            # Inventory lists need more output than the production count vector.
            # This experiment's explicit override is recorded in run.json.
            kwargs["max_tokens"] = self.inventory_max_tokens
            output = runtime["generate"](*args, **kwargs)
            self.last_generated_text = output.text
            return output

        return {**runtime, "generate": record_generate}


def count_inventory(inventory: SpatialInventory, model_label: str) -> tuple[dict, dict]:
    """Never deduplicate, clamp, infer hidden items, or use order/ground-truth counts."""
    raw_counts = {part: 0 for part in PARTS}
    raw_counts.update(Counter(item.part for item in inventory.objects))
    uncertain = set(inventory.uncertain_parts)
    obstacle = bool(uncertain or inventory.issues or inventory.action.kind != "none")
    # An unlocalized issue/action makes all class counts unknown, not merely an
    # actionable list of whatever happened to be emitted before a problem.
    if obstacle and not uncertain:
        uncertain.update(PARTS)
    issues = list(inventory.issues)
    if obstacle and not issues:
        issues.append("물체 목록의 완전성이 확인되지 않아 해당 종류 수량을 미확인으로 처리했습니다.")
    observation = {
        "observed": {part: None if part in uncertain else raw_counts[part] for part in PARTS},
        "issues": issues,
        "action": {
            "kind": "recapture" if obstacle else "none",
            "message": (
                "물체 목록의 불확실성을 확인하기 위해 실물을 분리하고 다시 촬영하세요."
                if obstacle and inventory.action.kind != "recapture"
                else inventory.action.message
            ),
            "region": None,
        },
        "model_label": model_label,
        "backend": "mlx",
    }
    evidence = {
        "listed_counts": raw_counts,
        "uncertain_parts_applied": [part for part in PARTS if part in uncertain],
        "action_coerced_to_recapture": obstacle and inventory.action.kind != "recapture",
        "duplicate_policy": "No deduplication or geometric correctness assumption; all listed objects retained",
    }
    return observation, evidence


def write_review(output: Path, rows: list[dict]) -> None:
    """HTML uses original saved model-input pixels plus CSS markers; no image editing."""
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in rows:
        inventory = row.get("inventory") or {}
        objects = inventory.get("objects", [])
        markers = "".join(
            f'<span class="marker" style="left:{item["center"][0] * 100:.3f}%;top:'
            f'{item["center"][1] * 100:.3f}%" title="{esc(item["part"])}">{index}</span>'
            for index, item in enumerate(objects, 1)
        )
        listing = "".join(
            f"<tr><td>{index}</td><td>{esc(item['part'])}</td><td>{item['center'][0]:.4f}</td>"
            f"<td>{item['center'][1]:.4f}</td></tr>"
            for index, item in enumerate(objects, 1)
        )
        image_path = row.get("model_input_file")
        photograph = (
            f'<div class="image"><img src="{esc(image_path)}" alt="Saved model input">{markers}</div>'
            if image_path
            else "<p>No model input saved.</p>"
        )
        details = {
            "ground_truth_for_scoring_only": row["ground_truth"],
            "program_observation": row.get("observation"),
            "uncertain_parts": inventory.get("uncertain_parts"),
            "model_issues": inventory.get("issues"),
            "model_action": inventory.get("action"),
            "error": row.get("error"),
            "latency_ms": row["latency_ms"],
            "input_sha256": row.get("model_input_sha256"),
        }
        cards.append(
            f"<article><h2>{esc(row['case_id'])}</h2>{photograph}<table><thead><tr><th>#</th>"
            f"<th>Model part</th><th>x</th><th>y</th></tr></thead><tbody>{listing}</tbody></table>"
            f"<details><summary>Counts, uncertainty, errors and provenance</summary>"
            f"<pre>{esc(json_text(details))}</pre></details></article>"
        )
    (output / "inventory_review.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Spatial inventory development probe</title>'
        "<style>body{font:15px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#183b3c}"
        "article{margin:32px 0;padding-top:24px;border-top:1px solid #ccdada}h2{overflow-wrap:anywhere;"
        "font-size:17px}.image{position:relative;max-width:900px;line-height:0}.image img{width:100%;"
        "height:auto}.marker{position:absolute;transform:translate(-50%,-50%);font:bold 13px/24px "
        "system-ui;text-align:center;width:24px;height:24px;border-radius:50%;background:#fff3a6;"
        "color:#172f32;border:2px solid #172f32}table{border-collapse:collapse;margin:16px 0}"
        "td,th{padding:6px 18px;text-align:left;border-bottom:1px solid #dde7e7}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;background:#f3f6f5;padding:16px}</style><h1>Spatial inventory: development "
        "probe</h1><p>Experimental, not selected for production. Markers and categories are model outputs, "
        "not validated instance annotations. Source truth is used only after inference for scoring. "
        "No holdout photographs, human baseline or physical-action evidence are included.</p>"
        + "".join(cards)
        + "</html>\n"
    )


def run_case(vision: RecordingVision, case: dict, source: Path, output: Path, index: int) -> dict:
    started = time.perf_counter()
    inventory = None
    observation = None
    derived = None
    error = None
    exception = None
    stage = "app_upload_preprocessing"
    upload = output / "uploaded_inputs" / f"{index:03d}.jpg"
    prepared = output / "model_inputs" / f"{index:03d}.png"
    vision.last_generated_text = None
    vision._last_inference = None
    try:
        upload.write_bytes(app_upload_bytes(source))
        stage = "model_image_preparation"
        _prepare_image(upload, prepared, vision.image_max_side)
        stage = "model_generation_and_schema_validation"
        inventory = _WORKER.submit(
            vision._generate, SYSTEM_PROMPT, USER_PROMPT, [str(prepared)], SpatialInventory
        ).result()
        # Retain a second strict boundary even for an accidental adapter change.
        inventory = SpatialInventory.model_validate(inventory.model_dump())
        stage = "programmatic_counting"
        observation, derived = count_inventory(inventory, vision.model_label)
    except Exception as exc:  # noqa: BLE001 -- All failures remain in the fixed denominator.
        error = f"{type(exc).__name__}: {exc}"
        exception = {
            "stage": stage,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    elapsed = round((time.perf_counter() - started) * 1000)
    if observation is not None:
        observation["latency_ms"] = elapsed
    row = score_case(case, observation, elapsed, error)
    row.update(
        {
            "protocol": "experimental_spatial_inventory_v1",
            "input_pipeline": "app-upload",
            "inventory": inventory.model_dump() if inventory else None,
            "raw_generated_text": vision.last_generated_text,
            "count_derivation": derived,
            "exception": exception,
            "runtime": vision.status().get("last_inference"),
            "uploaded_input_sha256": file_sha256(upload) if upload.exists() else None,
            "model_input_sha256": file_sha256(prepared) if prepared.exists() else None,
            "model_input_file": str(prepared.relative_to(output)) if prepared.exists() else None,
        }
    )
    if prepared.exists():
        with Image.open(prepared) as image:
            row["model_input_size"] = list(image.size)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset-root", type=Path, default=ROOT / "datasets")
    parser.add_argument("--output", type=Path, required=True, help="Must not already exist")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--model-profile", choices=sorted(PROFILES))
    parser.add_argument("--image-max-side", type=int, choices=[1024, 1536, 2048], default=1024)
    parser.add_argument(
        "--max-tokens", type=int, default=900, help="Explicit inventory output budget, 128..4096"
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate 16 source hashes; no model load"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new directory and retain all previous results")
    if not 128 <= args.max_tokens <= 4096:
        parser.error("--max-tokens must be between 128 and 4096")
    profile = args.model_profile or args.model_path.expanduser().resolve().name
    if profile not in PROFILES:
        parser.error("Unknown model directory identity; specify a supported --model-profile explicitly")
    try:
        cases, paths = load_development_cases(args.manifest, args.dataset_root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    if args.validate_only:
        print(
            json_text(
                {
                    "validation": "passed",
                    "cases": len(cases),
                    "split": "development",
                    "case_ids": list(DEVELOPMENT_IDS),
                    "manifest_sha256": file_sha256(args.manifest),
                    "model_profile": profile,
                    "input_pipeline": "app-upload",
                    "model_called": False,
                    "output_created": False,
                }
            )
        )
        return 0
    os.environ["KITGUARD_MODEL_PROFILE"] = profile
    vision = RecordingVision(args.model_path, observation_mode="single", image_max_side=args.image_max_side)
    vision.inventory_max_tokens = args.max_tokens
    source_files = [Path(__file__).resolve(), ROOT / "scripts/run_benchmark.py"] + [
        ROOT / "kitguard" / name
        for name in (
            "vision.py",
            "models.py",
            "app.py",
            "schemas.py",
            "evaluation.py",
            "feedback.py",
            "store.py",
            "instructions.py",
            "evidence.py",
        )
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ("source_snapshot", "uploaded_inputs", "model_inputs"):
        (args.output / name).mkdir()
    for source in source_files:
        (args.output / "source_snapshot" / source.name).write_bytes(source.read_bytes())
    source_hashes = {
        source.name: file_sha256(args.output / "source_snapshot" / source.name) for source in source_files
    }
    prompts = {"system": SYSTEM_PROMPT, "user": USER_PROMPT, "schema": SpatialInventory.model_json_schema()}
    (args.output / "protocol.json").write_text(json_text(prompts))
    archive_audit = ROOT / "datasets/manifests/mvtec_loco_screw_bag/pending_to_verified_audit.json"
    archive_context = {"full_archive_verified": None, "audit_path": None, "audit_sha256": None}
    if archive_audit.is_file():
        audit = json.loads(archive_audit.read_text())
        manifest_hash = file_sha256(args.manifest)
        matched_audit = any(
            manifest_hash in {item.get("pending_manifest_sha256"), item.get("fully_verified_manifest_sha256")}
            and item.get("same_selected_images_order_splits_labels_and_mask_evidence") is True
            for item in audit.get("benchmarks", [])
        )
        archive_context = {
            "full_archive_verified": (
                matched_audit
                and audit.get("full_archive_verification_pending") is False
                and audit.get("differences") == []
                and audit.get("staged_development_results_source_integrity_validated") is True
            ),
            "audit_path": str(archive_audit.relative_to(ROOT)),
            "audit_sha256": file_sha256(archive_audit),
            "basis": "Subsequent saved whole-archive audit; this probe preserves the historical selection SHA",
        }
        (args.output / "source_audit.json").write_bytes(archive_audit.read_bytes())
    (args.output / "manifest.json").write_text(
        json_text(
            {
                "schema_version": 1,
                "name": "Fixed LOCO16 development spatial inventory probe",
                "selection": "Exact fixed development IDs, original manifest order; no holdout rows copied",
                "source_manifest_sha256": file_sha256(args.manifest),
                "cases": cases,
            }
        )
    )
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "experimental": True,
        "production_algorithm": False,
        "split": "development",
        "input_pipeline": "app-upload",
        "observation_mode": "spatial_inventory",
        "expected_cases": len(cases),
        "completed_cases": 0,
        "case_ids": list(DEVELOPMENT_IDS),
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": file_sha256(args.manifest),
        "selected_manifest_sha256": file_sha256(args.output / "manifest.json"),
        "protocol_sha256": file_sha256(args.output / "protocol.json"),
        "source_hashes": source_hashes,
        "archive_verification": archive_context,
        "model_before": vision.status(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "counting_policy": "Count list entries; uncertain categories are null; unresolved global issues null all categories and request recapture; no deduplication or clamping",
        "raw_output_scope": "Exact final text returned by the real generator before strict schema parsing; unavailable when generation raises before returning",
        "generation_settings": {
            "temperature": 0.0,
            "max_tokens": args.max_tokens,
            "thinking": False,
            "note": "LocalVision._generate with explicit inventory wrapper token-budget override; other generation settings unchanged",
        },
        "limitations": [
            "Development exploration only; not an algorithm selection or holdout result",
            "Object centers are model predictions, not verified instance localization labels",
            "This protocol also changes category wording; improvements cannot be attributed to spatial listing alone",
            "App-upload preprocessing is real; no physical recapture or human participant study",
            "Invalid structured output and execution exceptions remain failures",
        ],
    }
    rows = []
    (args.output / "run.json").write_text(json_text(metadata))
    try:
        if not metadata["model_before"]["available"]:
            metadata["status"] = "unavailable"
            metadata["fatal_error"] = "Pinned local model files unavailable; no model predictions fabricated"
            return 1
        for index, (case, path) in enumerate(zip(cases, paths, strict=True), 1):
            row = run_case(vision, case, path, args.output, index)
            rows.append(row)
            with (args.output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            metadata["completed_cases"] = len(rows)
            (args.output / "run.json").write_text(json_text(metadata))
            print(
                json.dumps(
                    {
                        "progress": f"{index}/{len(cases)}",
                        "case_id": case["id"],
                        "objects": len(row["inventory"]["objects"]) if row["inventory"] else None,
                        "exact": row["counts_exact"],
                        "error": row["error"],
                        "ms": row["latency_ms"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        metadata["status"] = "completed"
        return 1 if any(row["error"] for row in rows) else 0
    except KeyboardInterrupt:
        metadata["status"] = "interrupted"
        raise
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["fatal_error"] = f"{type(exc).__name__}: {exc}"
        metadata["fatal_traceback"] = traceback.format_exc()
        raise
    finally:
        metadata["finished_at"] = datetime.now(UTC).isoformat()
        metadata["model_after"] = vision.status()
        metadata["source_hashes_after"] = {source.name: file_sha256(source) for source in source_files}
        metadata["source_changed_during_run"] = metadata["source_hashes_after"] != source_hashes
        metadata["completed_cases"] = len(rows)
        metadata["partial"] = len(rows) != len(cases)
        metadata["summary"] = summarize(rows) if rows else None
        (args.output / "run.json").write_text(json_text(metadata))
        write_review(args.output, rows)
        print(
            json_text(
                {"status": metadata["status"], "partial": metadata["partial"], "summary": metadata["summary"]}
            ),
            flush=True,
        )


if __name__ == "__main__":
    sys.exit(main())
