"""Fixed 28-case development experiment: one inventory, conditional identity review.

Never selected automatically; never imports or evaluates the historical 64 holdout.
Production LocalVision, its modes and its default are not modified. All inference
uses LocalVision.observe and its original single _WORKER. Raw model text, actual
prepared images, errors and the entire predeclared denominator are retained.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from kitguard.evaluation import file_sha256, score_case, summarize
from kitguard.identity import SYSTEM_PROMPT as IDENTITY_SYSTEM
from kitguard.identity import IdentityResponse, build_prompt, save_crops, validate_response
from kitguard.models import PROFILES
from kitguard.schemas import Observation
from kitguard.vision import LocalVision, ModelOutputError, ModelUnavailableError, _parse_json

ROOT = Path(__file__).resolve().parents[1]
PARTS = ("bolt", "nut", "washer", "bracket")
MODE = "selective_identity_experimental_v1"
DEV_RUN = ROOT / "evaluation-runs/v03_guarded_integrated_development_v1"
DEV_PREDICTIONS_SHA = "defa8353d8f0ea2eb89ec3ae8fd0ecb0bc4e90b80caa8a32c075765548d6e9a4"
DEV_MANIFEST_SHA = "8e85c97a5dee7d0c571964597a8282b312e7691e66c8c36da541cf41dd2283c6"
POLICY = {
    "mode": MODE,
    "production_selected": False,
    "selection_uses_truth": False,
    "base": "One spatial_inventory original-frame call, 1536px, max_tokens=900",
    "identity": "All nut/washer points only when base is complete and clear; max_tokens=1800",
    "gate": "Same category AND independent_object AND empty issue; washer requires through_hole",
    "conflict": "Null original and non-unknown conflicting category; never repair or recount",
    "malformed_response": "Retain raw output and fail entire observation; no ready result",
    "identity_contract": "Explicit single-direction adapter; no synthetic orientation verification",
    "budget": "At most two actual generate calls per case; no retry or search",
}
EVALUATION_POLICY = {
    "population": "Exactly the already-exposed v03 integrated development 28, historical order",
    "input_pipeline": "Saved hash-verified app-normalized JPEG; no new upload timing",
    "timing": "Copied normalized input to observation result; includes first-case cold load",
}


def utc_now():
    return datetime.now(UTC).isoformat()


def save_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def single_direction_targets(base: dict) -> list[dict]:
    """Adapt only eligibility, without inventing the two-pass guard contract."""
    parsed = Observation.model_validate(base)
    if parsed.verification is not None or parsed.identity_verification is not None:
        raise ValueError("Expected an actual single-direction base observation")
    if parsed.object_evidence is None:
        raise ValueError("Missing original spatial inventory")
    if (parsed.issues or parsed.action.kind != "none"
            or any(getattr(parsed.observed, p) is None for p in PARTS)):
        return []
    return [
        {"id": f"p{index:03d}", "object_index": index,
         "original_part": item.part, "center": list(item.center)}
        for index, item in enumerate(parsed.object_evidence.objects, 1)
        if item.part in ("nut", "washer")
    ]


def single_direction_decision(base: dict, targets: list[dict], response) -> dict:
    """Use the frozen identity acceptance predicate; only turn counts unknown."""
    if not targets or targets != single_direction_targets(base):
        raise ValueError("Identity targets must be exactly the eligible single-direction points")
    parsed = validate_response(response, targets)
    by_id = {item.id: item for item in parsed.objects}
    blocked, decisions = set(), []
    for target in targets:
        item = by_id[target["id"]]
        accepted = (
            item.part == target["original_part"]
            and item.status == "independent_object"
            and not item.issue.strip()
            and (item.part != "washer" or item.opening == "through_hole")
        )
        affected = set()
        if not accepted:
            affected.add(target["original_part"])
            if item.part != "unknown" and item.part != target["original_part"]:
                affected.add(item.part)
        blocked.update(affected)
        decisions.append({"id": item.id, "accepted": accepted,
                          "original_part": target["original_part"],
                          "identity": item.model_dump(),
                          "blocked_categories": [p for p in PARTS if p in affected]})
    result = copy.deepcopy(base)
    if blocked:
        for part in blocked:
            result["observed"][part] = None
        result["object_evidence"]["uncertain_parts"] = [p for p in PARTS if p in blocked]
        result["issues"] = ["실험적 단방향 신원 확인에서 불확실한 종류가 남았습니다 / 单方向实验身份核查存在未确认类别"]
        result["action"] = {"kind": "recapture", "region": None,
                            "message": "필요한 종류를 추가 확인하세요 / 请补充核查未确认类别"}
    # Deliberately no identity_verification field: that schema requires two real passes.
    Observation.model_validate(result)
    return {"observation": result, "blocked_categories": [p for p in PARTS if p in blocked],
            "targets": decisions, "response": parsed.model_dump()}


class SelectiveIdentityVision(LocalVision):
    """Experimental observer; inherited observe owns the original serial worker."""

    def __init__(self, model_path: Path | None = None):
        super().__init__(model_path, observation_mode="spatial_inventory", image_max_side=1536)
        pinned = PROFILES["Qwen3.6-27B-4bit"]
        if any(self.profile[k] != pinned[k] for k in ("repo_id", "revision")):
            raise ValueError("This experiment fixes the pinned Qwen3.6-27B profile")
        self.model_label += " · selective identity experiment"
        self.protocol_sources.update({
            "identity.py": file_sha256(ROOT / "kitguard/identity.py"),
            "schemas.py": file_sha256(ROOT / "kitguard/schemas.py"),
            "probe_selective_identity.py": file_sha256(Path(__file__)),
        })
        self.protocol_sha256 = hashlib.sha256(json.dumps(
            {"sources": self.protocol_sources, "policy": POLICY}, sort_keys=True
        ).encode()).hexdigest()
        self.artifact_dir: Path | None = None

    def status(self):
        value = super().status()
        value.update(observation_mode=MODE, base_observation_mode="spatial_inventory",
                     production_selected=False)
        return value

    def _generate(self, system, prompt, images, schema, *, max_tokens=450):
        """Mirror the existing generate boundary, additionally retain raw text."""
        if self.artifact_dir is None:
            raise ValueError("Set a new per-case artifact directory before observation")
        calls = self._observation_attempt.setdefault("generation_calls", [])
        call_dir = self.artifact_dir / f"call-{len(calls) + 1:02d}"
        call_dir.mkdir(parents=True, exist_ok=False)
        saved_images = []
        for index, source in enumerate(images, 1):
            source_path = Path(source)
            target = call_dir / f"image-{index:02d}{source_path.suffix}"
            shutil.copyfile(source_path, target)
            saved_images.append({"path": str(target.relative_to(self.artifact_dir)),
                                 "sha256": file_sha256(target)})
        record = {"schema": schema.__name__, "system": system, "prompt": prompt,
                  "max_tokens": max_tokens, "temperature": 0.0, "images": saved_images,
                  "status": "pending", "raw_text": None, "runtime": None}
        calls.append(record)
        save_json(call_dir / "generation.json", record)
        self._last_inference = None
        try:
            runtime = self._load()
            formatted = runtime["template"](
                runtime["processor"], runtime["config"],
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                num_images=len(images), enable_thinking=False,
            )
            tokenizer = getattr(runtime["processor"], "tokenizer", runtime["processor"])
            grammar = runtime["grammar"](tokenizer, schema.model_json_schema())
            started = time.perf_counter()
            output = runtime["generate"](
                runtime["model"], runtime["processor"], formatted, image=images or None,
                max_tokens=max_tokens, temperature=0.0, logits_processors=[grammar], verbose=False,
            )
            self._last_inference = {
                "seconds": round(time.perf_counter() - started, 3),
                "prompt_tokens": output.prompt_tokens, "generation_tokens": output.generation_tokens,
                "mlx_reported_peak_memory_gb": round(output.peak_memory, 3),
                "finish_reason": output.finish_reason,
            }
            record.update(raw_text=output.text, runtime=dict(self._last_inference), status="returned")
            save_json(call_dir / "generation.json", record)  # Preserve before parsing can fail.
            payload = _parse_json(output.text.strip(), schema)
            record.update(parsed=payload.model_dump(), status="parsed")
            self._error = None
            return payload
        except Exception as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            self._error = f"Experimental inference failed: {type(exc).__name__}"
            if isinstance(exc, (ModelOutputError, ModelUnavailableError)):
                raise
            raise ModelUnavailableError(self._error) from exc
        finally:
            save_json(call_dir / "generation.json", record)

    def _observe_passes(self, image_path, references, context=None):
        if references or context is not None:
            raise ValueError("This fixed experiment uses no reference images or previous context")
        started = time.perf_counter()
        self._observation_attempt["mode"] = MODE
        self._observation_attempt["experimental_policy"] = POLICY
        base = super()._observe_passes(image_path, {}, None)
        self._observation_attempt["single_direction_base"] = copy.deepcopy(base)
        targets = single_direction_targets(base)
        if not targets:
            clear = (not base["issues"] and base["action"]["kind"] == "none"
                     and all(value is not None for value in base["observed"].values()))
            self._observation_attempt["experimental_identity"] = {
                "status": "skipped_no_candidates" if clear else "skipped_base_unclear",
                "model_called": False, "targets": [],
            }
            result = base
        else:
            identity_dir = self.artifact_dir / "identity"
            identity_dir.mkdir(exist_ok=False)
            crops = save_crops(image_path, targets, identity_dir)
            prompt = build_prompt(crops)
            original = self.artifact_dir / self._observation_attempt["generation_calls"][0]["images"][0]["path"]
            review = {"status": "running", "model_called": True, "targets": targets,
                      "prompt": prompt, "source_sha256": file_sha256(image_path),
                      "full_input_sha256": file_sha256(original),
                      "crops": [{**c, "crop_file": str(Path(c["crop_file"]).relative_to(self.artifact_dir)),
                                 "pixel_crop_file": str(Path(c["pixel_crop_file"]).relative_to(self.artifact_dir))}
                                for c in crops]}
            self._observation_attempt["experimental_identity"] = review
            try:
                response = self._generate(IDENTITY_SYSTEM, prompt,
                                          [str(original), *[c["crop_file"] for c in crops]],
                                          IdentityResponse, max_tokens=1800)
                # Save a valid-JSON response before exact-ID validation can fail.
                review["response"] = response.model_dump()
                decision = single_direction_decision(base, targets, response)
                result = decision.pop("observation")
                review.update(decision)
                review["status"] = "blocked" if decision["blocked_categories"] else "confirmed_candidates"
            except Exception as exc:
                review.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                review["runtime"] = copy.deepcopy(self._last_inference)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        Observation.model_validate(result)
        self._last_inference = {
            "mode": MODE, "production_selected": False,
            "calls": [copy.deepcopy(c["runtime"]) for c in self._observation_attempt["generation_calls"]],
        }
        return result


def fixed_development_inputs():
    """No split/max-cases selector: every run is exactly the same exposed 28."""
    if file_sha256(DEV_RUN / "predictions.jsonl") != DEV_PREDICTIONS_SHA:
        raise ValueError("Historical development predictions changed")
    if file_sha256(DEV_RUN / "manifest.json") != DEV_MANIFEST_SHA:
        raise ValueError("Historical development manifest changed")
    meta = json.loads((DEV_RUN / "run.json").read_text())
    rows = [json.loads(line) for line in (DEV_RUN / "predictions.jsonl").read_text().splitlines()]
    if (meta["status"] != "completed" or meta["split"] != "development"
            or meta["source_changed_during_run"] or len(rows) != 28
            or meta["expected_cases"] != 28 or [r["case_id"] for r in rows] != meta["case_ids"]):
        raise ValueError("Historical fixed development run is incomplete or changed")
    manifest = json.loads((DEV_RUN / "manifest.json").read_text())
    by_id = {c["id"]: c for c in manifest["cases"]}
    cases, inputs = [], []
    for index, row in enumerate(rows, 1):
        case = by_id[row["case_id"]]
        if case["split"] != "development":
            raise ValueError("Nondevelopment case is forbidden")
        for key in ("ground_truth", "sha256", "source_id", "image", "split"):
            if case[key] != row[key]:
                raise ValueError("Historical case identity or truth mismatch")
        path = DEV_RUN / "normalized_inputs" / f"{index:03d}.jpg"
        if file_sha256(path) != row["model_input_sha256"]:
            raise ValueError("Historical normalized input changed")
        cases.append(case)
        inputs.append(path)
    return cases, inputs


def outcome(row):
    if row["error"]:
        return "E"
    return "C" if row["counts_exact"] and row["actionable_counts"] else "W" if row["actionable_counts"] else "U"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Verify fixed inputs and protocol; never load MLX")
    args = parser.parse_args()
    cases, inputs = fixed_development_inputs()
    vision = SelectiveIdentityVision(args.model_path)
    if args.dry_run:
        print(json.dumps({"policy": POLICY, "evaluation_policy": EVALUATION_POLICY,
                          "cases": len(cases), "model": vision.status()}, ensure_ascii=False, indent=2))
        return
    if args.output is None:
        parser.error("--output is required for a real experiment")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), *[ROOT / "kitguard" / name for name in (
        "vision.py", "spatial.py", "identity.py", "schemas.py", "evaluation.py", "app.py",
        "consensus.py", "feedback.py", "models.py", "instructions.py", "regions.py")]]
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    for path in source_paths:
        shutil.copyfile(path, snapshot / path.name)
    metadata = {
        "started_at": utc_now(), "status": "running", "split": "development", "expected_cases": 28,
        "completed_cases": 0, "case_ids": [c["id"] for c in cases], "policy": POLICY,
        "evaluation_policy": EVALUATION_POLICY,
        "source_run": str(DEV_RUN), "source_predictions_sha256": DEV_PREDICTIONS_SHA,
        "source_manifest_sha256": DEV_MANIFEST_SHA, "input_pipeline": EVALUATION_POLICY["input_pipeline"],
        "python": platform.python_version(), "platform": platform.platform(),
        "source_hashes": {p.name: file_sha256(p) for p in source_paths}, "model_before": vision.status(),
    }
    save_json(output / "manifest.json", {"cases": cases, "source_manifest_sha256": DEV_MANIFEST_SHA})
    save_json(output / "protocol.json", {"policy": POLICY, "evaluation_policy": EVALUATION_POLICY,
                                        "model": metadata["model_before"],
                                        "case_ids": metadata["case_ids"], "source_hashes": metadata["source_hashes"]})
    save_json(output / "run.json", metadata)
    if not metadata["model_before"]["available"]:
        metadata.update(status="model_unavailable", finished_at=utc_now())
        save_json(output / "run.json", metadata)
        raise SystemExit("Pinned model unavailable; no predictions fabricated")
    rows = []
    try:
        for index, (case, source) in enumerate(zip(cases, inputs, strict=True), 1):
            started = time.perf_counter()
            case_dir = output / "cases" / f"{index:03d}"
            case_dir.mkdir(parents=True)
            normalized = case_dir / "normalized.jpg"
            shutil.copyfile(source, normalized)
            vision.artifact_dir = case_dir
            observation, error, diagnostics = None, None, None
            try:
                observation = vision.observe(normalized, {p: 1 for p in PARTS}, {})
                diagnostics = copy.deepcopy(vision.status()["last_observation_attempt"])
            except Exception as exc:  # noqa: BLE001 -- Every model failure stays in the planned denominator.
                error = f"{type(exc).__name__}: {exc}"
                diagnostics = copy.deepcopy(getattr(exc, "observation_diagnostics", None))
            elapsed = round((time.perf_counter() - started) * 1000)
            row = score_case(case, observation, elapsed, error)
            row.update(observation_diagnostics=diagnostics, model_input_sha256=file_sha256(normalized),
                       input_pipeline=EVALUATION_POLICY["input_pipeline"], experimental_mode=MODE,
                       runtime=None if error else copy.deepcopy(vision.status()["last_inference"]))
            rows.append(row)
            save_json(case_dir / "result.json", row)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            metadata["completed_cases"] = len(rows)
            save_json(output / "run.json", metadata)
            print(json.dumps({"progress": f"{index}/28", "id": case["id"], "outcome": outcome(row),
                              "ms": elapsed, "error": error}, ensure_ascii=False), flush=True)
        metadata["status"] = "completed"
    except BaseException as exc:
        metadata.update(status="interrupted", interruption=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        metadata.update(finished_at=utc_now(), model_after=vision.status(),
                        source_hashes_after={p.name: file_sha256(p) for p in source_paths},
                        not_attempted_case_ids=[c["id"] for c in cases[len(rows):]])
        metadata["source_changed_during_run"] = metadata["source_hashes_after"] != metadata["source_hashes"]
        metadata["summary"] = summarize(rows) if rows else None
        metadata["outcomes"] = {k: Counter(outcome(r) for r in rows)[k] for k in "CWUE"}
        save_json(output / "run.json", metadata)
    print(json.dumps({"outcomes": metadata["outcomes"], "summary": metadata["summary"],
                      "source_changed_during_run": metadata["source_changed_during_run"]},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
