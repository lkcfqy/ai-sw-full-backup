# LOCO24 组合数量验证：可冻结运行协议

2026-10-02；实现与 CPU 合同稿。本文、入口和合成测试的创建不授权模型执行。当前不读取 24 张候选的像素、不写正式 truth/freeze。实际预飞、冻结、推理由根在完整 identity-only 51 审计后执行。v0.7、已封存 v0.8、作者 unresolved/null truth 和既有评分/来源凭证不改。

完整设计与口径沿用 [设计追加](LOCO24_RUNNER_DESIGN_ADDENDUM.md)。入口 [run_loco_combined.py](../../scripts/v08/run_loco_combined.py) 固定全部 24 原图、四个数量组各 6；先从作者原 mask 标签/defects 配置和已复核提案逐字段重算两种不同类别的全局差量，再绑定新 `author_combined_quantity_defect_rule_v1` 清单。mask 不是实例；同类别重复差量、额外缺陷、改过的映射均拒绝。含 4 件的 12 张不截断、不排除。未登记曝光只指已绑定的历史登记；相似图、同物件/会话及预训练曝光未知。

## 方法决定必须先于新 24 模型结果

根保存新的 `method_selection.json`，结构如下（示意值不能直接运行）：

```json
{
  "schema": "kitguard.v08.loco-combined-method-selection.v1",
  "status": "approved_for_freeze",
  "approved_by": "root_agent",
  "selected_at_utc": "<完整 identity51 独立审计之后的 ISO 时间>",
  "methods": ["spatial_guarded"],
  "identity_decision": {"include": false, "role": "excluded", "reason": "<完整证据支持的理由>"},
  "no_loco24_model_results_used": true,
  "identity51_evidence": {
    "run": {"path": "evaluation-runs/v0.8/identity_reference_guarded_v1/run.json", "sha256": "<实际 SHA>"},
    "predictions": {"path": "evaluation-runs/v0.8/identity_reference_guarded_v1/predictions.jsonl", "sha256": "<实际 SHA>"},
    "independent_audit": {"path": "<实际 passed 审计路径>", "sha256": "<实际 SHA>"}
  },
  "exposure_since_source_preflight": []
}
```

未决定时可用 `draft_pending_selection` 留存工作草案，但 preflight/freeze/run 一律拒绝。`include:true` 必须同时指定 methods=[G,I] 的上述完整 mode 名，role 为 `eligible_candidate` 或 `failed_candidate_comparison`；不可因文件存在自动加入。即使排除 I，也先绑定完整、已独立审计的 51 作为根决策基础。新增实际曝光凭证显式列入最后字段，不反写旧预飞。

G 固定无参考原 guarded，I 为既有 identity-only adapter：首两轮无参考，原条件允许身份阶段时才追加 nut297/washer057；同一个 VLM 的相关复核，不能称独立身份确认。两臂均从 `identity_reference_guarded_freeze_v1` 清单复制原 v0.7 基类及已冻结 adapter 字节，G-only 的包可含未使用 I 文件。当前生产工作版不进入实验。固定模型 Qwen3.6-27B-4bit/revision c000ac…、1536 输入界、900/1800 tokens、temperature 0、单 worker、零重试、无 warmup。G 只加输入/原文及真实 generate 边界记录，不改原模型协议；另外绑定新记录器源码 SHA。I 的原 observer protocol 保持不变。

## 输入与执行边界

source SHA 固定哈希排序成中性 case-001…024；双臂逐图 AB/BA 交替，各 12 次先手。整个日程和所有 N 行先保存，之后逐项尝试一次；失败 E、未执行 N 均在完整分母内。根选择后一次冻结，不依据新结果切换方法、参考、提示或提前停掉差臂。

预飞通过原冻结 app-upload API 归一化，生成 JPEG 和原向准备 PNG；源、归一图、准备图 SHA/RGB/尺寸均保存。归一图与固定参考 source/crop/prepared 链再做精确重复核验；若冲突停止，不换图。freeze/run 的非计时完整性阶段重新验证 canonical upload/prepare 结果以拒绝可改的预飞输入列表；**实际观察各臂共用同一份持久化 JPEG**。每次观察的 timer 包含首次复制、模型冷加载（若发生）、观察及 raw/images 保存；另外披露预处理及 setup/final 核验耗时。这不是全产品端到端耗时。共享全局模型缓存明确记录每次 loaded_before，冷首例保留全分母，同时报告 warm 子集。

observer 只获得中性 JPEG 路径、固定占位 BOM 1/1/1/1、该方法固定 refs；不获得作者缺陷/真值、mask、源 ID 或其他臂结果。每次生成保留 exact prompts、完整 schema SHA、图片字节/顺序/角色、raw、解析失败、tokens/结束原因和实际 generate start/end。stage record 不等于 model call：加载/grammar 失败可能从未调用 generate；合法 JSON 错 ID 仍属 E。两臂完整 Observation 先经原冻结 schema（含对象/身份一致性）验证，之后才交纯计数评分投影。

全部运行由 isolated Python 从 snapshot 导入；任何 app/evaluation 导入前设置 `KITGUARD_DATA_DIR` 到独立 runtime-app-data，源快照不允许新增 SQLite。完整源/模型/输入、选择/真值/日程/正常回归绑定在冻结时和运行前后重验。所有输出新建，不能覆盖、续跑或补齐重试。

## 评分与报告

原 [score_loco_combined.py](../../scripts/v08/score_loco_combined.py) SHA `939192…c94` 不改。其内嵌草稿 API `protocol_frozen:false` 保留；正式外层 analysis schema 绑定实际 freeze SHA，明确内层是函数历史元数据。每臂 C/W/U/E/N=24、四组各 6；C 表示正确可执行观察，不等于 ready。12 合法真值匹配 BOM；另 12 匹配订单 N/A 但观察计分完整。标准 2/2/2/0 订单的正确差量报告全 24。

主 all_four 255 合法 BOM/图=6120 次相关回放、6108 错配；次 source_supported 63/图=1512、1500 错配。分别列任何 false-ready 的图片数/24、E/N 未测风险，次面板不能代替主面板。恒正常与全拒答是无模型分析对照，分别 0C/24W 和 24U；不计入模型次数。双臂保留全部配对转换、逐组及每例明细，不掩盖 C 损失/W 新增。无自动晋升；发布解释前必须另做独立 raw/输入/评分完整性审计。

原 51 中完整 16 LOCO 正常图，G 绑定原 v0.7 manifest/predictions/audit；I 仅纳入时绑定本轮完成的 51/predictions/audit。各 16 source IDs/SHA 必须逐项相同。全部 16 保存，而不只取 14 个旧 C；正常面板是已曝光、历史、非同期，不重跑、不与新 24 合成分数或样本数。

## 根后续命令（当前未执行）

```sh
.venv/bin/python scripts/v08/run_loco_combined.py preflight --selection <根实际审批JSON> --output test-results/v0.8-loco-combined-preflight-v1.json
.venv/bin/python scripts/v08/run_loco_combined.py freeze --preflight test-results/v0.8-loco-combined-preflight-v1.json --output docs/v0.8/loco_combined_freeze_v1
.venv/bin/python scripts/v08/run_loco_combined.py run --freeze docs/v0.8/loco_combined_freeze_v1/freeze.json --output evaluation-runs/v0.8/loco_combined_v1
```

本轮只做合成 CPU 合同及源码审查；不依赖新图片，不调用真实模型，不写根最终方法选择。结果名称应为“来源未登记曝光的同域作者组合数量标签推导验证”，不能写成作者原生计数真值、独立实物试验、真实现场效益或零错误放行保证。
