# 三类检测器整图影子否决协议 v1

2026-10-02。状态：**规则已由 root 确认，独立 runner 与合同测试已实现；尚无影子推理成绩。** 实际运行由 root 统一执行。候选仅用于旧 51 图完整开发回归，不改生产链、旧结果或 v0.7 交付。

## 先说明规则能证明什么

- 检测数是固定后处理、阈值下的**预测候选数**，会有误检、漏检和重复；不是“真实数量下界”。此前 [设计评审](NEXT_PERCEPTION_DESIGN_REVIEW.md) 的该措辞不适用于本协议。
- `detector_count > G_count` 是模型间冲突触发器，不是真值裁决。计数相等仍可能身份错换；检测数更少也可能漏检。本轮不追加低计数否决、置信度例外或按案例选择策略。
- 同类 NMS 不能消除跨类重复：一个对象可能同时产生 nut、washer 框。保留并披露这种冲突，不能事后按作者标签删除其中一个来改善回归成绩。
- FOD 的监督/计量范围是 `author_annotated_target_only`，不等于整图全部可见物体已完整标注；未标注目标可能被训练当成背景。Screws 的 type_ID→nut 使用预定教学语义投影，[语义审查](SCREWS_CATEGORY_SEMANTICS_REVIEW.md)中的不确定性继续适用。异构模型不是独立物理真值。

## 两次冻结与固定输入

1. **训练前冻结规则**：本协议、[三类训练计划](GROUPED_DETECTOR_TRAINING_PLAN.md)、训练源码/参数与数据分组。训练为 Screws 214/FOD 400；验证为 Screws 44/FOD 36。FOD held-back 不读、不用于选模。照片许可范围仍未细化，不分发图片或宣称商业授权。
2. **回归前冻结产物**：成功完成固定 12 轮后，绑定 `best.pt`、训练协议、全部验证选择证据、代码/依赖、实际设备和阈值的 SHA。阈值只读取所选 checkpoint，不能 CLI 覆盖。验证规则固定为共用阈值 0.1…0.9，双来源均衡准确计数率→低 MAE→pooled 框 F1；同轮同分高阈值，跨轮同分较早 epoch。看旧 51 成绩后不得重调；新假设另开版本，不能覆盖本次。
3. **准确含义**：51 个唯一 case，按旧完整 manifest 顺序，每个一次 detector 调用。每张使用旧 `spatial_guarded` 的 `call-01`、`transform=original`、`generation.json.images[0]` 所存的整幅实际输入，核对该图 SHA、原 G 观察和独立审计绑定。不是原始采集大图，也不是身份检查裁剪；35 个 Screws case 仍是原冻结安全裁剪，16 个为 LOCO 正常图。不使用旋转重复输入、VLM 点、检测前 ROI、BOM 数量或标签选择输入。
4. 若上述实际输入与 `normalized_inputs` 尺寸不同，以前者为准；检测器仅做冻结模型本身的 min640/max960 resize，再返回到该输入坐标。旧二类 veto 曾用 `normalized_input`，不能把二者的变化全部归因于新增 washer 类。绑定失败就停止/记失败，不能改用近似图片。

## 检测返回、重叠与融合规则

模型固定 `background/bolt/nut/washer`；bracket 不支持。沿训练模型的 score floor=0.05、同类 NMS IoU=0.5、max100；保存**该边界之后全部返回框、原始浮点分数、类别与原顺序**，包括低于所选阈值的框。不能称为全部网络 proposal/logit。模型架构、实际 NMS 实现/依赖和设备在回归冻结时绑定；不追加自定义同类 NMS。

跨类不做 NMS、不做最高分类别挑选，**全部保留**。逐图记录跨类两框 IoU≥0.5 的索引对，仅用于诊断，不改变计数/融合。相同框坐标的跨类预测也不能静默删除。保留重复可能导致过拒答，这是本候选必须承担的实测代价。

设 `D[c]` 为类别 c、score≥冻结阈值的候选数。设 `G[c]` 为最终已审计 G 观察中的非负整数数量；null/不确定类别不是“已知”，不能当作 0。按如下唯一规则执行：

```text
trigger = any(c in {nut, washer}
              where G[c] is a known nonnegative integer
              and D[c] > G[c])
if trigger:
    effective_counts[nut] = null
    effective_counts[washer] = null
else:
    effective_counts = original_G_counts
```

触发时记录触发类、两个模型原计数、对应保留框索引和固定冲突原因。**两类一起置 unknown**，不把 detector 数填入 G，不改变 bolt/bracket，不解除原有问题/拒答，不把 U/W 变 C。若原本 nut 或 washer 已 unknown，保持 unknown；仍可对另一已知类应用同一比较。

原 G payload、object evidence、原始 JSON 和计时原样保存；融合另存实验 overlay/effective observation，不把修改后的历史 payload 冒充模型原返回或生产 schema。评判使用与旧协议同一可执行性规则：原有 action/issues/unknown 均继续使其非可执行。检测/输出验证失败记 E，不默默回退为 G 成功；未尝试记 N。固定零重试，单例失败仍记录并继续其余 case，完整分母始终 51。

## 分开报告 detector 与融合

| 层面 | 预定输出与边界 |
|---|---|
| Detector 验证 | 完整 80 图按来源/类别/来源组报告作者标注目标计数、带符号误差、MAE、exact count、TP/FP/FN、precision/recall/F1。固定 IoU≥0.5、同类得分降序贪心一对一；同分原预测序，同 IoU 原 GT 序。不是 COCO mAP，也不是现场全物体计数。 |
| Detector 旧 51 | 独立三类计数先保存，再按原标签范围分析。Screws 35 的框由原作者旋转框→AABB、冻结 crop 平移和实际输入 resize 明确转换；只用 included annotation IDs，不用 VLM 点生成框真值。若转换绑定不能核验，框指标标未测，不能猜。其 washer=0 只表示预定投影无该阳性标签。LOCO 16 仅有正常 2/2/2 数量依据，没有实例框，不报告 LOCO IoU/AP/定位正确。 |
| 融合旧 51 | G 原 C41/W3/U7/E0 对照 overlay 全量 C/W/U/E/N；逐例转换矩阵、Screws35/LOCO16分层、原3W逐例是否被拒答、原41C损失。已知转unknown是拒答，不叫纠正数量。 |
| 规则风险 | all_four 主面板 any-false-ready 图数/51，复用旧每类0…3、排除全零及真实订单的完整枚举；另列 source_supported 窄面板，后者0不能替代主面板。E/N单列为风险未测，不能用它们制造“零风险”。 |
| LOCO代价 | 原14个C逐一是否保留、C→U/E数，以及原2个U变化；16张正常图均2/2/2，不能证明异常数量优势。 |
| 耗时 | 新 detector加载、每图解码/张量、推理、融合和完整case wall分开，记录P50/P90与分母。旧 G 历史延迟单列；未重跑 G，不能把相加值称为实测端到端延迟。 |

作者范围外预测继续保留；“FP”是相对给定标签集合，不能据此证明物理对象不存在。计数准确与定位正确分别报告。每图没有预测也留分母；不按对象尺寸、难度、GT 或融合成败删样。

## 开发继续门槛，不是生产晋升

全部条件同时满足才可讨论下一阶段：51/51完成且 E=N=0；原3个W全部变U；原14个LOCO C全保留；总C≥41、W=0、all_four any-false-ready=0；冻结/输入/原始返回/融合均经独立复算。

由于本规则只增加拒答且不能修正计数，C不可能超过原41；因此 `C≥41` 实际要求原41个C一个不丢。通过时预期只能是 C41/W0/U10/E0/N0，而不是“准确率提升到全对”。任一项失败就保存负结果，不更改阈值重跑寻找通过。

旧51已充分曝光，以上只是开发回归资格；不证明新来源泛化、独立实物识别、现场收益或工业安全。FOD来源组非独立实物，held-back仍保留；MANTA单物体身份诊断也不能替代新的多物体BOM验证。

入口为 `scripts/v08/probe_three_class_shadow.py`。`preflight`/`freeze` 不导入 Torch、不加载模型；先要求训练 completed12 且独立训练审计通过，再核验全部51输入和作者框链。`run` 只调用冻结脚本中的三类 CPU 模型，零重试。命令（在项目根目录执行；输出不得已存在）：

```sh
.venv/bin/python scripts/v08/probe_three_class_shadow.py preflight --training-run training-runs/v0.8/grouped_detector_v1 --output test-results/v0.8-three-class-shadow-preflight-v1.json
.venv/bin/python scripts/v08/probe_three_class_shadow.py freeze --training-run training-runs/v0.8/grouped_detector_v1 --output docs/v0.8/three_class_shadow_freeze_v1
.venv/bin/python docs/v0.8/three_class_shadow_freeze_v1/source_snapshot/probe_three_class_shadow.py run --freeze docs/v0.8/three_class_shadow_freeze_v1/freeze.json --output evaluation-runs/v0.8/three_class_shadow_v1
```
