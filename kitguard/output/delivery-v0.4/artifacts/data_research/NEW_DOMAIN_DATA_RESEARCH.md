# 新拍摄域与 L 形角码公开数据调研

检索与核验：2026-09-26。只把作者、大学/研究机构、数据集官方仓库作为结论依据。没有把网络转载图片、AI 自标注或渲染图当成作者实拍真值；本轮未运行模型。

**优先获取 InO-10-190 的作者完整实拍子目录。** 它具有明确的 `L-bracket` 作者类别、可追踪的人工作者框和 MIT 仓库许可，能够补当前缺乏 bracket 阳性的来源。它不能直接变成一个覆盖 bolt/nut/washer/bracket 四类的完整新场景基准：十类工业件中只有作者 class 0 可以无歧义映射到当前 L-shaped support 定义。下面统计均直接解析作者标签，没有看模型表现选图。[作者项目页](https://www.danielhorvath.eu/sim2real/index.html)、[作者仓库 README](https://git.sztaki.hu/emi/sim2real-object-detection/-/blob/master/README.md)

## 1. InO-10-190：优先来源

作者为 Dániel Horváth 等；论文为 IEEE Transactions on Robotics 2023，DOI `10.1109/TRO.2022.3207619`。作者说明这是 190 张真实 RGB/深度图的人工目标框数据，而不是其生成器产生的合成训练图。作者仓库把数据、实现和结果列在同一个 README 中，根目录 LICENSE 为 MIT，版权为 Dániel Horváth 2021；本地获取保留该声明与论文引用。[作者说明](https://www.danielhorvath.eu/sim2real/index.html)、[作者 LICENSE](https://git.sztaki.hu/emi/sim2real-object-detection/-/blob/master/LICENSE)

固定作者版本：`c733a3543157135c591cbe3f9de27e209964af63`。真实路径是 `test/test_datasets/test_01`，README 中的 `test/test_dataset/test_01` 少了一个 `s`。数据分为 `origin` 与 `cropped`，各有 A–F 六个作者目录；它们是同一批来源的不同表示，不是 380 张独立照片。只需下载这个子目录，不需要克隆整个仓库、下载 YOLO 权重或执行作者安装脚本。[固定版本](https://git.sztaki.hu/emi/sim2real-object-detection/-/tree/c733a3543157135c591cbe3f9de27e209964af63/test/test_datasets/test_01)

作者 `test_01_class.names` 的顺序为：

| 作者 ID | 作者名称 | 当前 KitGuard 映射 |
|---|---|---|
| 0 | L-bracket | `bracket`，唯一直接采用的阳性映射 |
| 1 | U-bracket | 暂不映射 |
| 2 | angle_bracket | 暂不映射，不能仅因名称含 bracket 就合并 |
| 3–9 | seat、pipe_clamp、handle、bonnet、body、ball、cable_shoe | 非当前目标目录；不据此补造另外三类真值 |

来源：[作者 class.names](https://git.sztaki.hu/emi/sim2real-object-detection/-/blob/c733a3543157135c591cbe3f9de27e209964af63/test/test_datasets/test_01/test_01_class.names)。标签是每行 `class_id center_x center_y width height` 的归一化框。

完整作者子目录的 Git LFS 指针与标签元数据已核对：**1,141 个文件，760 个 PNG，展开共 288,401,627 bytes（约 275.04 MiB）**。PNG 包括两种表示各 190 张彩色图和 190 张深度图，不能把深度图也当成额外 RGB 样本。尺寸估计来自作者 LFS 的精确 size 字段，而非网页口径。[作者子目录 API](https://git.sztaki.hu/api/v4/projects/505/repository/tree?ref=c733a3543157135c591cbe3f9de27e209964af63&path=test%2Ftest_datasets%2Ftest_01&recursive=true&per_page=100)

**实际获取完成（2026-09-26 14:48:38 UTC）**：保存于 `datasets/raw/ino-10-190/`。作者原始 tar.gz 为 **254,962,260 bytes**，SHA-256 为 `6cd26e12957cd870b4c456fb0be3647b2a9000bcb543baf3b8fd6123befaea34`；压缩包与展开数据合计约 543 MB，未下载整仓或模型权重。所有 1,141 个文件已重新哈希验证，其中 760 个 PNG 逐一匹配作者 Git LFS SHA，381 个标签/类名文件匹配固定版本元数据。`SOURCE_MANIFEST.json` 保留完整来源、路径、大小与 SHA；`AUTHOR_README.md`、`LICENSE`、`CITATION.bib` 一并保留。仅读取 PNG header 确認 190 张 origin 均为 1280×720，没有观看或标注图中内容。

### 只读标注统计与限制

| 作者目录 | 原图数 | 含 class 0 的原图 | class 0 实例数 | 全图标签仅 class 0、数量 1–3 |
|---|---:|---:|---:|---:|
| A | 53 | 4 | 4 | 4 |
| B | 19 | 19 | 19 | 0 |
| C | 20 | 15 | 15 | 0 |
| D | 21 | 9 | 18 | 0 |
| E | 22 | 12 | 12 | 0 |
| F | 55 | 3 | 12 | 0 |
| 合计 | 190 | 62 | 80 | 4 |

`origin` 和 `cropped` 每个对应来源的类别计数一致。全图仅 class 0 且数量 1–3 的来源是 **A/39、A/40、A/41、A/42**，均 1 件。它们均来自 A，不能宣称四个独立拍摄域。

发现两处必须保留的数据质量事实：当前作者版本每套标签实际共 **919 个框**，与 README/论文说的 920 差 1；另有 15 个 `origin` 框超出归一化图像边界，涉及 12 张图，均不是 class 0；`cropped` 中未发现越界框。本轮不修改作者数据，不擅自补上“缺失的第 920 个框”，也不自动截断坏框。

可检查的统计证据：`test-results/audit/v04-data-research/ino_annotation_stats_pre_download.json`、`ino_source_groups.json`。后者保存全部 190 个固定 `source_id`、对应原图/裁图路径、作者框及类别计数，不根据推理表现做任何筛选。

### 冻结协议前的建议

1. 保留作者全部 A–F 来源；至少以 `A/39` 这样的 `source_id` 绑定原图、作者裁图、深度图及未来派生 ROI。更保守的开发/验证划分应让整个 A–F 目录不跨集合，不能把同一来源的 origin/cropped 拆开。
2. 只把 class 0 作为 L 形支撑件阳性。四张纯 class 0 图片数量太少，无法据此宣称四类计数泛化已成立。
3. 如下一阶段使用作者框派生 ROI，应在任何推理前固定完整物体、边界留量、其他类别排除、最大数量、可见性及源分组规则；所有被排除项保留理由。作者 10 类对象的标注也不自动证明相机框架等背景里没有其他硬件。
4. 本轮没有生成 ROI、没有人工修改真值、没有训练/推理或挑选“容易成功”的样例。固定作者真值和 source 分组后再由主任务冻结新验证协议。

主任务随后固定了一组用于新域描述性验证的候选规则：L 数量 1–3、每个作者 class 0 框短边至少 32px；全标签为 class 0 时用原图，否则取全部 class 0 框并集，加并集短边的 10% 边距，左上 floor/右下 ceil；任何作者框超出原图（归一化容差 1e-6）则整来源排除，任何 ROI 越界或接触非 0 框也排除。仍然没有生成图片或运行模型。

按此规则只读统计得到 **20 个来源，4 个全图 + 16 个 ROI 候选**，来自 A/B/C/E 各 4/5/5/6 个。它们全部只有 **1 个 L-bracket**，不能据此验证多个角码计数。170 个主排除理由分别为：无 class 0 共 126、作者框越界 12、与非 0 框相交 26、class 0 数量超过 3 共 6。完整候选整数坐标、逐来源类别、非法原始标注行和全部排除理由保存在 `test-results/audit/v04-data-research/ino_roi_eligibility_preview.json`；正式协议/评测清单应由主任务冻结并独立核对，不能把该预览当作已经完成的模型成绩。

## 2. MVTec ITODD 验证集：有许可的后备来源

它是另一个数据集，区别于当前已用 LOCO/Screws。作者公开 28 个工业物体、3,500 个标注场景，灰度相机/深度传感器采集；对象包括 bracket_big、bracket_planar、bracket_screw、multi_bracket、screw、screw_black、washer 等。作者物体名称与数字 ID 仍须逐一核对，不能把所有 bracket 名称自动并入 L-shaped support。[MVTec 官方页面](https://www.mvtec.com/research-teaching/datasets/mvtec-itodd)、[作者论文](https://openaccess.thecvf.com/content_ICCV_2017_workshops/papers/w31/Drost_Introducing_MVTec_ITODD_ICCV_2017_paper.pdf)

许可是 **CC BY-NC-SA 4.0**。BOP 官方说明物体级标注包含类别、6D pose、2D 框/掩膜；但 **ITODD 测试图真值不公开，只有训练/验证公开**。因此应优先考虑 `itodd_val.zip`，不能下载大 test 集后把模型结果自行当真值。[官方许可](https://www.mvtec.com/research-teaching/datasets/mvtec-itodd)、[BOP 官方下载与标注范围](https://bop.felk.cvut.cz/datasets/)

官方 BOP Hugging Face 文件元数据：验证 ZIP **195,550,980 bytes**，模型 ZIP **5,504,325 bytes**，base ZIP **4,042 bytes**；test ZIP 约 2.54 GB、合成 PBR 约 36.51 GB，本轮不下载后二者，也未下载验证图。仅保存了 4 KB base 包与官方文件列表，以检查数据说明。它提供新场景，但仍属于工业固定相机灰度域，不能替代真实操作者实验。[BOP 官方文件列表](https://huggingface.co/datasets/bop-benchmark/itodd/tree/main)

## 未列为可直接获取的候选

IPD 的作者目录确实有 `l_bracket`、`corner_bracket` 等，并给出原件 ID 与分场景下载表，技术上相当相关。但当前一手材料的许可互相不同：作者 README 写 NC-SA、同仓 LICENSE.md 写 **NC-ND**，BOP 汇总写 BY-SA。本轮不替作者选择较宽松版本，也不将其纳入下一步默认获取。[作者零件表](https://github.com/intrinsic-ai/ipd/blob/main/Parts.md)、[README](https://github.com/intrinsic-ai/ipd)、[LICENSE.md](https://github.com/intrinsic-ai/ipd/blob/main/LICENSE.md)、[BOP 页面](https://bop.felk.cvut.cz/datasets/)

SortScrews 是另一组作者实拍，但主要为图像级螺丝分类，不能补 L 角码物体框真值；网上常见 Bolt/Nut/Washer/Pin 分类集与部分工业件合集作者自己说明含网上采图，来源权利和逐物体计数不满足本任务筛选条件，未凑入可用数量。[SortScrews 作者仓库](https://github.com/ATATC/SortScrews)、[工业件合集作者说明](https://github.com/mauricio-zamora-ucr/Dataset-for-Visual-Control-Assistant-for-Assembly-in-Industry)
