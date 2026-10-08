# v0.3 新来源公开实拍验证协议

数据选择已完成；本子任务没有加载或运行模型。主流程须先用开发数据选择并冻结 v0.3 模型协议，然后再运行这里的留出集。

“未用”指排除旧模型/预留清单来源后的新原图集合，不表示全球未见或未被基础模型预训练使用。

唯一推荐运行入口：[`CANONICAL_NEW_SOURCE_BENCHMARK_V1.json`](../../datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json)。SHA-256：`85f331c47d50256e1e98c3b346bef109e30a98e7e101da6ea3f46c9b7b3dcaf2`。清单所有 76 个 case 已通过项目现有 `read_manifest` 和 `validate_case`，其中开发 12、留出 64。

## 1. 可用数据与本轮选择

| 数据层 | 本轮数量 | 真值依据 | 可以支持的结论 |
| --- | ---: | --- | --- |
| 新 Screws 开发 | 12 个不同原图的裁剪视图 | 作者完整实例框计数；不使用模型伪标签 | 调整对木板背景、阴影、多种螺纹件/螺母及不同目标数量的处理；不是成绩 |
| 新 Screws 留出 | 32 个不同原图的裁剪视图 | 同上；每原图最多一视图 | 固定裁剪条件下另一公开拍摄背景和变动数量组合的描述性表现 |
| 新 LOCO 留出 | 32 张未用原图：正常 16、数量异常 16 | 正常组成及作者单一明确数量缺陷标签 | 同一 LOCO 拍摄域内，对未用原图的重复验证；不是新工厂泛化 |
| 旧 v0.2 的 16 开发 + 48 留出 | 原文件全部保留；未混入上述 76 | 原冻结记录 | 现在只能作为开发/回归证据，不能再次称 v0.3 未见留出 |

LOCO 全部 590 个合格候选排除旧 64 张后，尚有 **526 张**：正常 510、明确数量异常 16。510 张正常均为 2/2/2/0，不应靠增加其数量美化“准确率”。本轮保留全部剩余数量异常，并从 98 张未用官方 test-normal 中按最初固定 seed/SHA 顺序取 16 张；不分给开发。

剩余异常计数向量（螺纹件、螺母、垫圈、角码）：(3,2,2,0) 5 张，(1,2,2,0) 4 张，(2,2,1,0) 3 张，(2,2,3,0) 2 张，(2,1,2,0) 2 张。**没有剩余 (2,3,2,0)**，不能称六种数量异常都获得了新的 LOCO 留出证据。

Screws 原图每粗类≤3的数量仍为 0。新视图不改变这一事实，也不把裁剪成绩写成原图成绩。严格排除旧证据文件曾列出的 **53 个 Screws 原图**，其中实际旧推理来源为 16 个，另外的原图主要只是旧清单预留，保守地一并排除。作者框越出原图的 50 个实例涉及 46 个源图；这两种排除合计 97 源图（有 2 个重叠）。384 张原图中，剩余 287 个源图参与确定性候选生成；113 个源图产生 518 个安全的不同实例子集视图。没有为了凑数量放宽边界规则。

## 2. 安全裁剪与原始坐标定义

作者的 `bbox` 是 **(row 中心, col 中心, width 全长, height 全长, phi 弧度)**，不是普通 COCO 的左上角 `x,y,width,height`。phi 从图像水平轴起算、数学正方向为逆时针。COCO 图像坐标原点位于左上角像素的左上边界；不能把 HALCON 的半轴格式套入本文件。

程序依据作者定义将旋转框转成轴对齐包围范围，并对每边加 **16 个原图像素**的安全余量。一个候选矩形内，每个原始标注实例必须满足以下二者之一：

1. 加余量后的整个框完全包含在视图内；
2. 加余量后的整个框与视图不相交。

其余候选一律剔除，不能只数中心在图内的框。作者框本身越出原图的整张源图先行排除。候选尺寸为 768×576、960×720、1152×864、1440×1080；在原图上按 64 像素步长和右/下边界位置枚举。相同源图、相同保留实例集合的候选，优先保留更大的背景范围，再以固定 SHA 破平局。计数取完整包含实例的原类别投影，要求各粗类 0–3、总数 1–12。

独立审计另外用四个显式旋转角点重新计算边界，而非直接信任生成器的 AABB 字段。最终 44 个视图没有切断或边界模糊框；实际最小完整框到裁剪边缘距离为 **16.0985 像素**。该保证依赖作者标注的完整性和几何准确性，不是对每个真实像素物体的额外人工认证。

裁剪输入保存在 [`datasets/derived/v0.3/screws_views/`](../../datasets/derived/v0.3/screws_views/)。44 张 PNG 共 41,051,087 字节；全部逐像素核对为原图 RGB 矩形切片，不旋转、不缩放、不拼贴、不抹除、不生成物体。开发审阅联系表另有缩放与绿色作者框，只作审阅，**不能把联系表送入评测**。

## 3. 分组、目标多样性和独立性

Screws 在裁剪候选筛选前，按原图 SHA 分配组：`SHA256(seed | source-split | original_SHA)` 转整数，偶数为开发、奇数为留出。seed 是 `KitGuard-v0.3-source-grouped-crops-20260926-v2`。之后只在各组内部按数量向量平衡选择，绝不参考模型输出；每个源图最多取一视图。

最终 Screws 开发 12 个原图（原官方 train 10、val 2）；留出 32 个原图（原官方 train 26、val 6）。这是一套**自定义原图分组**，不是作者官方 test。新开发和新留出原图无交叉；所有新 76 源图与旧证据清单中合计 117 个 LOCO/Screws 源图无交叉。全部 1,145 张本地原图还做了解码 RGB 内容 SHA 检查：新选原图彼此无完全相同像素内容，也不与排除集合有完全相同像素内容。此项不识别近似场景或同一实物的连拍。

Screws 留出覆盖螺纹件/螺母在 0–3 范围内的 **15 种非空组合**；垫圈和角码恒为 0。每个螺母计数 0/1/2/3 都各有 8 张。保留的原始类别为 type_004～type_013；开发另含 type_003，本轮没有 type_001、type_002。长木螺丝也仅属于“带头螺纹件”粗类，不把 wood screw 宣称为特定 bolt SKU。

“源图不重叠”不等于统计上独立采样、陌生工厂、不同实物批次或不同拍摄会话。数据缺乏这类独立分组信息。公开图片是否进入 Qwen 预训练也未知。本轮能扩展到另一个公开背景域及变动计数，但不能证明实物纠正、真实复拍、现场出库安全或人工效率。

## 4. 评测约束

- 原 16 张开发与新 12 张开发可用于方案选择。新 64 张留出必须等模型、提示词、输出预算、预处理和拒绝/重拍策略冻结后才运行；不得看结果后挑图或改候选集合。
- 对同一新留出集比较冻结 v0.2 与 v0.3；分别报告 LOCO 正常 16、LOCO 数量异常 16、Screws 裁剪 32。不能拿旧 LOCO 的 95.8% 直接与新裁剪集成绩做因果提升比较，也不把三组拼成“工业总体准确率”。
- 主要指标仍按原图来源计数：四类计数全对、明确给出错误数量、拒绝/执行失败和耗时。64 个留出 case 来自 64 个源图，多个订单任务不会增加图片分母。
- LOCO 保留作者的正常订单 2/2/2/0；单独报告 16 张数量异常的错误 `ready`，以及恒定正常计数基线（16/32 全对，但16/16异常会误放行）。Screws 没有作者的“正常工单”，不虚构制造商 BOM。
- 可选规则压力面板另存 [`OPTIONAL_RULE_ORDER_PANELS.json`](../../datasets/manifests/v0.3/OPTIONAL_RULE_ORDER_PANELS.json)：Screws 15 个合法两类工单、LOCO 63 个合法三类工单。这些是程序生成的任务条件，不是新的照片或实际订单；不传入视觉观察器。若使用，报告每图是否存在任何错误 `ready`，避免用大量容易拒绝的订单稀释风险。
- 角码正例仍未验证。LOCO 补足垫圈正例，但静态照片不能证明同一套实物补件前后的闭环收益。

## 5. 许可、来源与审阅

原图、作者标注、裁剪衍生图和联系表均按 **CC BY-NC-SA 4.0** 处理，保留 MVTec Software GmbH 署名和变化说明。免费公开获取不表示可任意商业使用；对大赛奖金、外部分发和后续商业用途的具体授权不能由本协议替代。

- [MVTec Screws 作者页面](https://www.mvtec.com/research-teaching/datasets/mvtec-screws)，原件说明 [`README_v1.0.txt`](../../datasets/raw/mvtec_screws_v1.0/README_v1.0.txt)，原标注 [`mvtec_screws.json`](../../datasets/raw/mvtec_screws_v1.0/mvtec_screws.json)。原包实际含 4,427 个唯一实例，保留其与 README 4,426 的已知差异；没有删标签凑说明数字。
- [MVTec LOCO AD 作者页面](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad)，原件 [`readme.txt`](../../datasets/raw/mvtec_loco_ad/screw_bag/readme.txt)，原始正常构成和缺陷投影详见 [既有来源档案](../DATA_PROVENANCE.md)。
- [CC BY-NC-SA 4.0 许可](https://creativecommons.org/licenses/by-nc-sa/4.0/)。Screws 研究引用：Ulrich, Follmann, Neudeck, *A comparison of shape-based matching with deep-learning-based object detection*, 2019, DOI 10.1515/teme-2019-0076。LOCO 引用：Bergmann et al., *Beyond Dents and Scratches*, IJCV 2022。
- [开发集12图联系表](SCREWS_DEVELOPMENT_CONTACT_SHEET.png)：已逐格目视查看，没有据此改写作者标签。未向主开发代理展示任何留出照片。
- [独立程序审计](../../datasets/manifests/v0.3/FINAL_DATA_AUDIT.json)保留来源许可 SHA、清单验证、旋转框复算、逐像素一致性、数据重叠和审阅记录。只进行了 CPU 读图/几何/散列检查，没有加载或调用模型。

## 6. 文件版本和运行

[`CANONICAL_FILES.json`](../../datasets/manifests/v0.3/CANONICAL_FILES.json)是唯一索引。初始探索的 v1 按作者官方 split 分组时，只剩 1 个安全 test 源图，因此保留探索文件后，新增 v2 自定义原图分组。最初的 LOCO32 选择在最终合并清单中**原样保留**。v2 裁剪生成脚本顺带产生的另一份 LOCO 正常图候选并非权威集合，不运行；全部变化都发生在新数据模型推理前，未改动旧 v0.2 冻结文件。

生成和审计的精确 Python 代码保存在 [初步候选分析](prepare_new_data_protocol.py)、[源分组与实际裁剪](prepare_new_data_protocol_v2.py)、[独立审计和最终索引](validate_new_data_protocol.py)。它们拒绝覆盖已经写出的清单或视图。重新生成应使用新版本目录，不能覆盖这里的来源、时间和 SHA。

只跑新开发集的兼容命令（应由主流程根据当前候选模型配置执行；本数据子任务未执行）：

```sh
.venv/bin/python -m scripts.run_benchmark \
  --manifest datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json \
  --dataset-root datasets --output evaluation-runs/v03_new_development_candidate \
  --split development --input-pipeline app-upload \
  --observation-mode spatial_inventory --image-max-side 1536 \
  --model-path "$HOME/Downloads/AI-Models/Qwen3.6-27B-4bit"
```

留出命令应在 v0.3 配置冻结记录存在之后另行创建。所有失败必须留下，不能重新命名旧留出为“全新验证”。

主流程先使用 Screws 子清单启动的12张开发，与权威合并清单的开发部分完整一致；ID、顺序、图像文件SHA、解码像素和真值逐项等价，见 [映射审计](../../datasets/manifests/v0.3/DEVELOPMENT_MANIFEST_EQUIVALENCE.json)。无需重跑以更换清单文件名。
