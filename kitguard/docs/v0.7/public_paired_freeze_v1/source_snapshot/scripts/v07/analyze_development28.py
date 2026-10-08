"""Audit a completed fixed-development candidate without model calls or holdout reads."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from kitguard.identity import IdentityResponse
from kitguard.schemas import Observation
from kitguard.spatial import SpatialInventory
from kitguard.vision import _parse_json

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "evaluation-runs/v03_guarded_integrated_development_v1"
HISTORY_PREDICTIONS_SHA = "defa8353d8f0ea2eb89ec3ae8fd0ecb0bc4e90b80caa8a32c075765548d6e9a4"
HISTORY_MANIFEST_SHA = "8e85c97a5dee7d0c571964597a8282b312e7691e66c8c36da541cf41dd2283c6"
PARTS = ("bolt", "nut", "washer", "bracket")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def require_complete(metadata, predictions, expected=28):
    if metadata["status"] != "completed":
        raise ValueError("Run is not completed; do not inspect or select from partial results")
    ids = [row["case_id"] for row in predictions]
    if (metadata.get("split") != "development" or metadata["expected_cases"] != expected
            or metadata["completed_cases"] != expected or len(predictions) != expected
            or ids != metadata["case_ids"] or len(set(ids)) != expected):
        raise ValueError("Completed development run does not preserve the entire planned denominator")
    if metadata.get("source_changed_during_run") is not False:
        raise ValueError("Run source was changed or its unchanged status is unverified")
    if metadata["source_hashes"] != metadata["source_hashes_after"]:
        raise ValueError("Saved before/after source hashes disagree")


def outcome(row):
    if row["error"]:
        correct, actionable, category = False, False, "E"
    else:
        parsed = Observation.model_validate(row["observation"])
        correct = parsed.observed.model_dump() == row["ground_truth"]
        actionable = (all(getattr(parsed.observed, part) is not None for part in PARTS)
                      and not parsed.issues and parsed.action.kind == "none")
        category = "C" if correct and actionable else "W" if actionable else "U"
    if correct != row["counts_exact"] or actionable != row["actionable_counts"]:
        raise ValueError("Saved score disagrees with independently recomputed observation")
    return category


def timing(predictions):
    values = sorted(row["latency_ms"] for row in predictions)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Invalid latency")
    return {"measured": len(values), "p50_ms": statistics.median(values),
            "p90_ms": values[(9 * len(values) + 9) // 10 - 1],
            "total_ms": sum(values), "maximum_ms": max(values)}


def admission(candidate_outcomes, historical_outcomes, audit_passed=True):
    checks = {"complete_input_raw_and_source_audit": audit_passed,
              "zero_wrong_actionable": candidate_outcomes["W"] == 0,
              "zero_execution_failures": candidate_outcomes["E"] == 0,
              "correct_actionable_at_least_historical_guarded": candidate_outcomes["C"] >= historical_outcomes["C"],
              "correct_actionable_at_least_fixed_24_of_28": candidate_outcomes["C"] >= 24}
    return {"predeclared_checks": checks, "admit_to_new_51_three_method_comparison": all(checks.values()),
            "automatic_default_change": False,
            "timing_used_for_admission": False,
            "decision_scope": "Development selection only; a fair pre-frozen holdout comparison is still required"}


def safe_artifact(directory, relative):
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Recorded artifact path escapes the case")
    return path


def verify_calls(case_dir, row):
    diagnostics = row["observation_diagnostics"] or {}
    calls = diagnostics.get("generation_calls", [])
    if len(calls) > 2 or (not row["error"] and not 1 <= len(calls) <= 2):
        raise ValueError("Candidate exceeded its one/two-call budget or lost successful call records")
    call_files = sorted(case_dir.glob("call-*/generation.json"))
    if len(call_files) != len(calls):
        raise ValueError("Raw call files and observation diagnostics disagree")
    counts = Counter()
    image_checks = 0
    for index, (path, saved) in enumerate(zip(call_files, calls, strict=True), 1):
        record = read(path)
        if path.parent.name != f"call-{index:02d}" or record != saved:
            raise ValueError("Raw call record differs from persisted diagnostics")
        expected_schema = "SpatialInventory" if index == 1 else "IdentityResponse"
        expected_tokens = 900 if index == 1 else 1800
        if record["schema"] != expected_schema or record["max_tokens"] != expected_tokens or record["temperature"] != 0:
            raise ValueError("Recorded generation protocol differs from fixed candidate")
        counts["generation_boundaries"] += 1
        counts["raw_text_returns"] += isinstance(record.get("raw_text"), str)
        counts[record["status"]] += 1
        for image in record["images"]:
            if sha(safe_artifact(case_dir, image["path"])) != image["sha256"]:
                raise ValueError("Saved model input image hash changed")
            image_checks += 1
        if record["status"] == "parsed":
            schema = SpatialInventory if index == 1 else IdentityResponse
            parsed = _parse_json(record["raw_text"].strip(), schema).model_dump()
            if parsed != record["parsed"]:
                raise ValueError("Reparsed raw model text differs from saved parsed record")
    if not row["error"]:
        passes = diagnostics["passes"]
        if len(passes) != 1 or passes[0]["transform"] != "original":
            raise ValueError("Candidate should retain exactly one real orientation")
        if passes[0]["input_sha256"] != calls[0]["images"][0]["sha256"]:
            raise ValueError("Raw original input differs from inventory diagnostics")
        if bool(diagnostics["experimental_identity"]["model_called"]) != (len(calls) == 2):
            raise ValueError("Identity-call declaration disagrees with raw calls")
    return counts, image_checks


def audit(run, history=HISTORY):
    metadata = read(run / "run.json")
    # Deliberately check completion before opening any current prediction file.
    if metadata["status"] != "completed":
        raise ValueError("Run is not completed; partial predictions are intentionally unread")
    predictions = rows(run / "predictions.jsonl")
    require_complete(metadata, predictions)
    if sha(history / "predictions.jsonl") != HISTORY_PREDICTIONS_SHA or sha(history / "manifest.json") != HISTORY_MANIFEST_SHA:
        raise ValueError("Historical development evidence differs from fixed inputs")
    historical, historical_metadata = rows(history / "predictions.jsonl"), read(history / "run.json")
    require_complete(historical_metadata, historical)
    if metadata["case_ids"] != historical_metadata["case_ids"]:
        raise ValueError("Candidate/historical case order changed")
    manifest = read(run / "manifest.json")
    cases = manifest["cases"]
    if [case["id"] for case in cases] != metadata["case_ids"]:
        raise ValueError("Candidate manifest differs from fixed case order")
    for name, expected in metadata["source_hashes"].items():
        if sha(run / "source_snapshot" / name) != expected:
            raise ValueError(f"Frozen source snapshot changed: {name}")
    if metadata["source_predictions_sha256"] != HISTORY_PREDICTIONS_SHA or metadata["source_manifest_sha256"] != HISTORY_MANIFEST_SHA:
        raise ValueError("Candidate recorded a different input origin")
    categories = [Counter(), Counter()]
    paired = []
    raw_counts, raw_images = Counter(), 0
    raw_call_counts = Counter()
    artifacts = {}
    for index, (case, candidate, baseline) in enumerate(zip(cases, predictions, historical, strict=True), 1):
        for field in ("ground_truth", "sha256", "source_id", "image", "split"):
            if candidate[field] != baseline[field] or candidate[field] != case[field]:
                raise ValueError("Candidate/historical source or truth mismatch")
        directory = run / "cases" / f"{index:03d}"
        normalized = directory / "normalized.jpg"
        historical_input = history / "normalized_inputs" / f"{index:03d}.jpg"
        if not (sha(normalized) == sha(historical_input) == baseline["model_input_sha256"] == candidate["model_input_sha256"]):
            raise ValueError("Normalized input is not the exact historical development image")
        if read(directory / "result.json") != candidate:
            raise ValueError("Per-case receipt differs from predictions ledger")
        calls, images = verify_calls(directory, candidate)
        raw_counts.update(calls)
        raw_images += images
        raw_call_counts[calls["generation_boundaries"]] += 1
        before, after = outcome(baseline), outcome(candidate)
        categories[0][before] += 1
        categories[1][after] += 1
        paired.append({"case_id": case["id"], "historical_guarded": before, "selective_identity": after,
                       "historical_ms": baseline["latency_ms"], "candidate_ms": candidate["latency_ms"],
                       "candidate_generation_boundaries": calls["generation_boundaries"]})
        for path in directory.rglob("*"):
            if path.is_file():
                artifacts[str(path.relative_to(run))] = sha(path)
    baseline_counts, candidate_counts = [dict.fromkeys("CWUE", 0) | dict(c) for c in categories]
    result = {
        "schema": "kitguard.v07.development28.audit.v1", "checked_at": datetime.now(UTC).isoformat(),
        "status": "passed", "source_changed_during_run": False, "planned_cases": 28, "completed_cases": 28,
        "candidate_run": str(run.resolve()), "historical_run": str(history.resolve()),
        "source_snapshot_files_verified": len(metadata["source_hashes"]),
        "normalized_inputs_identical": 28, "raw_input_images_verified": raw_images,
        "raw_generation_counts": dict(raw_counts), "cases_by_call_count": dict(raw_call_counts),
        "historical_guarded_outcomes": baseline_counts, "candidate_outcomes": candidate_counts,
        "historical_guarded_latency": timing(historical), "candidate_latency": timing(predictions),
        "paired_transitions": dict(sorted(Counter(f"{p['historical_guarded']}->{p['selective_identity']}" for p in paired).items())),
        "paired_cases": paired, "admission": admission(candidate_counts, baseline_counts),
        "timing_comparison_valid_for_speed_claim": False,
        "timing_limitations": ["Historical guarded includes fresh isolated app-upload preprocessing; candidate copies saved normalized input.",
                               "Candidate additionally persists raw text and actual prepared images; historical logging differs.",
                               "Runs occur at different times without randomized method order; cold loading remains included.",
                               "These durations are descriptive; the new paired experiment is needed for a fair speed comparison."],
        "limitations": ["The same 28 images were repeatedly exposed during development; this is method selection, not new accuracy.",
                        "No new 51 holdout image or prediction is read; no prompt, threshold, or crop changes are made.",
                        "Passing admission only permits preregistering the candidate as a third comparison arm; no default change."],
        "evidence_sha256": {"candidate_run": sha(run / "run.json"), "candidate_predictions": sha(run / "predictions.jsonl"),
                            "candidate_manifest": sha(run / "manifest.json"), "candidate_protocol": sha(run / "protocol.json"),
                            "historical_predictions": HISTORY_PREDICTIONS_SHA, "historical_manifest": HISTORY_MANIFEST_SHA,
                            "analyzer_source": sha(Path(__file__))},
        "artifacts_sha256": artifacts,
    }
    return result


def markdown(result, json_path):
    passed = result["admission"]["admit_to_new_51_three_method_comparison"]
    historical, candidate = result["historical_guarded_outcomes"], result["candidate_outcomes"]
    old_time, new_time = result["historical_guarded_latency"], result["candidate_latency"]
    changed = [p for p in result["paired_cases"] if p["historical_guarded"] != p["selective_identity"]]
    text = ["# 单方向身份核查：旧28图完整开发结果", "", "日期：2026-10-02（韩国时间）。",
            "", ("**建议纳入新51图预注册三方法比较；不改变产品默认。**" if passed else
                   "**未通过预定开发纳入条件，不建议作为已合格候选进入新51图比较；保留完整负面结果。**"),
            "", "这是已曝光开发集的全量方法选择，不是新准确率。新51图未由本分析器读取或推理。", "",
            "| 方法 | C正确可执行 | W明确错误 | U不确定 | E执行失败 |", "|---|---:|---:|---:|---:|",
            f"| 历史guarded开发28 | {historical['C']} | {historical['W']} | {historical['U']} | {historical['E']} |",
            f"| 单方向身份核查候选28 | {candidate['C']} | {candidate['W']} | {candidate['U']} | {candidate['E']} |", "",
            "预定纳入条件为28全部完成、原始证据审计通过、W/E均0、C不少于历史guarded（24/28）。速度不参与这次开发纳入决定。", "",
            (f"28份归一化输入与历史字节完全相同；{result['source_snapshot_files_verified']}个源码快照散列正确，运行期间源码未改；"
             f"核对{result['raw_input_images_verified']}份实际模型输入图及全部原始文本/解析记录。"),
            f"生成边界记录：`{json.dumps(result['raw_generation_counts'], ensure_ascii=False)}`；每图调用数分布：`{json.dumps(result['cases_by_call_count'])}`。", "",
            "配对转换：`" + json.dumps(result["paired_transitions"], ensure_ascii=False) + "`。", "",
            "| 描述性运行时长 | P50秒 | P90秒 | 总秒 |", "|---|---:|---:|---:|",
            f"| 历史guarded | {old_time['p50_ms']/1000:.3f} | {old_time['p90_ms']/1000:.3f} | {old_time['total_ms']/1000:.3f} |",
            f"| 候选 | {new_time['p50_ms']/1000:.3f} | {new_time['p90_ms']/1000:.3f} | {new_time['total_ms']/1000:.3f} |", "",
            "**上述时长不能称为公平速度对照。** 历史流程包含隔离app上传，候选复制已归一化图片并额外保存raw文本/输入；运行时间、热状态与顺序也不同。只有后续同时冻结、同记录边界、顺序平衡的新51图试验可判断候选是否满足至少20%速度改善条件。", "",
            "逐例类别变化（完整28图仍在JSON中）：", ""]
    if changed:
        text += ["| Case | 历史guarded → 候选 |", "|---|---|"]
        text += [f"| `{p['case_id']}` | {p['historical_guarded']} → {p['selective_identity']} |" for p in changed]
    else:
        text.append("无类别变化。")
    text += ["", f"完整复核：[JSON]({json_path.resolve()})；候选原运行：`{result['candidate_run']}`。", ""]
    return "\n".join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.output.exists() or (args.report and args.report.exists()):
        raise SystemExit("Do not overwrite existing audit outputs")
    result = audit(args.run.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown(result, args.output))
    print(json.dumps({"audit": result["status"], "candidate": result["candidate_outcomes"],
                      "historical": result["historical_guarded_outcomes"], "admission": result["admission"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
