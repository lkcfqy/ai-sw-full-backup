"""Build the v0.3 Chinese assessment from complete, hash-bound evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(m):
    return f"{m['C']} / {m['W']} / {m['U']} / {m['E']}"


def ratio(m):
    n = m['denominator']
    return f"{m['numerator']}/{n} ({m['numerator']/n:.1%})" if n else "不适用（分母0）"


def link(path, output):
    import os
    return os.path.relpath(path.resolve(), output.parent.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve previous assessment; choose a new path')
    gate, audit, demo = map(read, (args.gate, args.audit, args.demo))
    run_dir = args.gate.parent
    run, raw = read(run_dir/'run.json'), [json.loads(s) for s in (run_dir/'predictions.jsonl').read_text().splitlines() if s]
    development_path = ROOT/'evaluation-runs/v03_guarded_integrated_development_v1/gate_report_v1.json'
    development = read(development_path)
    if not (gate.get('complete') is True and gate.get('stage') == 'holdout'
            and gate.get('planned_images') == gate.get('completed_images') == 64
            and run.get('status') == 'completed' and run.get('source_changed_during_run') is False
            and len(raw) == 64 and [r['case_id'] for r in raw] == run['case_ids']):
        raise ValueError('A complete, unchanged 64-image holdout is required')
    if gate['development_report_sha256'] != sha(development_path):
        raise ValueError('Development evidence changed')
    if gate['protocol_sha256'] != sha(ROOT/'docs/v0.3/HOLDOUT_GATES_V1.json'):
        raise ValueError('Protocol changed')
    for key, path in [('run_json_sha256', run_dir/'run.json'), ('predictions_sha256', run_dir/'predictions.jsonl')]:
        if gate[key] != sha(path):
            raise ValueError('Gate evidence changed: '+key)
    if not (audit['run_sha256'] == gate['run_json_sha256']
            and audit['predictions_sha256'] == gate['predictions_sha256']
            and audit['input_audit']['verified'] is True
            and audit['schema_revalidated'] == 64):
        raise ValueError('Independent audit does not cover this exact run')
    if not (demo.get('status') in {'completed', 'completed_with_execution_errors'} and demo.get('finished_at')
            and demo.get('source_changed_during_run') is False and len(demo.get('outcomes', [])) == 4):
        raise ValueError('Complete real API demo evidence is required, including failures')
    if any(item.get('status') != 'execution_error' and
           (item.get('backend') != 'mlx' or item.get('runtime_mode') != 'spatial_guarded') for item in demo['outcomes']):
        raise ValueError('Demo must retain actual MLX guarded runtime identity')
    junit = ROOT/'test-results/engineering-v03-final.xml'
    suites = ElementTree.parse(junit).getroot()
    tests = sum(int(s.get('tests', 0)) for s in suites.iter('testsuite'))
    failed = sum(int(s.get('failures', 0))+int(s.get('errors', 0)) for s in suites.iter('testsuite'))
    c, b, comparison = gate['candidate'], gate['baseline'], gate['comparison']
    adopted = gate['default_adoption_eligible']
    decision = ('通过内部事前冻结门槛，启动脚本采用 spatial_guarded 作为研究版默认' if adopted else
                '未满足全部冻结门槛，不提升 spatial_guarded 为默认；保留 spatial_inventory，强化协议标记为实验候选')
    group_lines = []
    for name, group in gate['groups'].items():
        m = group['candidate']
        group_lines.append(f"| {name} | {m['images']} | {counts(m)} | {counts(group['baseline'])} | "
                           f"{m['latency_ms']['median']/1000:.2f}s | {'通过' if group['passed'] else '未通过'} |")
    matrix_lines = [f"| {label} | " + ' | '.join(str(comparison['paired_matrix_baseline_rows_candidate_columns'][label][col]) for col in 'CWUE')+' |' for label in 'CWUE']
    exceptions = []
    for item in gate['cases']:
        candidate, baseline = item['candidate'], item['baseline']
        if candidate['classification'] != 'C' or baseline['classification'] == 'W':
            observed = (candidate.get('observation') or {}).get('observed')
            exceptions.append(f"| {item['case_id']} | {item['ground_truth']} | {observed} | "
                              f"{baseline['classification']} → {candidate['classification']} |")
    latencies = sorted(r['latency_ms'] for r in raw)
    p95 = latencies[math.ceil(.95*len(latencies))-1]/1000
    calls = []
    for row in raw:
        diagnostic = row.get('observation_diagnostics') or row.get('error_diagnostics') or {}
        identity = diagnostic.get('identity') or {}
        calls.append(len(diagnostic.get('passes', []))
                     + int(identity.get('model_called') is True or bool(identity.get('response'))))
    demo_lines = []
    decision_labels = {'ready':'数量相符（仍需人确认）', 'correct':'需要增减调整',
                       'recapture':'要求补拍', 'manual':'转人工', 'blocked':'检查阻断'}
    for o in demo['outcomes']:
        elapsed = f"{o['request_wall_ms']/1000:.2f}s" if o.get('request_wall_ms') is not None else '未完成计时'
        demo_decision = decision_labels.get(o.get('decision'), o.get('decision') or o.get('status'))
        demo_lines.append(f"| {o['sample']} / R{o['revision']} | {o.get('http_status')} | "
                          f"{demo_decision} | {elapsed} | {o.get('check_id')} |")
    instruction = demo.get('instruction_outcome') or {}
    instruction_time = (f"{instruction['actual_elapsed_ms']/1000:.2f}秒"
                        if instruction.get('actual_elapsed_ms') is not None else '无完成计时')
    instruction_note = (f"韩语修改提案实际返回 `{instruction.get('status', '未记录')}`，请求耗时{instruction_time}；"
                        f"提案符合明确指令：{instruction.get('proposal_matches_intended', '未记录')}；"
                        f"使用结构化回退：{instruction.get('fallback_used', '未记录')}。"
                        f"确认路径：`{(instruction.get('approval') or {}).get('via', '未确认')}`。")
    files = {'holdout_gate': args.gate, 'independent_audit': args.audit, 'real_api_demo': args.demo,
             'engineering': junit, 'development_gate': development_path}
    references = '\n'.join(f"- [{name}]({link(path,args.output)})；SHA-256 `{sha(path)}`" for name,path in files.items())
    text = f"""# KitGuard v0.3 自检与竞争力评估

生成于 {datetime.now(UTC).isoformat()}。实际开发始于2026-09-26（韩国时间）。本报告是内部技术评估，不是官方评分、获奖预测或提交回执。

## 本轮结论

**{decision}。** 新64张公开实拍留出全部保留：强化候选 {counts(c)}（正确明确 / 错误明确 / 弃权补拍 / 执行失败）；同次真实首轮为 {counts(b)}。正确明确覆盖 {ratio(c['correct_actionable'])}，错误明确占全部照片 {ratio(c['wrong_actionable_all_images'])}，已明确回答中的错误为 {ratio(c['wrong_given_actionable'])}。

强化候选挡住首轮 {comparison['blocked_baseline_wrong']} 次错误，新增错误 {comparison['introduced_wrong']} 次，同时把 {comparison['correct_to_abstention']} 次原本正确的回答变为弃权。这些数量及延迟共同决定取舍，不能只挑“答对时准确率”宣传。

争夺高名次的优势在于完整可运行的业务流程、版本与证据约束，以及敢于保留失败的可复查实验。本轮新增了实拍入口、公开开发图库、内容级补证去重、局部身份核查与离线审计。**仍缺真实零件连续补件实验、真人效率对照及新拍摄域验证；现有证据不能证明必拿第一或已经达到工业可靠性。**

## 新64张冻结评测

开发28张为 {counts(development['candidate'])}，同次首轮为 {counts(development['baseline'])}。开发结果已用于选型，不能当留出成绩。新64来自32张LOCO（16正常、16数量异常）和32张Screws来源分组裁剪；与旧评测原图及开发图无完全重叠。它们仍来自公开数据源，不是64家工厂或独立拍摄会话。

| 新留出分层 | 张数 | 强化 C/W/U/E | 同次首轮 C/W/U/E | 强化中位耗时 | 冻结门槛 |
| --- | ---: | --- | --- | ---: | --- |
{chr(10).join(group_lines)}

C=四类数量正确且可执行；W=数量错误但可执行；U=无执行错误但需补拍/未知；E=执行或解析失败。C+W+U+E始终为原定分母；计数刚好正确但带有阻断问题不算C。每类预先固定正确覆盖门槛分别13/16、13/16和27/32，错误明确及执行错误都必须为0，中位耗时≤60秒；不在看见结果后放宽。

| 规则模拟指标 | 强化候选 | 同次首轮 |
| --- | --- | --- |
| LOCO数量异常对名义2/2/2/0订单的错误ready | {ratio(c['nominal_anomaly_false_ready'])} | {ratio(b['nominal_anomaly_false_ready'])} |
| 每图一个固定扰动订单的错误ready | {ratio(c['fixed_perturbation_false_ready'])} | {ratio(b['fixed_perturbation_false_ready'])} |
| 255个合法四类订单中存在任意错误ready的图片 | {ratio(c['panel_any_false_ready'])} | {ratio(b['panel_any_false_ready'])} |

255个派生订单不增加照片样本数。错误ready是静态规则模拟中的就绪误判，没有对应真实出库；0个观察错误也不能推导现场零风险。第一轮对照从同次实际模型调用恢复，输入相同而调用相关；没有另跑独立的完整v0.2服务计时，因此首轮端到端延迟为“不适用”，不是0秒。

强化完整观察的中位耗时 {c['latency_ms']['median']/1000:.2f}秒，p95（nearest-rank）{p95:.2f}秒，最大 {c['latency_ms']['maximum']/1000:.2f}秒。已保留第一张/冷启动相关开销；共保存 {sum(calls)} 个实际调用阶段记录。该计时包括隔离上传、SQLite、归一化和观察，不包含真人操作，也不走完整/inspect响应超时接口。真实API计时另列。

| 首轮 → 强化 | C | W | U | E |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(matrix_lines)}

## 方法、探索失败与边界

所有视觉调用使用本机 `mlx-community/Qwen3.6-27B-4bit`，固定revision `c000ac2c2057d94be3fa931000c31723aac53282`，MLX，主图最长边1536，temperature=0、关闭thinking。前两轮各900输出token，局部身份核查1800。模型共享目录为 `~/Downloads/AI-Models/`；另一台3080电脑未连接实测。正常推理不需要云API key，也不把照片发送给云模型。

先列出可见物体，代码统计粗类数量，视觉模型不接收目标BOM；强化模式再独立询问旋转90度照片，数量冲突置为未知。两轮清楚时，对原图中已找到的nut/washer裁剪复核类别及孔形；只允许增加不确定性，不能凭订单目标修正为期望数量。相同模型、旋转和裁剪仍有相关错误；两轮共同漏检无法由此恢复，孔形也是模型判断。角码没有阳性验证，Screws没有垫圈阳性，不能宣称四类泛化完整。

原双方向方案在12张新开发图仍有2次错误明确计数，普通局部类别复核仍有1次，因此均未直接采用。固定CPU探测器探索也保留：OWL v2完整计数LOCO 0/16、Screws 0/12；Grounding DINO Tiny为0/16、1/12。它们未接入主判定，不把负面结果删掉，也不把这些开发样本相加为新留出。

旧v0.2的48张结果（46/48完整正确、2次错误明确、名义异常错误ready 1/24）仅作历史记录。不能与本次64直接相减当作提升；旧48已暴露，不再称v0.3未见数据。当前64运行结束后也全部视为已暴露，之后改进必须明确为回归或另设新验证集。

## 已交付的工程与真实操作

- 韩中工作台支持拍摄、预览、重拍和明确保存，绑定拍摄时订单版本，页面隐藏释放相机；模拟摄像头工程测试不冒称真实摄像头拍摄验证。
- 三个固定来源/SHA的公开开发样例可建新工单，实际推理时才得到结果；没有缓存标准答案。公共演示工单无法记录实物完工。
- 归一化内容SHA识别重复补证：同图新ID、元数据变化及A→B→A不算额外有效照片；真正新图才进入追加证据预算。
- 订单变化、换图或参考变化使旧核验失效；失败/超时/缺失身份阶段不能放行，最终完成仍由操作者确认实物。
- 在线与离线双语报告展示当时需求、照片、原图估计点位、两轮观察、局部复核及散列。生产导出保存裁剪参数和SHA；实际临时裁剪图不被导出，不能说ZIP内含每张裁剪。SHA证明字节完整性，不能证明现场真实性或签名。

Python工程回归 **{tests-failed}/{tests}通过**；失败/错误 {failed}。这些测试使用隔离环境和明确模型替身，不算识别准确率。模型输入独立复算验证 {audit['input_audit']['prepared_inputs_recreated']} 个预处理输入、{audit['input_audit']['identity_crop_files_recreated']} 个裁剪文件，均与保存SHA一致；全部64返回记录重新进行结构和计分核验。

真实Chrome自动化→FastAPI→本地MLX演示覆盖3个已有公开开发样例、4次视觉核验，另有1次韩语修改提案请求，保存全部请求、运行身份、原始录像、订单与证据ZIP。总计5个模型API请求；每次视觉请求内部有多阶段调用，不等于一共只生成5次。订单R1修改后，原照片记录不能用于R2；通过真实上传控件把同一公共图重新绑定R2，再实际核验。这验证版本隔离和重新检查，**没有发生实体补件或实物完成**，也不增加独立评测样本。明确批准按钮由浏览器自动化点击，属于接口/界面验收，不是真人用户研究。

{instruction_note} 语言运行身份记录是请求前后状态快照，不冒充独立的逐请求生成轨迹。失败或澄清不得计为提案成功。

| 公共开发样例 / 订单版本 | HTTP | 实际决策 | 请求总时长 | 核验ID |
| --- | ---: | --- | ---: | --- |
{chr(10).join(demo_lines)}

## 所有非C结果和首轮错误

保留每个U/W/E以及被挡住的首轮错误，不删困难图片。数量向量的顺序为bolt、nut、washer、bracket；null为未知，不等于0。详细原图来源、提示/输出及规则任务见原始predictions.jsonl。

| 来源案例ID | 作者真值 | 强化观察 | 首轮 → 强化 |
| --- | --- | --- | --- |
{chr(10).join(exceptions) or '| 无 | — | — | — |'}

## 竞争力判断与下一步

| 维度 | 当前判断 | 最有价值的后续证据 |
| --- | --- | --- |
| 业务价值 | 订单改版和照片证据失效有明确流程，容易现场讲清 | 与真实清单核对流程并排演示 |
| 产品完成度 | 本机运行、拍照、版本控制、补证和证据导出已实现 | 在比赛设备上完整彩排 |
| 方法说服力 | 有冻结门槛、同次首轮对照、失败保留及输入复算 | 对新拍摄场景和真实零件建立未见评测 |
| 效果与落地 | 当前只支持静态公开图描述性结论 | 真人计时/错误基线、真实少件→补件→新照片连续验证 |
| 参赛材料 | 新版评估与技术证据可复查，旧版材料保持历史身份 | 按说明会最终评分表与模板核对 |

可自主获取的公开数据和工程验证已经推进；公开图不能替代本人实际移动零件、真实相机现场采集和主办方对参赛条款的解释。现场数据准备清单见 [REAL_WORLD_VALIDATION.md](../REAL_WORLD_VALIDATION.md)，韩语答辩见 [JUDGES_QA_KO.md](JUDGES_QA_KO.md)。这不是要求现在停工，而是如实区分软件完成度与尚无证据的现场收益。

真实开发日期继续保留9月26日。已存原始同意书的赛前开发限制不会因为来源披露自动豁免；正式采用需按主办方解释。9月26日读取的[昌原大学公告](https://www.changwon.ac.kr/haksa/na/ntt/selectNttInfo.do?mi=18769&nttSn=1430805)列报名至9月29日12:00、开发期9月29日至10月6日，校内招募对象与总赛事一般部资格是不同范围。没有代发邮件、签字、报名或提交。

## 复核入口

{references}

原始记录和快照保留在 `evaluation-runs/v03_guarded_holdout_v1/`；评分器 `scripts/evaluate_v03_gate.py`；输入与首轮复算 `scripts/analyze_consensus_run.py`。复算无需GPU。重新运行模型需要新输出目录，已暴露64只能标为同集回归。完整协议散列 `{gate['protocol_sha256']}`。
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(json.dumps({'output': str(args.output), 'holdout_images':64, 'default_adoption_eligible':adopted,
                      'candidate':{k:c[k] for k in ('C','W','U','E')}, 'engineering_passed':tests-failed},ensure_ascii=False))


if __name__ == '__main__':
    main()
