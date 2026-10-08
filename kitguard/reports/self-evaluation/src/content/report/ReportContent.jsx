import React from "react";
import { DataComponent, DataTable, ReportSection, RichNarrative, useDataApp } from "../../data-app-public.jsx";
import { ReportDisclosure } from "../shared/ReportDisclosure.jsx";
import { V03Progress } from "./V03Progress.jsx";

const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
const count = (value) => isNumber(value) ? String(value) : "未提供";
const pct = (value) => isNumber(value) ? `${(value * 100).toFixed(1)}%` : "未评估";
const fraction = (value, total) => isNumber(value) && isNumber(total) ? total === 0 ? "不适用（无分母）" : `${value} / ${total}` : "未提供";
const seconds = (value) => isNumber(value) ? `${(value / 1000).toFixed(2)} 秒` : "未提供";
const splitLabel = (value) => ({ development: "开发集", holdout: "留出集", test: "测试集" })[value] || value || "未标明";
const runLabel = (row) => row.label || row.run || "未命名运行";
const statusLabel = (value) => ({ completed: "运行完成", pending: "待运行", running: "运行中", failed: "运行失败" })[value] || value;

function RunCell({ row }) {
  return <div className="kg-run-cell"><strong>{runLabel(row)}</strong><span>{row.model || "模型信息未提供"}</span>
    <small>{row.dataset || "未标明数据集"} · {splitLabel(row.split)}</small>
    {row.protocol && <small>{row.protocol}</small>}
    {row.status && <small>{statusLabel(row.status)}</small>}
  </div>;
}

function EvidenceTable({ id, title, description, queryId, rows, columns, displayRows = rows }) {
  return <DataComponent id={id} title={title} description={description} queryId={queryId}
    kind="table" sourceRows={rows} displayRows={displayRows} className="kg-evidence-table">
    <DataTable rows={displayRows} columns={columns} caption={title} searchable={displayRows.length > 8} />
  </DataComponent>;
}

function OptionalEvidence({ snapshot, visible, queryId, id, title, children, columns }) {
  const rows = snapshot.queries?.[queryId]?.rows;
  if (!visible(id)) return null;
  if (!Array.isArray(rows)) return children;
  return <EvidenceTable id={id} title={title} queryId={queryId} rows={rows} columns={columns}
    description="按当前保存的工程记录展示；未知状态保留，不作为零值。" />;
}

export function ReportContent() {
  const { snapshot, reviewedPeriodRows, visible, canEdit, mode, appTitle, setAppTitle } = useDataApp();
  const v03Available = ["v03_selection", "v03_runs", "v03_features"].some((id) => Array.isArray(snapshot.queries?.[id]?.rows));
  const runs = reviewedPeriodRows("benchmark_runs");
  const instructionRuns = snapshot.queries?.instruction_runs ? reviewedPeriodRows("instruction_runs") : [];
  const summaryQueryIds = ["benchmark_runs", ...(instructionRuns.length ? ["instruction_runs"] : [])];
  const summarySourceRows = { benchmark_runs: runs, ...(instructionRuns.length ? { instruction_runs: instructionRuns } : {}) };
  const baseline = runs.find((row) => row.run === "screws_development_baseline_v1");
  const revised = runs.find((row) => row.run === "screws_development_v2");
  const paired = baseline && revised;
  const scopeNames = [...new Set(runs.map((row) => `${row.dataset || "未标明数据集"} · ${splitLabel(row.split)}`))];
  const latestByScope = runs.reduce((map, row) => map.set(`${row.dataset || "未标明数据集"} · ${splitLabel(row.split)}`, row), new Map());
  const eligibleKnown = runs.filter((row) => isNumber(row.eligible));
  const noEligible = runs.length > 0 && eligibleKnown.length === runs.length && eligibleKnown.every((row) => row.eligible === 0);
  const subgroupRuns = runs.filter((row) => [row.normalImages, row.anomalyImages, row.constantNominalImages].some(isNumber));
  const nominalRuns = runs.filter((row) => [row.nominalNormalTotal, row.nominalAnomalyTotal].some(isNumber));
  const timedRuns = runs.filter((row) => row.timingNote);
  const perturbationRuns = runs.filter((row) => row.split === "holdout" && isNumber(row.eligible) && row.eligible > 0 && isNumber(row.mismatchFalseReady));
  const releaseDevelopment = runs.find((row) => row.run === "loco_development_release_v1");
  const releaseHoldout = runs.find((row) => row.run === "loco_holdout_release_v1");
  const controlHoldout = runs.find((row) => row.run === "loco_holdout_27b_single_control_v1");
  const completeHoldout = (row) => row?.status === "completed" && row.images === 48 && isNumber(row.exact) && isNumber(row.wrongActionable);
  const releaseComplete = completeHoldout(releaseHoldout);
  const controlComplete = completeHoldout(controlHoldout);
  const pairedHoldout = releaseComplete && controlComplete;
  const exactDifferencePoints = pairedHoldout ? ((releaseHoldout.exact / releaseHoldout.images - controlHoldout.exact / controlHoldout.images) * 100).toFixed(1) : null;
  const latencyDifference = pairedHoldout && isNumber(releaseHoldout.medianMs) && isNumber(controlHoldout.medianMs) ? seconds(releaseHoldout.medianMs - controlHoldout.medianMs) : "未提供";
  const headlineRows = releaseComplete ? [releaseHoldout, ...(controlComplete ? [controlHoldout] : [])] : releaseDevelopment ? [releaseDevelopment] : paired ? [baseline, revised] : runs;
  const summary = [
    v03Available ? "## v0.2 历史阶段结论" : "## 阶段结论",
    "KitGuard 已具备可运行、可追溯的核验流程。现阶段最需要解决的是识别证据是否足够可靠，以及它相较人工清单能带来什么实际改善。软件功能完成不能替代这两项验证。",
    releaseComplete
      ? `- **冻结配置的公开图留出结果已记录。** 空间清单完整计数为 ${fraction(releaseHoldout.exact, releaseHoldout.images)}（${pct(releaseHoldout.accuracy)}），明确给出的数量中有 ${fraction(releaseHoldout.wrongActionable, releaseHoldout.actionable)} 计数错误。它仍不是现场操作或角码阳性验证。${controlComplete ? `同模型直接计数对照为 ${fraction(controlHoldout.exact, controlHoldout.images)}，提高 ${exactDifferencePoints} 个百分点；这是提示词、输出结构和 token 预算共同变化的协议比较。` : "预定的同模型对照尚未完整汇入。"}`
      : releaseDevelopment
      ? `- **选定配置已冻结，留出结果尚待完整汇入。** 集成开发运行完整计数为 ${fraction(releaseDevelopment.exact, releaseDevelopment.images)}，明确给出的数量中仍有 ${fraction(releaseDevelopment.wrongActionable, releaseDevelopment.actionable)} 计数错误。开发图已参与选型，不能当作留出泛化成绩。`
      : "- **当前已选定并冻结空间清单协议。** 正式集成开发结果与预定留出结果正在汇入；下方保留已有开发运行。尚未完整核对的结果不用于最终效果结论。",
    ...(releaseComplete ? [`- **数量异常图中 ${fraction(releaseHoldout.nominalAnomalyFalseReady, releaseHoldout.nominalAnomalyTotal)} 被错误判为就绪。** 这是同一正常构成订单下的离线派生错误，没有发生人工确认或真实出库。高完整计数率仍不能消除错误就绪风险。`] : []),
    ...(pairedHoldout ? [`- **计数改善伴随更长耗时。** 中位测量区间从直接计数的 ${seconds(controlHoldout.medianMs)} 增至空间清单的 ${seconds(releaseHoldout.medianMs)}，增加 ${latencyDifference}。它包含上传处理与观察，未测量真人操作总时间。`] : []),
    `- **当前可查阅 ${runs.length} 次真实视觉运行记录。** 覆盖 ${scopeNames.length} 个数据集与划分组合；新增结果继续加入下方表格，未完成评测不填入零分。`,
    ...(instructionRuns.length ? [`- **文字改版另行计分。** 已保存 ${instructionRuns.length} 次指令开发评测，明确修改与应澄清/拒绝分列报告，避免“全部拒绝”抬高总体分数。`] : []),
    "- **已有可复查的技术证据，仍不能承诺名次。** 现场连续补证、人类基线及开发期参赛资格仍需明确。现有证据不能支持夺冠概率或工业可靠性承诺。",
  ].join("\n\n");
  const comparison = releaseComplete
    ? `## 冻结配置的留出计数与错误回答一起报告\n\n空间清单在 ${count(releaseHoldout.images)} 张公开留出图上完整计数正确 ${count(releaseHoldout.exact)} 张（${pct(releaseHoldout.accuracy)}）；${fraction(releaseHoldout.actionable, releaseHoldout.images)} 个观察给出可执行数量，其中 ${fraction(releaseHoldout.wrongActionable, releaseHoldout.actionable)} 计数错误。正常图全对 ${fraction(releaseHoldout.normalExact, releaseHoldout.normalImages)}，数量异常图全对 ${fraction(releaseHoldout.anomalyExact, releaseHoldout.anomalyImages)}。\n\n**在固定正常构成订单下，数量异常图错误就绪 ${fraction(releaseHoldout.nominalAnomalyFalseReady, releaseHoldout.nominalAnomalyTotal)}，正确纠正 ${fraction(releaseHoldout.nominalAnomalyCorrect, releaseHoldout.nominalAnomalyTotal)}。** 这些是离线规则派生的决策，没有发生人工确认或真实出库。中位测量耗时 ${seconds(releaseHoldout.medianMs)}；包含上传处理与观察，不能当作完整人工工作流耗时。\n\n${controlComplete ? `相同模型、1536px、产品上传处理及相同留出图的直接计数对照为 ${fraction(controlHoldout.exact, controlHoldout.images)}（${pct(controlHoldout.accuracy)}），完整计数差值为 +${exactDifferencePoints} 个百分点；对照明确计数错误为 ${fraction(controlHoldout.wrongActionable, controlHoldout.actionable)}，固定正常订单下数量异常图错误就绪为 ${fraction(controlHoldout.nominalAnomalyFalseReady, controlHoldout.nominalAnomalyTotal)}。空间清单使用 900 输出 token，对照使用 450；提示词和输出结构也不同。因此只能解释为整套协议的比较，不能把差异单独归因于点位或列表。\n\n中位测量区间为 ${seconds(releaseHoldout.medianMs)} 对 ${seconds(controlHoldout.medianMs)}，增加 ${latencyDifference}。计数与时延应一起评估；这不是人类效率实验，也未建立统计独立性或显著性结论。` : "预定的同模型直接计数对照尚未完整汇入，当前不估算它的结果或两者差异。"}`
    : releaseDevelopment
    ? `## 开发集支持选型，留出集才检验冻结后的表现\n\n选定的 27B、1536px 单次空间清单协议在集成开发运行中完整计数为 ${fraction(releaseDevelopment.exact, releaseDevelopment.images)}（${pct(releaseDevelopment.accuracy)}），其中明确给出的数量仍有 ${fraction(releaseDevelopment.wrongActionable, releaseDevelopment.actionable)} 错误。开发图已反复用于比较和修改，不能当作未见过的新数据。\n\n冻结后的 48 张公开图留出与同模型直接计数对照按预定协议运行。完整结果核对前不把部分正确数当作最终成绩；两种协议的提示词、输出结构与 token 预算共同变化。`
    : paired
    ? `## 计数正确增加了，但明确给出的错误也增加了\n\n首次运行完整计数正确为 ${fraction(baseline.exact, baseline.images)}（${pct(baseline.accuracy)}），修改后为 ${fraction(revised.exact, revised.images)}（${pct(revised.accuracy)}）。两次都使用开发样本，差值不能当作留出泛化收益。\n\n第二次运行的 ${count(revised.actionable)} 个观察满足“可执行”条件，其中 ${count(revised.wrongActionable)} 个计数错误。明确给出数量的覆盖扩大了，未同时证明这些答案更可靠。应优先处理错误明确回答，再比较补证策略或更强模型。`
    : "## 每个运行保留自己的评测范围\n\n表格保存每次真实运行的原始分母与失败。没有配对的相同样本、相同规则和冻结版本时，不把不同运行的差异解释为改进效果。";
  const benchmarkColumns = [
    { field: "run", label: "运行 / 模型", renderCell: (_, row) => <RunCell row={row} /> },
    { field: "images", label: "原图数", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
    { field: "exact", label: "完整计数正确", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.images)}<small>{pct(row.accuracy)}</small></span> },
    { field: "actionable", label: "可执行观察", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.images)}</span> },
    { field: "wrongActionable", label: "其中计数错误", renderCell: (value, row) => <span className={`kg-number ${isNumber(value) && value > 0 ? "kg-adverse" : ""}`}>{row.actionable === 0 ? "不适用" : fraction(value, row.actionable)}</span> },
    { field: "errors", label: "运行异常", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
    { field: "medianMs", label: "中位耗时", renderCell: (value) => <span className="kg-number">{seconds(value)}</span> },
    { field: "eligible", label: "产品范围内原图", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
  ];
  const scopeRows = [...latestByScope.entries()].map(([scope, row]) => ({
    scope, run: runLabel(row), images: row.images, eligible: row.eligible,
    interpretation: row.eligible === 0 ? "仅支持该范围的计数压力分析；不提供匹配工单性能分母。"
      : !isNumber(row.eligible) ? "产品数量范围覆盖未提供，不能推断工单完成效果。"
      : "存在范围内图片；工单就绪/错误放行仍须读取对应指标，不能由计数率代替。",
  }));

  return <article className="report-content kg-report" aria-label="KitGuard 中文开发自检报告">
    <header className="report-hero">
      <RichNarrative id="report:stage" value={v03Available ? "v0.3 当前进展 · v0.2 历史证据保留" : pairedHoldout ? "公开图评测已汇总 · 现场效果待验证" : "开发自检 · 持续更新"} className="kg-stage" label="编辑报告阶段说明" />
      <h1 data-data-app-title contentEditable={canEdit && mode === "edit"} suppressContentEditableWarning
        aria-label={canEdit && mode === "edit" ? "编辑报告标题" : undefined}
        onBlur={canEdit && mode === "edit" ? (event) => setAppTitle(event.currentTarget.textContent.trim() || appTitle) : undefined}
        onKeyDown={canEdit && mode === "edit" ? (event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } } : undefined}>{appTitle}</h1>
      <RichNarrative id="report:description" className="report-deck" label="编辑报告说明"
        value="检查系统已经做到什么、真实模型还错在哪里，以及哪些证据会改变下一步的开发决定。" />
    </header>

    <V03Progress snapshot={snapshot} reviewedPeriodRows={reviewedPeriodRows} visible={visible} />

    {v03Available && <RichNarrative id="v02:historical-scope" className="kg-v02-divider" label="编辑历史评测范围说明"
      value={"## v0.2 冻结评测与历史细节\n\n以下 48 张对照结论属于 v0.2，其“冻结配置”指当时的版本。后面的全部运行、分组和耗时明细也收录已经完成的 v0.3 记录，每行保留自己的协议、数据划分与分母；不能合并为新版本成绩。当前采用判断以本页上方 v0.3 部分为准。历史错误就绪和较差结果继续保留。"} />}

    {visible("report-summary") && <ReportSection id="report-summary" title={v03Available ? "v0.2 历史阶段结论" : "阶段结论"} queryId="benchmark_runs" queryIds={summaryQueryIds} sourceRowsByQuery={summarySourceRows} sourceRows={runs} showHeading={false} className="report-summary">
      <RichNarrative id="report-summary:body" value={summary} label="编辑阶段结论" />
    </ReportSection>}

    <section className="kg-report-section" aria-label="真实模型结果">
      {visible("benchmark-findings") && <ReportSection id="benchmark-findings" title="真实计数结果" queryId="benchmark_runs"
        sourceRows={headlineRows} showHeading={false}>
        <RichNarrative id="benchmark-findings:body" value={comparison} label="编辑计数结果分析" />
      </ReportSection>}
      {visible("benchmark-table") && <EvidenceTable id="benchmark-table" title="全部真实图像核验运行"
        queryId="benchmark_runs" rows={runs} displayRows={[...runs].reverse()} columns={benchmarkColumns}
        description="每行是一轮运行，近期在前；重复使用相同开发图片的行不能相加成为独立样本。异常与拒绝保留在原图分母中。" />}
      <RichNarrative id="benchmark:actionability-note" className="kg-evidence-note" label="编辑可执行指标说明"
        value="**如何理解“可执行”：** 模型给出的四类数量均非空、问题列表为空、动作类型为无需补拍。它只描述观察输出格式与表态，既不保证计数正确，也不等于工单已就绪或人工已确认。运行异常为 0 也不能说明识别没有错误。" />
      {timedRuns.length > 0 && visible("benchmark-timing") && <EvidenceTable id="benchmark-timing" title="不同运行的耗时口径"
        queryId="benchmark_runs" rows={timedRuns} displayRows={[...timedRuns].reverse()}
        description="组合多个调用的离线耗时与集成端点实测耗时分别标明。"
        columns={[{ field: "run", label: "运行", renderCell: (_, row) => <RunCell row={row} /> }, { field: "timingNote", label: "记录口径" }]} />}
      <RichNarrative id="benchmark:split-note" className="kg-evidence-note" label="编辑开发与留出区分"
        value="**开发与留出分开看。** 每行保留模型、策略和数据划分。original 表示原始文件输入，app-upload 表示经过产品上传处理；压缩、集成方式和图像方向可能改变结果，不能互相替代。开发图上的策略选择不构成留出成绩；尚未完成的候选模型或留出运行不补成零分。同一原图旋转后的再次观察仍是同一个计分单位。" />
      {subgroupRuns.length > 0 ? <>
        {visible("subgroup-findings") && <ReportSection id="subgroup-findings" title="正常构成与变化数量分别检验"
          queryId="benchmark_runs" sourceRows={subgroupRuns} showHeading={false}>
          <RichNarrative id="subgroup-findings:body" label="编辑子组解释"
            value={"## 正常样本与数量异常不能只报一个平均数\n\n正常袋的四类真值为固定构成，恒输出正常数量也能答对这部分。因此分别查看正常照片、变化数量照片，并保留完全不用图像的固定构成对照。支架阳性、长短型号或现场物理动作不由这组四类计数结果证明。"} />
        </ReportSection>}
        {visible("subgroup-table") && <EvidenceTable id="subgroup-table" title="分组完整计数与固定构成对照"
          queryId="benchmark_runs" rows={subgroupRuns} displayRows={[...subgroupRuns].reverse()}
          description="每格使用自己的原图分母；固定构成对照不是另一个视觉模型。"
          columns={[
            { field: "run", label: "运行 / 划分", renderCell: (_, row) => <RunCell row={row} /> },
            { field: "normalExact", label: "正常图全对", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.normalImages)}</span> },
            { field: "anomalyExact", label: "数量异常图全对", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.anomalyImages)}</span> },
            { field: "constantNominalExact", label: "恒猜正常构成全对", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.constantNominalImages)}</span> },
          ]} />}
      </> : <RichNarrative id="subgroups:pending" className="kg-evidence-note" label="编辑子组等待说明"
        value="**正常构成与数量异常的分组结果待汇入。** 当前不根据总正确率倒推子组成绩，也不把未提供的留出结果写成 0。" />}
      {nominalRuns.length > 0 && <>
        {visible("nominal-findings") && <ReportSection id="nominal-findings" title="以正常构成订单检验数量异常"
          queryId="benchmark_runs" sourceRows={nominalRuns} showHeading={false}>
          <RichNarrative id="nominal-findings:body" label="编辑正常订单任务解释"
            value={"## 面对同一张正常订单，异常袋是否会被错误判为就绪\n\n将作者定义的正常构成作为订单，正常照片应就绪，数量异常照片应被发现并提出正确差异。这里的 ready 是离线规则派生的就绪决策，没有发生人工确认或真实出库。\n\n同时报告正常图就绪、异常图错误就绪和异常图正确纠正，避免把全部转人工或拒绝的策略误读成准确。观察到 0 个错误只说明本次样本未出现该错误，不等于风险为零。"} />
        </ReportSection>}
        {visible("nominal-table") && <EvidenceTable id="nominal-table" title="正常构成订单下的派生任务"
          queryId="benchmark_runs" rows={nominalRuns} displayRows={[...nominalRuns].reverse()}
          description="正常组与数量异常组使用不同分母；每图派生任务不增加独立图像样本。"
          columns={[
            { field: "run", label: "运行 / 划分", renderCell: (_, row) => <RunCell row={row} /> },
            { field: "nominalNormalReady", label: "正常图正确就绪", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.nominalNormalTotal)}</span> },
            { field: "nominalAnomalyFalseReady", label: "异常图错误就绪", renderCell: (value, row) => <span className={`kg-number ${isNumber(value) && value > 0 ? "kg-adverse" : ""}`}>{fraction(value, row.nominalAnomalyTotal)}</span> },
            { field: "nominalAnomalyCorrect", label: "异常图正确纠正", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.nominalAnomalyTotal)}</span> },
          ]} />}
        <RichNarrative id="nominal:consensus-note" className="kg-evidence-note" label="编辑共识策略限制"
          value="历史双方向策略中，同模型两次观察具有相关性，不能称为独立验证器；必须同时看覆盖与错误。当前选定协议为单次空间清单。点位同样是模型估计，可能重复、遗漏或分类错误，没有定位真值验证；它与人的实际分放、补拍是不同证据。" />
      </>}
      {perturbationRuns.length > 0 && <>
        {visible("perturbation-findings") && <ReportSection id="perturbation-findings" title="固定扰动订单与正常构成订单使用不同分母"
          queryId="benchmark_runs" sourceRows={perturbationRuns} showHeading={false}>
          <RichNarrative id="perturbation-findings:body" label="编辑固定扰动任务说明"
            value={"## 另一种派生任务：每张图固定改变一项订单数量\n\n程序先根据四类真值建立匹配订单，再按预定规则改变第一类可调整零件的数量，形成一个确定不匹配的订单。扰动不参考模型输出；每张范围内照片只派生一个这样的不匹配任务。\n\n这个分母包含正常和数量异常照片，与上表固定正常构成订单下仅含异常图的分母不同。两种派生任务共用原图，不增加独立图像样本，也不覆盖所有可能的错误订单。"} />
        </ReportSection>}
        {visible("perturbation-table") && <EvidenceTable id="perturbation-table" title="留出图的匹配与固定扰动订单"
          queryId="benchmark_runs" rows={perturbationRuns} displayRows={[...perturbationRuns].reverse()}
          description="每个分母都是本轮产品数量范围内原图；派生决策不等于人工完成或真实出库。"
          columns={[
            { field: "run", label: "运行 / 划分", renderCell: (_, row) => <RunCell row={row} /> },
            { field: "matchedReady", label: "真值匹配订单就绪", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.eligible)}</span> },
            { field: "mismatchFalseReady", label: "固定扰动错误就绪", renderCell: (value, row) => <span className={`kg-number ${isNumber(value) && value > 0 ? "kg-adverse" : ""}`}>{fraction(value, row.eligible)}</span> },
            { field: "mismatchCorrect", label: "固定扰动正确纠正", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.eligible)}</span> },
          ]} />}
      </>}
      {visible("scope-coverage") && <DataComponent id="scope-coverage" title="每个评测范围能说明什么" queryId="benchmark_runs"
        kind="table" sourceRows={runs} displayRows={scopeRows} className="kg-evidence-table">
        <DataTable rows={scopeRows} searchable={false} caption="按数据集和划分区分证据范围"
          columns={[{ field: "scope", label: "数据范围" }, { field: "run", label: "该范围最近一轮" }, { field: "eligible", label: "产品范围内原图", renderCell: (value) => <span className="kg-number">{count(value)}</span> }, { field: "interpretation", label: "解释边界" }]} />
      </DataComponent>}
      <RichNarrative id="scope-coverage:note" className="kg-evidence-note" label="编辑产品范围说明"
        value={noEligible ? "**产品范围内性能尚无分母。** 当前已完成的 Screws 原图至少有一类数量超过每类 3 件的产品上限，因此不能据此计算匹配工单就绪率或真实场景错误放行率。" : "各数据集的范围内原图数单独记录。缺失值表示尚未提供；不同范围的结果不能合并替代现场工单指标。"} />
    </section>

    <section className="kg-report-section" aria-label="自然语言改版评测">
      {instructionRuns.length ? <>
        {visible("instruction-findings") && <ReportSection id="instruction-findings" title="改版理解与拒绝分别计分"
          queryId="instruction_runs" sourceRows={instructionRuns} showHeading={false}>
          <RichNarrative id="instruction-findings:body" label="编辑指令评测解释"
            value={"## 正确改数量与正确拒绝，必须同时做到\n\n固定文字开发案例覆盖韩、中、英三种语言：9 条明确修改和 15 条应澄清或拒绝的请求。所有请求都拒绝也能得到 15/24，因此总体通过率必须与明确修改、拒绝两组结果一起看。\n\n每轮结果保留在下表。明确修改只有完整四类数量正确才通过；合理拒绝按预期算成功，模型执行失败另列并保留在分母。反复调整后的结果仍属于作者生成的开发工程集，不是独立用户或留出泛化成绩。"} />
        </ReportSection>}
        {visible("instruction-table") && <EvidenceTable id="instruction-table" title="真实指令开发评测"
          queryId="instruction_runs" rows={instructionRuns}
          description="同一套固定案例的多轮开发运行分别保存；不将重复运行相加当作新增独立案例。"
          columns={[
            { field: "run", label: "运行 / 模型", renderCell: (_, row) => <div className="kg-run-cell"><strong>{runLabel(row)}</strong><span>{row.model || "模型信息未提供"}</span></div> },
            { field: "attempted", label: "尝试条数", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
            { field: "passed", label: "全部通过", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.attempted)}</span> },
            { field: "proposalPassed", label: "明确修改正确", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.proposalTotal)}</span> },
            { field: "clarificationPassed", label: "应拒绝正确拒绝", renderCell: (value, row) => <span className="kg-number">{fraction(value, row.clarificationTotal)}</span> },
            { field: "executionErrors", label: "执行异常", renderCell: (value) => <span className={`kg-number ${isNumber(value) && value > 0 ? "kg-adverse" : ""}`}>{count(value)}</span> },
          ]} />}
      </> : <RichNarrative id="instruction:pending" label="编辑指令评测状态"
        value={"## 指令修改与正确拒绝的结果正在汇总\n\n固定的 24 条文字开发案例覆盖明确修改、越界、含糊、不相关与越权完成请求。真实结果核对后单列明确修改和应澄清两组；缺少结果时不以零分代替。"} />}
    </section>

    <section className="kg-report-section" aria-label="系统工程完成度">
      <RichNarrative id="engineering:body" label="编辑工程实现说明" value={"## 流程与追溯能力已实现，工程检查单独报告\n\n当前工作台支持结构化及自然语言改版提案、人工批准、参考图登记、照片核验、补证建议、重核验和人工完成记录。改版、换照片或更新参考图后，旧核验失效；提交前再次核对版本与证据状态。\n\n历史详情保留当时需求、照片、差异、模型与耗时，并展示真实程序步骤和补证前后观察。空间清单记录可展开物体列表及估计点位，证据 ZIP 可离线查阅关联照片和完整 JSON；哈希只支持完整性追溯，不证明现场真实性。图片变化只能说明观察变化，不能证明操作者确实移动或补充了同一批物料。"} />
      <OptionalEvidence snapshot={snapshot} visible={visible} queryId="engineering_checks" id="engineering-table" title="工程验证记录"
        columns={[
          { field: "suite", label: "检查集" },
          { field: "pass", label: "通过", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
          { field: "fail", label: "失败", renderCell: (value) => <span className={`kg-number ${isNumber(value) && value > 0 ? "kg-adverse" : ""}`}>{count(value)}</span> },
          { field: "scope", label: "验证范围" },
          { field: "evidence", label: "已保存的依据" },
        ]}>
        <RichNarrative id="engineering:pending" className="kg-evidence-note" label="编辑工程记录状态"
          value="工程回归与专项检查的结构化记录正在整理。已完成的自动化和浏览器检查用于验证版本保护、数据一致性与交互行为；不能替代视觉计数准确率。" />
      </OptionalEvidence>
      <RichNarrative id="engineering:separation" className="kg-evidence-note" label="编辑工程测试边界"
        value="通过用例数量不等于识别样本数量，也不等于每项场景都已达到工业安全要求。工程注入的测试观察器与合成图片仅用于软件验证。" />
    </section>

    <section className="kg-report-section" aria-label="未解决的参赛与效果问题">
      <RichNarrative id="gaps:heading" label="编辑未决问题说明" value={"## 下一步结论取决于尚未补齐的证据\n\n冻结后的公开图留出与预定对照用于检验选定观察协议；现场对照与官方规则解释则决定物理闭环效果和参赛资格是否成立。它们应分别解决。"} />
      <OptionalEvidence snapshot={snapshot} visible={visible} queryId="readiness_gaps" id="readiness-table" title="关键未决事项"
        columns={[
          { field: "item", label: "事项" }, { field: "status", label: "当前状态" },
          { field: "evidence", label: "现有依据 / 缺口" }, { field: "implication", label: "对参赛与开发的影响" },
        ]}>
        <RichNarrative id="gaps:pending" label="编辑证据缺口" value={"- **LOCO 与更强模型对照仍在进行。** 只有完整运行及复算后的结果才进入本报告。\n- **缺少人类现场基线。** 尚不能说明系统比人工清单更快、少漏件或更容易使用。\n- **缺少连续实物补证验证。** 静态公开图片不能建立“发出建议—人执行—新照片验证”的物理闭环效果。\n- **开发期资格仍未决。** 原始同意书有赛前开发限制；保留开发时间和来源不等于自动获得豁免。需要官方解释后再确定参赛主张。"} />
      </OptionalEvidence>
    </section>

    <section className="kg-report-section" aria-label="评测方法与解释限制">
      <RichNarrative id="methods:body" label="编辑评测方法" value={"## 保留失败、区分开发与留出，才能继续判断\n\n计数评测的计分单位是一张来源明确的原始实拍图。同图派生多个工单不能增加原图数量；同源或相近场景的图片也未被证明统计独立。完整计数必须四类全对，拒绝、超时及无效输出仍留在分母；另报可执行覆盖和其中的计数错误，以防全部拒绝被误读成可靠。\n\n开发图片已用于发现问题与修改策略，不能转称留出成绩。官方 test 中有 8 张异常图被预先划入开发，因此这里是自定义留出划分，不是官方完整测试协议。本轮公开图留出在冻结代码、模型、处理流程和规则后运行，完整保留每个输出与失败，未根据留出错误回调当前方案。空间清单与直接计数对照同时改变提示词、输出结构和 token 预算，不是单因素消融。公开照片也可能存在基础模型预训练污染，不能代替新现场的泛化证据。"} />
      <ReportDisclosure id="methods-details" label="展开复现约束与尚待执行的实物对照">
        <RichNarrative id="methods:details" label="编辑复现与实物对照说明" value={"### 复现记录\n\n运行脚本保留冻结 manifest、原图及上传处理 JPEG 的逐例哈希、源码快照、模型配置、逐例输出、异常和耗时。本次空间单次协议的 1536px prepared PNG 实际哈希仅在最后一例运行元数据中保留，其他输入可按冻结处理流程从上传 JPEG 重建，不声称已逐例保存该 PNG 摘要。每次修改采用新运行目录，保留较差结果。最终计数比较来自 loco_holdout_release_v1 与 loco_holdout_27b_single_control_v1 两个完整运行；程序归纳、逐例复算与来源边界保存在项目 docs/FINAL_EVALUATION.md 和 docs/FINAL_INDEPENDENT_AUDIT.md。自然语言指令的 24 条固定案例是作者生成的开发工程文字案例，合理澄清或拒绝按预期计分，模型执行失败单独记错；它不属于用户研究。\n\n### 现场对照尚未形成结果\n\n后续实物协议拟对相同起始零件配置比较人工清单、单次视觉核验和 KitGuard 补证流程，记录真实真值、前后照片、漏件/错误就绪、人工接管与总完成时间。最初设想的自采 16 个开发场景与 48 个实物盲测场景仍是待执行设计，不是已完成的现场样本；它们与本报告公开照片的开发/留出划分不同。"} />
      </ReportDisclosure>
      <RichNarrative id="report:closing" className="kg-evidence-note" label="编辑阶段报告说明"
        value="本报告用于决定下一轮开发与验证，不把未知结果填成 0，也不把软件完成、评测通过与比赛获奖视为同一件事。正式报名和作品提交仍需核对官方最新要求。" />
    </section>
  </article>;
}
