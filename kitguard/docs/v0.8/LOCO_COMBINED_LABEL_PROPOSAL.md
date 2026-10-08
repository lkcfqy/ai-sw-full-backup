# LOCO 双数量标签：可推导性提案（未冻结、未看图）

**结论：现有作者证据足以支持将全部 24 张定义为一种新的“作者标签推导计数”协议，但这仍是本项目显式推导，不是作者原生四类计数字段。** 旧 manifest 的 `unresolved`/`kitguard_counts:null` 不修改。本提案没有选取、冻结或推理新留出，没有打开照片或 mask 像素。

## 作者依据与实际关系

作者论文《Beyond Dents and Scratches: Logical Constraints in Unsupervised Anomaly Detection and Localization》§3.1 定义正常袋为两螺母、两垫圈、一长螺钉和一短螺钉；项目将后两者投影为 bolt=2。§3.2 说明数据中所有异常均提供 GT 标注；附录 D 和 Table 12 明确列出每种异常对应的 GT 灰度值。其值与原始 `defects_config.json` 一致，故下表依据的是作者定义的标签编码，**不是照片文件名含义，也不是数 mask 连通域**。

| 作者 GT 值与缺陷名 | 原图数 | 标准构成加两个差量的推导 | 分组 |
|---|---:|---|---|
| 249 `1_additional_nut`；241 `1_missing_washer` | 6 | bolt2 / nut3 / washer1 / bracket0 | 订单各类 0–3 内 |
| 247 `1_additional_washer`；243 `1_missing_nut` | 6 | bolt2 / nut1 / washer3 / bracket0 | 订单各类 0–3 内 |
| 248 `2_additional_nuts`；240 `2_missing_washers` | 6 | bolt2 / nut4 / washer0 / bracket0 | 观察含 4 件 |
| 246 `2_additional_washers`；242 `2_missing_nuts` | 6 | bolt2 / nut0 / washer4 / bracket0 | 观察含 4 件 |

论文 §3.4 进一步说明：missing 的 mask 标注物体可能出现的范围，additional 的 mask 标注该类别的所有实例。因此两张 mask 可以空间重叠，不能用 mask 数、面积或连通域数计算物件数。这里相加的是不同类别各一次的全局差量；同一次替换事件的 nut+1 与 washer−1 作用于不同计数坐标，并不造成同类重复相加。不得推广到同类重复数量标签或结构/尺寸缺陷。

独立追溯完成：24 个原图 stem 各对应一个原 GT 目录，每个目录实际恰有两张 mask；每张在历史完整源包清点中只有一个非零标签值。48 个原 mask 的文件 SHA 已重新核对，均与作者包文件清单及图像 manifest 中的 SHA 一致。所有标签均映射到两个不同类别的一增一减，没有第三种登记缺陷、未知编码或额外 mask。24 张均未出现在当前项目使用/查看记录扫描得到的 112 张曝光集合中。

读取链是：原照片 stem → 同 stem GT 目录 → 原 mask SHA → 历史已解码非零值清单 → 作者 Table 12/defects JSON → 数量差量。当前只对 mask 文件作字节哈希，未重新解码 mask，也未查看照片。作者 README 主要提供引用和许可；**可推导语义来自论文和缺陷配置，不能声称 README 本身规定了计数相加算法。**

## 推导假设与可信度

两个标签指向不同类别，可以在相同标准构成上分别加减；不会把同类两个标签重复相加。作者说明异常标注覆盖所有异常，而这批原目录只有这两个数量缺陷，因此剩余 bolt=2、bracket=0 是该标签体系下的推导。推导从语义和完整登记关系得到，未依赖模型答案或 AI 看图结果，具有清楚可审查的来源。

但论文没有直接发布 `bolt/nut/washer/bracket` 四类计数表，也没有逐句写出双缺陷的代数公式。因此拟用名称应为 **author_combined_quantity_defect_rule_v1（作者组合数量标签推导）**；不要称“作者直接提供了这些四类计数”或“独立人工逐件真值”。仍继承作者标注完整性假设、类映射边界和可能的数据标注错误。

## 将来可冻结的最小协议

若下一步采用，应先独立复核并冻结映射、来源/原图/48 mask/配置/论文哈希和**完整 24 张分母**，再运行固定方法一次。不得按图像外观、模型输出或成功率筛掉困难图；不得用本批结果调整参考/提示后仍称本批新留出。

全 24 张报告准确且可执行 C、明确错误 W、不确定 U、执行失败 E 和未完成 N，并分别列四个 6 张数量组。它们正常构成的总物件数仍都为 6；恒输出总数 6 无法证明分类计数能力，恒输出 2/2/2/0 应为 0/24。需预先确定正常对照与“总拒答”对照，防止只对全部异常拒答而产生虚假优势；正常对照若用已曝光样本，需与新来源成绩分开。

**12 张单类 4 件不删除、不裁成 3、不视作执行错误。** 观察数量支持 4；BOM 每类上限 3 只限制可创建的订单。此组仍可以验证超量观察和相对合法订单的差异：例如标准订单 2/2/2/0 应产生补/减建议而非 ready。

对订单派生规则应分开计分：

- 所有 24 张都可对合法 BOM（四类各 0–3、非全零）作错误 ready 面板及正常订单核验。
- 12 张 0–3 内照片可以构造与真实数量匹配的合法订单。
- 12 张含 4 件照片的“完全匹配真实数量订单”应标 `not_applicable_due_to_order_limit`；不能创建非法 4 件 BOM，也不能因此缩减观察评测分母。该组枚举面板的每个合法订单都与真值不匹配，应单独记录面板分母。
- 旧 `validate_case` / `verify_task_receipts` 的每类 ≤3 前提不能直接套用本组。将来需要显式区分合法观察域与合法订单域的新 runner/scorer 协议，原 51 计分器和历史结果保持不动。

这仍是同一公开物料域的来源未登记曝光验证，不认证不同物理零件/采集会话，也不知道 VLM 预训练是否见过；无 bracket 阳性。mask 异常区域不是完整实例标注，不能提供全物体定位正确性的真值。

## 凭证

- [独立语义核对结果](../../test-results/v0.8-loco-combined-label-semantics-v1.json)：24 图、48 mask SHA、逐图标签及条件计数、原标签保留、完整来源 SHA。
- [可执行只读核对脚本](../../scripts/v08/audit_loco_combined_label_semantics.py)：标准库，无图像解码/模型；Ruff 通过。
- [来源曝光清点](../../test-results/v0.8-loco-remaining-metadata-audit-v2.json)：616 份文字记录与五个只读应用订单数据库，精确差集及覆盖限制。
- [本地作者论文](../../datasets/provenance/mvtec_loco/original_paper.pdf)、[仅文本提取](../../test-results/v0.8-loco-author-paper-text.txt)、[作者缺陷配置](../../datasets/raw/mvtec_loco_ad/screw_bag/defects_config.json)。论文 DOI：<https://doi.org/10.1007/s11263-022-01578-9>。

独立同行文字复核已通过：另一个代理复算 24 个唯一源 SHA、48 个唯一 mask 路径/保存 SHA、四组各 6、12+12 分组及 7 份来源哈希，未看图、未改真值或调用模型。
