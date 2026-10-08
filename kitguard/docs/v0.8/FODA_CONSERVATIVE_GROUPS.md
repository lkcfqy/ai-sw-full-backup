# FOD-A 保守来源关联分组 v1

生成时间：2026-10-01T23:16:29.618653+00:00。仅复算已有 XML 映射元数据；未选图、读图或训练。

26 个已恢复 atomic 目录合并为 **14 个关联风险组、6,740 个单物体候选**；另 2 个 Bolt 候选（`012727`、`012728`）仍为 unknown，不参与后续来源分组划分。

| group_id | 作者类 | 候选数 | 目录数 |
|---|---|---:|---:|
| `DJI_Bolt` | Bolt | 977 | 1 |
| `DJI_Washer` | Washer | 870 | 2 |
| `GOPR0179` | Bolt | 118 | 1 |
| `GOPR0180` | Bolt | 114 | 1 |
| `GOPR0181` | Bolt | 657 | 5 |
| `GOPR0182` | Nut | 196 | 2 |
| `GOPR0183` | Nut | 324 | 2 |
| `GOPR0184` | Bolt | 443 | 2 |
| `GOPR0192` | Bolt | 807 | 1 |
| `GOPR0194` | Washer | 450 | 1 |
| `GOPR0197` | Washer | 477 | 1 |
| `unprefixed_Bolt` | Bolt | 182 | 1 |
| `unprefixed_Nut` | Nut | 783 | 4 |
| `unprefixed_Washer` | Washer | 342 | 2 |

同一 GOPR 数字前缀所有片段合并（本次没有跨类前缀；以后若出现，也必须共享 group_id）。DJI 同作者类全部合并；无此前缀的同作者类全部合并。完整目录成员、各目录计数和输入 SHA-256 见 [conservative_groups_v1.json](../../datasets/manifests/v0.8/fod-a-v2.1/conservative_groups_v1.json)。

**这是关联风险约束，不证明 14 个独立视频、实物或采集环境。** 不同 GOPR 编号仍可能复用实物或背景；未知映射不能靠 ID 顺序补齐。本记录没有分配 dev/validation/held-back，也没有把这些候选变成 BOM 多物体基准。

根代理已决定继续公开图片的本地研究；照片许可适用范围仍未解决，不分发图片或声称商业授权。原先“尚未读图”的阶段记录不回改。
