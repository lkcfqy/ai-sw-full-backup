# MVTec Screws type_007 语义来源审查

2026-10-02；有界只读审查。未联系作者、未浏览 FOD-A/MANTA 图片、未修改原始标签、冻结清单、模型输出或分数。外部追加搜索仅一次，用于定位 MVTec 的原论文入口。

## 结论

**`type_007 → nut` 有先于 v0.7 的外部教学来源，不是本项目仅凭视觉或模型结果临时推定；但本轮没有找到 MVTec 原作者对该 ID 的直接英文语义命名。** 最准确的依据链是：MVTec 实例框和 `type_ID` → Neuromatch 课程的解释性类别名 → KitGuard 预先采用的粗类投影。不能缩写成“MVTec 原作者直接把 type_007 标成 nut”，也不能反过来说“没有任何外部依据”。

## 核查到的证据

| 证据 | 实际支持什么 |
|---|---|
| [原始 README_v1.0.txt](../../datasets/raw/mvtec_screws_v1.0/README_v1.0.txt) | 作者说明数据为 13 种 screws and nuts、定向框及类别；没有逐一列出哪些 ID 是 nut。 |
| [原始 mvtec_screws.json](../../datasets/raw/mvtec_screws_v1.0/mvtec_screws.json) | 13 个类名只有 `type_001`–`type_013`，每类 supercategory 均为 `object`；没有 `nut` 或 `washer` 的直接类别名。 |
| [MVTec 官方数据页](https://www.mvtec.com/research-teaching/datasets/mvtec-screws) | 同样只说明整体包含 screws 和 nuts，未给 ID→语义表。[官方示意图](https://www.mvtec.com/fileadmin/_processed_/3/c/csm_teaser_image_dataset_screws_0aa53cf3fc.webp)是零件与定向框/箭头示例，没有可据以确认 type_007 英文名的图例。 |
| [Neuromatch 课程代码与示例](https://deeplearning.neuromatch.io/projects/ComputerVision/screws.html) | `category_names` 明确写 `7: 'nut'`、`9: 'large nut'`、`10: 'nut'`、`11: 'nut'`，且提供完整 13 类的解释性名表。后文还选择类别 7、10 构造 nut 分类练习。这是课程/镜像方的命名，不是 MVTec COCO 原类名。 |
| [项目最初来源文档](../DATA_PROVENANCE.md) | 日期记为 2026-09-26，已明确声明“英语说明来自 Neuromatch 课程，保留为解释性别名，不修改原始类名”，并列 7/9/10/11→nut。当前发现不是根据新 51 错例补造映射。 |
| [项目下载/投影代码](../../scripts/fetch_public_data.py) 与 [初始来源 manifest](../../datasets/manifests/mvtec_screws/manifest.json) | 映射明确固定为 `{7,9,10,11}`→nut，其余→宽口径 bolt；manifest 记录时间为 `2026-09-26T09:39:20.808946+00:00`。这是项目类别约定，不是额外作者认证。 |

9 月 26 日保存的 [Neuromatch HTML 原件](../../datasets/provenance/mvtec_screws/neuromatch_course.html) 与本次实时页面均含上述映射，旧文件 SHA-256 为 `73112ba27fdc0f5cd931f382a1cea590c3d8da7610f9267aa35c8ec3602a31ed`。原始 JSON 共 365 条 category 7 实例；数字 ID 的来源可审计，但 ID 的英文解释层级必须另外披露。

## 原论文与视觉核查的限制

[MVTec 官方论文目录](https://www.mvtec.com/research-teaching/publications)确认 Ulrich、Follmann、Neudeck 的 2019 论文 *A comparison of shape-based matching with deep-learning-based object detection*，DOI [10.1515/teme-2019-0076](https://doi.org/10.1515/teme-2019-0076)。本轮取得的是官方引用及出版页摘要信息，出版站全文入口未能读取；**没有核实全文中是否存在 13 类语义表，不能声称论文一定没有该表，也不能把未读全文当作已确认依据。**

已查看官方概览图及课程的 [“nut 7” 五例示意](https://deeplearning.neuromatch.io/_images/ee38563ef324078b0a7d902e7585017f4a41ec14f160755a29d3448cc927d384.png)。课程图像标题直接支持其命名，部分示例可见六角外缘；这些小尺寸顶视图不构成对每个零件内螺纹、厚度或实际型号的独立物理确认。本轮不以视觉印象重新裁决标签，也不以多个模型一致输出 washer 作为改真值理由。

## 对结果和后续表述的影响

推荐表述：**“五个 inventory 不一致样本集中于 MVTec 的 type_007；该类依据 Neuromatch 教学别名、按项目预先固定映射归入 nut，模型观察多次给出 washer。该现象是模型输出与预定语义投影不一致，包含跨数据语义映射的不确定性。”**

现有 C/W/U/E 和门槛继续按原冻结协议解释，不回改成成功；独立审计通过证明记录及计算一致，不额外证明语义投影获得原作者认证。若今后获得可信的新语义证据，应单独版本化标签审查、披露所有受影响样本并做敏感性分析；不得只为这五张改标或把新标签追写进原实验。

这也限制“异构检测器核实真实螺母”的主张：现有 detector 训练沿用了同一个 `{7,9,10,11}` 投影，其 nut 输出并不是独立于该语义假设的真值证据。后续更准确的研究目标是检验 **type_007 映射对象与 washer 的身份区分/冲突处理**，并用类别语义更直接的新来源验证；不能宣称已定位到经原作者直接认证的物理螺母误识别。
