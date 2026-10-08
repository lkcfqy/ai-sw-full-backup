# MANTA 身份组件：已曝光跨来源诊断草案

2026-10-02。**仅 metadata 建议，尚未授权执行或冻结跨来源实验。** 本轮只读取已有 JSON/文档，没有裁图、读取图片像素、加载模型，也没有接触 FOD held-back36、新 LOCO24 或 MANTA test。本稿不改变 MANTA trainer、生产默认或任何既有标签与 split。

## 启动条件与目的

只有固定 MANTA **内部 256 条**验证的完整独立审计通过，且第10轮、固定 softmax 最大值≥0.9 的既定门槛通过（每类连通组 macro 正确覆盖≥75%，W/E/N=0），根任务才考虑另行批准本诊断。内部失败就停止，不用外部数据救选 epoch、阈值、预处理或样本。当前没有写入任何新模型成绩。

优先检查已完成三类检测器实验的完整 **80 张 validation 整图：44 Screws + 36 FOD**。目标是检验固定两类组件能否跨来源识别；使用作者标注定位的 ROI，**不是独立检测、全图计数、BOM 验证或新留出成绩**。原验证图已参加三类检测器12轮验证与选模，不声称此前未曝光；MANTA 初始化的预训练曝光同样未知。

## 完整作者目标分母

| 来源及原分组 | 图数 | nut | washer | bolt 拒绝对照 | 标注语义 |
|---|---:|---:|---:|---:|---|
| Screws 原 validation，保守作为一个 collection | 44 | 156 | 0 | 387 | 原数字类型7/9/10/11按既有教学映射投影为nut；不是作者直接英文命名 |
| FOD `GOPR0183` | 12 | 12 | 0 | 0 | 作者单目标 Nut |
| FOD `unprefixed_Washer` | 12 | 0 | 12 | 0 | 作者单目标 Washer；无前缀来源身份未知 |
| FOD `GOPR0181` | 12 | 0 | 0 | 12 | 作者单目标 Bolt |
| **合计** | **80** | **168** | **12** | **399** | **180 N/W + 399 bolt = 579 ROI** |

FOD 有三个既有来源—类别组合，不能拆成任意独立物件或拍摄 session；不同类别与背景仍可能混杂。Screws 156 个 nut 的原类型分布为7:44、9:36、10:38、11:38。完整保留同图所有作者目标，不把相邻 ROI 当独立物理样本。579 是一次完整诊断的候选数量，不能沿用旧“80/128次编码”预算名称。

## 尺寸与裁切：不删难例

| 来源/类 | 分母 | 原框短边<16像素 | ≥16像素 | 已有 `bbox_clipped=true` |
|---|---:|---:|---:|---:|
| Screws nut | 156 | 0 | 156 | 1 |
| Screws bolt | 387 | 0 | 387 | 8 |
| FOD Nut | 12 | 0 | 12 | 不由该字段提供 |
| FOD Washer | 12 | 4 | 8 | 不由该字段提供 |
| FOD Bolt | 12 | 4 | 8 | 不由该字段提供 |

Screws 同时保存原定向框和派生 AABB：原定向短边最小 nut55 / bolt43 像素，中位90.8018 / 103；其派生 AABB 的<16计数也为0。FOD 使用现有原图 `box_xyxy`，最小短边 Nut20.8479、Washer6.9438、Bolt9.1863像素。所有 tiny、边缘裁切与失败都留在分母；上采样不会产生新的形态细节。Screws 被裁切 nut 为原 annotation 89005，8个 bolt 为15018/56009/59006/145005/203014/361005/365014/368009。

若之后批准，必须在首次裁图前冻结完整579条顺序、原图/标注SHA、原坐标及唯一像素取整规则。建议直接使用现有原图坐标 AABB 的 floor/ceil边界并限制在原图内，不加人工余量、不旋转挑视角、不按模型或目检结果换样本；记录原定向框、实际像素裁区及裁切标记。AABB可能含邻近物体或背景，不能冒充无干扰单物体认证。

## 固定方法与报告

- 仅用已通过内部门槛的**固定第10轮权重**，绑定其实际SHA。沿用RGB→L→RGB、保持比例缩放并补黑至224×224、既定ImageNet标准化和0.9阈值；不重新设图库、校准阈值、增强或多视角。最终输入与原图/作者框各自留SHA。
- N/W完整180条报告C/W/U/E/N、双向错类、按来源×类别及tiny/clipped子组。washer仅12条，不能用168个nut的总分掩盖；记录数与原图/来源组数分开。保留固定argmax、常答nut、常答washer、全拒答解析对照。
- 399个bolt是**开放类别拒绝对照**：分别报被接收为nut/washer、unknown、E/N及误接收率。unknown只表示拒答，不能称识别出了bolt；0.9不保证开放类别可靠。
- 每条只尝试一次，完整保留失败与未尝试，不换样本或重复取最好结果。即使通过也仅是作者框定位的组件证据；进入系统前仍需独立proposal召回、定位错误、时延和完整旧51开发回归，不能直接晋升产品。

## 为什么不先用旧51或旧参考80

旧51中仅35张Screws安全裁图有作者实例定位，合计29nut+57bolt=86目标，**作者washer阳性为0**；其余16张LOCO没有作者实例框。故旧51不适合作第一份两类跨来源诊断。它与本次44张Screws原图SHA无交集，但这不是物理独立证明，也不能消除两批数据均已曝光的事实。

此前 `REFERENCE_RETRIEVAL_METADATA_DRAFT` 的 gallery8/calibration36/evaluation36是**未生成裁区、未编码的80条metadata提案**，混用了既有train与validation并因尺寸/来源混杂暂不推进。本稿的80是完整检测器validation整图，分母为579作者目标；两者不是同一名单，**不能把旧80提案的tiny统计搬到这里**。

## 可复算来源（本稿读取时SHA-256）

| 路径 | SHA-256 |
|---|---|
| `datasets/derived/public_detector_v1/val.json` | `cd2604d0d11bee0824188f287168490436085e150784a599822180edef311d66` |
| `datasets/derived/public_detector_v1/manifest.json` | `27044ecee0fd81d3f29b7cb70c5c8252f08d6588cbba46d346388b2cf83adf23` |
| `datasets/derived/v0.8/foda_grouped_v1/validation.json` | `9eb41e12060da09732f9c5a1b1160feafcc98222e0d7cd836dd90aff5d6e958c` |
| `training-runs/v0.8/grouped_detector_v1/protocol.json` | `0230682fac7d542cf6669a42a6ba274402747908795da874b80f1f33c54be24a` |
| `docs/v0.8/SCREWS_CATEGORY_SEMANTICS_REVIEW.md` | `42acee3eea618463969ba2116b65b067a7d0e42eacaa30ce527b3e7e17622e27` |
| `docs/v0.8/REFERENCE_RETRIEVAL_METADATA_DRAFT.json` | `10c8b2240eb97fd431e317511b81c7eaae117bc036f404a6046806e39555e7a9` |
| `docs/v0.8/MANTA_CLASSIFIER_PROTOCOL_V1.md` | `cbb3ca611bd4ba3be4c4a082f7d2b4d7b8319713bc3f04a2a62724acfa9a0959` |
| `docs/v0.8/manta_classifier_freeze_v1/freeze.json` | `226f739d011c5f4095888251b572663fd2c12a485c6b48d8c36e206553111f9e` |
| `datasets/derived/v0.7/public_paired_v1/manifest.json` | `efe4633e873d45032101a26e035c23d267bafa6605d147d3d2f7fcb51b697643` |

统计只由上述现成标注元数据复算，未再次读取原图字节核验；未来真实准备仍必须在解码前核对源图字节及绑定。不修改原始真值、历史分母或原实验记录。
