# v0.8 异构检测否决：已曝光 51 图开发诊断

版本：2026-10-02；状态：推理前约定。v0.7 交付、冻结来源和默认 `spatial_guarded` 均不变。本轮不训练、不重新调用 VLM、不自动晋升；只测试一个保守叠加规则能否把部分已知错误转为不确定，以及会误拒多少真实 washer。

## 1. 问题和可主张范围

v0.7 的完整 51 图中，G 为 C41 / W3 / U7 / E0 / N0；三次明确错误均把作者标注为 type_007、按预先冻结类别投影计为 nut 的对象认作 washer，原向、旋转与同模型身份检查同时错。原作者标注是 type_ID，不是直接标注 nut。相关模型重复判断不能证明独立正确性。本轮使用现有两类 Faster R-CNN 提供**冲突否决证据**，不是对 washer 的独立确认，也不是 YOLO。

全部 51 图已曝光，方法选择受到这些错误启发，故结果只属于开发诊断。继承清单中的历史 `split: holdout` 字符串只保存来源，不代表 v0.8 留出。不能挑三张错误图报告、不能将旧 51 再称新留出、不能将合成订单数当独立照片数。Screws 已无可认证未曝光的剩余原始来源；下一次一般化验证须另冻新来源，按物理零件、场景和拍摄会话分组，并含独立 nut 与真实 washer 阳性。

## 2. 来源曝光审计与固定资产

独立只读审计入口：`scripts/v08/audit_heterogeneous_veto.py exposure`；凭证：`docs/v0.8/heterogeneous_veto_exposure_v1.json`。其 schema 为 `kitguard.v08.heterogeneous-veto.exposure.v1`。

| 核查项 | 冻结事实 |
|---|---|
| v1 数据阶段 | train 214 / val 44 / test 22；四份数据 JSON 哈希与原训练 protocol 一致 |
| 51 图与上述阶段重叠 | 原始文件名、原始文件 SHA256、原始解码 RGB SHA256 三类匹配均为 0；裁剪视图不能替代原始来源族 |
| 模型 | Torchvision `fasterrcnn_mobilenet_v3_large_320_fpn`；仅 bolt/nut 头；原 min_size 640、max_size 960 |
| 权重 | `training-runs/public_detector_v1_mps_20260930/best.pt`，151571509 字节，epoch 10 |
| 权重 SHA256 | `2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c` |
| 固定阈值 | 原验证记录选定 0.5；比较为 `score >= 0.5`；不因本轮结果改阈值 |
| 输入 | v0.7 G 实际上传归一化 JPEG 原字节，不重新上传、不重裁剪、不用标注框选 ROI |
| 本轮设备 | CPU、4 线程；不预热、0 重试；51 个计划样本均记录一次尝试 |

没有已记录原始来源重叠，不等于统计或领域独立。两组数据仍来自既有公开域；同一实物/拍摄会话重复和基础模型预训练曝光无法认证。Faster R-CNN 的 COCO 预训练来源与 Qwen 的预训练曝光均不能据此排除。此模型未训练 washer/bracket，不能把其未检测到的类别当作不存在。

完整旧基线绑定：v0.7 manifest SHA `efe4633e873d45032101a26e035c23d267bafa6605d147d3d2f7fcb51b697643`；predictions SHA `9b525702cb2665274c37a7d7740c1d93c05562ab5fb5a17e171e31b75a6859ee`；freeze SHA `cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7`；独立完整审计 SHA `94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9`。runner 的 freeze 须绑定本计划、曝光凭证、config、执行脚本与 worker 源码快照、Python/torch/torchvision/Pillow 版本、上述旧资产及 51 个 case 的哈希。

## 3. 点坐标、输入图与资格

1. detector 读取每个 G 的 `normalized_inputs/{attempt:03d}-spatial_guarded.jpg` 原字节，先核对文件 SHA 与保存的 G `normalized_sha256`。同时绑定原始图、裁剪视图和清单来源哈希。
2. G 原向 VLM 图为 `cases/{attempt:03d}-spatial_guarded/call-01/image-01.png`。按冻结 `_prepare_image` 的 RGB、LANCZOS thumbnail(max_side=1536) 重建，并精确核对其尺寸、像素和编码文件哈希。LOCO detector 图为 1600×1100，而 VLM 图为 1536×1056：这是已绑定的缩放血缘，不是假设两者同像素。不得新增 EXIF 旋转、crop、padding；若血缘不符，报错而非猜坐标。
3. 只使用 `verification.passes[0]` 且 `transform=original` 的物体点；要求 objects 与原向 raw/parsed inventory、`object_evidence.coordinate_frame=normalized_original` 一致，原向 uncertain_parts 与 raw/parsed inventory 一致。最终 object_evidence 的 uncertain_parts 可能被 G 后续检查扩大，不能误当原向资格。不得用旋转图坐标、身份裁剪坐标、GT 框或检测器中心替代 VLM 点。
4. 原 schema 只有 `part`、`center`，没有对象级 certainty，不伪造 `clear` 标志。washer 资格由原向类级证据确定：`washer` 不在原向 uncertain_parts，原向 observed.washer 为非负整数且等于原向列出的 washer 点数量。其余 washer 点须明确记录为未具资格；不得用真值或最终是否错误选择点。原向具资格但 G 后续因旋转/身份成为 U 的记录仍可否决，仍为 U。
5. center 必须是两个有限数、均在 [0,1]。detector 图宽高为 W,H，固定映射 `px=x*(W-1), py=y*(H-1)`；图原点左上，bbox 为绝对 `xyxy`。闭区间 `x1 <= px <= x2 && y1 <= py <= y2` 视为命中，边界也命中。
6. 仅模型 label=2 / class_name=nut 且 score≥0.5 的合法框可触发。保存模型实际返回的全部 boxes/labels/scores（包括阈值以下），不宣称保存了 NMS 前全部 proposals。拒绝 NaN、无穷、越界或倒置框、类别映射冲突、损坏输入。多框同点/多点同框保留每个匹配对，但每张图仅算一次否决。

## 4. 固定融合与失败规则

融合函数的推理输入只包含旧 G 观察、资格合格的原向点、绑定的图尺寸和 detector 原始结果。BOM、ground_truth、case 错误标签和 GT 框不能流入模型/融合。真值只在完整推理结束后的评分中使用。

若存在至少一个合格 washer 点命中 nut 框：复制 G，仅将 `observed.nut` 与 `observed.washer` 设为 null，附加固定冲突说明。若原 action.kind=none，改为 recapture；原有 recapture/region/reference/manual 保留，原 issues 保留，不降低原谨慎程度。bolt/bracket、原 object_evidence、verification、identity_verification 均不改。绝不把 washer 改成 nut，绝不加减计数，不用 detector 弥补任何缺失数量。

这是**实验覆盖层**，不冒称已通过生产 Observation 的全套身份一致性校验：历史 G 证据原样保留，detector 冲突另列，不伪造 `identity_verification.blocked_categories`。无否决时，除移除历史顶层 latency_ms 外，覆盖层与原 G 完全一致。原 G 另以 `base_observation` 完整保留。

任何 detector、输入血缘、输出解析或融合执行失败均保留原始错误、原结果（若有）和计时；覆盖层为空，类别 E。不能默默回退为 G 并记为成功。全程 0 重试；不能只重跑失败图再冒充首遍。完整 51 次尝试后才写 completed；未尝试记 N，未完成运行不能作为完整结论通过独立审计。

## 5. 全分母分析与预先解释

清单固定为 35 Screws + 16 LOCO 正常图，每图一次检测，无论有无 washer 点、旧 G 是否 U，均进入 51 全分母。LOCO 的作者真值全为 2/2/2/0；固定常量输出也能 16/16，因此不能据这 16 张证明异常识别优势。其价值之一是提供真实 washer 负控。

- 独立重算 C（四类数量完整、无 issue、action none 且全正确）、W（同样可执行但数量有错）、U（不确定/非可执行）、E（执行失败）、N（未尝试），报告全部 51 及两个来源组。
- 对旧 G 每图配对，完整列出 C→U、W→U、U→U、任何→E 等转换；不得把 W→U 称为纠正识别。保守融合不能产生 U→C 或 W→C；出现即视为实现矛盾。
- 真实 washer 误拒同时报告：LOCO 16 张计划图中否决数、旧 G 正确可执行的 14 张中 C→U 数；原 U 为 2 张，不偷换分母。图与点匹配统计分开，32 个 washer 不能当 32 个独立场景。
- 规则 false-ready 沿用原非空 0..3 四类订单面板，剔除等于真值的订单；以有任一 false-ready 的图数/51 为主，并另列 source_supported 窄面板。旧 G all_four=3/51，窄面板=0/51；窄面板不能替代主风险。E/N 风险未测，不算已安全。
- 报告 detector CPU 调用、融合与 added_seconds 的 P50/P90/总和，逐项说明加载、解码和进程开销是否包含。旧 G 耗时仅字段 `baseline_guarded_reused_latency_ms`，`full_end_to_end_measured=false`；两者相加也不能称本轮端到端 MLX 实测或公平速度比较。

仅当完整性审计通过、W/E/N 均为 0、主面板 false-ready=0，且相对 G 没有损失任何 C（含 LOCO 14 个旧正确样本）时，才记“值得进入新来源验证”。若未满足，保留失败原因并不晋升；即使满足，也无生产自动晋升、零风险、自动放行或真实用户效率主张。固定方法不得根据本轮结果继续调阈值后仍用本轮作验证。

## 6. 执行与独立审计约定

runner 所有新输出只放 v0.8 新目录，先 freeze 再一次完整运行。本实现为进程内 CPU 调用，完整保存每图输入绑定、模型原始返回 labels/boxes/scores、模型/输入哈希、washer 点及资格、匹配对、覆盖前后观察、软件/设备元数据、计时和错误；不虚构子进程 stdout/stderr。先保存全量原始结果，再生成分析，不读取前缀成绩用于变更方案。

独立脚本不导入 runner 的融合/评分代码，不加载 torch 或 MLX；从 frozen binding、完整 51 行与原始 detector JSON 重算几何、资格、否决、覆盖层、C/W/U/E/N、主/窄面板和配对变化。核对全部原始结果哈希与 lineage，不能只检查文件存在，也不能用 analysis.json 证明自己。若无法重建诊断，明确失败，不放宽到略过。独立凭证写新路径且不覆盖。

本轮尚未执行模型；最终 freeze 哈希及实际命令由 runner freeze 回执补记到新执行记录，不修改这份推理前计划。
