# Grounding DINO Tiny 独立 CPU 开发诊断

2026-09-26。第二种开词汇检测器已按首跑前固定协议完成同一批 28 张开发图片。**本轮结果不支持将它加入当前工单放行链或用于自动修数。** 保留全部结果，不挑选单张成功框宣传，不修改主产品。

| 数据 | 整图四类计数完全正确 | bolt / nut / washer / bracket 分别正确 | CPU中位 / 最大 |
|---|---:|---|---|
| LOCO 开发16图 | 0/16 | 0/16、0/16、1/16、3/16 | 1.411 / 1.481 秒 |
| Screws 开发12图 | 1/12 | 2/12、6/12、6/12、3/12 | 1.315 / 1.338 秒 |

28/28推理成功，0运行错误。合计中位1.405秒、最大1.481秒；CPU单例流程时间包括输入读取、预处理、推理、输出保存和评分，不含一次性模型加载。没有运行MPS/CUDA。没有触发单图60秒暂停条件。

Screws定位以作者旋转框外接AABB，经裁剪平移及输入缩放，在同类IoU≥0.5进行一对一匹配：**9 TP、18 FP、27 FN，precision 33.33%、recall 25.00%**，覆盖12图/36作者实例。包含1个无法唯一映射类别的候选框作为FP；该框完整保留，没有强行改成期望类别。这是固定阈值定位诊断，不是COCO mAP或旋转IoU。LOCO无逐实例框真值，不报告定位指标。

## 固定规则与失败解释

- caption：`a metal screw or bolt. a metal nut. a metal washer. an L-shaped metal bracket.`，每图完全一致。无BOM、目标数量、Qwen观察或作者真值进入模型输入。
- 官方Transformers后处理 `threshold=0.4`、`text_threshold=0.3`，采用官方使用示例参数；同类greedy NMS IoU>0.50，不跨类强行抑制，不事后扫描阈值。
- 对原始解码短语做整词匹配：screw/bolt→bolt，nut→nut，washer→washer，bracket→bracket。只有恰好一个类别才映射；缺词/多类短语保存为unmapped。本轮共1个unmapped框。
- 整图计数正确要求四类数值均匹配且没有unmapped框；逐类数值匹配、绝对误差只针对已经映射的框。不能把未分类候选当作不存在。
- 唯一整图正确的是 `screws_119` 单螺母图。其余样本出现漏件、错类和大范围错误框；如LOCO首图有一个较高分的washer框覆盖大部分袋子区域。分数不是校准后的正确概率。
- 所有图片均无角码正例，Screws无垫圈正例。许多真值为0的类别正确不能证明该类识别能力。

## 模型及可复现文件

模型 `IDEA-Research/grounding-dino-tiny`，revision `a2bb814dd30d776dcf7e30523b00659f4f141c71`，Apache-2.0。

- 本地共享目录 `/Users/lkc/Downloads/AI-Models/grounding-dino-tiny`。原始safetensors为 **689,359,096 字节**；原配置/分词/模型卡等上游文件合计 **690,309,644 字节**。
- 权重SHA-256：`1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3`。上游LFS文件核对SHA-256，其他文件核对Git blob SHA-1，全部记录本地SHA-256和大小。
- 保留原README、配置、tokenizer、权重、`UPSTREAM_API_METADATA.json`、`DOWNLOAD_MANIFEST.json`。仓库没有独立LICENSE，另存规范Apache正文并明确来源。未下载重复pickle权重。
- 运行环境：Python3.12.14、torch2.14.0、Transformers5.17.0；float32、`torch.device("cpu")`、4计算线程、1 inter-op线程、`USE_HUB_KERNELS=0`。使用本地Transformers原生实现，没有另编译CUDA扩展。
- 首跑前协议 `docs/v0.3/GROUNDING_DINO_DEVELOPMENT_PROTOCOL.json`，SHA `0b4bd88fe2d591cc9a0d6f93e8af0bc470aab84a992ebcd2717934db5718bfbe`；首跑UTC12:11:05前写入。
- 输入复用OWLv2协议中的相同28张、且逐图核对Qwen实际app-upload JPEG SHA；随后由GroundingDINO原processor处理。各模型内张量处理并不相同。
- 完整目录 `evaluation-runs/v03_grounding_dino_development_v1`：`run.json`、`predictions.jsonl`、`protocol.json`、28张输入JPEG、全部原始token logits/归一化框/input IDs的NPZ、阈值后NMS前后框/短语/分数/映射、unmapped及抑制理由、实际pixel_values张量SHA/形状/类型、源码快照。
- 逐图复核入口 `evaluation-runs/v03_grounding_dino_development_v1/review.html`。彩色实线是模型估计框，黑虚线是Screws作者旋转框的外接AABB。
- 独立完整性记录 `independent_integrity_check.json`：28输入SHA、28原始输出SHA、36作者框从原始旋转参数重算通过；运行期间脚本未改变。
- `scripts/download_grounding_dino_model.py`、`scripts/probe_grounding_dino_detector.py` 为独立脚本，不改核心代码。10项新CPU工程测试通过；连同OWL测试共16项通过，ruff通过。这些合成fixture测试不是识别性能证据。

## 两次异构检测器试验的共同结论

| 固定首轮 | LOCO整图计数 | 新Screws整图计数 | Screws AABB precision / recall |
|---|---:|---:|---|
| OWLv2 Base Ensemble | 0/16 | 0/12 | 9.55% / 47.22% |
| Grounding DINO Tiny | 0/16 | 1/12 | 33.33% / 25.00% |

这些结果只说明本轮通用查询、公开权重与预处理协议没有解决KitGuard小五金计数；不是证明这些模型经其他开发方法也必然无效。两者都不能当作独立真值；也不能选择性从各模型挑正确的点构造虚假的总体成功率。OWL原协议与结果保持不变，详见 `OWL_DEVELOPMENT_REPORT.md`。

没有读取或运行新64张留出，也没有利用这批开发结果修改生产计数。若未来继续此路线，应另立开发版本并在新未见数据上验证增量收益，完整记录错误拦截和对正确工单的误拦，而不是无限追调这28张图。

来源：[官方模型卡](https://huggingface.co/IDEA-Research/grounding-dino-tiny)、[官方Transformers使用说明](https://huggingface.co/docs/transformers/model_doc/grounding-dino)、[作者代码](https://github.com/IDEA-Research/GroundingDINO)。数据许可和作者标注来源沿用项目归档；不能将非商业研究数据许可解释为生产使用授权。
