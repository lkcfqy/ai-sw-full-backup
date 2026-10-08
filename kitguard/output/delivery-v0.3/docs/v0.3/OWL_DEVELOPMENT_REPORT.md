# OWLv2 独立 CPU 开发诊断（固定首轮，非产品能力证明）

2026-09-26；仅运行已公开给开发过程的 16 张 LOCO 与新 12 张 Screws 作者标注安全裁剪。没有读取或运行新 64 张留出图，没有改动主产品核验结果。

**结论：本轮固定通用协议不适合加入工单放行链。** 两组整图四类计数均为零正确，主要表现为多框、误分类及漏检。此结果不能推导 OWLv2 经其他预注册协议或专门训练也一定无效，但不支持现在接入自动修数。

| 数据 | 整图四类计数完全正确 | bolt / nut / washer / bracket 分别正确 | CPU中位 / 最大 |
|---|---:|---|---|
| LOCO 开发16图 | 0/16 | 3/16、0/16、6/16、6/16 | 1.047 / 1.097 秒 |
| Screws 开发12图 | 0/12 | 1/12、5/12、5/12、10/12 | 1.037 / 1.055 秒 |

28/28推理成功，无解析/运行错误。时间是本机CPU四线程实际单例流程（含图片读取、预处理、模型推理、输出保存与计分），不含一次性模型加载；不是跨机器延迟承诺。脚本强制 `torch.device("cpu")`、float32、最多4计算线程和1 inter-op线程，没有调用MPS/CUDA。

Screws以作者旋转框的外接AABB，经裁剪平移及输入尺寸缩放，在固定同类IoU≥0.5做一对一匹配：**17 TP、161 FP、19 FN；precision 9.55%、recall 47.22%**。分母为12成功图/36作者实例，所有失败另外记账（本次0）。这不是COCO mAP，也不是旋转IoU。LOCO没有本任务可用的逐实例框，不报告定位准确率。

## 一个有用但不足以采用的例子

`screws_222` 的小螺母获得同类框（与作者AABB IoU 0.8689），但同时螺栓漏检/定位错误：真值 `{bolt:2,nut:1,washer:0,bracket:0}`，检测计数 `{bolt:1,nut:1,washer:0,bracket:0}`。不能选择性取螺母结果、忽略其余错误，把检测器当成真值修正Qwen。

## 首跑前协议与可复现证据

- 模型 `google/owlv2-base-patch16-ensemble`，固定revision `cfd3195ba4ea9592eec887ded089f4c08eff231d`；Apache-2.0。
- 权重 `619,918,824` 字节；原始安全序列化与配置/分词文件总计 `621,511,889` 字节，未重复下载 `pytorch_model.bin`。
- 权重SHA-256 `e1e130b9e404cf91a75ad45644c1da9d7fa5284085eecc864266a6923efb99e7`；所有上游文件按LFS SHA-256或Git blob SHA-1校验，全部本地SHA保留。
- 共享目录 `/Users/lkc/Downloads/AI-Models/owlv2-base-patch16-ensemble`：原始README、原配置/分词、原权重、LICENSE、`UPSTREAM_API_METADATA.json`、`DOWNLOAD_MANIFEST.json`。HF未附独立LICENSE，因此另存规范Apache许可正文，并保留原模型卡许可声明；没有冒称LICENSE来自该仓库。
- 协议 `docs/v0.3/OWL_DEVELOPMENT_PROTOCOL.json`，SHA `07a9a128fc722faeec63e69b328980af2e49fcbda9cf563a3b620d9aae34f3df`，12:03:27 UTC首次运行前已于11:58:50 UTC写入。
- 固定4类英文查询；每候选框取最高类别分数，score>0.10；同类greedy NMS IoU>0.50，不跨类抑制，不按真值或BOM调阈值、限数量。查询、阈值和NMS没有在看到结果后修改。
- 复用Qwen已有真实app-upload JPEG，每图先核对原run的`model_input_sha256`，再由OWLv2原processor处理。保存JPEG、实际`pixel_values` tensor的形状/类型/SHA、全部原始logits/boxes/objectness NPZ、阈值后NMS前/后框与抑制理由。与Qwen后续模型内视觉预处理不同，不能解释成完全相同模型输入张量。
- 运行记录 `evaluation-runs/v03_owl_development_v1/run.json`；逐例 `predictions.jsonl`；28张叠框索引 `review.html`；源码快照 `source_snapshot/probe_owl_detector.py`；独立复核 `independent_integrity_check.json`。
- 脚本 `scripts/probe_owl_detector.py` 禁止覆盖输出、只允许开发28图；`tests/test_owl_probe.py` 的6项工程测试通过，验证NMS、匹配、坐标与失败分母。这些测试不算真实图识别性能。

## 解释边界

此轮零检测只表示检测器在固定阈值下未找到物体，不是证明物体不存在。分数没有校准成可靠性概率；NMS既可能保留重复件，也可能合并邻件。所有样本无角码正例，Screws无垫圈正例；不能因某类真值常为0宣称该类可识别。模型与Qwen架构不同但可能共享语义和数据偏差，二者一致仍不是真值。

本轮不做事后阈值扫描，不把某张定位成功图单列为总体成功。如以后继续，应写新的开发协议并用新的未见样本验证增量价值，衡量捕捉错误与误拦正确工单的权衡。

来源：[Google官方模型卡](https://huggingface.co/google/owlv2-base-patch16-ensemble)、[Transformers OWLv2实现](https://huggingface.co/docs/transformers/model_doc/owlv2)、[Apache许可](https://www.apache.org/licenses/LICENSE-2.0.txt)。数据作者来源与许可见既有 `datasets/manifests/mvtec_screws/manifest.json` 及LOCO归档；未将这些非商业数据许可解释为生产使用授权。
