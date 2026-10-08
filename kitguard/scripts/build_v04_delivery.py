"""Assemble a portable v0.4 evidence index; never invent results or overwrite delivery.

Default is a preparation preview. --final additionally requires passing final JUnit,
a matching verified source archive and a final assessment. No inference is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "partial_independent": ("새 도메인 독립 재계산 / 新域独立复算说明", "docs/v0.4/INO_RUN_INDEPENDENT_AUDIT.md"),
    "two_independent": ("2개 진단 재계산 / 双角码诊断独立复核", "test-results/audit/v04-data-research/ino2-independent-run-audit.json"),
    "inputs_independent": ("21개 입력 재구성 / 21输入独立重建", "test-results/audit/v04-data-research/independent-21-derived-audit.json"),
    "flow_review": ("수동 확인 문구 수정 / 人工复核提示修正", "docs/v0.4/FIELD_FLOW_FOCUSED_REVIEW.md"),
    "flow_receipt": ("최종 문구 검증 / 最终界面定向检查", "test-results/browser/field-study-flow-review-v04/regression-result.json"),
    "real_independent": ("실제 내보내기 독립 검증 / 真实导出独立重算", "test-results/audit/v04-real-study-independent-verification.json"),
    "wheel_receipt": ("최종 설치 패키지 검증 / 安装包实际验证", "test-results/audit/v04-wheel-final-verification.json"),
    "source_disclosure": ("AI·자료 출처 / AI 与数据来源披露", "docs/AI_AND_SOURCE_DISCLOSURE.md"),
    "judge_qa": ("발표 질의응답 / 答辩问题与证据", "docs/v0.4/JUDGE_QA_KO_ZH.md"),
    "two_bracket_run": ("2개 브래킷 단일 진단 / 单个双角码诊断", "evaluation-runs/v04_ino_two_bracket_v1/run.json"),
    "two_bracket_rows": ("2개 사례 원본 출력 / 双角码完整输出", "evaluation-runs/v04_ino_two_bracket_v1/predictions.jsonl"),
    "field_design": ("기록 프로토콜 / 记录协议", "docs/v0.4/FIELD_API_CONTRACT.md"),
    "field_review": ("독립 프로토콜 검토 / 独立审查", "docs/v0.4/FIELD_VALIDATION_INDEPENDENT_AUDIT.md"),
    "ui_qa": ("화면·오프라인 검증 / 界面与离线验收", "docs/v0.4/FIELD_UI_QA.md"),
    "runtime_review": ("실행 신뢰성 수리 / 运行可靠性修复", "docs/v0.4/RUNTIME_REVIEW.md"),
    "runtime_protocol": ("관찰 프로토콜 보존 / 观察协议保持", "test-results/audit/v04-runtime/protocol-preservation.json"),
    "runtime_tests": ("실행 계층 집중 테스트 / 运行层定向测试", "test-results/audit/v04-runtime/targeted-final.xml"),
    "real_review": ("실제 MLX 연결 기록 / 真实 MLX 连接验收", "docs/v0.4/REAL_API_INTEGRATION.md"),
    "real_result": ("실제 API 전체 응답 / 真实 API 全部结果", "test-results/browser/field-study-real-v04/result.json"),
    "real_verification": ("실제 바이트·연결 감사 / 字节与绑定审计", "test-results/browser/field-study-real-v04/verification.json"),
    "real_browser": ("실제 기록 읽기 화면 / 真实记录只读界面", "test-results/browser/field-study-real-v04/browser-result.json"),
    "real_shutdown": ("추론 종료 확인 / 模型服务已释放", "test-results/browser/field-study-real-v04/shutdown.json"),
    "real_export": ("공개 재생 JSON / 公开回放完整 JSON", "test-results/browser/field-study-real-v04/public-replay.json"),
    "real_html": ("공개 재생 HTML / 公开回放报告", "test-results/browser/field-study-real-v04/public-replay.html"),
    "real_evidence": ("공개 사진 증거 ZIP / 公开图证据包", "test-results/browser/field-study-real-v04/public-replay-evidence.zip"),
    "photo_sources": ("공개 사진 출처·라이선스 / 图片来源与许可", "kitguard/public_demo_catalog.py"),
    "engineering_ui": ("공학 대역 74개 UI 검사 / 工程替身 UI 检查", "test-results/browser/field-study-v04/result.json"),
    "engineering_archive": ("공학 증거 ZIP 점검 / 工程证据包检查", "test-results/browser/field-study-v04/archive-result.json"),
    "independent_verifier": ("독립 JSON 재계산 / 独立 JSON 重算", "test-results/audit/v04-study-export-verification.json"),
    "partial_review": ("ㄱ자 브래킷 단일 클래스 검토 / 角码单类别审查", "docs/v0.4/INO_PARTIAL_LABEL_REVIEW.md"),
    "data_research": ("새 도메인 자료 조사 / 新域资料调查", "docs/v0.4/NEW_DOMAIN_DATA_RESEARCH.md"),
    "historical_gate": ("v0.3 동결 64장: 과거 기록 / 旧版冻结 64 例", "evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json"),
    "final_tests": ("최종 전체 테스트 / 最终全套测试", "test-results/engineering-v04-final.xml"),
    "source_archive": ("v0.4 소스 ZIP / 源码包", "output/KitGuard_source_v0.4.zip"),
    "source_verification": ("실제 압축 해제 검증 / 源码解压验证", "test-results/audit/source_v04_verification.json"),
    "final_evaluation": ("최종 자체 평가 / 最终自检评估", "docs/v0.4/FINAL_EVALUATION.md"),
}
OPTIONAL = {"partial_run": "ㄱ자 브래킷 진단 실행 / 角码诊断运行", "partial_predictions": "ㄱ자 브래킷 전체 행 / 角码全部输出",
            "partial_report": "ㄱ자 브래킷 단일 라벨 보고 / 角码单标签报告", "partial_audit": "ㄱ자 브래킷 독립 감사 / 角码独立审计"}
ALLOWED_SUFFIXES = {".json", ".jsonl", ".md", ".html", ".xml", ".zip", ".py", ".pdf", ".pptx"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def junit(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    leaf = [suite for suite in suites if not suite.findall("testsuite")]
    counts = {key: sum(int(suite.get(key, 0)) for suite in leaf) for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    if counts["tests"] < 1 or counts["passed"] < 0:
        raise ValueError("JUnit has no valid executed test count")
    return counts


def validated_file(path, root):
    original = Path(path)
    candidate = original if original.is_absolute() else root / original
    if candidate.is_symlink():
        raise ValueError("Symbolic artifact links are not accepted")
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError(f"Artifact is missing or outside project: {path}")
    if candidate.suffix.lower() not in ALLOWED_SUFFIXES or any("报名" in part or "등록신청" in part for part in candidate.parts):
        raise ValueError(f"Unsupported or private artifact: {path}")
    if candidate.suffix in {".json", ".jsonl", ".md", ".html", ".xml", ".py"}:
        content = candidate.read_text(encoding="utf-8")
        if re.search(r"[\w.+-]+@(?:qq|gmail)\.com|\+82[ -]?1[016789][ -]?\d{3,4}[ -]?\d{4}", content):
            raise ValueError(f"Personal contact information forbidden: {path}")
    if candidate.suffix == ".zip":
        with ZipFile(candidate) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip() is not None:
                raise ValueError("Invalid archive CRC or duplicate member")
            for name in names:
                item = PurePosixPath(name)
                if item.is_absolute() or ".." in item.parts or "\\" in name or item.suffix in {".sqlite3", ".db", ".safetensors", ".gguf"}:
                    raise ValueError(f"Unsafe archive member: {name}")
    return candidate


def collect(root, overrides):
    artifacts, missing = [], []
    for role, (title, default) in {**DEFAULTS, **{k: (v, None) for k, v in OPTIONAL.items()}}.items():
        value = overrides.get(role) or default
        if value is None or not (Path(value) if Path(value).is_absolute() else root / value).exists():
            if overrides.get(role):
                raise ValueError(f"Explicit artifact does not exist: {value}")
            missing.append(role)
            continue
        source = validated_file(value, root)
        artifacts.append({"role": role, "title": title, "source": str(source.relative_to(root)),
                          "destination": f"artifacts/{role}/{source.name}", "bytes": source.stat().st_size, "sha256": sha(source)})
    return artifacts, missing


def actual_summary(root, artifacts, final):
    by_role = {entry["role"]: root / entry["source"] for entry in artifacts}
    summary = {"human_field_samples": 0, "new_accuracy_samples_from_public_replay": 0,
               "historical_v03_64_is_new_result": False, "release_status": "final" if final else "preparation"}
    if "final_tests" in by_role:
        summary["final_tests"] = junit(by_role["final_tests"])
    if "real_result" in by_role:
        real = read_json(by_role["real_result"])
        summary["real_api"] = {"status": real.get("status"), "planned_requests": real.get("planned_inspections"),
                               "attempted_requests": real.get("attempted_inspections"), "source_changed": real.get("source_changed"),
                               "decisions": [{"sample": case.get("sample_id"), "status": case.get("status"),
                                              "decision": case.get("check", {}).get("decision")} for case in real.get("cases", [])]}
    if "independent_verifier" in by_role:
        value = read_json(by_role["independent_verifier"])
        summary["independent_verifier"] = {key: value.get(key) for key in ("status", "source_kind", "physical_authenticity_verified", "photo_bytes_verified")}
    if "partial_predictions" in by_role:
        rows = [json.loads(line) for line in by_role["partial_predictions"].read_text().splitlines() if line.strip()]
        summary["partial_prediction_records"] = len(rows)
    if "partial_run" in by_role:
        value = read_json(by_role["partial_run"])
        summary["partial_run_status"] = value.get("status", "see_original_record")
    if "source_verification" in by_role:
        value = read_json(by_role["source_verification"])
        summary["source_verification"] = {key: value.get(key) for key in ("status", "source_archive_sha256", "extracted_suite")}
        if "source_archive" in by_role and value.get("source_archive_sha256") != sha(by_role["source_archive"]):
            raise ValueError("Source verification does not bind the supplied source archive")
    if final:
        for required in ("final_tests", "source_archive", "source_verification", "final_evaluation", "real_result", "real_verification"):
            if required not in by_role:
                raise ValueError(f"Final delivery missing: {required}")
        if any(summary["final_tests"][key] for key in ("failures", "errors")):
            raise ValueError("Final test suite contains failures/errors")
        if summary["source_verification"]["status"] != "passed":
            raise ValueError("Extracted-source verification has not passed")
        extracted = summary["source_verification"].get("extracted_suite") or {}
        if extracted.get("tests") != summary["final_tests"]["tests"] or extracted.get("returncode") != 0:
            raise ValueError("Extracted and final suite counts do not match or extraction tests failed")
        real_verification = read_json(by_role["real_verification"])
        if real_verification.get("status") != "passed" or real_verification.get("artifact_sha256", {}).get("result.json") != sha(by_role["real_result"]):
            raise ValueError("Real integration verification does not bind the actual result")
        if summary["real_api"]["status"] not in {"completed", "completed_with_errors"} or summary["real_api"]["source_changed"] is not False:
            raise ValueError("Real integration must be completed against unchanged source")
    return summary


def render(manifest):
    escape = html.escape
    s = manifest["summary"]
    tests = s.get("final_tests")
    tests_text = (f"{tests['passed']} passed / {tests['tests']} · 실패 {tests['failures']} · 오류 {tests['errors']} · skip {tests['skipped']}" if tests else "최종 파일 대기 / 等待最终测试文件")
    cards = "".join(f'<li><a href="{quote(a["destination"], safe="/")}">{escape(a["title"])}</a>'
                    f'<small>{a["bytes"]:,} B · SHA256 <code>{a["sha256"]}</code></small></li>' for a in manifest["artifacts"])
    real_rows = "".join(f'<tr><td>{escape(str(item["sample"]))}</td><td>{escape(str(item["status"]))}</td><td>{escape(str(item["decision"]))}</td></tr>'
                        for item in s.get("real_api", {}).get("decisions", []))
    state = "최종 인도 / 最终交付" if manifest["final"] else "준비 미리보기 / 准备预览，未作最终发布"
    missing = ", ".join(manifest["missing_roles"]) or "없음 / 无"
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KitGuard v0.4 · 검증 증거</title><style>
*{{box-sizing:border-box}}body{{max-width:1160px;margin:0 auto;padding:38px 22px 70px;background:#f7f8f5;color:#193e37;font:15px/1.7 system-ui,sans-serif;overflow-wrap:anywhere}}h1{{font-size:38px;line-height:1.2;margin:12px 0}}h2{{font-size:20px}}.kicker{{font-size:12px;letter-spacing:2px;color:#487966}}section{{background:white;border:1px solid #d6e4dc;padding:24px;border-radius:14px;margin:20px 0}}.notice{{background:#fff5e5;border-color:#ebd6b4}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.metric{{background:#eef5f0;padding:18px;border-radius:10px}}.metric strong{{font-size:29px;display:block}}small{{display:block;color:#5b756b;font-size:11px}}ul{{padding:0;list-style:none}}li{{padding:13px 0;border-bottom:1px solid #e2ebe5}}a{{color:#086655;text-underline-offset:3px}}code{{font-size:11px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #dce7df;text-align:left}}.scroll{{overflow:auto}}details{{margin-top:20px}}pre{{white-space:pre-wrap;font-size:12px}}@media(max-width:620px){{body{{padding:25px 14px}}h1{{font-size:29px}}section{{padding:18px 15px}}.grid{{grid-template-columns:1fr}}}}
</style><header><p class="kicker">KITGUARD / VERIFIABLE DELIVERY</p><h1>검증 가능한 기록을 남깁니다.</h1><p>KitGuard v0.4 · {state}</p><p>可复核的验证记录、真实 API 连接和完整失败分母。</p></header>
<div class="grid"><div class="metric"><strong>0</strong>실제 사람 현장 표본 / 真人现场样本</div><div class="metric"><strong>0</strong>공개 재생으로 추가된 정확도 표본 / 回放新增准确率样本</div><div class="metric"><strong>v0.3</strong>동결 64장은 과거 결과 / 冻结64例仅为历史</div></div>
<section class="notice"><h2>해석 범위 / 解释范围</h2><p>새 도구의 기능 및 무결성을 확인한 배포입니다. 현장 효율 개선, 독립 사용자 실험 또는 우승을 입증하지 않습니다. 这是功能与完整性验收，不证明现场收益、真人实验或比赛名次。</p><p>公开图验证的 manual 栏由脚本输入作者真值；100%与0秒不代表人工表现，不能用于人工与模型效率比较。</p></section>
<section><h2>최종 엔지니어링 검사 / 最终工程测试</h2><p>{escape(tests_text)}</p><p>源码与解压验收：{escape(str(s.get('source_verification',{}).get('status','等待真实文件 / pending')))}</p></section>
<section><h2>실제 MLX 연결 / 真实 MLX 连接</h2><p>아래 세 장은 기존 개발 사례입니다. 아래 상태는 저장된 실제 JSON에서 읽었습니다. 三张既有开发图仅验证集成，不新增独立准确率样本；correct 意为数量调整。</p><div class="scroll"><table><thead><tr><th>样例</th><th>试次状态</th><th>API 决策</th></tr></thead><tbody>{real_rows or '<tr><td colspan="3">等待实际运行文件 / pending</td></tr>'}</tbody></table></div></section>
<section class="notice"><h2>ㄱ자 브래킷 단일 양성 진단 / 角码单阳性诊断</h2><p>계획된 20개는 모두 ㄱ자 브래킷 1개입니다. 정답 ROI를 사용하며 항상 1이라고 답해도 20/20입니다. 计划20例全部只有1个角码，恒定回答1即可20/20；这是4张完整图与16张作者标注 ROI 的单阳性诊断，不证明计数泛化，也不能补齐四类准确率。</p><p>实际输出记录数：{escape(str(s.get('partial_prediction_records','尚未纳入 / pending')))}。未输出或失败必须保留，详细结论以原始行与独立审计为准。另有单独预先冻结的1例双角码诊断，不能据此声称多件泛化。整图背景固定件可能属于模型通用类别却不在作者目标标注内，因此 W_b 只表示作者实例计数不一致。</p></section>
<section><h2>자료 열기 / 打开交付资料</h2><p>모든 링크는 동봉 파일입니다. 本页仅链接随包相对文件，不连接运行中的工作台。公开图使用范围与署名见来源许可资料。</p><ul>{cards}</ul><p><a href="BUILD_MANIFEST.json">交付清单 · BUILD_MANIFEST.json</a> · <a href="SHA256.json">文件哈希 · SHA256.json</a></p><details><summary>未包含的资料 / 누락·대기 항목</summary><p>{escape(missing)}</p></details></section>
<footer><small>{escape(manifest['created_at'])} · 无个人联系方式 · 不修改 v0.2/v0.3 历史交付</small></footer></html>'''


def build(output, *, root=ROOT, overrides=None, final=False):
    root = root.resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refuse to overwrite an existing delivery")
    artifacts, missing = collect(root, overrides or {})
    summary = actual_summary(root, artifacts, final)
    manifest = {"schema_version": 1, "kind": "kitguard_v04_delivery", "final": final,
                "created_at": datetime.now(UTC).isoformat(), "summary": summary,
                "artifacts": artifacts, "missing_roles": missing}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v04-build-", dir=output.parent) as temp:
        stage = Path(temp) / "delivery"
        stage.mkdir()
        for artifact in artifacts:
            source, target = root / artifact["source"], stage / artifact["destination"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha(target) != artifact["sha256"]:
                raise ValueError("Artifact changed while being copied")
        (stage / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        (stage / "index.html").write_text(render(manifest))
        for link in re.findall(r'href="([^"]+)"', (stage / "index.html").read_text()):
            if link == "SHA256.json":
                continue
            if not (stage / unquote(link)).is_file():
                raise ValueError(f"Missing relative link: {link}")
        hashes = {str(path.relative_to(stage)): sha(path) for path in sorted(stage.rglob("*")) if path.is_file()}
        (stage / "SHA256.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=2))
        (stage / "SHA256.json.sha256").write_text(sha(stage / "SHA256.json") + "  SHA256.json\n")
        stage.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/delivery-v0.4")
    parser.add_argument("--final", action="store_true")
    for name in ("final_tests", "source_archive", "source_verification", "final_evaluation", *OPTIONAL):
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    args = parser.parse_args()
    overrides = {key: value for key, value in vars(args).items() if key not in {"output", "final"} and value is not None}
    value = build(args.output, overrides=overrides, final=args.final)
    print(json.dumps({"output": str(args.output), "final": value["final"], "artifacts": len(value["artifacts"]), "summary": value["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
