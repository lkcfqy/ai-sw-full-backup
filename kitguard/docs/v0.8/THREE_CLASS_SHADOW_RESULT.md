# 三类影子否决未通过：挡住 3 个旧错误，却损失 16 个旧正确结果

2026-10-02。**拒绝本候选进入下一阶段或生产默认；生产保持 v0.7。** 完整 51 图由 root 一次运行完成，训练选模和融合结果均通过独立审计。审计通过证明证据和计算一致，不代表候选通过开发门槛。原实验、冻结源码、原标签及 v0.7 交付均保留。

## 完整分母与裁决

| 方法 / 分组 | C 正确可执行 | W 错误可执行 | U 拒答或不确定 | E 失败 | N 未尝试 | all_four any-false-ready |
|---|---:|---:|---:|---:|---:|---:|
| 旧 G，51 | 41 | 3 | 7 | 0 | 0 | 3/51 |
| 三类影子覆盖层，51 | 25 | 0 | 26 | 0 | 0 | 0/51 |
| 其中 Screws，35 | 25 | 0 | 10 | 0 | 0 | 0/35 |
| 其中 LOCO，16 | 0 | 0 | 16 | 0 | 0 | 0/16 |

转换为 C→C 25、C→U 16、W→U 3、U→U 7。原 3 个 W 全被拒答，但原 41 个 C 只保留 25 个；损失的 16 个包含全部 14 个旧正确 LOCO 和 Screws 233、128。因此“C≥41”“保留 LOCO 原14C”失败，**开发继续门槛为 false**。source_supported 窄面板也为 0/51，不能替代 all_four 主面板。

零 false-ready 是本固定订单面板上拒答后的结果，不是全 51 张识别正确、零物理风险或数量纠正；本候选仅有 25 张正确可执行，另 26 张非可执行。检测数不是真实数量下界。旧 51 图已用于发现问题和开发，不能重新称新留出。

## 原始输出说明了什么

所有 51 张均恰好一次 CPU detector 调用，51 started / 51 completed，没有失败、遗漏或重试。验证选择固定 epoch 7、阈值 0.5；保留检测器固定 score floor/NMS/max100 边界后的 643 个原始返回框，其中 251 个达到阈值。跨类 IoU≥0.5 共 313 对，其中 2 对双方都达到阈值；均未按 GT 删框。21 张触发，只有 nut/washer 被置 unknown；原 G payload、点证据、action、bolt/bracket 及历史计时不改。

- **原 3 个 W（120、024、172）**：均有 detector nut=1 > G nut=0，触发两类 unknown。这是 W→U，不是把它们改对；024 的 detector 还给出 bolt=2，而原冻结数量为 1，规则并不替换 bolt。type_007→nut 仍受[教学语义投影的边界](SCREWS_CATEGORY_SEMANTICS_REVIEW.md)约束，没有事后改标签。
- **LOCO 16 张**：均仅由 nut 超量触发，G 的 nut 已知数均为 2，detector nut 为 5–9（5个×3图、6个×3图、7个×1图、8个×4图、9个×5图）；washer 候选数全部为 0。它们相对作者正常组合 nut=2、washer=2 明显不一致。LOCO 没有实例框真值，不能仅凭数量断言所有多余 nut 框都是 washer 错分，或都是重复框。
- **额外损失的 Screws 233、128**：detector 的 bolt/nut 候选数与 G 一致，但各增加 1 个 washer 候选，高于 G washer=0，因此旧 C→U。这里“多报”是相对预定作者类型投影，不能扩写成物理真值已获得额外认证。

## 检测器数量与定位分开看

以下由保存的逐图 detector 指标汇总，范围为作者标注目标集合；不是生产四类 Observation，也不是 COCO mAP。融合独立审计重点复算原始框筛选、计数、触发与风险；这些定位汇总不应被描述为新增现场标注认证。

| 数据范围 | 三类数量完全一致 | MAE：bolt / nut / washer | 实例框可用性 |
|---|---:|---|---|
| Screws 35 个既定安全裁剪 | 22/35 | 0.429 / 0 / 0.057 | 原作者定向框→AABB→冻结裁剪平移→实际 G 输入尺寸，IoU≥0.5匹配 |
| LOCO 16 个正常组合 | 0/16 | 0.313 / 5.313 / 2.000 | 无实例框，定位指标未测 |

Screws 的 bolt TP/FP/FN=54/18/3，nut=29/0/0，washer=0/2/0。Screws 没有作者投影下的 washer 阳性；该组 nut 数量/框匹配良好不能证明 washer 身份问题已解决，更不能覆盖 LOCO 混放失败。FOD 训练仍仅为 `author_annotated_target_only`，未标注目标及低分辨率限制继续保留。

## 和旧二类否决器的差异

旧方案用已训练二类模型，要求原 G 的 washer 点落入 detector nut 框；本方案从原始 COCO 初始化训练三类模型，使用完整 G `call-01` 实际输入，并比较独立整图候选数量，不读取 VLM 点来选择框或 ROI。旧二类方案使用较大的 `normalized_input`，本次严格使用实际模型输入。训练数据、模型、输入尺寸链和触发规则一起变化；这不是只增加 washer 类的受控消融，不能把成绩变化全部归因于新增 washer。

## 耗时与证据

CPU 实测 2026-10-02 09:09:47–09:09:53 KST；模型加载 0.145 s。每图 detector P50/P90 为 0.089691/0.097503 s，case wall 为 0.101061/0.116151 s。case wall 包含输入绑定、解码、张量、推理、融合及保存前计算；不含旧 G 重新推理，也不是端到端产品延迟。本轮没有重新运行 G。

- [实际 run](../../evaluation-runs/v0.8/three_class_shadow_v1/run.json)、[全部原始返回与覆盖层](../../evaluation-runs/v0.8/three_class_shadow_v1/predictions.jsonl)、[全量分析](../../evaluation-runs/v0.8/three_class_shadow_v1/analysis.json)、[推理前冻结](three_class_shadow_freeze_v1/freeze.json)。
- [训练独立审计](../../test-results/v0.8-grouped-detector-independent-audit-v1.json)：12轮、960个验证观察、8,640个阈值×案例复算，固定epoch/阈值选择通过。
- [融合独立审计](../../test-results/v0.8-three-class-shadow-independent-audit-v1.json)：51个原始输出、输入像素/原G/冻结/训练审计绑定及完整融合计数通过；没有调用新模型。SHA-256：`7c4beca063064c1819df124abd9a67401d5d470d49cd010fd8fa8ac2a48219d9`。
- 所有实际文件 SHA-256、失败门槛和逐例 LOCO 触发计数见[机器可读裁决](DECISION.json)。不修改本次权重、阈值、原始记录或生产默认；后续新假设必须另立版本。
