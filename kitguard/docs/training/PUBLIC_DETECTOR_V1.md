# 公开数据两类检测器实验

2026-09-30：用户明确指示“用网上数据训练”，恢复此项独立实验。此记录不改变2026-09-29的历史暂停事实，也不改变实际开发始于2026-09-26的记录。学校GPU账号已申请，实际型号和配额尚未确认。

## “首轮训练”的含义与历史记录

本文件的“首轮”指**项目现有记录中的第一次监督微调实验，即通过反向传播和optimizer更新模型权重**。本次在COCO预训练检测器上微调bolt/nut；一共12个epoch属于同一次训练运行。此前已经做过多轮模型选型、提示词/观察流程改进、检测器推理诊断和冻结评测，它们有独立记录，未更新模型权重。

| 历史阶段 | 实际做过的工作 | 原始记录 |
|---|---|---|
| 早期8B与27B选型 | 本地预训练模型推理、观察方式比较；开发日志明确记载没有训练或微调 | [开发日志](../DEVELOPMENT_LOG.md)、[9月26—27日来源披露](../AI_AND_SOURCE_DISCLOSURE.md) |
| v0.2 | Qwen 27B空间清单观察与直接计数对照，同一48张留出分别46/48、34/48完整计数正确 | [v0.2评估](../FINAL_EVALUATION.md) |
| v0.3观察流程 | 原图、旋转和局部身份复核；64张留出59张正确明确、5张需补拍 | [v0.3评估](../v0.3/FINAL_EVALUATION.md) |
| v0.3检测器探索 | OWLv2、Grounding DINO使用公开权重做28张开发图CPU推理诊断，未训练；保留失败结果 | [OWLv2记录](../v0.3/OWL_DEVELOPMENT_REPORT.md)、[Grounding DINO记录](../v0.3/GROUNDING_DINO_DEVELOPMENT_REPORT.md) |
| v0.4 / v0.5 | 新域角码诊断、现场记录工具与选区管线联调；沿用冻结的视觉方法 | [v0.4评估](../v0.4/FINAL_EVALUATION.md)、[v0.5真实模型联调](../v0.5/REAL_MODEL_INTEGRATION_RESULT.md) |
| 2026-09-30 本次 | Faster R-CNN检测器首次监督微调，12个epoch；更新权重并保存模型/optimizer/scheduler | [训练日志](../../training-runs/public_detector_v1_mps_20260930/history.jsonl)、[完成摘要](../../training-runs/public_detector_v1_mps_20260930/training_summary.json) |

此前推理/评测产物在`evaluation-runs/`，本次训练产物在`training-runs/`。历史报告中的“首轮观察”通常指一次多阶段推理的第一阶段，也不是训练轮次。历史来源披露的“没有训练或微调”适用于其记载的9月26—27日阶段，本次新实验单独记录，不回改历史事实。各阶段的数据、类别范围和评分不同，表中成绩不能直接排名或相减当作提升。

## 范围与来源

先微调螺栓/螺母检测器，不接入v0.5线上判断，不修改原有64图成绩。`bolt`采用项目既有广义螺纹紧固件映射，包含木螺钉；不表示精确SKU识别。垫圈、角码未覆盖，不能把未预测解释为数量零。

- [MVTec Screws作者页面](https://www.mvtec.com/research-teaching/datasets/mvtec-screws)：MVTec Software GmbH，CC BY-NC-SA 4.0；保留署名和许可，当前用途为本地非商业研究实验。许可不自动确认赛事资格或商业使用权。
- [已下载镜像来源](https://deeplearning.neuromatch.io/projects/ComputerVision/screws.html)：原始文件、下载哈希和许可证记录保留在`datasets/manifests/mvtec_screws/manifest.json`。
- 原始包384图、4427条标注；作者说明写4426，固定JSON实际条数为4427，以原始数据为准并保留差异。
- 模型：[Torchvision Faster R-CNN MobileNet V3 Large 320 FPN](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn.html)，从COCO预训练权重换成背景/bolt/nut分类头。该构造器的分辨率在此实验显式改为短边640、长边上限960。

## 数据协议

保留作者train/val/test归属，排除104张曾用于历史holdout或被指定为holdout候选的原图。一个原图的全部裁剪和增强视为同一来源，不能进入不同集合。准备器检查原始哈希、标注关系、文件重复及解码像素重复，记录排除依据和逐框裁边。

| 集合 | 原图 | 标注框 | bolt | nut |
|---|---:|---:|---:|---:|
| 训练 | 214 | 2597 | 1820 | 777 |
| 验证 | 44 | 543 | 387 | 156 |
| 测试 | 22 | 315 | 222 | 93 |

作者框为`[row_center, col_center, width, height, phi_radians]`，不能直接当COCO xywh。准备器转为轴对齐包围框并裁到图片边界；原始旋转框和转换记录可追溯。官方split中的ID会重置，因此使用文件名连接全量标注。

实际检查发现126个角度超出作者README声明的`(-π,π]`范围。转换保留原始有限弧度，利用sin/cos周期性处理；不修改作者标签。训练/验证/测试分别33/9/6个轴对齐框超边界，均逐框clip并保留记录，未丢弃标注。全部384张原图的文件SHA、图像尺寸和解码RGB去重通过。

这些数据来自相同采集域、同批零件与背景。精确像素去重不等于近重复场景检测；22张测试图也不能代表真实现场。LOCO计数标签和InO不完整类别标签不混进此次两类监督训练。

## 固定首轮训练方案

- 本机MPS，FP32，batch 2，12个epoch，随机种子20260930，训练集水平/垂直翻转各0.5概率。
- SGD lr 0.005、momentum 0.9、weight decay 0.0005；前100步warmup，第8轮后学习率乘0.1。
- 每轮只在44张验证集上，遍历0.1至0.9阈值。先选两类计数同时完全正确率，再选类别计数MAE，再选同类IoU≥0.5框匹配F1。
- 最佳checkpoint固定后，才执行22张测试图评估。简化precision/recall/F1不称COCO mAP。计数完全正确与定位正确分别报告。
- checkpoint保存模型、optimizer、scheduler、随机状态、数据/源码哈希和配置。新输出目录拒绝覆盖；原始图片、历史交付保持不变。

## 运行

在`kitguard`目录中执行：

```bash
.venv/bin/python scripts/prepare_public_detector_data.py
.venv/bin/python -u scripts/train_public_detector.py train --device mps --output training-runs/public_detector_v1_mps_20260930
.venv/bin/python -u scripts/train_public_detector.py evaluate --device mps --checkpoint training-runs/public_detector_v1_mps_20260930/best.pt --output training-runs/public_detector_v1_mps_20260930/test
```

学校GPU环境需要独立安装与其驱动匹配的CUDA版PyTorch/Torchvision，不能复制Mac虚拟环境。复制相同原图、derived manifest、脚本和checkpoint后，以新输出目录恢复：

```bash
python scripts/train_public_detector.py train --device cuda --resume training-runs/public_detector_v1_mps_20260930/last.pt --epochs 24 --output training-runs/public_detector_v1_cuda_resume
```

恢复需保持图片哈希、分割、batch和主要训练参数一致；如要更改分辨率或重新调参，应建立新实验并记录，而非伪装为同一运行。首次测试曝光之后的调优不能再把同一测试集称为全新留出。

单张新照片预测入口使用验证集已经选定的阈值，自动处理EXIF方向并输出原图坐标下的框、置信度、图片与权重哈希。`washer`和`bracket`为`null`，`decision`也为`null`，不生成工单放行结论：

```bash
.venv/bin/python scripts/predict_public_detector.py --checkpoint training-runs/public_detector_v1_mps_20260930/best.pt --image /absolute/path/to/photo.jpg --output /absolute/path/to/new-result.json --device mps
```

## 执行结果

首轮已完成。本机MPS实际运行12个epoch，共1284个batch、2568次训练图片呈现，用时313.33秒（约5分13秒，不含此前下载与数据准备）。验证集选中第10轮，冻结分数阈值0.5；没有因测试结果调整轮次或阈值。

| 指标 | 验证集（用于选模型/阈值） | 测试集（选模后一次评估） |
|---|---:|---:|
| 图片数 | 44 | 22 |
| 两类数量同时完全正确 | 38/44（86.4%） | **16/22（72.7%）** |
| 框级TP / FP / FN | 527 / 7 / 16 | 302 / 3 / 13 |
| 框级precision | 98.7% | 99.0% |
| 框级recall | 97.1% | 95.9% |
| bolt每图计数MAE | 0.182 | 0.318 |
| nut每图计数MAE | 0.114 | 0.136 |

框级正确指同类别、IoU≥0.5、一对一匹配，不是COCO mAP。99.0%的precision不能当成整图计数准确率。6张计数错误图片均有少计，说明漏检是当前主要问题；存在定位/分类不匹配预测框，并不因整图数量相等而成为正确框。

测试集MPS单图推理中位数25.28毫秒，计时包含tensor设备传输、模型预处理/推理/后处理及结果回CPU，不含读图和完整工作台流程；不能与原27B四类、多次观察工作流的耗时直接比较。此实验没有测试垫圈/角码、订单判断、现场照片或真人作业收益，也未证明比v0.5完整方案更好。

已完成保存权重后重新加载与单张训练照片的命令行预测联调；该照片用于验证接口，不作为新准确率样本。另恢复第12轮模型、optimizer动量与scheduler，在一张训练图上执行一次可丢弃的真实反向更新，验证保存的checkpoint未变。CUDA续训仍须学校账号可用后实测。

新增数据准备26项、指标33项、训练恢复15项、单张预测处理17项测试，共**91项测试通过**，相关脚本与测试的Ruff检查通过。未重跑或改写历史v0.5成绩。

产物均位于`training-runs/public_detector_v1_mps_20260930/`：

- [冻结训练协议与版本记录](../../training-runs/public_detector_v1_mps_20260930/protocol.json)
- [每轮真实训练/验证记录](../../training-runs/public_detector_v1_mps_20260930/history.jsonl)
- [训练结束摘要](../../training-runs/public_detector_v1_mps_20260930/training_summary.json)：其中`test_evaluated=false`描述训练结束时的状态；后续测试记录在下方文件。
- [最终测试指标](../../training-runs/public_detector_v1_mps_20260930/test/metrics.json)及[逐图计数错误清单](../../training-runs/public_detector_v1_mps_20260930/test/count_errors.json)
- [最佳模型best.pt](../../training-runs/public_detector_v1_mps_20260930/best.pt)：第10轮，SHA256 `2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c`。
- [末轮续训断点last.pt](../../training-runs/public_detector_v1_mps_20260930/last.pt)：第12轮，保留optimizer与scheduler。
- [实际断点恢复检查](../../training-runs/public_detector_v1_mps_20260930/resume_smoke.json)及可重现的`verify_resume.py`
- [单张照片接口联调](../../training-runs/public_detector_v1_mps_20260930/single_photo_training_image_smoke.json)：训练来源`screws_002.png`，不是现场或留出样本。
- [数据质量与104源排除依据](../../datasets/derived/public_detector_v1/manifest.json)

下一轮优先扩大有逐件标注的数据、改善漏检并评估更高分辨率，再补垫圈/角码覆盖。当前22张测试图片已曝光；之后如据此改模型，必须记录其开发用途并另设新留出/现场验证，不能继续称其为全新测试。生产应用接入应等到完整类别和计数可靠性验证完成。
