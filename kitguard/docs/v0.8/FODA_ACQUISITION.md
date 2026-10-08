# FOD-A v2.1 获取与元数据审查

2026-10-02 KST，v0.7.0 正式交付封装后的下一轮研究。状态：**仅获取、保存来源、检查 ZIP/标注元数据；未采纳为评测或训练数据。** 全部图片未浏览、未解码、未推理、未对外发布；未执行作者代码。

## 决策

取得的 VOC 包包含 **6,742 张 Bolt/Nut/Washer 单类单实例身份诊断候选**，但它们不是 6,742 个独立实物，也不是新的混合 BOM 计数验证集。后续只读 XML 追溯已恢复其中 **6,740 张到 26 个标注来源目录**，2 张仍 unknown，详见 [独立映射报告](FODA_GROUP_RECOVERY.md)；最初的元数据审计保持原样。照片授权及视频/实物独立性仍未解决，不构建独立留出、不运行模型。原始官方划分及问题完整保留，没有悄悄去重或重划分。

## 来源、版本、许可证与获取回执

| 项目 | 核查结果 |
|---|---|
| 数据与作者 | FOD-A，University of Nebraska Omaha 作者团队；Pascal VOC **v2.1**，README 指定 300×300。 |
| 作者仓库 | [FOD-UNOmaha/FOD-data](https://github.com/FOD-UNOmaha/FOD-data)，获取时固定 commit `a22e5bd5c314f4c7b5d5c5f01224db453c62248f`。 |
| 作者下载 URL | [Google Drive VOC v2.1](https://drive.google.com/file/d/1RdErcq8PGRXZUOGauaACkQG44T-QyZ4x/view?usp=sharing)，来自固定 commit 的 [README](https://github.com/FOD-UNOmaha/FOD-data/blob/a22e5bd5c314f4c7b5d5c5f01224db453c62248f/README.md)。 |
| 作者声称大小 | `412 mb`；Drive 显示 `412M`。 |
| 实际取得 | `FODPascalVOCFormat-V.2.1.zip`，**431,758,527 B**；响应 Content-Length 同值。ZIP 文件内容总大小 **442,221,638 B**，未解压图片。 |
| 获取时间 | 2026-10-02 **07:45:17–07:46:10 KST**（UTC 2026-10-01 22:45:17–22:46:10）；时间来自脚本回执。 |
| 下载响应修改时间 | `Sat, 09 Mar 2024 00:57:09 GMT`，只作为服务端响应元数据，不改称拍摄日期。 |
| 本地 SHA-256 | `408af3ac5be8af399367a7a846c6bd720727391c2d89de17985321c27468dd87`。 |
| 官方公开 hash | 在作者 README、LICENSE、公开下载确认页中**未找到**；本地散列只标识本次取得的归档，不能冒充与作者公开 hash 核对成功。 |
| 作者许可原文 | [固定 commit LICENSE](https://github.com/FOD-UNOmaha/FOD-data/blob/a22e5bd5c314f4c7b5d5c5f01224db453c62248f/LICENSE) 为 MIT，版权 `2020 FOD-UNOmaha`，授权对象描述为 “software and associated documentation files”。完整原文已保存在本地来源快照。 |
| ZIP 内许可 | 归档文件目录中没有 LICENSE、README、copyright 或 terms；除 JPEG/XML 外仅天气光照说明、CSV 与两个 split TXT。未找到明确对外置照片数据授予 MIT 的额外声明。故**仓库 MIT 已确认，照片许可仍待澄清**，不自动采纳或再分发。 |

获取回执：[acquisition.json](../../datasets/raw/fod-a-v2.1/acquisition.json)；来源原文：[author_README.md](../../datasets/raw/fod-a-v2.1/author_README.md)、[author_LICENSE](../../datasets/raw/fod-a-v2.1/author_LICENSE)。归档留在 `datasets/raw/fod-a-v2.1/`，没有进入已封装的 v0.7.0 交付包。

## 标签质量与实际样本单位

解析 **33,793 个 XML + 33,793 个 JPEG 条目**，所有 XML 声称 300×300，共 **34,472 个标注实例、31 类**。33,114 张有一个实例；679 张有两个实例，全部是 `Label+Pliers`。这不证明背景中没有未标注物体，仅描述作者标注。

| 原始类别 | 图数 = 该类实例数 | 本轮处理 |
|---|---:|---|
| Bolt | 3,300 | 单件身份候选 |
| Nut | 1,303 | 单件身份候选；关键正例 |
| Washer | 2,139 | 单件身份候选；检查 nut 纠错是否伤害真 washer |
| BoltWasher | 1,017 | 组合类，排除；不拆解或改标 |
| BoltNutSet | 514 | 组合类，排除；不拆解或改标 |
| Screw | 157 | 保留原类，未自动映射到 Bolt |

“完整元数据候选”的预先定义：所有标注对象均为原名 Bolt/Nut/Washer，标注总数 1–12、每类不超过 3，图/XML 配对存在、框为有效有限正面积且在图内，作者的 occluded/truncated/difficult 均为 0。符合的 **6,742 张全是 1 件**；2–12 件候选 **0**，多目标类别混合图 **0**。因此这里只能支持单件身份诊断；没有 bracket 阳性，其他三类为 0 也只是标注范围内的推导，不证明全图四类物体已被穷尽检查。

全部 XML 检查未见缺图、文件名错配、非法框；所有 34,472 个对象的三项标记均为 0，不能把作者统一的 0 标记当作我们已看图确认无遮挡。原文件没有被修正。

## 原 split 与独立性风险

| 原文件 | 行数 | 不重复 ID 数 | 问题 |
|---|---:|---:|---|
| trainval.txt | 25,345 | 25,298 | 重复行 47 |
| test.txt | 8,448 | 8,429 | 重复行 19 |

两份划分共享 **4 个 ID**：`014567`、`015731`、`016653`、`016763`；它们分别是 AdjustableClamp、AdjustableWrench、BoltNutSet、BoltNutSet。另有 **70 张** `033723`–`033792` 未出现在两份文件中。虽然这 4 个重叠 ID 不在上述原子类候选中，官方 split 也不能不加审查地称为干净独立划分。

**候选子集的限定：** 对 6,742 张 Bolt/Nut/Washer 原子候选单独复核，原 trainval 含 **5,012**、test 含 **1,730**，候选内没有重复 ID、跨集合交集或遗漏。不能把全库 split 的问题误称为候选已经发生同 ID 泄漏；候选仍未解决的是视频/实物相关性，二者是不同问题。

所有 XML 的 `folder=frame`，`source/database`、`source/annotation`、`source/image` 均为 `Unknown`。文件名为连续数字 ID；CSV 只有 File/Weather/Light，未含原视频或实物身份。`track_id` 和 keyframe 是局部跟踪属性，缺少视频作用域时不能当全局唯一物体 ID。**不能推测数字连续就代表原视频边界，不能靠随机抽帧构造独立留出。**

原划分有 12,754 对相邻数字 ID 横跨 trainval/test；这只是可复算的相邻 ID 指标，不是 12,754 对已确认近重复。JPEG ZIP 条目中没有同 CRC32+字节大小的组；CRC 结果不是感知重复证明。未解码图像，所以视觉近重复检查未做，独立视频/实物总数仍为 unknown。

影响与处理：原始分组不可恢复时，相关视频帧最多作为开发身份诊断；停止该来源的独立留出构建。不得用帧数计算为同等数量的独立物体，或将其单件分类结果宣传成料包清点成绩。

## 可复算脚本与证据

```bash
python3 scripts/v08/acquire_foda.py
python3 scripts/v08/audit_foda_metadata.py
```

- [acquire_foda.py](../../scripts/v08/acquire_foda.py)：标准库获取作者固定版本来源和公开归档，流式 SHA-256，重跑时核对已保存归档而不覆盖；不会执行外部脚本或解码图片。
- [audit_foda_metadata.py](../../scripts/v08/audit_foda_metadata.py)：只读 ZIP 文件元数据、XML 和 CSV/TXT，保存全部标签清单及上述规则的候选清单；不取图像像素。
- [audit_summary.json](../../datasets/manifests/v0.8/fod-a-v2.1/audit_summary.json)：完整 31 类统计、原 split 重复频次/重叠/遗漏、来源字段、有效性结果和输出哈希。本文数字由此生成；它的时间字段会在重跑时更新。
- [annotation_metadata.jsonl](../../datasets/manifests/v0.8/fod-a-v2.1/annotation_metadata.jsonl)：全部 XML 的路径、原标签/框/属性及 XML SHA-256；SHA-256 `a246c23f28bfa9d253c26eabee7341dda846a82306bb1b485dce7a072016ab2b`。
- [metadata_candidates.jsonl](../../datasets/manifests/v0.8/fod-a-v2.1/metadata_candidates.jsonl)：6,742 条元数据合规单件候选；SHA-256 `ebd765d31dd2d5b3fbf50e72a73708a9e2931ecac7ef871c9757fb89c46bb0e3`。该名称不表示图片许可或独立性已经通过。
- [zip_file_metadata.jsonl](../../datasets/manifests/v0.8/fod-a-v2.1/zip_file_metadata.jsonl)：完整 ZIP 路径、大小、CRC 与归档时间；SHA-256 `6e286e76220ed9e6a72ba897d3c1d13b3b719fd7c337df5c0c357ed3245bac1d`。

## 已完成的作者代码与原始 ZIP 目录追溯

2026-10-02 07:53 KST 完成只读追溯。作者仓库确有 [VOC 转换器 v1.2](https://github.com/FOD-UNOmaha/FOD-data/blob/a22e5bd5c314f4c7b5d5c5f01224db453c62248f/Tools/FODtoPascal/FODtoPASCAL-Version-1.2.zip)，文件仅 3,234 B；本轮仅解读源码，没有执行。源码的 `traverse_dataset` 以没有显式排序的 `os.walk`/文件列表收集 XML，随后递增编号，`update_files` 用新编号改写 filename，没有保存原路径与 VOC ID 的映射表。仓库完整目录也未提供这样的映射表。**因此源码说明了编号生成方式，却不能恢复本次作者运行时的文件遍历顺序。** 不能拿当前 ZIP 顺序、字母排序或连续数字直接补成真映射。

作者原始格式 ZIP 支持 HTTP Range。只取得：

| 响应 | 取得字节 | 核查 |
|---|---:|---|
| 文件尾部 `bytes=-65557` | 65,557 | HTTP 206，Content-Range 指示整个文件为 8,925,497,958 B |
| 中央目录 `bytes=8915289897-8925497859` | 10,207,963 | HTTP 206，位置及长度与 ZIP64 尾记录一致 |

**没有下载 8.93 GB 原包或任何原包 PNG/XML 内容。** 中央目录包含 68,180 条目；其中 33,863 PNG、33,863 XML 分布在 150 个原始帧目录，另有天气光照 TXT/CSV，没有许可或映射表文件。可见 `GOPR0182_Nut1`、`GOPR0182_Nut2`、`DJI_Washer1` 等目录名。作者扩展工具用视频文件名加增量号创建目录，所以这些是比裸数字更有意义的采集线索；同一源视频的多个切段和同一实物的复拍仍可能相关，不能把 150 目录直接当 150 个独立实物。

原始目录的 33,863 帧与 VOC 的 33,793 图也不一一等长。转换代码会排除空标注，并在排除前将编号加入 split 列表；这为所见重复/遗漏提供了一个机制解释，但本轮未读取原始 XML、未执行转换，也未验证作者实际生成过程，所以不把它写成已证实的唯一根因。

此阶段结论：**已存在原始采集目录，但目录和转换源码本身不足以证明原始目录 → 当前 VOC 图的对应关系，当前不建立独立留出。** 下一步仅允许比较有依据的标注指纹；不能用目录顺序观察充当映射完成。照片许可和物理实物身份仍需分别处理。

复算入口：[inspect_foda_lineage.py](../../scripts/v08/inspect_foda_lineage.py)。它遇到非 206 响应就关闭大包响应而不读取整包，目录读取上限 32 MiB。证据：[inspection.json](../../datasets/raw/fod-a-v2.1/lineage/inspection.json)、[原始 ZIP 目录清单](../../datasets/raw/fod-a-v2.1/lineage/original_zip_file_metadata.jsonl)、[只读保存的转换源码](../../datasets/raw/fod-a-v2.1/lineage/converter_FODtoPASCAL.py)、[作者帧提取源码](../../datasets/raw/fod-a-v2.1/lineage/FODExpansionTool.py)。任何图片查看、开发推理、许可采纳或正式分组都尚未发生。

## 有限 XML Range 追溯方案

目录元数据进一步证明，33,863 个原始 XML 可分成 **150 段连续区间，合计 13,881,727 B，最大一段 502,888 B**，这些区间不包含图像 payload。因此可以只取 XML 做精确对应，而无需几千次请求或全包下载。预先保存的范围方案见 [original_xml_range_plan.json](../../datasets/raw/fod-a-v2.1/lineage/original_xml_range_plan.json)。

只读作者 [DatasetResizer v1.0](https://github.com/FOD-UNOmaha/FOD-data/blob/a22e5bd5c314f4c7b5d5c5f01224db453c62248f/Tools/DatasetResizer/DatasetResizer-Version-1.0.zip) 可知，框坐标按宽高比例缩放后 `round(..., 4)`。本地追溯代码只重写该明确转换和 VOC 默认字段插入规则，删除被改名的 filename 后，对保留全部其他 XML 结构的规范表示作精确指纹匹配；原始端和 VOC 端都必须唯一。没有匹配、多重匹配或冲突一律 unknown，不容许靠近似框、相邻编号、目录顺序或类别数量来补齐。

执行入口：[recover_foda_groups.py](../../scripts/v08/recover_foda_groups.py)。范围、CRC/大小和每段 SHA-256 均留证；不解码图像、不运行作者程序。这只尝试恢复标注来源关系，不证明不同目录是不同实物，也不解决照片许可。结果以独立的 group recovery 记录为准，未据此建立正式留出。

**本阶段已完成：** 全库 33,768 唯一对应、25 多重；候选 6,740 唯一对应、2 多重。所有原始 XML 的解压大小及 CRC 已核对，原始大包的 PNG 内容未取。26 个恢复目录全部跨越作者 trainval/test，因此即使候选 ID 不重复，该划分也不是来源目录隔离。完整方法、未匹配边界和散列见 [FODA_GROUP_RECOVERY.md](FODA_GROUP_RECOVERY.md)。
