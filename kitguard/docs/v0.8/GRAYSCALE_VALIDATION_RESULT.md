# 固定三类检测器：旧验证集灰度诊断

**不采用统一灰度输入，不改变默认。** 固定 epoch 7 / score≥0.5 的三类检测器在原 80 张验证图上，三类计数完全正确从历史 RGB **53/80 降至 39/80**。本次是事后输入敏感性诊断；这些图已用于选模型/阈值，不是新留出，不证明训练颜色捷径的因果。

## 执行与独立审计

首轮 v1 在配置检查处停止：0 次 forward、80 条 setup 失败。原因仅是 checkpoint `config.classes` 使用整数键、JSON 协议使用字符串键。原 runner/文稿字节按原 SHA 封存，失败记录保持原样。只接受完整整数或字符串 1/2/3 键后规范化该字段；完整配置、selected、epoch、阈值、协议哈希比较仍保留。v2 使用新的计划和目录，没有覆盖 v1，也不将 v1 当模型质量结果。

v2 于 2026-10-02 10:34:01–10:34:07 KST 完成 80/80，setup_error=null，80 次调用全部完成，完整性通过。每图只在原 RGB 规范化之后增加 L→RGB 转换；尺寸、几何、原标签、权重、模型内部 transform、MPS、FP32、底阈 0.05、NMS 0.5、最多 100 框均不变。

独立审计不导入 runner、trainer、Torch、MLX 或生产 KitGuard：重建全部 80 张灰度像素和 CHW FP32 tensor SHA，核对 741 个完整返回框、原 RGB 基线、所有逐图/类别/来源组指标、一对一 IoU 混淆和正确性转移。源、模型、库文件、原计划与运行前源码快照 SHA 全部一致；运行目录前后哈希不变。审计通过，新增模型调用 0。6 项轻量合成合同通过，Ruff 通过。

## 全分母结果

“正确”仅指作者标注目标集合的三类计数完全匹配，不表示全图硬件完整性或混合 BOM 可执行状态。

| 来源/类别组 | 图数 | 历史 RGB 正确 | 灰度正确 | RGB FP/FN | 灰度 FP/FN |
|---|---:|---:|---:|---:|---:|
| 全部 | 80 | 53 | 39 | 27/36 | 12/58 |
| Screws | 44 | 36 | 20 | 8/18 | 6/41 |
| FOD 全部 | 36 | 17 | 19 | 19/18 | 6/17 |
| FOD GOPR0181 Bolt | 12 | 12 | 12 | 0/0 | 0/0 |
| FOD GOPR0183 Nut | 12 | 0 | 3 | 12/12 | 0/9 |
| FOD unprefixed_Washer | 12 | 5 | 4 | 7/6 | 6/8 |

全部框 F1 为 0.9452→0.9371，三类平均计数 MAE 为 0.2208→0.2667。18 张原正确变错，4 张原错变对。Screws 的 bolt FN 从 14 增至 38，是整体损失的重要组成；FOD 的小幅净改善不能抵消它。

| 全 80 的类别 | RGB TP/FP/FN | 灰度 TP/FP/FN |
|---|---:|---:|
| bolt | 385/8/14 | 361/5/38 |
| nut | 152/7/16 | 156/7/12 |
| washer | 6/12/6 | 4/0/8 |

按预定“分数降序、IoU≥0.5、一对一、不限制类别”的几何匹配，FOD Nut 被 washer 命中为 **12→0**。这不是 12 例都修复：仅 `foda:013025`、`foda:013081`、`foda:013208` 的 nut 正确检出，剩余 9 张是漏检。Washer 组仍有 6 个错误 nut 框，只有 4/12 计数正确。Screws 只有 `screws:131` 从错变对，却有 17 张原正确变错。完整 ID 与逐框匹配见审计凭证，不筛去失败子组。

## 判定和解释边界

结果支持“固定模型的输出对该灰度输入干预敏感”，与先前观察到的颜色/来源关联相容；它不能区分训练中的颜色捷径、推理分布偏移、亮度/纹理损失等原因。历史 RGB 没有同期重推，MPS 也不保证逐位确定，因此不是精确因果估计或速度对照。

FOD 单图通常一个作者目标，计数正确不能单独证明一般混合 BOM 能力；作者目标之外是否有漏标未获认证。来源组不是物理对象或采集会话的严格隔离。本诊断没有读取 held_back、LOCO24 或 MANTA，也未新训练或重新选择阈值。统一灰度不进入生产；任何训练增强或按类策略都需要另行预登记及独立新来源验证。

## 证据

- [独立全量审计](../../test-results/v0.8-grayscale-validation-independent-audit-v2.json)，SHA `ad3d10fa86a50b7050e94a6e0cd076d824d68049be4e5a75d09d743d29085f20`。
- [v2 运行](../../evaluation-runs/v0.8/grayscale_validation_v2/run.json)、[全原始返回](../../evaluation-runs/v0.8/grayscale_validation_v2/predictions.json)、[原分析](../../evaluation-runs/v0.8/grayscale_validation_v2/analysis.json)。
- [首轮配置失败独立凭证](../../test-results/v0.8-grayscale-validation-independent-failure-v1.json)、[原字节保留凭证](../../evaluation-runs/v0.8/grayscale_validation_v1/source_snapshot/preservation.json)。
- [协议](GRAYSCALE_VALIDATION_DIAGNOSTIC_PLAN.md)、[最终判定与 SHA 绑定](GRAYSCALE_VALIDATION_DECISION.json)。

保存 raw 和哈希证明的是本地记录一致性，不是不可篡改签名或对原模型输出真实性的外部证明。
