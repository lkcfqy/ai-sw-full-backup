# LOCO24：来源预飞状态追加与可冻结 runner 设计

2026-10-02；**设计草稿，不是方法选择、冻结或推理授权。** 本追加只读既有 JSON/源码，不查看照片或 mask 像素，不改已被 SHA 绑定的评分草案、原 truth、当前 identity-only 候选或冻结文件。

## 先纠正状态，不回写旧凭证

[原评分草案](LOCO_COMBINED_SCORING_DRAFT.md) SHA `01c8bbb0b3482c13d185b38562e53c180c064c63bf9f70002c745f9923bc9250` 中“来源预飞尚未执行”描述的是该稿保存时的状态，**现在已被后续执行记录更新**。

[来源预飞 v1](../../test-results/v0.8-loco-combined-source-preflight-v1.json) 已于 2026-10-02 01:21:52–01:21:55 UTC 完成，SHA `5a099cd576d4014c306beeb9183247953d7dea13303333d1d7e7b020b80e7cf4`，状态为 `passed_no_exact_overlap_in_bound_registry`：

- 全 24 保留；比较固定历史登记 112 原图及两个参考的四个 source/crop 角色，机器解码 139 个唯一文件。
- 精确原字节/RGB 重合、完整性错误、检查期间元数据变化均为空；24 内部的精确重复比较也已记录。
- 机器解码仅用于完整性/精确重复；没有显示图像、模型调用、写新真值或选定方法。
- RGB 指纹明确绑定原尺寸与 RGB 字节，无 EXIF 转向/resize；不排除相近场景、压缩/缩放变体、同一物理件或同一采集会话。历史数据库行仅使用原扫描绑定，不声称本次重读了全部历史现场。

[评分合同 v2](../../test-results/v0.8-loco-combined-scoring-contract-v2.json) SHA `491f035c40a98b0c383c052982c3c19dcc839c304f719ae99084a6e043506f9d` 已通过 13 项合成 CPU 合同，并对六类观察×255合法 BOM 与真实 `decide` 交叉核对。其 `preflight_pending` 同样保留为历史字段，由本追加说明现状，不能静默改写旧 JSON。

## 方法选择先于这 24 张的任何模型结果

等待完整 identity-only 旧 51 结果及独立审计。根先保存一份新 `method_selection.json`：无参考原 G 固定为基线；是否增加 identity-only，以及增加时是合格候选还是明确标为失败候选的比较臂，必须由根在首次 LOCO24 推理前决定并写理由与证据 SHA。不能用 24 的前几张选择方法、换参考、改提示或提前停止差臂。

方法最多两个，精确复用其已审查协议/源版本；不把空间参考旧候选、灰度、检测器或本轮后备研发草案自动加入。固定同一 27B 模型、1536输入界、空间900/身份1800、temperature0、零重试、无warmup。候选原 identity 条件与裁剪不变，不为 count4 增加数量提示。

样本全 24、四数量组各6，不能丢掉含4的12张。确定方法后，一次冻结不含模型输出的 case 顺序与调用表：建议以 source SHA 的固定哈希排序；双臂时按 case 交替 AB/BA、各12次先手。同一模型运行时共享加载状态需披露，首个 cold case 计入完整耗时；另列 warm 子集，不能把历史51时延冒充同期对照。G单臂为24观察、最多72次生成；双臂为48观察、最多144次生成，身份跳过/前序失败会减少实际调用。

## 新 runner 的三个阶段与文件接口

建议新入口 `scripts/v08/run_loco_combined.py`，提供 `preflight / freeze / run`；本文件没有实现入口。

1. **preflight**：绑定上述来源预飞、语义提案/同行复核、原源包清单/作者配置/论文、完整24原图及48mask SHA；核对4×6和每类差量仅应用一次。生成独立版本化 `author_combined_quantity_defect_rule_v1` 真值清单；原 manifest 仍 unresolved/null。源登记清单若新增实际曝光，追加披露，不能反写历史“无人看过”。归一化后再检查本次输入 bytes/RGB 与选定参考链的精确重合；发现问题保留24分母并停止原声明，不悄悄换图。
2. **freeze**：拷贝 manifest-listed v0.7 基类、选定候选 adapter、记录器、评分器、依赖/模型/参考版本及新 runner 到全新 snapshot；不复用活动工作版 `kitguard`，不复制旧快照的 SQLite。预飞 JSON 在冻结前再逐字段对照源清单、真值、方法表、原参考 approval 与实际文件 SHA，防止仅 hash-check 文件却接受被误改的列表。冻结后禁止改源码或分析门槛。
3. **run**：以 `python -I` 从该 snapshot 导入，**任何 app/evaluation import 前**设置 `KITGUARD_DATA_DIR=<新output>/runtime-app-data`。只有根执行；当前没有运行授权。保存不可覆盖的新 run/freeze副本/manifest/inputs/cases/predictions/analysis；结果后才独立审计并作决定。

运行输入队列与真值表分开：observer仅拿中性编号路径（例如 `case-001.jpg`）、固定占位 BOM `1/1/1/1`、该方法固定参考及明确图角色。不传缺陷名、mask、作者数量、source目录语义或其他方法答案。应用上传归一化只做一次，各方法复用相同存储字节；每个实际原向/旋转/crop/reference PNG均保存并核 SHA。

## count4 与完整 Observation 验证

原 v0.7 `ObservedCounts` 和身份阶段 `Count` 均允许0–100；BOM要求仍0–3。因此观察4合法，API占位订单1/1/1/1也合法，二者不能混用。未来合成合同须让**完整冻结 Observation schema**接受4，并验证它经过真实 `decide` 对合法3件订单产生数量不符，而不是构造4件BOM或把观察截到3。

每个方法观察先通过其冻结完整 schema（含对象/身份/坐标关联），再交[既有纯评分投影](../../scripts/v08/score_loco_combined.py)。完整 schema失败、JSON/ID失败、执行失败都为E，不能靠 projection 的宽接口重新接纳。原评分器源码 SHA `9391920712f523780e099836c54f21024cc2778360c94fdd68a25dc5fef28c94` 保留；其静态 `protocol_frozen:false` 是草稿 API 元数据，正式报告应使用新的外层 schema绑定实际freeze，并明确评分函数来源，不静默改写旧评分文件或旧凭证来声称已冻结。

## 一次完整运行应记录什么

每个计划 `case_id × method` 必有 completed/error/not_attempted 状态；中断后的N由计划表显式物化，绝不复制另一臂/历史G补齐。每行保存原sourceSHA、归一化SHA、实际目标SHA、运行源协议SHA、loaded_before、完整观察或错误及 diagnostics。重复/计划外/错源行属于完整性失败，停止结论发布，不简单计W掩盖。

每次生成记录 exact system/user、完整JSON schema SHA、图片顺序/角色/字节、max_tokens、raw返回与解析错误、tokens、结束原因和耗时。区分 **generation attempt record / model_call_started / model_call_completed**：加载/grammar失败可能从未进入实际generate；合法JSON错ID可能已返回模型文本但身份阶段失败。identity skip保持无参考输入及原原因，不能写成已检查。G记录无参考；identity-only记录真实末尾两参考索引，不能套用当前生产host的identity无参考元数据。

每次检查的总耗时包含冷加载（若发生）与实际输入/观察工作；另外记录setup hash核验与最终保存/分析时长，避免互相混用。只有全部计划终态后才读取、排名或比较效果；失败和中断原文保留。

## 固定报告与解释

- 每个方法 C/W/U/E/N 分母24，四个数量组各6。C是正确明确观察，**不等于订单ready**；错误数量即使让规则返回correct，也不算正确差量。
- 12个合法真值匹配订单；含4的12个匹配订单标 `not_applicable_due_to_order_limit`，观察仍完整计分。
- 主 `all_four`：每图255合法BOM，6120相关规则回放，其中6108错配订单。次 `source_supported`：每图63，1512回放，其中1500错配。报告有任何false-ready的图数/24及E/N未测数；次面板不能遮蔽bracket幻觉。
- 恒2/2/2/0为0C/24W，任一错误ready24图；全拒绝为24U、观察到错误ready0但正确观察0。两个都是无模型分析对照，不能加入模型调用统计或伪装独立图数。总数六恒对不证明分类计数。
- 标准BOM2/2/2/0的正确差量完整24；旧51内完整16 LOCO normal作为**已曝光、历史、非同期**正常回归单列，不与新24合并分数或重跑凑正常对照。
- 若双臂，报告完整配对变化与所有C损失/W增减；不因总体净收益隐藏某个6图组失败。无自动晋升，结果良好仍需独立完整性/原文回放审计及范围审查。

最终名称应是“来源未登记曝光的同域作者组合数量标签推导验证”。作者§3.4的mask是缺陷区域，不是实例数；两不同类别delta各用一次。它不是作者原生四类计数字段、独立实物随机试验、现场效益或真人验证；预训练污染未知，无bracket阳性。**选择方法、正式冻结、模型运行和发布结论仍由根完成。**
