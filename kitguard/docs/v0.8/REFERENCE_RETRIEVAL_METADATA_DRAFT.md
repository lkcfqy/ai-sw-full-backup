# 参考特征检索：既有开发数据清单与可行性草案

2026-10-02。**仅 metadata 提案；未授权像素 QA、特征编码、模型实现或推理，尚未冻结实验。** 本文件不改变正在进行的旧 51 候选或下一份 24 图比较的方法集。精确 80 条裁区记录、原图/标注元数据、来源 SHA、排序键见 [JSON 草案](REFERENCE_RETRIEVAL_METADATA_DRAFT.json)。本轮没有读取图像字节、解码/显示像素、加载模型，未读取 `held_back.json`、新 LOCO 24 或 MANTA test。

## 可行性结论

现有已用于训练/验证的数据足以组成 **gallery 8 + calibration 36 + evaluation 36 = 80 个单裁区**，每个用途内 Nut/Washer 数量相等，校准与评估各有 12 个 Bolt 拒绝对照。若以后批准，每裁区仅编码一次可落在最多 128 次的预算内；余下 48 次不是增方法、增视图或重试授权。

这只支持**既有开发资料上的组件身份机制诊断**，不是新 holdout、完整图像检测或 BOM 计数。FOD 已曝光来源中 Nut 只有两个保守来源组，**无法在不取用 held-back 的前提下构成纯 FOD 的三角色 Nut 分离**。以下方案把整个 Screws 数据源只用于 gallery，以换取三用途的来源组互斥；没有把 Screws 不同文件虚构成独立采集组。

| 用途 | 类别 | 保守来源 | 原 split | 已曝光可选量 | 提案数量 |
|---|---|---|---|---:|---:|
| gallery | nut | Screws 全集合，只使用 train 的作者 ID 7/9/10/11 各一个实例 | train | 777 个项目投影 nut 实例 | 4 |
| gallery | Washer | GOPR0194 | train | 50 | 4 |
| calibration | Nut | GOPR0183 | validation | 12 | 12 |
| calibration | Washer | GOPR0197 | train | 50 | 12 |
| calibration | Bolt 拒绝 | GOPR0181 | validation | 12 | 12 |
| evaluation | Nut | unprefixed_Nut | train | 50 | 12 |
| evaluation | Washer | unprefixed_Washer | validation | 12 | 12 |
| evaluation | Bolt 拒绝 | unprefixed_Bolt | train | 50 | 12 |

原 train/validation 身份逐条保留；diagnostic_role 是未来诊断用途，不重分旧训练数据。所有提案图像都属于已完成三类检测器 614/80、12 轮实验的训练或验证数据；不据此推断每张都被人目检过。OWL 预训练是否见过这些图未知。

## 固定的 metadata 选择与来源约束

FOD 在指定组的既有已曝光记录内按 `SHA256(seed|group_id|image_id)` 升序，取表中数量；seed 为 `kitguard-owlv2-component-metadata-draft-20261002-v1`。不按框大小、图像内容或模型成绩筛选。Screws 按同一 seed、固定集合组名和 annotation ID 排序，作者数字类型 7、9、10、11 各取一个，重复原图则顺延；所有同原图实例只能归 gallery。选中的 80 个原图 SHA 均不同。

Screws 提案实例为 `237:a237002`、`097:a97006`、`296:a296005`、`359:a359006`；Washer gallery 为 `016213`、`016609`、`016252`、`016385`。其余逐图 ID、未修改作者框、原像素宽高/短边和路径均在 JSON 中。Screws 同时保留作者定向框宽高及派生 AABB 宽高，不把二者混写。

FOD 的[既有保守组定义](FODA_CONSERVATIVE_GROUPS.md)明确按类别区分 `unprefixed_Nut`、`unprefixed_Washer`、`unprefixed_Bolt`：Nut 对应 Nut1/Nut1a/Nut2/Nut3，Washer 对应 Washer1/Washer1e，Bolt 对应 Bolt1a。本草案另做更保守的 **跨类别 unprefixed 全合并检查**：三个组全部只出现在 evaluation，因此即使把它们视为同一潜在拍摄来源，也无跨用途重叠。这个额外聚合只检查相关风险，不覆盖原 group_id 或旧 split。

GOPR 同编号跨片段合并、不同编号可能复用实物/背景、无前缀目录来源未知的限制全部保留。来源组互斥不等于独立实物、视频或会话；未重新做近重复像素检查。旧去重凭证没有跨组的完全相同图像，但这不能排除近重复。

## 低分辨率是事前停止理由之一

| 用途/类 | 数量 | 作者框短边 <16 原像素 | ≥16 原像素 |
|---|---:|---:|---:|
| gallery nut | 4 | 0 | 4 |
| gallery Washer | 4 | 0 | 4 |
| calibration Nut | 12 | 0 | 12 |
| calibration Washer | 12 | 2 | 10 |
| calibration Bolt | 12 | 4 | 8 |
| evaluation Nut | 12 | **10** | 2 |
| evaluation Washer | 12 | 4 | 8 |
| evaluation Bolt | 12 | 2 | 10 |

evaluation Nut 最小短边为 5.75 像素；其可选的完整 50 图中 39 个框短边小于 16 像素，中位约 10.49 像素。不能承诺这些裁区具有可见螺纹/厚度等身份线索，放大也不会产生新细节。若以后运行，必须事前保留 `<16` / `≥16` 子组且完整报告分母，不能为达到先前草案的 75% 覆盖目标事后删小图或替换难例。

另有显著来源与类别混杂：gallery nut 全来自 Screws，washer 全来自 FOD。参考特征可能更容易区分来源/背景而非零件身份；校准的 FOD Nut 能暴露此失败，却不能消除它。Screws 的 nut 仍是 [Neuromatch 解释名→项目预定投影](SCREWS_CATEGORY_SEMANTICS_REVIEW.md)，不是 MVTec 原作者直接英文命名。FOD 则仅支持作者标出的单目标身份，不能认证全图物件完整性。

因此当前结论是 **清单与分组可行，机制价值未证实，尚不足以建议直接编码**。根任务可先依据上述尺寸和来源混杂否决；若仍认为值得，只能先批准这份固定清单的有限像素 QA，再决定是否冻结单一特征/裁区/校准规则。QA 失败应留记录并停止，不应默默替换样本。

## 可复查依据

JSON 绑定原 FOD train/validation/protocol/duplicate_audit、Screws train/projection、语义审查，以及已完成训练的 protocol/run/独立审计文件 SHA。前六份输入 SHA 与实际训练 protocol 的绑定一致。图像 SHA 来自这些已绑定元数据，本轮未重新读图像字节核 SHA；若未来获准准备裁区，须在解码前核对实际图像字节，并为实际裁区另存 SHA。未生成裁区或修改任何原始来源、标签、实验记录、生产代码。
