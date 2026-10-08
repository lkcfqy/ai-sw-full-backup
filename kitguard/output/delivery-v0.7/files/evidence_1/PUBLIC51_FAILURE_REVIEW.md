# 新51图正式三方法错例复核

2026-10-02，只读事后诊断。**guarded 把 inventory 的两个错误结论转为需补证，没有新增错误结论；仍留下三个 `nut→washer` 错例。候选恢复了五张正确可执行照片，也把 217 号照片从需补证变回错误结论。三次同源、同模型调用一致，仍不足以验证类别正确。**

依据是完整153次正式运行及已通过的[独立审计](../../test-results/v0.7/public-paired-audit-v1.json)，不是运行中的前缀结果。本次没有修改原图、裁剪、真值、方法或运行记录，没有加载模型、重新推理或晋升候选。可机读的[证据索引](PUBLIC51_FAILURE_EVIDENCE.json)记录全部五个错例、15次完整观察、29个原始生成文件及模型输入的路径和 SHA256；正文只列出决定结论的证据。

## 范围、口径与完整结果

正式运行在 `2026-10-01T21:28:35.253626Z` 至 `22:14:54.621793Z` 完成，每张照片运行三种方法，共51张、153次。冻结 SHA256 为 `cec1cf5362a5154cfd6e4d27e5ed9dbb49d7757a12189474c13e643f1dc67be7`。审计状态 `passed`，运行中的冻结推理源码未改变；工作区的其他开发仍有变化，不能把两者混为一谈。模型均为 `mlx-community/Qwen3.6-27B-4bit`，revision `c000ac2c2057d94be3fa931000c31723aac53282`，三种协议的独立 hash 见索引。

下文 I 是 `spatial_inventory`；G 是 `spatial_guarded`（原方向、旋转方向及按条件运行的身份复核）；S 是 `selective_identity_experimental_v1`（单方向观察及选择性身份复核）。C/W/U/E/N 分别是正确可执行、错误可执行、不确定或不可执行、执行或输出失败、未尝试。U 不能算成正确识别，W 也不等同于现场实际出库事件。

| 方法 | C | W | U | E/N | 正确可执行率 | 四类面板 any-false-ready 照片 | 来源支持面板 | 完整观察 P50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| I | 46 | 5 | 0 | 0/0 | 46/51，90.2% | 5/51 | 0/51 | 8.962秒 |
| G | 41 | 3 | 7 | 0/0 | 41/51，80.4% | 3/51 | 0/51 | 21.814秒 |
| S | 46 | 4 | 1 | 0/0 | 46/51，90.2% | 4/51 | 0/51 | 15.625秒 |

51张由16张 LOCO 正常袋装照片与35张 Screws 作者标注安全裁剪组成。全部五个不同 W 错例来自后者。来源筛选、运行设计及所有结果仍以[冻结文件](../../evaluation-runs/v0.7/public_paired_v1/freeze.json)、[manifest](../../evaluation-runs/v0.7/public_paired_v1/manifest.json)、[analysis](../../evaluation-runs/v0.7/public_paired_v1/analysis.json)为准。审计通过表示记录与计算一致，不表示识别质量通过门槛。

完整配对转移为：

- I→G：C→C 41，C→U 5，W→U 2，W→W 3。**没有 C→W，也没有把旧 W 修成 C。**
- I→S：C→C 46，W→U 1，W→W 4。相对 I 没有新 W。
- G→S：C→C 41，U→C 5，U→U 1，**U→W 1**，W→W 3。

G 使原本正确结果转为 U 的五个来源为 LOCO `train-good-225`、`train-good-148`，以及 Screws `306`、`165`、`025`；S 将这五个全部恢复为 C。五个完整 ID 收录在索引中。G 的 W 比 I 少2张，却损失5张正确可执行结果；S 的中位耗时比 G 低28.37%，但仍有4张 W。G 和 S 都未通过预注册工程门槛，S 的进一步验证门槛也为 false；这些描述性差异不能改写为已证明安全优势或候选晋升依据。

## 真值从哪里来

作者原始 JSON 使用 `type_001` 至 `type_013` 类别名，并不是直接写 `nut`。本次冻结的类别投影将 category ID `7/9/10/11` 计为 `nut`，其他 ID 计为项目宽口径的 `bolt`；所选裁剪只包含完整作者标注框，其他带余量框均在裁剪外。投影代码是冻结的 [prepare_public_evaluation.py](public_paired_freeze_v1/source_snapshot/scripts/v07/prepare_public_evaluation.py)，原始标注为 [mvtec_screws.json](../../datasets/raw/mvtec_screws_v1.0/mvtec_screws.json)。本次逐项核对了五图所含 annotation ID 与类别。

下面的“nut→washer”指**相对于这一预先冻结的作者类别投影**发生误分类。五个错例中产生分歧的小件均来自作者 `type_007`，并按该投影计为 nut。即使照片的俯视轮廓容易让观察者想到 washer，也不能事后依据本模型答案或人的直觉改写本次真值、删除照片或重报分数。视觉复核不是一次独立的实物类别裁决。

## 五个错例逐一核对

所有计数按 `(bolt, nut, washer, bracket)` 排列；`?` 是实际输出的 `null`。括号内的 I/G/S 数字是正式153次运行中的 attempt 编号，便于定位原文。

| 来源与 attempt | 冻结真值 | I 终态 | G 终态 | S 终态 | 决定性记录 |
|---|---|---|---|---|---|
| 024：I114 / G112 / S113 | (1,1,0,0) | W (1,0,1,0) | W (1,0,1,0) | W (1,0,1,0) | G 两方向都误分；身份 `p002=washer`，无阻断 |
| 120：I91 / G92 / S93 | (1,1,0,0) | W (1,0,1,0) | W (1,0,1,0) | W (1,0,1,0) | G 两方向都误分；身份 `p001=washer`，无阻断 |
| 163：I103 / G105 / S104 | (2,2,0,0) | W (2,0,2,0) | U (2,?,?,0) | U (2,?,?,0) | 两方向仍误分，身份却返回两个 nut；冲突阻断 nut/washer |
| 172：I150 / G148 / S149 | (2,1,0,0) | W (2,0,1,0) | W (2,0,1,0) | W (2,0,1,0) | G 两方向都误分；身份 `p003=washer`，无阻断 |
| 217：I67 / G69 / S68 | (3,2,0,0) | W (3,1,1,0) | U (3,?,?,0) | W (3,1,1,0) | G 原方向和旋转方向冲突；S 身份接受原错分 |

**024 / 120 / 172：确认的共同失败链。** G 的原方向与90°逆时针旋转观察给出相同错误计数，随后身份原文分别给出 `p002`、`p001`、`p003` 为 `washer`，同时为 `status=independent_object`、`opening=through_hole`、`issue=""`。`blocked_categories=[]`，最终仍为 W。S 对相应目标也确认 washer，得到同一终态。关键身份原文：[024](../../evaluation-runs/v0.7/public_paired_v1/cases/112-spatial_guarded/call-03/generation.json)、[120](../../evaluation-runs/v0.7/public_paired_v1/cases/092-spatial_guarded/call-03/generation.json)、[172](../../evaluation-runs/v0.7/public_paired_v1/cases/148-spatial_guarded/call-03/generation.json)。所含 category-7 annotation ID 分别是 `24004`、`120004`、`172003`。

**163：身份冲突成功阻止了错误可执行结果，但没有完成正确识别。** G 的原方向与旋转方向均列出2个 bolt、2个 washer；[身份原文](../../evaluation-runs/v0.7/public_paired_v1/cases/105-spatial_guarded/call-03/generation.json)却把 `p001` 与 `p002` 都列为 `nut / independent_object / through_hole`。原判断与复核冲突，规则把 nut、washer 留为 null，并要求补证。S 的[身份原文](../../evaluation-runs/v0.7/public_paired_v1/cases/104-selective_identity_experimental_v1/call-02/generation.json)相同，两个目标 `accepted=false`。这是 W→U，不是 W→C；不能用身份子调用的正确类别替代实际终态。对应 category-7 annotation ID 为 `163004`、`163006`。

**217：G 的旋转分歧被 S 丢失。** G [原方向原文](../../evaluation-runs/v0.7/public_paired_v1/cases/069-spatial_guarded/call-01/generation.json)得到 (3,1,1,0)，[旋转方向原文](../../evaluation-runs/v0.7/public_paired_v1/cases/069-spatial_guarded/call-02/generation.json)得到与冻结真值相同的 (3,2,0,0)。规则因两方向不一致使 nut/washer 为 null；身份步骤记录 `skipped_base_unclear`、`model_called=false`。S 没有该旋转阶段；其[身份原文](../../evaluation-runs/v0.7/public_paired_v1/cases/068-selective_identity_experimental_v1/call-02/generation.json)接受 `p004=washer` 与 `p005=nut`，两者均为独立物体、through-hole、无 issue，保留 (3,1,1,0) 的 W。对应两个 category-7 annotation ID 为 `217004`、`217008`。这正是唯一 G U→S W；S 相对 I 没有新增错误照片，相对 G 则恢复了一张 G 已阻断的错误。

这里可以直接确认“哪些记录触发了哪些规则”。仅凭每方法一次观察，不能进一步宣称“删除旋转必然导致此类错误”或推算同类照片必有多少收益。

## 为什么来源支持面板是0，而四类面板是5/3/4

面板把同一照片的最终观察输入确定性订单核对器，检查合法但与真值不相等的 BOM 是否会被判 ready；没有因此产生新的图像推理或真实订单。

Screws 的 `supported_positive_classes` 只有 bolt、nut。每类数量取0–3，剔除全0及真值后，来源支持面板每张错例有 **14个不匹配订单**，其 washer/bracket 永远为0。五个 W 观察都虚增了 washer，因此不可能恰好匹配这一受限面板内的订单。来源支持面板0/51是其有限范围内的真实结果，**不表示 washer 错误消失，也不表示四类产品已安全**。

四类面板允许 bolt/nut/washer/bracket 各为0–3，同样剔除全0及真值；这五图每张有 **254个不匹配订单**。它包含与错误观察恰好相同的订单，例如120的 `(1,0,1,0)`、217的 `(3,1,1,0)`，故会得到 false-ready。本次每个 W 错例恰有一个这样的订单，照片级“至少一个 false-ready”恰好得到 I=5、G=3、S=4。索引保存逐图逐方法的实际 `false_ready_orders`。

分母是51张配对公开照片，不是 `51×254` 个独立样本；多订单枚举没有增加独立视觉证据。5/51、3/51、4/51不能解释为现实仓库出错率。此集没有新增 bracket 阳性，也没有覆盖 LOCO 的实物数量异常；同公开采集域和未知预训练接触仍限制外推。报告必须同时保留两个面板，不能用来源支持0覆盖四类面板的已知失败。

## 可观察事实与成因假设

本次直接查看了五张完整原图、五张实际选定裁剪，以及七张已保存的身份放大输入。错分目标都具有明亮外缘和可见中心区域，位于木纹背景；小件在原裁剪中占比低。肉眼看到这些形态，不能据此判定内螺纹存在或不存在。

**已经确认的机制边界：**

- G 的复核记录明确标记 `same_model_correlated_calls=true`。三个残留 W 通过了同模型的方向一致性及身份检查；这些调用是相关观察，不是三位独立检验者。
- 身份输入是同照片的全图上下文和重采样局部。三个残留错例的局部源像素范围分别是144×174、173×173、208×208，之后放大至最长边512；元数据明确 `interpolation_creates_information=false`。放大不等于取得新的实拍细节。
- 身份 system prompt 已定义“nut 为带内螺纹的紧固件，可为圆形或滚花；washer 为无螺纹环”，并要求看不清时返回 unknown/uncertain。不能把失败简单归因于“没有写类别定义”。
- 身份请求只给目标 ID 与坐标，没有把初始预测标签写入目标 prompt；不能据此声称模型在照抄传入的 washer 标签。不过目标位置和裁剪由首轮检测提供，取证仍依赖同一观察链。
- `through_hole` 只能记录模型对孔形的判断；它不是“无内螺纹”的独立证据。三个残留 W 的身份响应没有提供可审计的螺纹判别字段，且 issue 为空，规则因此未得到阻断信号。

**仍待验证的成因假设：** 高反光俯视小件的内缘细节可能不足以稳定地区分冻结 nut 类与 washer；同模型可能重复依赖外缘和中心孔形。217显示类别判断会随旋转输入改变，163显示局部身份提示能改变类别，但这只能证明本次输出不稳定，不能确定是分辨率、光照、提示、类别投影还是模型表征在主导。当前证据不支持作者标注错误、所有圆形件都应改为 washer、所有小件都应拒绝，或增大图片就必然修复。

## 两个有边界的后续方向（未执行）

1. **独立验证 nut/washer 的可见判别依据。** 先在另行许可、来源独立、同时含真实 nut 与 washer 的开发资料上固定类别说明及物件依据，优先使用作者规格或可核对的多视角资料；再预注册一个身份协议变体，要求区分“可见内螺纹 / 可见无螺纹 / 无法辨认”，无法辨认时保留补证。三种字段本身仍是模型判断，必须以预先锁定、盲于模型答案的真值检查；不可把“有孔”当“无螺纹”。这51张现在已暴露，只能作为回归集；改善主张须用新的来源隔离留出集，同时报告 W、两个 false-ready 面板、正确可执行率与时延。不得通过全面封禁 washer 换取表面安全。
2. **检验受限旋转触发是否保留217的阻断能力。** 只设计一个预先固定、与图片 ID 无关的规则，例如首轮出现 nut/washer 候选时保留方向分歧检查；用完整51张做回归并单列五个原 C→U 的代价，再在新留出集比较。此方向只针对 S 丢掉的分歧信号：024/120/172两方向已经一致误分，不能预期它解决三张残留 W。禁止根据这五图逐张特判；预算、门槛、退出条件须在新实验前冻结，结果不触发自动默认切换。

任何后续设计都不能覆盖本次正式结果。当前交付应保留失败证据、需补证路径和人工数字审查边界，不宣称获得了真实仓库验证或足以夺冠的实测证明。
