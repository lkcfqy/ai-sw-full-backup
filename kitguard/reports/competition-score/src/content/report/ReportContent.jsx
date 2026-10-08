import React from 'react';
import {DataComponent,DataTable,ReportSection,RichNarrative,useDataApp} from '../../data-app-public.jsx';
const states={in_progress:'执行中',planned:'待执行',done:'完成并验证',done_no_score_change:'核查完成 · 不加分',no_supported_uplift:'暂无加分依据',negative_evidence:'负面证据 · 不提升',constraint_excluded:'约束排除',unknown_not_awarded:'缺少证据 · 不计分',not_observable:'无法观察'};
const names={own_goal:'当前照片与BOM目标',task_comparison:'前瞻机器任务对照',five_same_version:'同版本五项材料',visual_candidates:'既有识别候选',human_field_outcomes:'真人与实物收益',customer_pricing:'客户与定价',judge_rank:'评委与排名',deployment_capacity:'部署容量',prior_art_scope:'相关方案核查',repeat_exposed_photos:'重复曝光图片',more_feature_count:'继续堆功能',new_independent_evidence:'新独立证据'};
function Evidence({id,title,queryId,rows,columns}){return <DataComponent id={id} title={title} queryId={queryId} kind="table" sourceRows={rows} displayRows={rows}><DataTable rows={rows} columns={columns} caption={title} searchable={false}/></DataComponent>;}
export function ReportContent(){
 const {snapshot,visible,appTitle,setAppTitle,canEdit,mode}=useDataApp();
 const q=id=>snapshot.queries[id].rows;const rows=q('rubric'), rounds=q('rounds'), candidates=q('candidates');
 const score=rows.reduce((s,r)=>s+r.score,0); const stop=snapshot.scoringStop;
 return <article className="report-content kg-score-report">
 <header className="report-hero"><h1 data-data-app-title contentEditable={canEdit&&mode==='edit'} suppressContentEditableWarning onBlur={canEdit&&mode==='edit'?e=>setAppTitle(e.currentTarget.textContent.trim()||appTitle):undefined}>{appTitle}</h1><RichNarrative id="review-intro" value="官方权重决定看什么，自评分帮助决定先做什么。这里的分数是开发审查判断，不能预测名次；资格和提交回执仍未核实。"/></header>
 {visible('score-summary')&&<ReportSection id="score-summary" title="当前判断" queryId="rubric" sourceRows={rows} showHeading={false}><RichNarrative id="score-summary:body" value={`## 当前自评 ${score} / 100\n\n${snapshot.scoreNarrative||'起点为 dev3，72.5 分。最有依据的补分方向是支持自己的照片与 BOM、完成预定机器任务对照，以及把五项参赛材料同步到最新实测版本。'}\n\n${stop?stop:'正在开发与验证。每轮只在证据支持后调整评分，增加功能或测试数量本身不涨分。'}`}/></ReportSection>}
 {visible('rubric-table')&&<Evidence id="rubric-table" title="本赛七项 · 官方附录5权重" queryId="rubric" rows={rows} columns={[{key:'name',label:'项目'},{key:'score',label:'自评',align:'right'},{key:'max',label:'满分',align:'right'},{key:'reason',label:'证据与扣分理由'}]}/>}
 {visible('round-table')&&<Evidence id="round-table" title="开发与评分记录" queryId="rounds" rows={rounds} columns={[{key:'round',label:'轮次'},{key:'score',label:'自评',align:'right'},{key:'change',label:'变化',align:'right'},{key:'evidence',label:'完成证据'}]}/>}
 {visible('candidate-table')&&<Evidence id="candidate-table" title="改善项与停止依据" queryId="candidates" rows={candidates} columns={[{key:'id',label:'改善项',renderCell:v=>names[v]||v},{key:'status',label:'状态',renderCell:v=>states[v]||v},{key:'reason',label:'判断依据'}]}/>}
 <RichNarrative id="screening-method" value={`## 初筛和本赛分别看\n\n初筛内容准备度为 ${snapshot.screeningContent||72} / 90，资格材料另有 10 分，提交接收状态未知。已制作文件不代表比赛方已经接收，因此正式初筛总分留空。\n\n本赛按主题15、Agent20、技术20、新颖性10、实际效果15、数据安全10、商业模式10计分。子项权重来自正式规则，子项取值为保守自评；加分项暂计0。\n\n## 识别效果仍按原分母\n\n原 51 图评估保留 41 正确、3 错误、7 不确定，以及 3 个 false-ready。公开旧图的再次执行仅检验任务流程，不增加新图准确率分母，也不证明真人提效。\n\n[比赛方规则与提交公告](https://contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5) · 以附录4、5为评分依据。`} sourcePreviews={{'https://contest.gnict.org/bbs/board.php?bo_table=notice&wr_id=5':{title:'比赛官方 v1.0 规则与最终材料通知',summary:'通知列出五项最终材料与 2026-10-06 12:00 KST 截止时间。附件附录4为初筛，附录5为本赛七项100分。',source:'경남 AI·SW 경진대회',approvedForReport:true}}}/>
 </article>;
}
