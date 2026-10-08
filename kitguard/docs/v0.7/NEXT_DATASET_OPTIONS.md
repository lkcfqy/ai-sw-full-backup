# 下一轮独立公开实拍数据候选

研究记录：2026-10-02 07:41 KST。**本文件在 v0.7.0 源码封装完成后新增，属于下一轮研究，不是已封存提交材料的一部分。** 本轮只核查作者网站、论文、仓库和下载元数据；未下载数据包、未运行模型、未新增实验成绩。

## 结论

优先核查 **FOD-A v2.1**；它同时提供 Bolt、Nut、Washer 的实拍实例框，下载规模较小。**MANTA** 可作为单件身份检查的补充，但许可标记冲突、五视角样本关系和任务差异需要处理。此次保留两项，不为凑满三项推荐缺少螺母阳性或来源混杂的数据。

这两个来源均不是 MVTec Screws/LOCO 的余量，但目前只能称为“新的来源候选”，不能直接称为“已建立的独立留出集”。模型预训练是否包含这些公开图未知。

## 1. FOD-A v2.1 — 首选，先完成元数据与计数适用性核查

| 项目 | 已核实事实与边界 |
|---|---|
| 作者与来源 | University of Nebraska Omaha 的 Munyer、Huang、Zhong 团队；作者仓库 `FOD-UNOmaha/FOD-data`。 |
| 真实采集与任务域 | 手持相机及 UAV 拍摄机场跑道/滑行道异物视频，再提取帧。环境含干湿、明暗变化；与桌面料包存在明显域差异。 |
| 所需阳性 | 作者论文图 3 明确列出 **Bolt、Nut、Washer**；还存在 **BoltWasher、BoltNutSet** 等组合类以及 Screw。不是只在背景文字中提到这些零件。 |
| 标注与数量 | 31 类、超过 30,000 个框标注实例；Pascal VOC XML，并有天气/光照标签。它们不是 30,000 个独立实物或独立视频。当前 v2.1 的每类图数、实例数、原视频数及同框多件分布尚未下载核算；不套用旧版统计表。 |
| 计数适用性 | 框可以支持实例数量核对，但必须先确认全部目标的标注完整性与类映射；不能将复合类当作一个 bolt/nut/washer，也不能根据类名自行拆成多个单件。 |
| 下载成本 | 作者推荐 VOC 版：300×300，**412 MB**；原始格式版：400×400，**8.3 GB**。链接公开；本轮没有验证完整传输、解压空间或 ZIP 内目录。小分辨率下目标是否足以辨识需独立检查。 |
| 许可状态 | 作者仓库明确是 **MIT**；该 LICENSE 的文本针对软件及相关文档。尚未检查外置 Google Drive ZIP 是否有数据专用条款，因此不能仅凭仓库徽标断言所有照片的再分发/商用许可已核实。下一步应先查包内许可；必要时取得作者澄清。 |

一手依据：[作者仓库与当前下载版本](https://github.com/FOD-UNOmaha/FOD-data)、[作者论文 §III、图 3](https://arxiv.org/html/2110.03072v1)、[图 3 原图](https://arxiv.org/html/2110.03072v1/figures/AnnotationInstances.png)、[仓库 LICENSE](https://github.com/FOD-UNOmaha/FOD-data/blob/main/LICENSE)、[作者链接的 VOC v2.1 下载页](https://drive.google.com/file/d/1RdErcq8PGRXZUOGauaACkQG44T-QyZ4x/view)。

**建议用途（方案判断）：** 先验证 nut→washer 错认和真 washer 被过度拒答的风险，再决定是否建立多物体计数面板。先按原始视频/采集会话分组，不能把相邻帧随机分到开发集和留出集。作者降到 15 FPS 不等于已经消除近重复。若 VOC 文件名无法恢复视频关系，应暂停随机切分，先恢复来源映射；确实无法恢复时，只能报告相关帧诊断，不能声称严格独立泛化。

## 2. MANTA — 有条件补充，适合单件 nut/washer 身份压力测试

| 项目 | 已核实事实与边界 |
|---|---|
| 作者与来源 | Lei Fan 等作者项目；CVPR 2025 论文及作者链接的 Figshare 记录。 |
| 真实采集与任务域 | 受控条件下的微小实物、多视角异常检测；每条多视角记录包含五个视角。不是机场场景，也不是混合料包。 |
| 所需阳性 | 补充材料表 I：**Nut 2,217**、**Red Washer 2,298**、**Yellow-Green Washer 2,288**、**Screw 2,324**；另有 Flat Nut。这里保留作者类别，**不把 Screw 未经核对并为 Bolt，也不把 Nut Cap 当 Nut**。 |
| 标注与样本单位 | 类别、正常/异常分组及异常像素区域标注；上述数值为作者的 multi-view image/record 数，不能直接称为独立实物数，更不能再将每条的五视角算成五个独立样本。物体身份及跨记录复拍关系尚待核对。 |
| 计数适用性 | 可检查单件身份混淆；异常掩膜不是多物体实例计数框。不能单凭该集证明混合包计数能力。彩色 washer 与反光金属 washer 有域差异，材质不能只凭类别名推断。 |
| 下载成本 | Figshare 可按类取文件：`nut.tar.gz` **1,432,391,956 B**，`yellow_green_washer.tar.gz` **1,400,208,198 B**，两类约 **2.83 GB**；另加 `screw.tar.gz` **3,614,536,653 B** 后约 **6.45 GB**。不需要先下整个 Mechanics 域。解压空间未验证。 |
| 许可状态 | **存在明确冲突：** 作者项目页标 **CC BY-NC-SA 4.0** 且禁止商业用途，作者链接的 Figshare API 元数据标 **CC BY 4.0**。本记录不选择宽松标签来消除冲突；在数据许可澄清前仅列为有条件候选，不作商用/再分发已获准的声明。 |

一手依据：[作者项目页](https://grainnet.github.io/MANTA)、[作者补充材料第 4 页，表 I](https://grainnet.github.io/static/pdfs/Manta-supp.pdf#page=4)、[Nut/Red Washer 官方数据记录](https://figshare.com/articles/dataset/manta-mechanics-button_gear_nut_nut_cap_red_washer/27937518)、[Screw/Yellow-Green Washer 官方数据记录](https://figshare.com/articles/dataset/manta-mechanics-terminal_screw_wrie_cap_square_button_cap_yellow_green_washer/27937521)。文件大小与许可字段读取自 [Figshare API 27937518](https://api.figshare.com/v2/articles/27937518) 和 [27937521](https://api.figshare.com/v2/articles/27937521)，仅读取元数据，未取归档。

**建议用途（方案判断）：** 固定单视角规则或将一件的全部视角作为同一组，评价 nut/washer 身份检查是否有效及 washer 的过度拒答率。不能根据模型输出来挑最佳视角。原始拼接的五视角图不能直接交给数量观察器后按“五件”评分。优先保留正常和异常实物两个面板，避免只挑外观容易的正常件。

## 已有曝光核查与没有进入优选的来源

在写入本记录前，对 `docs`、`README.md`、`datasets/manifests`、`datasets/derived`、`scripts` 中的 Markdown/JSON/TXT/Python/YAML 进行名称检索（`FOD-A/FOD-UNO/MANTA/IndustReal/CSEM-MISD/ITODD`），仅命中 [v0.4 新域数据研究](../v0.4/NEW_DOMAIN_DATA_RESEARCH.md) 中的 ITODD。未发现 FOD-A、MANTA 的既有引用或清单记录。这是有范围的文本核查，不是像素级无交集证明；未来仍须与历史来源清单及图像哈希/感知重复核对。

- **MVTec Screws/LOCO：** 本轮正式 51 已曝光；Screws 未曝光源已用尽，LOCO 未曝光余量仅 normal。不得重新命名为下一轮新留出。依据是现有项目来源盘点与正式实验记录，而非本轮外部网页的新发现。
- **MVTec ITODD：** v0.4 已查官方文件清单与约 4 KB base，记录未下载验证图或运行推理。作者 28 物体表有 washer、screw，但没有 nut，不能补足本轮关键的 nut 阳性。其灰度/深度域和测试真值不公开也限制直接复用。[官方页](https://www.mvtec.com/research-teaching/datasets/mvtec-itodd)、[作者论文](https://openaccess.thecvf.com/content_ICCV_2017_workshops/papers/w31/Drost_Introducing_MVTec_ITODD_ICCV_2017_paper.pdf)
- **InO-10-190：** v0.4 已实际下载、曝光部分图像；主任务是工业对象/支架，不能补出其原标签中没有的 nut/washer 类。详见上述本地历史记录。
- **IndustReal：** 作者实拍装配数据虽有 PLA 打印的 nuts/washers，但已核查说明以动作/装配状态标签为主，本轮未确认逐个 nut/washer 的完整计数标注；不优先于 FOD-A。[作者仓库](https://github.com/TimSchoonbeek/IndustReal)
- **混合网络图及合成数据：** 本轮不列为独立实拍留出来源。作者若明确混用互联网照片和自摄，不能假定所有图的来源/许可均已独立核实；合成图也不能代表真实拍摄证据。

## 最小下一步与冻结条件（尚未执行）

1. 优先完成 FOD-A 的数据许可与小规模文件目录核验。保留下载版本、网址、作者许可、归档哈希、采集组 ID 和原始标注；不先运行模型。
2. 在看新模型输出前固定纳入规则：区分原子类与组合类，列清各类阳性/阴性、每组数量、模糊与遮挡处理。只凭完整来源标注或独立人工标注建立真值，不能以模型答案补真值；没有确认的类别应标“不支持/未标注”，不能默认为 0。
3. 以视频/物体/采集会话为隔离单位建立开发与封存验证组；对历史数据和组间做重复核查。标签映射、模型/提示词、拒答规则、计时、全量 C/W/U/E 与 false-ready 口径都在运行前冻结。旧 28、旧 64、正式 51 仅作曝光开发/回归数据，分别报告。
4. 留出必须同时有 nut 阳性和真正 washer 阳性，分别报告 nut→washer 错认、washer 被拒答/错认、覆盖率和总时延。若仅有分类单件集，不报告为混合 BOM 计数成功；若只验证来源支持的子任务，不把其 false-ready 为 0 说成整个四类工作流为 0。
5. 若缺少可恢复的物体/视频分组、许可仍冲突或正反例不足，先保留为开发诊断，不据此晋升候选。公开数据能继续支持开发，但不替代现场效益、真人可用性或用户反馈验证。

本轮已完成的是候选及约束核查；下载、许可澄清、标注验收、新来源冻结和任何模型结果均未完成。
