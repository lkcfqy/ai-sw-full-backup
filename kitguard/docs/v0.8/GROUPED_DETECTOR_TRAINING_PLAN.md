# 三类影子检测器：固定训练与验证协议

状态：入口与 33 项轻量合同测试已完成，独立只读审查未见阻断项，未训练；须通过根任务的 FOD 六图目检凭证和完整 preflight 后才启动。此前 v0.7 和 v0.8 二类否决器的来源、结果和生产默认不变。

## 数据与边界

- Screws 沿用 `public_detector_v1` 原始 SHA 固定的 214 张训练和 44 张验证，并保留 104 个原图排除。源图分组不是独立物理件认证。入口不读原 `test.json`。
- FOD-A 采用新准备器的 400 张训练（8 来源组、每组 50 张）、36 张验证（3 来源组、每组 12 张）。GOPR 合并段、同类 DJI 合组、同类未知来源保守合组；仍无法证明独立物理件或采集会话。
- `held_back.json`、保留图像不被训练入口读取，不用于阈值、选轮或训练；准备阶段对全部候选解码仅做完整性和像素去重，与人工/渲染曝光分开记录。
- FOD 监督范围仅 `author_annotated_target_only`。六张预览不是全 400 图标注完整性认证；允许按作者框训练部分可见、小而模糊的目标，不更改作者类别，不排除困难样本。
- Screws 的 washer 标注数为零仅表示原作者类型投影中没有 washer 阳性；不是实地不存在 washer 的证明。bracket 始终不支持，没有 bracket=0 输出。
- FOD 单目标、低分辨率、类别与背景/颜色的共变不能证明混合 BOM 计数。模型预训练曝光未知。只计算训练/验证指标，不作生产晋升。

## 固定实现

入口：`scripts/v08/train_grouped_detector.py`。使用 Torchvision Faster R-CNN MobileNetV3 320 FPN，四输出为 background/bolt/nut/washer。从现有本地原始 COCO 权重（SHA `907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5`）严格加载，随后重新初始化四类头。**不从已训练二类 v1 权重继续训练**。使用固定的原 v1 架构可训练参数名单作训练范围，不导入或 monkeypatch 旧训练器/指标代码，不联网下载。

固定 12 轮、seed 20261002、MPS FP32、batch 2、min640/max960、SGD lr .005/momentum .9/weight decay .0005、第 8 轮后 StepLR×.1、前 100 步线性 warmup .01→1、梯度范数限 10、线程 6、训练随机水平/垂直翻转各 .5。614 张训练图统一 shuffle；不做验证后增删轮数、重新训练或选不同随机种子。MPS 固定种子不保证逐位可复现。

检测输出边界固定为 score floor .05、NMS .5、每图最多 100 框；保存此边界后的所有原始返回框，不声称是未经后处理的网络 logits。

## 预声明选模规则

每轮完整验证 80 图；对全类共用阈值 .1/.2/…/.9 逐一评分，score 等于阈值保留。分类别、按得分降序的一对一匹配，IoU≥.5；同分保留原预测次序，同 IoU 选原 GT 次序。保存每类 TP/FP/FN、误框/漏框索引、每图计数真值/预测/有符号误差、每类 MAE、准确计数率和框 F1。

排名按以下优先级，不使用训练集成绩或保留集：

1. 最大化 `0.5 × Screws 44 图准确计数率 + 0.5 × FOD 3 个验证来源组准确计数率的均值`。
2. 同分最小化同样双来源均衡的三类平均绝对计数误差（每图三类 MAE，FOD 先组内平均再组间平均）。
3. 同分最大化全部验证实例的分类别框 F1。
4. 跨轮同分保留较早轮；同一轮的阈值同分选择较高阈值。

准确计数与定位分开：计数相同但框错位仍有 FP/FN。任何验证调用失败仍保留该行/错误并继续收集全 80 图；该轮不能选择阈值，训练最终标记失败，不用缩小分母掩盖执行错误。

## 审查与留证

`manual_review.json` 必须绑定 train/validation/六图预览 SHA，并明确 `approved_for_local_training`、`author_annotated_target_only`、`held_back_human_or_rendered=false`、`all_frame_completeness_certified=false`。无凭证、SHA 不符、源组重叠、数据变化均拒绝。

preflight 仅标准库：核验允许的元数据与 694 张图文件 SHA，不加载 Torch、不解码图像。训练启动前保存自身/准备器源码、允许的 JSON 元数据快照、所有数据/源码/原始 COCO SHA、实际 Torch/Torchvision/Pillow 版本与关键 Python/二进制依赖 SHA。每轮核验绑定；训练后再次核验依赖。训练留存逐步损失、逐轮全部验证原始输出及完整九阈值报告、选模历史；best.pt/last.pt 含模型、优化器、scheduler 和 Python/Torch/MPS/DataLoader RNG，历史保留每轮 last checkpoint SHA（旧 last 文件被下一轮替换，不宣称保留了每轮模型文件）。

未取得训练结果前不宣称改进。即使验证提升，也必须在**已曝光**旧 51 图做完整开发回归，检查 LOCO 的真 washer 是否仍被错误阻断及三例 type_007 误认是否修复；另行固定输入、融合规则和计时，不能把既有 51 图称作新留出。新域 MANTA 的单件身份诊断不替代混合 BOM 评测。

## 实现验收（训练前）

33 项纯合同测试通过，Ruff 通过；记录为 `test-results/v0.8-grouped-detector-contracts-v2.log` 和同名 JUnit XML。本地原始 COCO 仅在 CPU 初始化严格加载，确认四输出、70 个预声明可训练参数；无图像加载、forward 或优化器步骤，记录 `test-results/v0.8-grouped-detector-initialization-v2.json`。真实全数据 preflight 仍须 root 写入实际目检凭证后执行。初始化凭证中的 plan SHA 对应补本段之前的计划正文；最终训练会重新绑定当前完整文档 SHA。
