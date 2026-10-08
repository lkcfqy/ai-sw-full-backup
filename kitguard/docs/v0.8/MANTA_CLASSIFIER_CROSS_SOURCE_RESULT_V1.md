# MANTA 身份组件：跨来源诊断结果 V1

2026-10-02。**完整 180 个 nut/washer 作者目标得到 12C/161W/7U/0E/0N；独立审计首次通过，但组件跨来源迁移明显失败，不集成、不晋升生产。** 另有 399 个作者 bolt 目标 AABB，其中 136 个被接收为 nut/washer；两种分母不合并。内部 256C 的记录保留，不能外推为通用身份能力。

## 已执行范围

沿用 [固定协议](MANTA_CLASSIFIER_CROSS_SOURCE_PROTOCOL_V1.md)：旧检测器完整 80 张 validation 图、全部 579 个作者 AABB，按原顺序一次执行，零重试、零训练。44 张 Screws 与 36 张 FOD 都是已曝光开发材料，不是新留出；同图多个框不等于独立实物。未读取 MANTA test、FOD held-back 或用新 LOCO24 选择参数。

只用固定 MANTA 第 10 轮 checkpoint，原输出类顺序为 `nut / yellow_green_washer`，后者仅在本诊断语义映射为 washer。作者 AABB floor/ceil/clamp、RGB→L→RGB、224 等比例补黑、原 ImageNet 标准化、MPS/FP32/eval、batch32、max softmax≥.9 全部固定。19 批实际 started/returned，全部 579 行 ok；模型状态未变、最终完整性通过。

## 180 身份目标：明确错误占多数

| 来源/目标 | 分母 | C | W | U | E | N |
|---|---:|---:|---:|---:|---:|---:|
| Screws 教学映射 nut | 156 | 0 | 153 | 3 | 0 | 0 |
| FOD GOPR0183 / Nut | 12 | 12 | 0 | 0 | 0 | 0 |
| FOD unprefixed_Washer / Washer | 12 | 0 | 8 | 4 | 0 | 0 |
| 合计 | **180** | **12** | **161** | **7** | **0** | **0** |

全部 153 个 nut→washer 明确误判来自 Screws；8 个 washer→nut 来自 FOD。nut 合计 12C/153W/3U（168 分母），washer 为 0C/8W/4U（12 分母）。总体正确覆盖 **6.67%**，明确错误 **89.44%**；两类等权正确覆盖 **3.57%**，三个非空来源×类别单元等权正确覆盖 **33.33%**。宏平均的分组定义不同，不能互换，也不能用 FOD Nut 的 12/12 掩盖其他两个来源单元。

Screws 原数字类型 7/9/10/11 按既有教学映射投影为 nut，不是作者直接英文命名。原标签与映射未按结果修改。FOD 的作者单目标标签只支持 `author_annotated_target_only`，不证明全图所有支持类均已标注。

| 固定解析对照 | 主身份分母 | C | W | U | E/N |
|---|---:|---:|---:|---:|---:|
| 当前 ≥.9 | 180 | 12 | 161 | 7 | 0/0 |
| 同次 logits 强制 argmax | 180 | 14 | 166 | 0 | 0/0 |
| 恒答 nut | 180 | 168 | 12 | 0 | 0/0 |
| 恒答 washer | 180 | 12 | 168 | 0 | 0/0 |
| 全拒答 | 180 | 0 | 0 | 180 | 0/0 |

恒答 nut 的 93.33% 是类别不平衡造成的解析基线，两种恒定类别的两类宏平均均 50%；不代表有感知能力。降低阈值并没有在本协议内被试用或选择，强制 argmax 只是事前固定的解析对照。softmax≥.9 显然不保证跨来源正确。

## 399 bolt 目标框：独立开放类别表

| 来源 | 分母 | 接收 nut | 接收 washer | U | E/N | 误接收 |
|---|---:|---:|---:|---:|---:|---:|
| Screws | 387 | 114 | 10 | 263 | 0/0 | 124/387（32.04%） |
| FOD GOPR0181 | 12 | 12 | 0 | 0 | 0/0 | 12/12（100%） |
| 合计 | **399** | **126** | **10** | **263** | **0/0** | **136/399（34.09%）** |

这些 accepted bolt 是开放类别误接收，不算入主 180 的 W。U 只是拒答，没有识别出 bolt；模型原本没有 bolt 类。强制 argmax 为 331 个接收 nut、68 个接收 washer，即 399/399；恒答任一身份也误接收全部 399。全拒答没有误接收，但主身份正确覆盖为零。

**这里不是干净单 bolt 图像准确率。** 推理前固定 27 条 QA 已发现 `roi-0002/0492/0515/0524` 等旋转框 AABB 含邻 nut/bolt 和背景。故指标只说明“作者 bolt 为目标的 AABB 被系统接收成支持身份”；不能把全部 136 次都归因于分类头认错纯 bolt。未排除这些框、重裁或利用结果挑样本。

## 小框与边界全部保留

tiny 按原连续 AABB 短边<16 定义，恰好 16 非 tiny；上采样不增加真实细节。

| 主身份切片 | 分母 | C/W/U/E/N |
|---|---:|---|
| tiny（均 FOD washer） | 4 | 0/3/1/0/0 |
| 非 tiny | 176 | 12/158/6/0/0 |
| author clipped=true（Screws nut） | 1 | 0/1/0/0/0 |
| author clipped=false | 155 | 0/152/3/0/0 |
| author clipped=unknown（FOD） | 24 | 12/8/4/0/0 |

bolt tiny 为 4 个接收 nut；非 tiny 为 122 接收 nut、10 接收 washer、263U。bolt clipped=true 的 8 个为 1 接收 nut/7U；false 的 379 个为 113/10/256；unknown 的 12 个全部接收 nut。FOD clipped 未提供，严格保留 unknown，不当作完整可见。完整二维/四维交叉、空格 N/A、混淆和宏平均保留在原 analysis 与独立审计中，不丢任何切片分母。

## 审计与时延的实际边界

独立审计器在推理前冻结；本次从冻结副本执行一次，exit 0，status passed，没有失败修复或重跑。审计核对完整 579 唯一顺序/80 图、metadata→preparation→raw 身份和输入 SHA、原 source/model/code/runtime/root 批准与布局凭证、原 raw.jsonl 与 predictions 完全一致；独立重算 .9/argmax、两主表、全部切片/空格/混淆/宏平均/解析基线，与原 analysis 一致。softmax 一致性容差 2e-6，不用于 .9 决策边界。

审计仅 stdlib 文件/哈希/数学计算：0 模型调用、0 图片解码。它没有重新 forward、重新测量时钟或从 tensor SHA 恢复 tensor；原张量记录与全部 579 输入字节绑定，root 另在推理前独立重裁 80 图→579 PNG 并逐字节核对一致。模型 unchanged 字段是原运行收据，审计没有加载权重重算 forward。

真实 run 为 KST **12:50:59–12:51:03**。记录 wall **3.534 秒**，同步模型/softmax阶段 **1.138 秒**，decode/tensor **0.564 秒**；按 19 批求和，不把同批耗时重复加 579 次。这是作者 ROI 组件的本机记录，不是完整系统、MLX 订单端到端时延或同期速度优势。

## 判定

完整性通过，迁移质量不支持集成。保留固定头与全部负结果；不换类别顺序、不事后改阈值/标签/裁区，不启动补救训练或重试。生产默认保持原 G 研究/数字辅助。没有本组件改善旧 51 三错、混合 BOM 或自动放行的证据。

内部 256 的 100% 与外部 180 的 6.67% 正确覆盖差异说明前者不能外推；本次不能因果确定是形状/亮度/背景/补黑、作者类别映射、视角还是邻件污染造成。跨来源作者框仍不是独立定位；后续若继续，须另定协议和独立候选框/定位召回证据。内部 256、迁移 180、bolt 399、旧 51、新 LOCO24 均不合并。许可继续按 MANTA 作者 CC BY-NC-SA 严格非商业约束，FOD 不推导商业或再分发许可。

完整文件哈希与机器判定见 [MANTA_CLASSIFIER_CROSS_SOURCE_DECISION_V1.json](MANTA_CLASSIFIER_CROSS_SOURCE_DECISION_V1.json)。关键原记录：[run](../../evaluation-runs/v0.8/manta_transfer_v1/run.json)、[raw](../../evaluation-runs/v0.8/manta_transfer_v1/raw.jsonl)、[analysis](../../evaluation-runs/v0.8/manta_transfer_v1/analysis.json)、[独立审计](../../test-results/v0.8-manta-transfer-independent-audit-v1.json)、[审计器事前冻结](../../test-results/v0.8-manta-transfer-auditor-v1/freeze.json)。均为本地研究证据，不是比赛提交或真人试验。
