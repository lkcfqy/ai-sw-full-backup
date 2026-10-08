# MANTA 身份组件 V1：完整训练与独立审计结果

2026-10-02。**固定第 10 轮在 256 条内部验证记录上得到 C256/W0/U0/E0/N0，独立审计首次通过。** 达到事前规定的组件继续研究门槛，生产默认不变；尚未证明旧 51 三错、银色混放、开放类别或混合 BOM 能力改善。

## 冻结范围与结果

沿用 [V1 协议](MANTA_CLASSIFIER_PROTOCOL_V1.md) 和 [准备结果](MANTA_CLASSIFIER_PREPARATION_RESULT.md)：作者 train/good 共选 1024 个 composite 记录，每类训练 384、验证 128；五视角绑定 record，仅第 0 面板灰度、固定 224 等比例补黑输入。32 个相邻编号代理组中 24 个用于训练、8 个用于验证。四个原开发记录均在训练侧；8 条 validation 记录曾按预声明方案做布局 QA，不能称图像盲测。

原 COCO MobileNetV3 骨干固定、只有 Linear(960,2) 头学习；MPS/FP32、固定 10 轮，无超参扫描、无重试或“最佳轮”挑选。最终选第 10 轮，门槛固定为保存 softmax 最大值 **≥.9**，低于门槛记 U；softmax 数值不等于校准正确概率。

| 最终方法/类别 | 分母 | C | W | U | E | N |
|---|---:|---:|---:|---:|---:|---:|
| 固定 ≥.9，nut | 128 | 128 | 0 | 0 | 0 | 0 |
| 固定 ≥.9，yellow_green_washer | 128 | 128 | 0 | 0 | 0 | 0 |
| 固定 ≥.9，合计 | 256 | 256 | 0 | 0 | 0 | 0 |
| 强制 argmax，合计 | 256 | 256 | 0 | 0 | 0 | 0 |
| 恒答 nut | 256 | 128 | 128 | 0 | 0 | 0 |
| 恒答 washer | 256 | 128 | 128 | 0 | 0 | 0 |

两类各 4 个验证组，8 组均为 32C/32；每类 group-macro 正确覆盖率及明确覆盖率均 100%。事前继续门槛为每类 group-macro 正确覆盖≥75%、W/E/N=0，本次通过。**这不是生产晋升门槛，也不是自动放行安全声明。**

完整训练 `run.json` 时间为 03:32:32.851420–03:33:01.435241 UTC（KST 12:32:32–12:33:01），该记录边界共 28.584 秒；不是系统端到端订单时延、吞吐量基准或真人耗时对照。原始每轮训练批次、完整验证 logits/probabilities、失败字段、模型/输入哈希和 checkpoint 均保留。

## 独立审计实际核对内容

训练前冻结审计器，只有终态 completed、10/10 和 selected_epoch=10 后才读取成绩。首次运行 exit 0、status passed；没有修正评分或重跑模型。

- 核对 71 个运行文件及完整目录清单、原训练 plan/根批准、准备冻结/数据/软件/源码哈希；每轮 768 条训练、256 条验证，全 10 轮及最终末轮引用一致。
- 不导入 trainer 的评分函数，独立重算 C/W/U/E/N、类混淆、8 个验证组、宏平均覆盖及恒定类别基线。保存概率与原 logits 的独立 softmax 一致性核验使用 2e-6 数值容差；`.9` 决策边界没有容差。
- CPU 读取原权重和完整 initial/final checkpoint：**262 个骨干状态 tensor 与原 COCO、初始、最终逐项一致**。head.weight 与 head.bias 均实际改变；最终头和 optimizer 与 epoch 10 一致。
- 从全部 1024 个已准备 PNG 独立重建归一化 tensor，SHA 全部相同。只做 CPU 反序列化及张量算术，没有构造模型、forward、额外训练或作者 test 图像读取。

该审计证明已保存数据/计算/权重链一致；不是历史物理执行的硬件证明，也没有重新测量记录的训练时钟。

## 结论仍受哪些限制

验证来自同一作者训练域，编号代理组不是可认证的实物或拍摄 session。原作者 test 尚未用于此分类实验，预训练曝光未知。布局 QA 已显示两类轮廓与亮度不同；尺寸元数据还显示左右补黑总宽中位数 nut 17 px、washer 2 px。形状、灰度亮度、背景、裁剪宽高比和补黑都可能成为线索；本次结果没有识别模型究竟使用哪种线索。

本任务只有两类单件身份，不能由“总数恒为一”声称计数能力，也不能提供 bolt/bracket/背景的开放类别拒绝保证。旧 Screws/LOCO 三个 G 明确错误仍是未解决记录；没有用新 LOCO24 选择参数或与其合并分母。

后续只允许继续做另立协议的开发诊断：检查独立候选区域、定位召回、跨来源类别迁移及完整旧 51 回归。不得将 VLM 点叫作独立定位，也不得以本次内部 100% 直接集成到生产。许可继续按作者 CC BY-NC-SA 非商业条件约束，保留 Figshare 元数据冲突与分发限制。

## 凭证

| 证据 | SHA-256 |
|---|---|
| [运行终态](../../training-runs/v0.8/manta_classifier_v1/run.json) | `2985d6152377b9031d7fd067c2974952c03c35a6d1018957a2e74ea74abfd1e9` |
| [第 10 轮原始最终预测](../../training-runs/v0.8/manta_classifier_v1/final_predictions.json) | `1e8b6dd9472959030bb95c380239fea0cb5c5c3e9b426010f37c6da0a00717db` |
| [原分析](../../training-runs/v0.8/manta_classifier_v1/analysis.json) | `c7487be2da3bd9b6fda46ae573f407c377e8e200791f06d8ffe8e9e9504cf7e6` |
| [独立审计](../../test-results/v0.8-manta-classifier-independent-audit-v1.json) | `b9df04653db0e0ded4b6db2e0165e74508cc2c02a20829f98f25a5f1a9c57afd` |
| [训练前审计器冻结](../../test-results/v0.8-manta-classifier-auditor-v1/freeze.json) | `366448c649a31733299c16a54a2c8e9bd4f13dd78e0f5155a7a4d20199e2a7da` |
| [完整最终 checkpoint](../../training-runs/v0.8/manta_classifier_v1/final.pt) | `ea29bfcf33dcf680e1b3ac2afa26de366991d029a42a3b5fe7ef7a5be1b3f985` |
| [只含最终头/optimizer 的 epoch10](../../training-runs/v0.8/manta_classifier_v1/epoch-10.pt) | `ff1179864316fbb9f76fad0fe52181c39cfa1bd9093e4ca5782c9609f193fa3f` |

独立判定与完整绑定见 [MANTA_CLASSIFIER_DECISION_V1.json](MANTA_CLASSIFIER_DECISION_V1.json)。没有自动启动后续评测或修改已冻结证据。
