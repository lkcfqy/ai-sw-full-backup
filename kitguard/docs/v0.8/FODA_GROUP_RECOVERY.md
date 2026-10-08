# FOD-A 标注来源组恢复：严格 XML 匹配

2026-10-02 KST。此记录补充 [FODA_ACQUISITION.md](FODA_ACQUISITION.md)，**没有覆盖最初元数据审计或改动任何作者原文件**。原 `audit_summary.json` 的 SHA-256 仍为 `7b7f2b9da74126762f0c3d4151a196c6cee3a65dc785558347f5899f69278b4a`。

## 结果与当前边界

6,742 张原子类别候选中，**6,740 张**的标注与原始 400×400 数据经过明确转换后的标注形成一对一精确对应，可恢复到 **26 个原始标注目录**。另 **2 张**存在多重对应，来源保持 unknown。没有按编号、目录顺序、类别频次或近似框强行配对。

这是**标注来源关系恢复**，不是已建立正式留出；没有图像像素匹配，也没有证实不同目录使用不同实物。照片数据许可仍未明确。所有图片继续未浏览、未解码、未推理、未发布。

| 范围 | 唯一精确对应 | 多重对应 | 无匹配 |
|---|---:|---:|---:|
| VOC 全库 33,793 图 | 33,768 | 25 | 0 |
| Bolt/Nut/Washer 候选 6,742 图 | 6,740 | 2 | 0 |

| 候选类别 | 唯一对应帧数 | 恢复的标注来源目录数 |
|---|---:|---:|
| Bolt | 3,298 | 12 |
| Nut | 1,303 | 8 |
| Washer | 2,139 | 6 |

候选 `012727`、`012728` 共享指纹 `b5edf480e7624bc42cd06414f0b554656f9b5795beacd3a2f8ed4eec802f117f`，原始端也有两条相同指纹，因此没有唯一的图级对应。它们的 `original_xml_path` 和 `annotation_source_directory` 都保留 null。

## 只取 XML 的范围与核对

已保存的 ZIP64 中央目录给出每个 XML 的偏移、压缩大小、解压大小和 CRC32。按物理偏移计算，每个原始 Annotations 文件夹的 XML 是连续区间；核查区间内没有 PNG 或其他图像 payload。

- 150 个 HTTP Range，总 **13,881,727 B**，最大单段 **502,888 B**；全部返回 **206**，Content-Range 与请求起止、文件总大小一致，实际接收字节数逐段一致。
- 每段的请求区间、响应区间、实际字节数和 SHA-256 单独保存在 `datasets/raw/fod-a-v2.1/lineage/xml_range_chunks/*.json`；响应体对应同名 `.bin`。
- 对 33,863 个 XML，逐一核对 ZIP 本地文件头中的路径、解压字节数及 CRC32；全部通过，XML SHA-256 另存。没有执行作者代码。
- 原始 XML 中有 **70 条空标注**。这是实际读取 XML 后的发现；不能因为也有 70 个 VOC ID 未列入原 split，就把两者宣称为相同来源或同一组文件。

目录及尾部先前读取 10,273,520 B，加本轮 XML 共读取原始大包的 **24,155,247 B 元数据/标注片段**，没有下载 8,925,497,958 B 的整包或原包图像内容。

## 匹配协议

预先保存的协议为 [group_recovery_policy.json](../../datasets/manifests/v0.8/fod-a-v2.1/group_recovery_policy.json)：

1. 根据只读核查的作者 VOC 转换器，插入相同默认字段；按作者 resizer 的规则将坐标乘目标/来源宽高比，再保留 4 位小数，并将 size 改为 300×300。
2. filename 被作者重命名，故只排除该字段。其余 XML 元素、顺序、属性和值均进入指纹；忽略格式空白，数值表示规范化。包含类别、全部框、track_id、keyframe 等信息，不以类别单独配对。
3. 只接受原始端一条、VOC 端一条的精确指纹。零匹配、多匹配和任一冲突保持 unknown。所有结果均留在完整 JSONL，未删除失败项。

匹配结果支持当前标注变换与来源目录一致；它不证明图片字节一致或作者未误配图/XML。未来若进入正式验证，还须独立核实图片/标注关系与许可，且不能把反复拍摄同一实物的帧当独立物体。

## 官方划分的正确解释

候选子集自身 trainval **5,012**、test **1,730**，没有重复 ID、交集或遗漏；[candidate_split_audit.json](../../datasets/manifests/v0.8/fod-a-v2.1/candidate_split_audit.json) 单列这个范围，避免把全库 4 个重复交叉 ID 的问题误加到候选上。

但是，**26/26 个已恢复的标注来源目录都同时出现于作者 trainval 和 test**。因此候选没有同 ID 泄漏，也仍不是按采集来源目录隔离的划分。若使用作者 split 训练和测试，不能声称已经隔离原视频来源。

目录名还提示更粗的关联：例如 `GOPR0181_Bolt1`–`GOPR0181_Bolt5`、`GOPR0182_Nut1/2`、`GOPR0183_Nut1/2`。作者提取工具按源视频名加增量号创建帧目录，多个目录可能是同一源视频的不同切段；同一实物跨其他目录复拍也未知。**26 只是已恢复的目录数，不是 26 个独立视频或独立实物的结论。**

## 可复算文件

依次运行以下代码可重建范围并复核已有下载；不需要执行作者程序。`plan_foda_xml_ranges.py` 若发现重算范围与保留计划不同会拒绝覆盖。

```bash
python3 scripts/v08/inspect_foda_lineage.py
python3 scripts/v08/plan_foda_xml_ranges.py
python3 scripts/v08/recover_foda_groups.py
```

已有元数据/段文件无需重新取得即可供复核。独立结果：

| 文件 | SHA-256 |
|---|---|
| [group_recovery_summary.json](../../datasets/manifests/v0.8/fod-a-v2.1/group_recovery_summary.json) | `5b658609a3b1084afbcf8d33f7e400dc15b45c192d7ba3cdc1057797d49aa32c` |
| [voc_original_group_mapping.jsonl](../../datasets/manifests/v0.8/fod-a-v2.1/voc_original_group_mapping.jsonl) | `34757eef11da790ff0b54e148b3d15c8110361550a87d0e51e05b80e523755fa` |
| [original_xml_fingerprints.jsonl](../../datasets/manifests/v0.8/fod-a-v2.1/original_xml_fingerprints.jsonl) | `dd27c2b06ca5031a5ee11f53acd178c55933c05c5d1db7037e973a4b29ca0fe6` |
| [candidate_split_audit.json](../../datasets/manifests/v0.8/fod-a-v2.1/candidate_split_audit.json) | `e8255fda699fe4504aeb0ec6892bad16f068fff992e8eecd5a312c29c0ec4470` |

后续可以在许可明确后考虑只用唯一对应项、合并可能同源的目录、以整个来源组划分来建立单件身份诊断。未知对应项不晋升，物理对象身份未知须保留，不会把该来源改称混合 BOM 计数验证集。本轮没有创建新的训练/开发/留出划分，也没有模型成绩。
