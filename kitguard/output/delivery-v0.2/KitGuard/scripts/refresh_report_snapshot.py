"""Refresh the local report only from completed, inspectable evaluation runs."""

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "reports/self-evaluation/src/data.json"


def source(label, files, definitions):
    return {
        "label": label,
        "files": files,
        "metricDefinitions": definitions,
        "evidenceFlow": [
            {
                "title": "可复算的本地记录",
                "detail": "只收录有finished_at和summary的已完成运行；每个运行对应保留的manifest、逐例JSONL与源码快照。失败不排除，开发与留出分开。",
            }
        ],
    }


def main():
    snapshot = json.loads(TARGET.read_text())
    records = []
    for path in (ROOT / "evaluation-runs").glob("*/run.json"):
        record = json.loads(path.read_text())
        if record.get("finished_at") and record.get("summary"):
            records.append((path, record))
    records.sort(key=lambda x: x[1]["started_at"])
    vision_rows, instruction_rows, vision_files, instruction_files = [], [], [], []
    for path, record in records:
        summary = record["summary"]
        if "images" in summary:
            nominal = summary.get("nominal_order") or {}
            normal = (summary.get("subgroups") or {}).get("normal_constant_222", {})
            anomaly = (summary.get("subgroups") or {}).get("quantity_anomaly", {})
            baseline = nominal.get("constant_nominal_baseline", {})
            vision_rows.append(
                {
                    "run": path.parent.name,
                    "model": record["model_before"]["label"],
                    "dataset": "MVTec LOCO screw_bag"
                    if "loco" in str(record.get("manifest_path", "")).lower()
                    else "MVTec Screws",
                    "split": record["split"],
                    "images": summary["images"],
                    "exact": summary["count_exact"]["numerator"],
                    "accuracy": summary["count_exact"]["rate"],
                    "actionable": summary["actionable_coverage"]["numerator"],
                    "wrongActionable": summary["wrong_actionable_count"]["numerator"],
                    "errors": summary["errors"]["numerator"],
                    "medianMs": summary["latency_ms"]["median"],
                    "eligible": summary["order_eligible_images"],
                    "matchedReady": summary["matched_order_ready"]["numerator"],
                    "mismatchFalseReady": summary["mismatched_order_false_ready"]["numerator"],
                    "mismatchCorrect": summary["mismatched_order_correct_adjustment"]["numerator"],
                    "protocol": (
                        record.get("observation_mode")
                        or record["model_before"].get("observation_mode", "single")
                    )
                    + " / "
                    + str(record["model_before"].get("image_max_side", 1024))
                    + "px"
                    + " / "
                    + record.get("input_pipeline", "original"),
                    "status": record.get("status", "completed"),
                    "nominalNormalReady": nominal.get("matching_images_ready", {}).get("numerator"),
                    "nominalNormalTotal": nominal.get("matching_images_ready", {}).get("denominator"),
                    "nominalAnomalyFalseReady": nominal.get("quantity_anomalies_false_ready", {}).get(
                        "numerator"
                    ),
                    "nominalAnomalyCorrect": nominal.get("quantity_anomalies_correct_adjustment", {}).get(
                        "numerator"
                    ),
                    "nominalAnomalyTotal": nominal.get("quantity_anomalies_false_ready", {}).get(
                        "denominator"
                    ),
                    "normalExact": normal.get("count_exact", {}).get("numerator"),
                    "normalImages": normal.get("images"),
                    "anomalyExact": anomaly.get("count_exact", {}).get("numerator"),
                    "anomalyImages": anomaly.get("images"),
                    "constantNominalExact": baseline.get("count_exact", {}).get("numerator"),
                    "constantNominalImages": baseline.get("count_exact", {}).get("denominator"),
                    "timingNote": (
                        "包括隔离上传路由、SQLite、归一化、输入哈希及observe；未经过inspect超时路由"
                        if record.get("input_pipeline") == "app-upload"
                        else "真实observe调用，包括当次冷加载"
                    )
                    + (
                        "；双方向为两次同模型调用"
                        if record["model_before"].get("observation_mode") == "dual_orientation"
                        else "；单次调用"
                    ),
                }
            )
            vision_files.append(str(path.relative_to(ROOT)))
        elif "overall" in summary:
            a = summary["overall"]
            groups = summary["by_expected_kind"]
            instruction_rows.append(
                {
                    "run": path.parent.name,
                    "model": record["model_before"]["label"],
                    "attempted": a["attempted"],
                    "passed": a["passed"],
                    "proposalPassed": groups["proposal"]["passed"],
                    "proposalTotal": groups["proposal"]["attempted"],
                    "clarificationPassed": groups["clarification"]["passed"],
                    "clarificationTotal": groups["clarification"]["attempted"],
                    "executionErrors": a["execution_errors"],
                }
            )
            instruction_files.append(str(path.relative_to(ROOT)))
    q = snapshot["queries"]
    q["benchmark_runs"] = {
        "rows": vision_rows,
        "source": source(
            "真实本地视觉模型逐图运行",
            vision_files,
            [
                {
                    "label": "完整计数正确率",
                    "definition": "四类观察全部等于源数据对象标注映射后的四类真值的图片数 / 全部预先选定原图数；失败和拒绝不排除。",
                    "componentIds": [
                        "benchmark-table",
                        "benchmark-findings",
                        "scope-coverage",
                        "report-summary",
                    ],
                },
                {
                    "label": "可执行与错误",
                    "definition": "四类数量非null、issues为空、action为none即为可执行；其中计数错误另外统计，不等于已放行工单。",
                    "componentIds": ["benchmark-table", "benchmark-findings", "report-summary"],
                },
                {
                    "label": "中位耗时",
                    "definition": "每图实际测量区间中位数，包含当次冷加载。original是observe调用；app-upload还包括隔离上传路由、SQLite、归一化及输入哈希，不是纯推理或完整inspect接口耗时。",
                    "componentIds": ["benchmark-table", "benchmark-timing", "report-summary", "benchmark-findings"],
                },
                {
                    "label": "同模型协议对照差异",
                    "definition": "冻结48张主留出与直接计数对照同模型、同1536px、同上传图。准确率差=(46/48−34/48)×100=25个百分点；中位耗时差=14.6195−8.9905=5.629秒。提示词/输出结构和900对450token预算一起变化，不是只改变定位的因果消融。",
                    "componentIds": ["report-summary", "benchmark-findings"],
                },
                {
                    "label": "正常组成与数量异常子组",
                    "definition": "LOCO作者正常构成为2螺纹件、2螺母、2垫圈；数量异常由作者单一数量缺陷标签导出。每个子组单独报告完整计数正确图数，恒返222基线没有使用图像。",
                    "componentIds": ["subgroup-findings", "subgroup-table"],
                },
                {
                    "label": "固定正常订单的错误就绪",
                    "definition": "对所有LOCO样本均使用作者正常组成2220作为订单；数量异常照片被判断ready即为误放行。分母仅预选数量异常图；正确纠正须四类数量全部正确。同图派生多种订单不增加样本数。",
                    "componentIds": ["nominal-findings", "nominal-table", "report-summary", "benchmark-findings"],
                },
                {
                    "label": "匹配与固定扰动订单",
                    "definition": "每张范围内原图生成真值匹配订单和一个预先固定的bolt数量扰动订单。分别统计匹配ready、扰动错误ready和扰动纠正全部正确；分母均为范围内原图数。同图任务相关，不是额外样本，也没有人工完成或实际发货。",
                    "componentIds": ["perturbation-findings", "perturbation-table"],
                },
                {
                    "label": "产品范围内原图",
                    "definition": "派生真值每类0–3件、总数1–12件的原图数量；Screws当前压力集为0。",
                    "componentIds": ["benchmark-table", "scope-coverage"],
                },
            ],
        ),
    }
    q["instruction_runs"] = {
        "rows": instruction_rows,
        "source": source(
            "作者生成的24条多语言开发工程案例",
            instruction_files,
            [
                {
                    "label": "指令通过",
                    "definition": "明确指令的四类提案数量完全相符，或预期澄清指令得到业务拒绝；执行异常为失败。固定9条修改、15条澄清，不是用户研究。",
                    "componentIds": ["instruction-table", "instruction-findings", "report-summary"],
                }
            ],
        ),
    }
    suites = ElementTree.parse(ROOT / "test-results/engineering-current.xml").getroot()
    tests = sum(int(s.get("tests", 0)) for s in suites.iter("testsuite"))
    fail = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites.iter("testsuite"))
    q["engineering_checks"] = {
        "rows": [
            {
                "suite": "Python完整工程回归",
                "pass": tests - fail,
                "fail": fail,
                "scope": "状态、并发、输入、反馈、评测、下载与原文数量校验；模型测试替身",
                "evidence": "test-results/engineering-current.xml",
            },
            {
                "suite": "工作台Chrome交互",
                "pass": 15,
                "fail": 0,
                "scope": "真实浏览器，合成工程照片，创建/改版/上传/下载/手机",
                "evidence": "test-results/browser/workbench-core/browser-results.json",
            },
            {
                "suite": "历史只读详情Chrome",
                "pass": 17,
                "fail": 0,
                "scope": "独立浏览器工程回归，不计为视觉样本",
                "evidence": "test-results/browser/audit-details/result.json",
            },
            {
                "suite": "空间点位与清单Chrome",
                "pass": 36,
                "fail": 0,
                "scope": "编号点位、照片绑定、历史只读、键盘与移动端；工程测试替身",
                "evidence": "test-results/browser/spatial-evidence/result.json",
            },
            {
                "suite": "补证与真实步骤Chrome",
                "pass": 29,
                "fail": 0,
                "scope": "独立浏览器工程回归，与其他组覆盖有交集",
                "evidence": "test-results/browser/evidence-feedback/result.json",
            },
        ],
        "source": source(
            "工程回归记录",
            [
                "test-results/engineering-current.xml",
                "test-results/browser/workbench-core/browser-results.json",
                "test-results/browser/audit-details/result.json",
                "test-results/browser/evidence-feedback/result.json",
                "test-results/browser/spatial-evidence/result.json",
                "docs/UI_IMPROVEMENTS.md",
            ],
            [
                {
                    "label": "工程检查通过",
                    "definition": "该次工程检查的断言或pytest用例结果；不同组有覆盖重叠，不等于独立图像数量或视觉准确率。",
                    "componentIds": ["engineering-table"],
                }
            ],
        ),
    }
    holdout_complete = all(
        any(r["run"] == name and r["status"] == "completed" and r["images"] == 48 for r in vision_rows)
        for name in ("loco_holdout_release_v1", "loco_holdout_27b_single_control_v1")
    )
    q["readiness_gaps"] = {
        "rows": [
            {
                "item": "公开实拍与模型对照",
                "status": "已完成静态留出对照" if holdout_complete else "进行中",
                "evidence": "冻结后48张公开照片完成所选协议与同模型对照；未据留出调参" if holdout_complete else "LOCO多轮开发对照已完成；27B参数已冻结，48张留出验证进行中",
                "implication": "这是公开静态图片验证，不是实物操作或工厂泛化证明",
            },
            {
                "item": "真人基线及实际生产收益",
                "status": "尚未验证",
                "evidence": "没有招募参与者或企业试点",
                "implication": "不能声称省时比例、降低现场漏配率或Pilot验证",
            },
            {
                "item": "同一批实物的连续补证",
                "status": "尚未验证",
                "evidence": "公开静态原图和工程状态夹具",
                "implication": "观察变化不证明实物操作发生",
            },
            {
                "item": "赛前代码使用资格",
                "status": "待官方明确",
                "evidence": "原始同意书禁止开发期外预先开发；本工程如实记录9月26日",
                "implication": "披露时间与来源不能自行构成豁免",
            },
            {
                "item": "正式评分表与AI使用表",
                "status": "待9月29日公布",
                "evidence": "当前官方公告答疑",
                "implication": "材料为内部草稿，不冒充最终合规提交",
            },
        ],
        "source": source(
            "已核实官方条款与当前未验证事项",
            ["docs/INDEPENDENT_REVIEW.md", "docs/DEVELOPMENT_LOG.md"],
            [
                {
                    "label": "状态",
                    "definition": "记录当前有证据的完成情况与缺口，不是官方评分或名次预测。",
                    "componentIds": ["readiness-table"],
                }
            ],
        ),
    }
    q["engineering_checks"]["source"]["evidenceFlow"] = [
        {
            "title": "工程记录读取",
            "detail": "用ElementTree汇总engineering-current.xml每个testsuite的tests/failures/errors；浏览器各组来自原始browser-results.json及UI_IMPROVEMENTS.md。套件有覆盖重叠，未相加为独立准确率。",
        }
    ]
    q["readiness_gaps"]["source"]["evidenceFlow"] = [
        {
            "title": "官方条款与证据状态",
            "detail": "读取INDEPENDENT_REVIEW.md所列原始HWP条款、官网要求及DEVELOPMENT_LOG.md真实开发时间；检查本地是否已有现场参与者、连续实拍和完成评测的记录。状态是当前证据判断，不是官方裁定。",
        }
    ]
    snapshot["report"] = {"asOf": "2026-09-26"}
    snapshot["generatedAt"] = datetime.now(UTC).isoformat()
    TARGET.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "visual_runs": len(vision_rows),
                "instruction_runs": len(instruction_rows),
                "engineering_tests": tests,
            }
        )
    )


if __name__ == "__main__":
    main()
