import React from "react";
import { DataComponent, DataTable, ReportSection, RichNarrative } from "../../data-app-public.jsx";
import "./v03-progress.css";

const number = (value) => typeof value === "number" && Number.isFinite(value);
const text = (value) => Array.isArray(value) ? value.join("；") : typeof value === "string" && value.trim() ? value : "未提供";
const count = (value) => number(value) ? String(value) : "未提供";
const fraction = (value, denominator) => !number(value) || !number(denominator) ? "未提供"
  : denominator === 0 ? "不适用（无分母）" : `${value} / ${denominator}`;
const seconds = (value) => number(value) ? `${(value / 1000).toFixed(2)} 秒` : "未提供";
const stages = { development: "开发集", holdout: "预先冻结的留出" };
const kinds = { integrated: "集成管线", replay: "离线回放", detector: "检测器实验", consensus: "同模型双方向" };
const statuses = { completed: "运行完成", pending: "待运行", running: "运行中", failed: "运行失败", development_passed: "开发门槛通过", holdout_running: "新留出运行中", holdout_passed: "新留出门槛通过", holdout_not_adopted: "完整评测后保留候选" };

export function v03DisplayRows(rows) {
  // Keep exact source rows untouched. Partial scores are never presented as final results.
  return rows.map((row) => row.status === "completed" ? { ...row } : {
    ...row, correct: null, actionable: null, wrong: null, abstained: null, errors: null, medianMs: null,
  });
}

function friendlyRun(row) {
  if (row.label && row.label !== row.run) return row.label;
  if (row.run?.includes("grounding_dino")) return "Grounding DINO · CPU 候选";
  if (row.run?.includes("owl")) return "OWL · CPU 候选";
  if (row.run?.includes("identity_geometry")) return "身份与孔形复核";
  if (row.run?.includes("identity_probe")) return "局部身份复核初版";
  if (row.run?.includes("guarded_holdout")) return "局部身份强化 · 新留出";
  if (row.run?.includes("guarded_integrated")) return "局部身份强化 · 完整开发流程";
  if (row.kind === "consensus") return "双方向一致性";
  return row.label || row.run || "未命名运行";
}

function RunLabel({ row }) {
  return <div className="kg-run-cell">
    <strong>{friendlyRun(row)}</strong><small>{row.run || "运行 ID 未提供"}</small>
    <span>{kinds[row.kind] || text(row.kind)} · {statuses[row.status] || text(row.status)}</span>
  </div>;
}

function ResultCell({ value, row, denominator, label, adverse = false }) {
  return <span className={`kg-number ${adverse && number(value) && value > 0 ? "kg-adverse" : ""}`}>
    {row.status !== "completed" ? "未完成" : fraction(value, denominator)}
    {label && <small>{label}</small>}
  </span>;
}

function Evidence({ id, title, queryId, rows, columns, displayRows = rows, description }) {
  return <DataComponent id={id} title={title} queryId={queryId} sourceRows={rows}
    displayRows={displayRows} kind="table" className="kg-evidence-table" description={description}>
    <DataTable rows={displayRows} columns={columns} caption={title} searchable={displayRows.length > 8} />
  </DataComponent>;
}

export function V03Progress({ snapshot, reviewedPeriodRows, visible }) {
  const queries = snapshot.queries || {};
  const available = (id) => Array.isArray(queries[id]?.rows);
  if (!["v03_selection", "v03_runs", "v03_features"].some(available)) return null;
  const rowsFor = (id) => available(id) ? reviewedPeriodRows(id) : [];
  const selections = rowsFor("v03_selection"), runs = rowsFor("v03_runs"), features = rowsFor("v03_features");
  const current = selections.at(-1);
  const columns = [
    { field: "run", label: "候选 / 运行性质", renderCell: (_, row) => <RunLabel row={row} /> },
    { field: "cohort", label: "样本组 / 划分", renderCell: (value, row) => <div className="kg-v03-cohort"><strong>{text(value)}</strong><small>{stages[row.stage] || text(row.stage)}</small></div> },
    { field: "images", label: "本组图片", renderCell: (value) => <span className="kg-number">{count(value)}</span> },
    { field: "correct", label: "正确 / 本组图片", renderCell: (value, row) => <ResultCell value={value} row={row} denominator={row.images} label={row.kind === "detector" ? "仅完整计数" : "正确且可执行"} /> },
    { field: "actionable", label: "可执行覆盖", renderCell: (value, row) => <ResultCell value={value} row={row} denominator={row.images} /> },
    { field: "wrong", label: "明确回答中的错误", renderCell: (value, row) => <ResultCell value={value} row={row} denominator={row.actionable} adverse /> },
    { field: "abstained", label: "补拍 / 拒绝", renderCell: (value, row) => <ResultCell value={value} row={row} denominator={row.images} /> },
    { field: "errors", label: "执行异常", renderCell: (value, row) => <span className={`kg-number ${number(value) && value > 0 ? "kg-adverse" : ""}`}>{row.status === "completed" ? count(value) : "未完成"}</span> },
    { field: "medianMs", label: "中位耗时 / 口径", renderCell: (value, row) => <div className="kg-number kg-v03-time">{row.status === "completed" ? seconds(value) : "未完成"}<small>{text(row.timingNote)}</small></div> },
  ];

  return <section className="kg-report-section kg-v03" aria-label="v0.3 当前开发与验证进展">
    {available("v03_selection") && visible("v03-summary") && <ReportSection id="v03-summary"
      title="v0.3 当前判断" queryId="v03_selection" sourceRows={current ? [current] : []} showHeading={false}>
      <div className="kg-v03-selection" data-reviewed-rows>
        <p className="kg-v03-stage">v0.3 · {current ? statuses[current.status] || text(current.status) : "选择记录待汇入"}</p>
        <h2>{current ? text(current.headline) : "v0.3 当前结论尚未提供"}</h2>
        <p>{current ? text(current.detail) : "已预留来源绑定。完整结果进入快照前，不预填分数或推定通过。"}</p>
        {current && <>
          <dl className="kg-v03-facts">
            <div><dt>新留出状态</dt><dd>{text(current.holdoutStatus)}</dd></div>
            <div><dt>当前默认配置</dt><dd>{text(current.selectedDefault)}</dd></div>
          </dl>
          <p className="kg-v03-limits">{text(current.knownLimits)}</p>
        </>}
      </div>
      <RichNarrative id="v03-summary:interpretation" className="kg-evidence-note" label="编辑 v0.3 选择边界"
      value="开发门槛用于选择待验证方案，不自动证明泛化能力或切换产品默认。新留出门槛通过并更新选择记录之前，保留 v0.2 单轮默认。计数、弃答、执行异常和耗时需要一起判断；它们都不是夺冠概率。" />
    </ReportSection>}

    {available("v03_comparison") && visible("v03-paired-results") && <Evidence id="v03-paired-results"
      title="同一批新64张：错误被挡住了多少，正确回答又损失了多少？"
      queryId="v03_comparison" rows={rowsFor("v03_comparison")}
      description="每个分层分别显示真实首轮与强化后的结果。两行来自同一批照片，不能相加为样本量。C+W+U+E为本组原定分母；弃权与失败完整保留。"
      columns={[
        { field: "cohort", label: "分层" }, { field: "method", label: "阶段" },
        { field: "images", label: "图片" }, { field: "correct", label: "C 正确可执行" },
        { field: "wrong", label: "W 错误可执行" }, { field: "abstained", label: "U 补拍 / 弃权" },
        { field: "errors", label: "E 执行错误" },
        { field: "medianMs", label: "中位耗时", renderCell: value => number(value) ? seconds(value) : "未独立测量" },
        { field: "gate", label: "冻结门槛 / 范围" },
      ]} />}

    <RichNarrative id="v03-runs:heading" label="编辑 v0.3 候选比较说明"
      value={"### 失败候选和额外开销也保留在同一张表里\n\nLOCO 与 Screws 分别保留自己的分母；开发、留出、集成运行、离线回放和检测器实验不混算。VLM 的正确数要求数量全对且可执行；检测器只报告完整计数正确，因为尚未接入业务决策，其可执行、明确错误和弃答项保持未提供。未完成运行不展示阶段性分数。"} />
    {available("v03_runs") && visible("v03-runs") && <Evidence id="v03-runs" title="v0.3 候选结果与代价"
      queryId="v03_runs" rows={runs} displayRows={v03DisplayRows(runs)} columns={columns}
      description="每行是一轮运行中的一个样本组。正确、补拍与错误同时报告；重复使用同一批图不能增加独立样本。运行完成不等于候选通过选择门槛。" />}
    <RichNarrative id="v03-runs:paired-and-timing" className="kg-evidence-note" label="编辑配对基线与时延限制"
      value={"**配对基线与时延。** 表中出现“同次首轮 / same-run first pass”时，它是相同图片、同一次流程中的配对基线，不是另一组独立样本。可用来比较后续核查怎样改变明确错误与弃答，不能把这些相关调用称为独立专家。\n\n离线回放的耗时是历史基础耗时加本次核查，不是新测得的端到端流程时间；检测器 CPU 耗时、集成管线耗时和真人完成时间也不可直接等同。按每行的记录口径解释，不将中位数差值冒充独立阶段的实测耗时。零个明确错误仍须结合可执行覆盖与弃答分母，不能解释为风险为零。"} />

    <RichNarrative id="v03-features:heading" label="编辑 v0.3 功能进展说明"
      value={"### 新增功能的工程证据单独列示\n\n拍摄、公开演示和身份追溯改善了可操作性与可检查性。下表说明各项实际完成状态及验证范围；浏览器模拟摄像头、只读工程夹具和开发输出回放不属于真人现场试验。"} />
    {available("v03_features") && visible("v03-features") && <Evidence id="v03-features" title="v0.3 功能与验证范围"
      queryId="v03_features" rows={features}
      description="功能状态取自已核对的工程记录，不从模型成绩推定；同一流程的重复 QA 不累计成独立样本。"
      columns={[{ field: "feature", label: "功能" }, { field: "status", label: "状态" }, { field: "evidence", label: "保存的依据" }, { field: "scope", label: "证据范围与限制" }]} />}
  </section>;
}
