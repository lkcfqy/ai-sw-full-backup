# 公开实拍数据来源与适用范围

记录日期：2026-09-26（韩国时间）。原始照片、标注、README 均与程序代码分目录保留；没有提交网站联系表单、登录账号或发送邮件。没有将拼图、生成图或原图裁剪冒充完整实拍场景。

## MVTec Screws v1.0：已取得并校验

- 作者：[MVTec Software GmbH](https://www.mvtec.com/research-teaching/datasets/mvtec-screws)。
- 下载依据：[Neuromatch Academy 官方课程](https://deeplearning.neuromatch.io/projects/ComputerVision/screws.html)明确链接到公开 [OSF 文件](https://osf.io/ruca6/download)。[OSF 项目元数据](https://api.osf.io/v2/nodes/hygbm/)标明项目名为 Neuromatch academy，描述为教学数据存储与其他来源的镜像。
- 原始归档：`datasets/archives/mvtec_screws_v1.0.tar.gz`，1,361,662,840 字节。
- SHA-256：`a742c5744cea973eca5d9eeee5896c8b458d3d695fb107a58707a9e7e0cc1342`，本地计算值与 OSF 文件 API 提供的 SHA-256 一致。
- 解包位置：`datasets/raw/mvtec_screws_v1.0/`。原文件只读，保留 384 张完整实拍 PNG、全量 COCO JSON、原 train/val/test JSON、HALCON 标注及原 README；不执行下载内容中的代码。
- 索引：`datasets/manifests/mvtec_screws/manifest.json`，含每图来源路径、SHA-256、原 split、原类别计数、原标注 ID 与 KitGuard 粗类投影。`raw_files_sha256.json` 为全部原始解包文件清单。
- 来源网页和 OSF 元数据副本：`datasets/provenance/mvtec_screws/`。

原包有 **384 张图和 4,427 条唯一实例标注**；官网和原 README 写的是 4,426。下载包经过其发布镜像的完整 SHA 校验，故保留原包实际的 4,427 条，未擅自删除一条以凑说明文字。官方 split 为 train 269 图/3,119 实例，val 55 图/647 实例，test 60 图/661 实例。各 split 的 `image_id` 从 1 重新编号，必须按 `file_name` 联结全量标注；文件名之间没有重叠。

### 类别投影

原标注的真实类名只有 `type_001` 至 `type_013`。下表英语说明来自 Neuromatch 课程，保留为解释性别名，不修改原始类名。KitGuard 的 `bolt` 在当前观察器中定义为“带头螺纹件”粗类，因此包含不同螺钉；这不是精确 SKU、长度或螺纹规格验证。

| 原 ID / 类名 | Neuromatch 解释性别名 | KitGuard 粗类 |
|---|---|---|
| 1 / type_001 | long lag screw | bolt |
| 2 / type_002 | lag wood screw | bolt |
| 3 / type_003 | wood screw | bolt |
| 4 / type_004 | short wood screw | bolt |
| 5 / type_005 | shiny screw | bolt |
| 6 / type_006 | black oxide screw | bolt |
| 7 / type_007 | nut | nut |
| 8 / type_008 | bolt | bolt |
| 9 / type_009 | large nut | nut |
| 10 / type_010 | nut | nut |
| 11 / type_011 | nut | nut |
| 12 / type_012 | machine screw | bolt |
| 13 / type_013 | short machine screw | bolt |

所有数量标签从原实例标注计数得到，未用待测大模型生成“真值”。所有图的 washer/bracket 标签为 0；本数据没有这两类的正例。

### 产品范围

按原图计数后，**每个粗类都不超过 3 件的图为 0 张**。总件数不超过 12 的图有 222 张（train 155、val 30、test 37），但至少一类超过 3 件。因此这些图片用于**超出当前订单单类范围的计数压力测试**；不能把它们并入“符合当前产品范围的订单核验成功率”，也没有为了适配数据而扩张产品规格。

例：`images/screws_022.png` 为官方 test 原图，原标注投影为 bolt 6、nut 2、washer 0、bracket 0；已视觉检查其为木板上真实零件图。是否用于盲测由评估清单另行预注册，不能因为模型表现好而挑选。

## MVTec LOCO AD screw_bag：已取得，完整归档与暂存对照均通过

[MVTec 官方页面](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad)当前使用下载表单；本次没有提交该表单。使用 [Anomalib 官方数据适配器](https://github.com/open-edge-platform/anomalib/blob/bc94f1abebbc06215aa2f992e7c44cb7c19b33cb/src/anomalib/data/datasets/image/mvtec_loco.py)公开引用的 MyDrive 原包链接与固定 SHA-256核对来源。适配器原文及来源记录已保存在 `datasets/provenance/mvtec_loco/`。

- 完整归档大小：6,126,996,224 字节。
- 本地完整包 SHA-256：`9e7c84dba550fd2e59d8e9e231c929c45ba737b6b6a6d3814100f54d63aae687`，与固定的上游适配器预期值一致。原包保存于 `datasets/archives/mvtec_loco_anomaly_detection.tar.xz`，只读保留。
- 完整归档尾部曾遇到主机明显降速；2026-09-26 已完成续传、全包尺寸/SHA 检查和所需类别解包。当前正式原件目录为 `datasets/raw/mvtec_loco_ad/`，其他类别保留在完整归档内，不重复解包。
- 较早完整接收的归档前缀包含整个 `screw_bag` 区段，直到下一个 `juice_bottle` 目录边界。曾将所需类别原件保存于 `datasets/staging/mvtec_loco_ad/`，先核对原始 tar 尺寸、全部原图/掩码完整像素解码、本地 SHA 和作者公布数量，供开发评测。暂存原件及其历史状态记录继续保留。
- 实际取得 **761 张实拍图、243 张原掩码、3 个原文档（readme、license、defects_config）**，共 1,007 个原文件；1,004 张 PNG 均为 1600×1100，已全部成功完整解码。train good 360、validation good 60、test good 122、test logical 137、test structural 82，与作者论文的该类别数量完全一致。
- 历史暂存 `acquisition_status.json`、派生清单及其冻结评测清单仍按当时真实状态记录 `full_archive_verification_pending: true`，不追改既往开发记录。后续核验报告 `datasets/manifests/mvtec_loco_screw_bag/pending_to_verified_audit.json` 证明：1,007 个原文件的尺寸和 SHA 与完整验证后的原包解件完全一致，差异 **0**，并确认 v1/v2 评测的 64 个 case 集合、顺序、划分、原图 SHA、真值和原掩码标注依据全部一致。该正式来源审计的 `full_archive_verification_pending` 为 `false`，正式 benchmark 已记录完整原包 SHA。因此先前使用暂存原图的评测，其来源完整性已获得后续验证，不因本次迁移而要求重跑。
- 两个归档合计 7,488,659,064 字节，低于本阶段 9GB 下载预算。

原论文 [§3.1](https://link.springer.com/content/pdf/10.1007/s11263-022-01578-9.pdf)明确正常袋含一长螺丝、一短螺丝、两螺母、两垫圈，可以投影为 bolt 2、nut 2、washer 2、bracket 0。原 `good` 图使用该正常组成规则。

### 保守派生数量真值

异常图仅在**恰好一个原始掩码，且掩码恰好一个非零缺陷像素值，且作者 `defects_config.json` 对应名称明确表示增加/缺少指定数量**时派生完整计数。以正常组成加减作者的数量标签；记录原像素值、`defect_name`、掩码路径和 SHA。其他图的完整计数留空，不将掩码区域数当成零件数量，不让待测模型自己生成真值。

实际得到 48 张符合每类≤3的明确数量异常：多/少 1 个螺纹件各 12 张，多/少 1 个螺母各 6 张，多/少 1 个垫圈各 6 张。另有 171 张异常图在此严格规则下不赋计数标签，包括多个掩码、混合缺陷、长度替换和结构损坏等。全部候选为 542 张正常图 + 48 张数量异常 = 590 张。

### 预先选择与指标版本

冻结文件：`datasets/manifests/mvtec_loco_screw_bag_pending/benchmark_v1.json`，SHA-256 为 `fb17e1a2e4fb516ba1ca5efd5e29ed6e89216342b7d2375f9789939fd65d5bf5`。seed 为 `KitGuard-LOCO-v1-20260926`，按 `SHA256(seed + '|' + 原图SHA)` 排序；选择不参考模型输出。

- 开发：8 张官方 train-good + 8 张官方 test 的明确数量异常，共 16 张。
- 留出：24 张官方 test-good + 24 张未用于开发的明确数量异常，共 48 张。
- 每组内交替正常/异常，保留既定 SHA 排序。这里明确将 8 张官方 test 异常重划为开发，属于自定义划分，不能冒充未改动的官方 test 评测。
- 恒定 2+2+2 的正常图单独报告，不能用它掩盖“总猜222”的模型。数量异常应单独报告，静态订单核验也与真实补件/复拍过程区分。

**v2 是查看 8B 开发结果后完善的指标版本，采用时留出模型推理尚未运行。** 它为每个 case 加入作者的正常工单 `nominal_requirements={bolt:2,nut:2,washer:2,bracket:0}`，检验真实数量异常是否被错误放行。v1及既往开发记录保留；v2 的图像集合、顺序、划分、原图 SHA、计数真值和标注依据全部不变，程序逐字段比较确认只有每 case 新增正常工单字段。

`benchmark_v2.json` SHA-256：`bbfe01e6a0c9887367ce86807dd46b939e505309d1e97a8d0d874e0f48ec40ff`。v2 记录 v1 SHA、原选择冻结时间与指标修订时机，避免把开发后确定的指标说成最初预注册。

完整归档核验后新增正式目录 `datasets/manifests/mvtec_loco_screw_bag/`，保留历史暂存目录不变。正式 v1 SHA 为 `2a429c3170f08eff1d478d2ed12e47dda95e29f745f623e62f7113e89f590ddc`；正式 v2 SHA 为 `3166a331b981635170794dbef4989ed7294a54f89fd56e1aeac4993163700cfb`。SHA 差异来自来源状态和原图位置等元数据，`pending_to_verified_audit.json` 逐 case 证明图像、标签、顺序、划分和掩码证据未变。正式文件的创建/冻结时间表示后续重新生成时间，原始选例冻结时间由未变的暂存文件证明，审计也单列该历史时间。旧运行仍引用原清单 SHA，新运行可以使用正式清单，不能因此把旧开发输出改写成新一次实验。

## 许可与报告边界

两个数据集的原图和标注均为 **CC BY-NC-SA 4.0**，应保留作者署名、非商业限制和适用的相同方式共享条件。依据是 MVTec 官方页面及归档内原 README，不能使用转存页面较宽松的标签覆盖原始许可。数据及其派生标注的许可与本项目代码分别处理；后续商业化须另行解决许可，比赛材料应准确披露公开数据来源。

公开基准图片可能进入基础模型预训练，无法保证对 Qwen 完全“从未见过”。报告只能称公开数据评估；不能由此声称陌生工厂泛化或实际生产准确率。静态照片也不能证明“用户按建议分开零件并重新拍摄”的真实行为闭环；该部分要与软件状态机测试、录制回放和真正连续复拍分别报告。

## 复现

```sh
.venv/bin/python scripts/fetch_public_data.py --dataset screws --workers 6
.venv/bin/python scripts/fetch_public_data.py --dataset loco --workers 8 --max-download-bytes 9000000000
```

获取脚本支持按固定大小分片断点重用，核对 HTTP 范围和最终 SHA；拒绝不符预期的原包、目录穿越、符号链接、硬链接和特殊文件。成功后原始文件设为只读。清单可使用 `--inventory-only` 从本地原件重建。
