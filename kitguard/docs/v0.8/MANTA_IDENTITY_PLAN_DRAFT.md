# MANTA 两类身份诊断草案：先确认对象组，再固定视角

2026-10-02；**DRAFT，尚未冻结、选图或推理。** 本文只基于作者论文、补充材料、项目页、公开仓库目录与下载元数据。两个完整包仍由 public_workflow 获取；本轮没有查看图像、解码图像像素、运行作者代码或调用模型。v0.7 交付及 v0.8 已完成否决实验均不改动。

## 1. 能回答的问题

拟验证既有方法在新来源的 `nut` 与 `yellow_green_washer` 上，能否正确给出身份、何时混淆、何时保守拒答。当前方法尚未在这些新图上试过；这不等于模型预训练未见过。MANTA 图像、上游预训练、可能的其他镜像传播均无法认证完全未曝光。

只把它作为**两类、单件身份诊断**。不据“总数量恒为 1”声称计数能力，不外推多件混放、真实订单放行、真实用户收益、bolt/bracket 或缺件检测。`yellow_green_washer` 是带有颜色特征的特定类别，颜色/背景捷径可能让两类识别变容易；即使通过，也不能证明已解决 LOCO 银色 washer 与 Screws type_007 的相似外观混淆。

## 2. 官方证据与尚不能确定的部分

| 问题 | 当前可核对事实 | 对方案的影响 |
|---|---|---|
| 五视角是什么 | 作者把同一单件的五个相机视图合并为一张 composite，视角次序固定；单件逐个采集 | 一张 composite 是最小对象记录组，五个视角不能分到开发/评测两侧，也不能当五件或五个独立对象 |
| 官方数据划分 | 论文给出训练仅正常；每类若有 N 个异常，则测试包含 2N 正常及 N 异常，其余正常用于训练 | 保留原作者 split 与 defect 子类，不把 train/test 当生产好坏标签 |
| Nut | 补充材料 Table I：train 2148、test normal 46、test anomalous 23，总 2217 | 是作者公布的 composite 数，须与实际包清单逐项对账，不是本地已验证数 |
| Yellow-Green Washer | 同表：train 2072、test normal 144、test anomalous 72，总 2288 | 同上；对照两类分母要平衡，不能用大类支配总体指标 |
| 拼接轴 | 主论文 §3.1 写纵向合并，§5.3 的模型提示词写从左到右 | **官方文本内部不一致，当前不能确定切割轴或切片坐标** |
| camera index 含义 | 作者描述四个斜上方相机和一个下方相机，但当前来源没有明确 0..4 到物理相机的映射 | 不把 index 0 自称俯视，也不靠图像长宽比猜映射 |
| 物理件/session ID | 论文说明单件采集；当前未找到可复核的物理件持久 ID、日期/批次/session 字段契约 | composite ID 只能叫对象记录 ID；不可声称不同记录必为不同物理件或会话 |
| 文件布局/标签名 | 完整包清单未到；官方正文未给出具体 loader 路径协议 | 不在本草案中固定 `train/good`、`test/xxx` 等推测路径 |

五视角、采集和划分依据：[作者论文 §3.1–3.2、§5.2–5.3](https://arxiv.org/html/2412.04867v1)。两类数量依据：[作者补充材料 Table I，第 4 页](https://grainnet.github.io/static/pdfs/Manta-supp.pdf)。补充材料只做文本提取，未渲染图片；部分旋转文字提取有 warning，所列两类表行另用普通文本提取核对。

### 官方加载器查证结果

作者项目页的 Code 区块仍是注释中的占位链接 `YOUR REPO HERE`，不是可用仓库。当前 GrainNet 公开仓库只有站点与 GrainBrain；完整站点 tree（未截断，commit `f69e8221612058dec28e18cbcb8d0d51d0295d1f`）内与 MANTA 对应的是 `MANTA.html`，未发现 MANTA loader。通讯作者 hellodfan 的当前公开仓库列表也未发现 MANTA 仓库。**结论仅为“在这些官方入口未定位到可执行数据契约”，不声称代码从未发布。** 不把第三方重制 split 或第三方 loader 当作作者官方代码，也不把同一团队其他粮食项目代码套用到 MANTA。

来源：[作者项目页](https://grainnet.github.io/MANTA)、[GrainNet 仓库列表](https://api.github.com/users/GrainNet/repos?per_page=100)、[站点完整 tree](https://api.github.com/repos/GrainNet/GrainNet.github.io/git/trees/master?recursive=1)、[hellodfan 仓库列表](https://api.github.com/users/hellodfan/repos?per_page=100)。小型来源快照、URL、时间和 SHA 保存在 [documentation receipt](../../datasets/manifests/v0.8/manta-documentation-v1/source_receipt.json)。未下载第三方模型或执行抓取到的代码。

## 3. 完整包到达后，先做元数据对账

当前选择是 `nut` 与 `yellow_green_washer`，合计 2,832,600,154 字节；两包选择原因是本次目标类别和下载规模，不是模型表现。选择凭证由下载线保存在 `datasets/raw/manta-identity-v1/selection.json`。**包内具体成员路径、数量和哈希尚待完整下载校验，不写成已确认事实。**

下载线将提供完整 tar 成员清单及 archive 摘要。下一步仅读头部与文本文件：

1. 检查归档字节数、官方校验值与本地 SHA；统计常规文件/目录/链接、路径唯一性、危险路径。图片先不解码、不展示。
2. 对所有成员归类：图像、异常 mask、README、distribution、JSON/CSV/XML 等文本。若存在作者原始 metadata/loader，先读完整规则并记录 SHA；绝不执行。
3. 建立影像—mask 配对，核对 category/split/normal-or-anomaly/defect-type，不把 ground_truth mask 当成输入图片。核对两类 train/test normal/anomaly 数是否等于表中数；不同则保留差异，不能为了对齐统计删文件。
4. 判定一个成员是否已包含五视角，或是否是五张各自命名的成员。用作者文本/可验证格式契约确认方向、面板边界和 camera 顺序；不得仅从文件长宽比或编号范围推断。当前禁止先做 `width/5` 或 `height/5` 裁剪。
5. 读取任何可用 object/sample/session/camera ID 的定义，验证唯一性与跨 split 重复。文件 stem 即使形似顺序编号，也不自动证明物理件身份或采集会话。

图片 hash/解码尺寸/像素去重属于随后明确允许的预处理阶段；本轮没有做。若最终仍无可信 view 切割契约，只能记录阻塞项，不用猜出的裁剪进入正式单视角评测。可以另拟“同一物体多视角身份输入”研究，但那是另一协议，不套用物品盘点数量规则。

## 4. 分组、曝光与固定视角的拟定顺序

最终 manifest 至少保存以下字段，当前不填虚构值：

`archive_id / archive_sha256 / member_path / member_sha256 / author_category / author_split / author_anomaly_label / author_defect_type / source_composite_id / physical_object_id(nullable) / session_id(nullable) / group_id / group_basis / view_index / view_semantics / crop_xyxy / input_sha256 / protocol_role / exposure_history`。

1. **先 group。** 同一 composite 的全部视角、裁剪、mask、转码必须合组；跨文件的同源或已知同一物理件/session 也合组。先做原始/解码重复连通分组，再分开发和评测。若只有 composite 记录而没有持久物理 ID，明确 `physical_identity_unverified=true`，只作对象记录层描述，不能宣称实物独立随机样本。
2. **再划角色。** 保留作者 split，项目的 `protocol_role` 另列。主评测优先作者 test/normal；拟 48 个对象记录组，nut 24、washer 24，数量以完整元数据确认为准。按预先固定的种子和 group 身份 SHA 排序选组；不足则报告实际全量，不去重复视角凑 N。现在不生成选组清单，也不最终冻结 48。
3. **最后固定 view。** 两类使用完全相同的一个 camera index，暂拟作者序列中的第 0 个，**只有在切割轴、边界和顺序已证实时才能落实**。不根据模型结果、孔洞是否清楚、类别或 GT mask 选“最好看”视角。坐标变换和输入归一化一次冻结，各方法使用相同输入字节。
4. 若将来做五视角补证，仍以原对象组为主分母；每次追加视角的顺序、停止条件、总调用数和耗时须另预注册。不能择五次预测中的最好一次，也不能把五视角当五个新样本来缩小误差。
5. 曝光注册包括开发调试、演示、评测和人工查看。最初技术检查若需要看图，只能用事先划出的开发组并记为曝光；不得看正式评测图后因质量差替换。预训练曝光始终列未知。

作者 train 组不是自动“已训练到本项目”也不是自动无泄漏；需检查本地历史训练/验证/测试来源。若使用任意 MANTA 组调 prompt、阈值或策略，该组及已知同一物理来源全部退出新评测。旧 Screws/LOCO 51 只能作已曝光回归，不与 MANTA 合并成新留出指标。

## 5. 身份与计数、正常与异常分开

主面板拟仅含作者 normal 的两类单件对象，以身份为目标：`nut` / `washer` / `unknown` / `other` / `execution_error`。正式映射 `yellow_green_washer → washer` 的语义与类别说明需在最终冻结前确定；模型输入不得包含作者类别、目录名、split、GT mask、样本标签或给出答案的 BOM。

如果复用四类盘点输出，只能通过事先固定规则提取身份：唯一非零类别为 nut 或 washer 且数量为 1，其他类别为 0、无 issue、无需补证，才记明确身份；其余记未知、额外/错误类别或执行失败，完整保留原输出。这个派生身份口径不把固定单件数量视为计数贡献。

必须报告平衡的逐类混淆矩阵及 C/W/U/E/N 全分母，尤其 nut→washer 与 washer→nut；unknown 和失败不能从准确率分母消失。报告两个常量身份基线“总答 nut”“总答 washer”，在拟平衡 48 图中都只是 50%；“总答总数 1”在单件正常组可恒对，明确说明它无法证明身份或数量识别。

作者 anomaly 是缺陷标签，不是错误身份标签或订单缺件真值。fragmentation 等异常可能使可见碎片数不同，不能给每个异常图硬贴“四类数量恰为一件”真值。异常样本可另做预注册的附属诊断，按 defect 分组且不与主身份面板混为同一难度；不据正常/异常标签判定 ready/manual。当前不选异常图、不运行该面板。

## 6. 比较与结论边界（待方法冻结）

比较方法名单、版本、模型哈希、prompt、输入预处理、采样参数和超时/失败处理均待最终冻结。旧 v0.8 两类 detector 否决已被拒绝，不因换到新数据就默认获得晋升资格。至少给出当前 G 的完整独立运行作基线；任何候选必须在首个新图预测前固定，所有方法同图字节、同失败规则并交错次序，保留原始返回和实际总时延。

一次按固定顺序完整运行后才分析。允许完整保留失败，禁止只重试错图后覆盖首遍。统计单位是对象记录组；所有候选都必须给出每类拒答损失和错误数，不能以总体高分掩盖 washer 误拒。该两类诊断无生产自动晋升结论；即便结果很好，也需另有多件、近外观、真实任务与其他类别的证据。

## 7. 最终冻结前的明确缺口

- 两包完整下载、官方校验、完整成员表与作者统计对账仍待完成。
- 官方 MANTA loader 尚未定位；包内文本是否补足加载契约尚未知。
- 五视角拼接方向、边界、序号与物理相机映射尚未解决，不裁图。
- composite/sample ID 与持续物理件/session ID 是否存在及能否跨 split 关联尚未知。
- 待固定主面板实际 group 数、唯一 view、重复处理、全部方法、指标与失败规则。
- 严格遵守现有 [MANTA 许可复核](MANTA_LICENSE_CHECK.md)：作者数据条款为 CC BY-NC-SA 4.0，Figshare 的 CC BY 元数据冲突未消除；本草案不授权商业发布或传播原始图片。

这是一份元数据阶段草案。任何上述结论更新都须引用新文本/目录证据并另记版本；不能把下载完成、样本尚未推理或类别平衡当作独立实物验证已经成立。
