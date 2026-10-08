# Nut/washer 多来源组件：迁移失败后的数据可行性复核

2026-10-02。**失败后的开发规划，不是事前注册或性能证明。仅 metadata/document 审查。** 本轮没有下载、解码或显示图片，没有训练/推理，没有读取 FOD `held_back.json`、新 LOCO24 的逐图清单/预测或 MANTA test 图像；不借这些集合选择下一方法。不修改原分割、作者标签、已审计分数或生产代码。

## 结论

**现有本地、带现成标签的材料不足以证明具备“同一采集来源内两类均出现，且不同背景/物件/会话可分离”的训练—验证设计。本轮不推荐再启动一个模型候选。** 这不等于没有公开数据路线，也不是必须购买实物；缺口是类间可比的数据、实例标签与分组依据，而不是再增加同类文件数量。

当前 MANTA 固定头内部256C，但已曝光跨来源180目标为12C/161W/7U，bolt目标AABB误接收136/399。Screws nut 为0C/153W/3U，FOD Nut为12C，FOD Washer为0C/8W/4U。原结果见[跨来源报告](MANTA_CLASSIFIER_CROSS_SOURCE_RESULT_V1.md)。这支持拒绝集成；**不能仅凭这些结果或 metadata 断言唯一原因就是背景、颜色、尺寸或补黑捷径**。AABB含邻件、类别语义投影和域差异均须保留，不能事后翻转标签或换阈值把错误改对。

## 五个现有来源能提供什么

| 来源 | 精确现有分割/已用状态 | 作者标注与两类覆盖 | 可分离性的实际限制 |
|---|---|---|---|
| **MVTec Screws** | 原384图：train269 / val55 / test60，4427实例。现有检测器开发子集train214图2597实例（nut777/bolt1820）；val44图543实例（nut156/bolt387）；旧test22图315实例（nut93/bolt222）也已评测。另104原图因历史holdout/候选来源被准备器排除，不改其角色。 | 定向实例框完整保留。**washer阳性0**；类型7/9/10/11→nut来自既有教学映射，不是作者直接英文命名。不能拿其他数字类型补成washer。 | 同批零件和背景；没有可认证不同物理件/session的ID。可诊断不同nut类型，但单独不能训练或验证N/W区分。 |
| **FOD-A VOC v2.1** | 已曝光检测器train400（Nut50/Washer100/Bolt250）、val36（各12），具体组见下表。另固定held-back36（各12）保留未用，不为本轮补位。 | 这些候选每图一个作者原子类目标框，**不等于全图完整实例标注**。Nut/Washer作者语义直接，但当前14个原子候选组中的GOPR前缀均单类，没有同一GOPR内跨类配对。组合类不能按外观拆成原子类标签。 | 有多个目录关联组，允许计算上保持组隔离，但目录不同不保证背景/物件不同；也不证明不同类共享相同背景条件。训练Nut只有一个组。 |
| **MANTA 本地两包** | 作者train/good：nut2148、yellow_green_washer2072。固定1024已用：每类train384/val128，合计768/256；两类各有512入选记录。其余作者train分别1636/1560未进入该实验。作者test：nut69（good46/异常23）、washer216（good144/异常72），没有用于本项目模型开发/评测。 | 作者产品类别和正常/异常标签；单composite五视角关联，异常mask不是实例检测框。第0面板组件输入不是作者实例框。`yellow_green_washer`只是一种具体产品类别，不能替代所有washer。 | 32编号块仅保守代理，不是物理ID/session；五视角不能拆成五个独立物件。既有QA记录显示类别相关尺寸/补黑差异，本轮未新增目检；metadata不能证明多背景或多独立型号的交叉设计。扩大未选train数量也不会自动补上这些ID。 |
| **InO-10-190** | 本地作者真实`test_01`有190来源、A–F六目录；origin/cropped/深度是同源表示，不是额外独立RGB样本。已核到两次正式部分标签实验共21来源；其余169不因此成为“保证从未看过”的新留出。没有本地真实train/val来补本任务。 | 919作者框、10类：L-/U-/angle-bracket及seat/pipe_clamp/handle/bonnet/body/ball/cable_shoe；**没有nut或washer作者类**。 | 目录与原图可关联，但没有足以给N/W建立标签的字段；不得把背景五金或名称近似物件自封为N/W真值。 |
| **MVTec LOCO screw_bag** | 原train/good360、validation/good60、test/good122，另logical137/structural82。既有较早曝光审计登记正常图train21/val3/test40，共64，以及48单数量异常；该报告早于后来24组合实验，不当作当前完整曝光清单。新24继续排除在本次设计之外。 | 正常袋**同图具有nut2+washer2**，最接近同场景两类对照；但没有全部零件的作者实例框/实例mask。正常构成与数量缺陷规则不能定位每一物体；异常区域mask不能当实例框。 | 只有同一袋装场景/物料域，缺物理件、背景/拍摄session ID。已有零星AI参考裁区不是完整独立实例真值。要做组件训练需另行取得/审核实例标签，目前不是可直接执行的数据集。 |

“未进入某次实验”不等于无人/无AI看过，作者train/test也不证明模型预训练未见。本表明确区分源目录、项目分割及已记录使用；没有把未读分割当作可任意重分的储备验证集。

## FOD：两类都存在，但不能把采集混杂说成已解决

| 既定角色 | 作者类/来源组 | 已选、已曝光数 | 原组候选数 |
|---|---|---:|---:|
| train | Nut / `unprefixed_Nut` | 50 | 783 |
| validation | Nut / `GOPR0183` | 12 | 324 |
| train | Washer / `GOPR0194`、`GOPR0197` | 50+50 | 450+477 |
| validation | Washer / `unprefixed_Washer` | 12 | 342 |
| train | Bolt / `GOPR0180`、`GOPR0184`、`unprefixed_Bolt`、`DJI_Bolt`、`GOPR0192` | 各50，共250 | 114/443/182/977/807 |
| validation | Bolt / `GOPR0181` | 12 | 657 |

仅从**已读的旧protocol/summary**记录保留状态：`GOPR0182` Nut、`DJI_Washer`、`GOPR0179` Bolt为held-back，各选12，本轮未打开其清单、图像或推理。作者原trainval/test跨这些源目录，不是来源隔离划分；继续沿用项目的保守组，不能改用作者split制造独立性。

FOD可以形成现有两角色的组不重叠诊断，但这不是交叉平衡的背景设计。无前缀Nut/Washer分别关联Nut1/Nut1a/Nut2/Nut3与Washer1/Washer1e；同名“unprefixed”既不证明相同采集，也不证明不同物件。更保守地把所有unprefixed视为潜在同源时，现有train Nut与val Washer跨角色相关风险仍在，不能删去其中一边来优化成绩。先前完整6740图曾做机器完整性解码；“held-back未模型评测/未提取展示”不能误写成从未机器解码。

现有参考检索的gallery8/cal36/eval36仅是**未编码的metadata提案**；本次跨来源实际80整图/579作者目标是另一群体。不能把旧参考名单、其tiny统计或任意混合split重新命名为新数据。

## 权利与定位边界

- Screws、LOCO：作者 **CC BY-NC-SA 4.0**，沿用非商业、署名与相同方式共享条件，不推导商业部署许可。
- MANTA：作者明确数据 **CC BY-NC-SA 4.0/非商业**；Figshare的CC BY4.0冲突保留，按较严格作者条件本地研究。不能把模型训练许可扩大成图片自动再分发许可。
- FOD：根任务已授权继续本地研究；代码MIT与照片许可分开，照片明确独立许可仍未解决，不自动分发或声称商业授权。
- InO：固定作者仓库MIT声明与版本保留，不扩展为所有未标注背景对象的权利或类别认证。

作者框只能提供标注目标的oracle定位；即使有框也可能含邻件和背景。组件分类通过不能替代独立proposal召回、全图开放类别、计数或现场任务验证。

## 本轮决定：不新增训练候选

当前没有一项现成来源同时满足两类直接实例真值、类间共享可比采集条件、每类跨背景/物件组，以及不动未用分割的独立验证要求。简单把Screws nut与FOD/MANTA washer拼接，只是再次允许模型利用来源线索；在既有失败集上重新调参数也不是新验证。

若继续这条研究线，前置工作应是**补足可追溯的交叉数据/实例标注**，例如同一采集条件内同时有两类，并在多个有ID的条件/物件组重复；合法公开资料同样可以满足，无须先买硬件。已曝光LOCO的同图共现值得后续标签可行性调查，但缺完整实例标注及多背景分组，当前不把它包装成可启动的新模型候选。本轮不选择照片、不画框、不联系作者、不启动此调查。

保留这次固定负结果。下次方法与数据设计必须重新说明它解决哪个证据缺口；本稿不授权重训、改变阈值、替换标签或生产晋升。

## 本轮只读来源绑定

下列哈希对应本次阅读时的文件；历史“尚未训练/尚未曝光”等字段只按该文件生成阶段理解，不覆盖之后独立运行记录。

| 路径 | SHA-256 |
|---|---|
| `docs/v0.8/MANTA_CLASSIFIER_CROSS_SOURCE_RESULT_V1.md` | `5e8f4cf1c994fe8788ac1fa91a312e185d9fb6f9e13743d46308cea8d76f83f8` |
| `datasets/manifests/mvtec_screws/manifest.json` | `159bbcf94c26eaa1305b2d0f4dada8b902d6cb19710227b2cc2d1fabdf1e6159` |
| `datasets/derived/public_detector_v1/manifest.json` | `27044ecee0fd81d3f29b7cb70c5c8252f08d6588cbba46d346388b2cf83adf23` |
| `docs/v0.8/SCREWS_CATEGORY_SEMANTICS_REVIEW.md` | `42acee3eea618463969ba2116b65b067a7d0e42eacaa30ce527b3e7e17622e27` |
| `docs/v0.8/FODA_CONSERVATIVE_GROUPS.md` | `da4136519d488aa16527b5c0972af85deb124fbb83d63a5c459c7e1a06c2799e` |
| `datasets/derived/v0.8/foda_grouped_v1/protocol.json` | `e42a2516abf111d3a269614542b517b47b42e75cea101d225e6fa78e20fb2812` |
| `datasets/derived/v0.8/foda_grouped_v1/summary.json` | `71097c8b4b90b625101940e5235ef2c40bb5d6fb3a6273e3b13c59b44179fc49` |
| `datasets/manifests/v0.8/manta-identity-v1/record_summary.json` | `89ac36d19c8b8654f0fce1b477e8a50feeda50ab444f9e19758101be61c2d971` |
| `docs/v0.8/MANTA_CLASSIFIER_PREPARATION_RESULT.md` | `5078a6826a0d29cb36aefa54a58063a62ccdd30bb5ff9a82584d020ea5ab3120` |
| `docs/v0.8/MANTA_CLASSIFIER_RESULT_V1.md` | `54bbd93ed185d25f23c6f94792b16004b1fc9cb98ae754f30710eb1739862bfa` |
| `docs/v0.8/MANTA_LICENSE_CHECK.md` | `e17468257e4021b4635af0cce94ba8369ae2550abab7db2b1dd0f6c500cc987b` |
| `docs/v0.4/NEW_DOMAIN_DATA_RESEARCH.md` | `25a91c2dc7e925abe42971a907800d3ce5a5b992de3d432aa4eaae029c6c26ae` |
| `docs/v0.4/INO_RUN_INDEPENDENT_AUDIT.md` | `11777e95bc4809f8b942c805ab187265b364c50ccbd54a000f5969b5049c13d6` |
| `docs/v0.8/LOCO_REMAINING_METADATA_AUDIT.md` | `91c9a0ce50c6724da94832915df4dc26ea597f02f80ea2a69cbb955a02ea57b3` |
| `datasets/manifests/mvtec_loco_screw_bag/manifest.json` | `76e2ece56c7d24a9e52a9eaad0e856298c8ab979c35653e40efd7a672df0ec17` |
