# 类别参考图备用方案：先选清晰完整的开发示例

2026-10-02；未冻结、未运行参考实验的开发草案，允许在推理前按清晰度与完整性改选。**目标是同域类别参考辅助，尚无实测收益，也不主张新域泛化。** 仅按root授权解码指定训练图并裁剪，未推理/训练、未改生产和三类检测器/影子协议。

**实际能力与限制。** [vision.py](../../kitguard/vision.py) 的 `observe(..., references: dict[str, Path])` 接受四类的任意子集；每类一张、最大边512，放在待检图后并明确类别及“不要计数”。这是类别示例，尚无多例检索库、相似度阈值或标签认证。[Store](../../kitguard/store.py) 替换同类参考会保存历史、使旧检查失效。空间原向和旋转两轮都收到相同参考；**guarded 最后身份调用只收待检整图与候选裁剪，不收类别参考**。其 [identity prompt](../../kitguard/identity.py) 将第二张起全部定义为待检图裁剪，因此不能直接追加参考而不改协议。选择性身份实验还显式拒绝参考。

**开发可用性选样（裁剪尚未制作）。** 从已曝光的官方训练来源选择清晰、完整可见的单件，不按旧51或后续模型表现择优。root 先目检下列候选，选定后保存理由、原图/裁剪/512输入 SHA 与边界来源到 `datasets/derived/v0.8/class_reference_dev_v1/`，再冻结。

| 类别 | 待目检候选与标签依据 | 必须保留的限制 |
|---|---|---|
| nut | Screws train002实例2001已按作者AABB裁 `[840,154,905,217]`，待QA；与作者邻定向框相交，不能先称单件清晰参考 | 标签为作者type_007→Neuromatch别名→项目nut投影。[语义审查](SCREWS_CATEGORY_SEMANTICS_REVIEW.md)。备用[训练候选排序](../../datasets/derived/v0.8/class_reference_dev_v1/nut_quality_candidates.json)：297/297004、339/339004，待目检 |
| washer | root已实际比较[046](../../datasets/raw/mvtec_loco_ad/screw_bag/train/good/046.png)/[057](../../datasets/raw/mvtec_loco_ad/screw_bag/train/good/057.png)，选057下方完整银色开口/弹簧垫圈；按原图1600×1100裁 `[524,682,665,819]`，裁剪待QA | 作者正常袋构成与既有映射支持类别/数量；选区与类别识别为root AI目检，**没有作者washer实例框**。046右washer更贴近nut而未选 |

两张LOCO均为官方train/good，在[旧28开发清单](../../datasets/manifests/v0.3/INTEGRATED_DEVELOPMENT_V1.json)及[2026-09-26开发运行](../../evaluation-runs/loco_development_27b_app_v1/predictions.jsonl)第3/11行，源SHA核对通过；不是官方test重划分。[来源manifest](../../datasets/manifests/mvtec_loco_screw_bag/manifest.json)保留CC BY-NC-SA4.0及作者正常构成依据。Nut备用只从v1 train214中选：完整AABB加4px边距、与所有邻AABB无正面积交集，再按最短边降序及source/annotationID排序；两名候选均非旧51源。

仅采用完整单件裁剪，不画答案、不发送整袋/文件名/GT/BOM；G点只作定位，不能当作者框或真人标注。已由[准备器](../../scripts/v08/prepare_class_references.py)先写[选择记录](../../datasets/derived/v0.8/class_reference_dev_v1/selection.json)，再保存原像素crop及[源/裁剪SHA、实际尺寸、邻框交集](../../datasets/derived/v0.8/class_reference_dev_v1/preparation.json)，尚未批准推理。模糊、截断或邻件混入可在冻结前改选。**FOD016255已拒**：约20×34且既有AI QA记录小/糊；旧草案不是不可更改的冻结协议。

**v2质量迭代已完成AI QA。** root实际看过v1：002边缘有其他亮物/上下文而未采用；057完整清晰但顶缘有邻bolt灰边。另存[v2选择](../../datasets/derived/v0.8/class_reference_dev_v2/selection.json)后，[准备器](../../scripts/v08/prepare_class_references_v2.py)将057收紧到 `[528,690,663,819]`（135×129），并准备297/297004（76×76）、339/339004（78×76）。root实际看过三张crop：紧washer完整无邻件；rank1 nut主体完整独立，按顺序采用，rank2备用不选。[新增AI审查回执](../../datasets/derived/v0.8/class_reference_dev_v2/visual_review.json)选择 **Screws297 + LOCO057**；背景保留无修图，只认可可用性/边界，不认证nut内螺纹。原[准备回执](../../datasets/derived/v0.8/class_reference_dev_v2/preparation.json)和v1记录不回写；正式runner approval另由root处理。

**最小可执行对照。** 另写runner，以替身捕获 `_generate` 核对图序与无计数/真值泄露，再冻结。完整旧28做 `spatial_guarded` 无参考/两参考配对，交替顺序，保留原模型/1536/900及1800 token预算；参考来源原图单列自源诊断，不算泛化收益。通过开发门槛才扩到完整旧51；报告 W→C/W→U/C→U、C/W/U/E/N、两个false-ready面板及LOCO负控。均为已曝光开发回归；不同时改身份提示，不切默认，不触碰MANTA正式test/FOD held_back。

**代价和预期边界。** 参考在两轮重复输入，增加视觉/提示token、时延和内存，也可能改变第三轮触发。保存逐调用输入/原文、tokens、峰值内存、失败及整体墙钟，不能外推旧时长。旧[benchmark](../../scripts/run_benchmark.py)与[v0.7 paired](../../scripts/v07/run_public_paired.py)都无参考，已有成绩不覆盖此能力。同模型重复读取仍会重复偏差；单例/类可能学习背景或项目映射，不能认证螺纹或跨域物理身份，也不替代三类检测器路线。
