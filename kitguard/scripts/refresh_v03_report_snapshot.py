"""Append reviewed v0.3 evidence to the existing report without resetting its identity."""

import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from scripts.refresh_report_snapshot import main as refresh_history

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'reports/self-evaluation/src/data.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(label, files, component_ids, definition, flow=None):
    return {
        'label': label, 'files': files,
        'metricDefinitions': [{'label': label, 'definition': definition, 'componentIds': component_ids}],
        'evidenceFlow': [{'title': '本地冻结结果复算', 'detail': flow or
            '只读取完整completed运行，按原图source_id分组；逐例counts_exact与actionable_counts同时成立才为正确明确计数。所有错误、拒绝仍留在分母。探测器单列完整计数，不假装已集成业务决策。'}],
    }


def validate_completed_run(run, saved, directory):
    detector = not run.get("model_before")
    finished = run.get("finished_at_utc" if detector else "finished_at")
    ids = run.get("case_ids")
    if run.get("status") != "completed" or not isinstance(finished, str) or not finished:
        raise ValueError("Run must be explicitly completed with a completion timestamp")
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        raise ValueError("Unique planned case IDs are required")
    if [row.get("case_id") for row in saved] != ids or run.get("completed_cases") != len(ids):
        raise ValueError("Results must match the complete planned order and count")
    if detector:
        if run.get("script_changed_during_run") is not False:
            raise ValueError("Detector must explicitly record unchanged script")
        summary = run["summary"]["all"]
        if (summary["planned"] != len(ids) or summary["completed"] != len(ids)
                or summary["exact_count_denominator"] != len(ids)):
            raise ValueError("Detector summary has a different planned denominator")
    else:
        if run.get("expected_cases") != len(ids) or run.get("source_changed_during_run") is not False:
            raise ValueError("VLM run must be complete with unchanged sources")
        if not run.get("source_hashes") or run["source_hashes"] != run.get("source_hashes_after"):
            raise ValueError("VLM source snapshots must agree before and after execution")
        for name, digest in run["source_hashes"].items():
            if Path(name).name != name or sha(directory/"source_snapshot"/name) != digest:
                raise ValueError("Preserved source snapshot hash differs")
        if "filtered" in run["summary"] and run.get("source_inputs_changed_during_run") is not False:
            raise ValueError("Replay must explicitly preserve its source inputs")


def main():
    snapshot = refresh_history(write=False)
    rows, files, hashes = [], [], {}
    for run_file in sorted((ROOT/'evaluation-runs').glob('v03*/run.json')):
        run = json.loads(run_file.read_text())
        if run.get('status') != 'completed':
            continue
        name = run_file.parent.name
        prediction_file = run_file.parent/'predictions.jsonl'
        saved = [json.loads(line) for line in prediction_file.read_text().splitlines() if line]
        validate_completed_run(run, saved, run_file.parent)
        detector = not run.get('model_before')
        kind = 'detector' if detector else 'replay' if 'filtered' in run['summary'] else 'integrated' if 'integrated' in name or 'holdout' in name else 'consensus'
        if not detector and (len(saved) != run['expected_cases'] or run.get('source_changed_during_run')):
            raise ValueError('Do not promote incomplete or changed-source run: '+name)
        groups = {}
        for r in saved:
            domain = 'LOCO' if 'loco' in r['source_id'] else 'Screws'
            cohort = domain + (' · 正常' if r.get('subgroup') == 'normal_constant_222' else ' · 数量异常' if r.get('subgroup') == 'quantity_anomaly' else '') if run.get('split') == 'holdout' else domain
            groups.setdefault(cohort, []).append(r)
        for cohort, values in groups.items():
            if detector:
                metric = run['summary']['loco' if cohort == 'LOCO' else 'screws']
                correct = sum(bool(r['counts_exact'] and not r['error']) for r in values)
                errors = sum(bool(r['error']) for r in values)
                median = statistics.median(r['latency_ms'] for r in values)
                if (metric['planned'] != len(values) or metric['completed'] != len(values)
                        or metric['exact_count_denominator'] != len(values)
                        or metric['exact_count_images'] != correct or metric['errors'] != errors
                        or metric['median_cpu_pipeline_ms'] != median):
                    raise ValueError('Detector cohort metrics differ from saved rows')
                actionable = wrong = abstained = None
                timing = '固定CPU检测实验管线，不含模型加载；不是完整工作台耗时'
            else:
                correct = sum(bool(r['counts_exact'] and r['actionable_counts']) for r in values)
                actionable = sum(bool(r['actionable_counts']) for r in values)
                wrong = sum(bool(r['actionable_counts'] and not r['counts_exact']) for r in values)
                errors = sum(bool(r['error']) for r in values)
                abstained = sum(not r['actionable_counts'] and not r['error'] for r in values)
                median = statistics.median(r['latency_ms'] for r in values)
                timing = '历史两轮基础耗时 + 新身份核查回放；非端到端实测' if kind == 'replay' else '隔离实际上传处理 + observe总时间；不含真人操作，不经过inspect超时接口'
                assert correct + wrong + abstained + errors == len(values)
            rows.append({'run': name, 'label': name, 'cohort': cohort, 'stage': run.get('split', 'development'),
                'kind': kind, 'images': len(values), 'correct': correct, 'actionable': actionable,
                'wrong': wrong, 'abstained': abstained, 'errors': errors, 'medianMs': median,
                'timingNote': timing, 'status': 'completed'})
        for path in (run_file, prediction_file):
            relative = str(path.relative_to(ROOT)); files.append(relative); hashes[relative] = sha(path)
    selection_path = ROOT/'docs/v0.3/REPORT_SELECTION_STATE.json'
    selection = json.loads(selection_path.read_text()) if selection_path.exists() else {
        'status': 'development_passed', 'headline': '局部身份核查通过开发门槛，独立留出尚未运行',
        'detail': '回放验证保留LOCO 14/16与Screws 10/12正确明确计数，分别2张要求补拍，无错误明确计数。集成运行正在验证；不将开发结果当泛化成绩。',
        'holdoutStatus': '未运行', 'selectedDefault': 'spatial_inventory（v0.2默认保留）',
        'knownLimits': '同模型相关调用；模型判断孔形不等于几何实测；公开图不是现场验证；无角码阳性与真人效率基线。',
    }
    selection_files = ['docs/v0.3/IDENTITY_GEOMETRY_SELECTION.json', 'docs/v0.3/IDENTITY_GEOMETRY_DEVELOPMENT_PROTOCOL.json']
    if selection_path.exists():
        selection_files.append(str(selection_path.relative_to(ROOT)))
    features = [
        {'feature':'拍摄、预览、重拍后显式保存', 'status':'已实现', 'evidence':'test-results/browser/camera-v03/result.json', 'scope':'浏览器模拟摄像头工程验证，非真实设备摄像头实拍结果'},
        {'feature':'可校验来源的公开实拍演示图库', 'status':'已实现', 'evidence':'test-results/browser/public-demo-v03/result.json', 'scope':'三张开发样例，创建不调用模型；公开图订单禁止记为实物完成'},
        {'feature':'在线身份与孔形复核明细', 'status':'已实现', 'evidence':'test-results/browser/identity-evidence-v03/result.json', 'scope':'只读工程夹具；原图绑定、双方向及裁剪SHA，不能证明物理操作'},
        {'feature':'可断网查阅的中韩证据报告', 'status':'已实现', 'evidence':'test-results/browser/offline-identity-v03/browser-results.json', 'scope':'桌面/手机file://；身份部分为开发输出回放，无现场API实录主张'},
        {'feature':'相同照片内容不消耗追加补证预算', 'status':'已实现', 'evidence':'tests/test_evidence_content_identity.py', 'scope':'重新编码后的内容SHA优先，包含A→B→A和不同PNG元数据场景'},
    ]
    demo_path = ROOT/'test-results/browser/real-api-v03/runs/candidate-real-api-v1/browser/result.json'
    complete_demo = None
    demo_selection_path = ROOT/'docs/v0.3/REAL_API_DEMO_SELECTION.json'
    if demo_selection_path.exists():
        demo_selection = json.loads(demo_selection_path.read_text())
        demo_path = (ROOT/demo_selection['receipt']).resolve()
        if not demo_path.is_relative_to(ROOT.resolve()):
            raise ValueError('Real API receipt must be a project-local record')
        if sha(demo_path) != demo_selection['receipt_sha256']:
            raise ValueError('Selected real API receipt changed')
    if demo_path.exists():
        demo = json.loads(demo_path.read_text())
        if demo.get('status') in {'completed','completed_with_execution_errors'}:
            if demo.get('source_changed_during_run') is not False or len(demo.get('outcomes', [])) != 4:
                raise ValueError('Real API demo is incomplete or source changed')
            complete_demo = demo
            instruction = demo.get('instruction_outcome') or {}
            features.append({'feature':'真实本地模型、韩语改版与版本失效演示',
                'status':'流程已执行（保留实际结果）', 'evidence':str(demo_path.relative_to(ROOT)),
                'scope':f"3个已用开发样例、4个视觉请求+1个韩语提案请求；提案状态{instruction.get('status', '未记录')}、结构回退{instruction.get('fallback_used', '未记录')}。浏览器自动化明确确认；非真人研究或实物补件。"})
    q = snapshot['queries']
    q['v03_runs'] = {'rows':rows, 'source':source('v0.3候选逐图结果', files, ['v03-runs'],
        '正确是actionable_counts且counts_exact；wrong是actionable且计数错；abstained是无执行异常但不可执行；errors为运行异常。探测器仅报告完整计数correct，未定义业务可执行/拒绝（null）。每图有多个派生订单，但分母仍按原图。'),
        'methods':[{'language':'Python','code':'python -m scripts.refresh_v03_report_snapshot；每个运行按source_id中的loco区分领域，holdout再按subgroup分层。源码保存于scripts/refresh_v03_report_snapshot.py。'}]}
    q['v03_runs']['source']['fileHashes'] = hashes
    q['v03_selection'] = {'rows':[selection], 'source':source('当前候选采用结论', selection_files, ['v03-summary'],
        '结论来自先于运行冻结的门槛与完整结果；开发通过不等于留出通过，零观察错误不等于风险为零；选默认与名次无等价关系。', '读取开发协议与选择记录，以及存在时的最新REPORT_SELECTION_STATE；不从工程检查数推算效果或比赛名次。')}
    gate_path = ROOT/'evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json'
    if gate_path.exists():
        gate = json.loads(gate_path.read_text())
        run_path, predictions = gate_path.parent/'run.json', gate_path.parent/'predictions.jsonl'
        if not (gate.get('complete') is True and gate.get('stage') == 'holdout'
                and gate.get('planned_images') == gate.get('completed_images') == 64
                and gate.get('run_json_sha256') == sha(run_path)
                and gate.get('predictions_sha256') == sha(predictions)
                and gate.get('protocol_sha256') == sha(ROOT/'docs/v0.3/HOLDOUT_GATES_V1.json')):
            raise ValueError('Completed holdout gate is not bound to the current frozen records')
        paired_rows = []
        labels = {'loco_normal16':'LOCO 正常', 'loco_anomaly16':'LOCO 数量异常', 'screws32':'Screws 散装零件'}
        for group, value in gate['groups'].items():
            for key, label in [('baseline','同次真实首轮'),('candidate','强化候选')]:
                metric = value[key]
                paired_rows.append({'cohort':labels.get(group,group), 'method':label,
                    'images':metric['images'], 'correct':metric['C'], 'wrong':metric['W'],
                    'abstained':metric['U'], 'errors':metric['E'],
                    'medianMs':metric['latency_ms']['median'] if metric['latency_ms'] else None,
                    'gate':('通过' if value['passed'] else '未通过') if key == 'candidate' else '配对消融，无独立端到端计时'})
        paths = [gate_path,run_path,predictions,ROOT/'docs/v0.3/HOLDOUT_GATES_V1.json']
        q['v03_comparison'] = {'rows':paired_rows, 'source':source('同64张的阶段配对比较',
            [str(p.relative_to(ROOT)) for p in paths], ['v03-paired-results'],
            'C为正确且可执行，W为错误且可执行，U为无执行错误但不可执行，E为执行错误；每行C+W+U+E为该层图片数。同次首轮来自真实保存调用，不是独立样本或独立端到端服务。',
            '读取完整64张冻结gate，核对run、逐例预测及协议SHA；按原有三个分层呈现首轮与最终候选，保持失败与弃权分母。')}
        q['v03_comparison']['source']['fileHashes'] = {str(p.relative_to(ROOT)):sha(p) for p in paths}
        q['v03_selection']['source']['files'].extend([str(gate_path.relative_to(ROOT)), 'docs/v0.3/HOLDOUT_GATES_V1.json'])
    deployment_path = ROOT/'docs/v0.3/DEPLOYMENT_SELECTION.json'
    if deployment_path.exists():
        q['v03_selection']['source']['files'].append(str(deployment_path.relative_to(ROOT)))
    q['v03_features'] = {'rows':features, 'source':source('新增可用流程', [f['evidence'] for f in features], ['v03-features'],
        '已实现代表功能及工程验证，不是现场识别或用户效率数据。每行证据只支持其声明范围。', '逐项读取camera/public-demo/identity/offline浏览器记录及照片内容去重测试；工程夹具、模拟摄像头和开发输出回放分别保留范围，未运行现场试验。')}
    for query in ('v03_selection','v03_features'):
        q[query]['source']['fileHashes'] = {
            name:sha(ROOT/name) for name in q[query]['source']['files'] if (ROOT/name).is_file()}
    junit = ROOT/'test-results/engineering-v03-final.xml'
    if junit.exists():
        tree = ElementTree.parse(junit).getroot()
        total = sum(int(n.get('tests',0)) for n in tree.iter('testsuite'))
        failed = sum(int(n.get('failures',0))+int(n.get('errors',0)) for n in tree.iter('testsuite'))
        q['engineering_checks']['rows'][0] = {'suite':'v0.3 Python完整工程回归','pass':total-failed,'fail':failed,
            'scope':'隔离状态、版本、相机输入、来源绑定、身份核查、评测协议；模型测试替身',
            'evidence':'test-results/engineering-v03-final.xml'}
        q['engineering_checks']['source']['files'][0] = 'test-results/engineering-v03-final.xml'
    for name, title in [('camera-v03/result.json','v0.3相机采集'),('public-demo-v03/result.json','v0.3公开图库'),('identity-evidence-v03/result.json','v0.3身份核验明细'),('offline-evidence-v03/browser-results.json','v0.3离线证据报告'),('offline-identity-v03/browser-results.json','v0.3离线身份明细')]:
        path = ROOT/'test-results/browser'/name
        if not path.exists():
            continue
        result = json.loads(path.read_text()); passed = result.get('passed', result.get('checksPassed'))
        if type(passed) is not int:
            raise ValueError('Unknown browser count schema: '+str(path))
        q['engineering_checks']['rows'].append({'suite':title, 'pass':passed,'fail':len(result.get('errors',[])),
            'scope':str(result.get('scope','浏览器工程验证，非模型准确率')), 'evidence':str(path.relative_to(ROOT))})
        q['engineering_checks']['source']['files'].append(str(path.relative_to(ROOT)))
    if complete_demo is not None:
        q['engineering_checks']['rows'].append({'suite':'v0.3真实UI/API验收',
            'pass':complete_demo['passed_engineering_assertions'],
            'fail':len(complete_demo.get('errors',[]))+len(complete_demo.get('failed_requests',[])),
            'scope':'3个已用开发样例；4视觉请求+1韩语提案请求，浏览器自动化确认，非真人/现场研究',
            'evidence':str(demo_path.relative_to(ROOT))})
        q['engineering_checks']['source']['files'].append(str(demo_path.relative_to(ROOT)))
    snapshot['buildStatus'] = 'updating'
    snapshot['generatedAt'] = datetime.now(UTC).isoformat()
    TARGET.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'v03_cohort_rows':len(rows),'features':len(features),'selection':selection['status']}))


if __name__ == '__main__':
    main()
