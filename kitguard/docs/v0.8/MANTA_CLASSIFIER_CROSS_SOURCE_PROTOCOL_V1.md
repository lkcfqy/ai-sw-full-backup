# MANTA 身份组件：跨来源固定执行协议 V1

2026-10-02。本协议固定一次**已曝光、作者框定位的组件诊断**，不授权推理或修改生产。准备工具/执行器/审计器的最终 SHA、579 条 manifest、根批准和软件环境由 root 在运行前另存不可覆写 freeze；未齐全不得运行。旧 [草案](MANTA_CLASSIFIER_CROSS_SOURCE_PLAN_DRAFT.md) 保留，不回写为执行记录。

## 目的与固定对象

内部第 10 轮已独立审计为 256C/0W/0U/0E/0N，达到继续研究条件，见 [结果](MANTA_CLASSIFIER_RESULT_V1.md) 与 [判定](MANTA_CLASSIFIER_DECISION_V1.json)。本次只检验该固定头在外部来源作者 ROI 上的身份迁移与 bolt 误接收；不检验独立定位、全图计数或 BOM。不得用本次结果换 epoch、阈值、裁区或样本，也不得用新 LOCO24 选择参数。

| 固定来源与分组 | 原图 | nut | washer | bolt 开放类别对照 |
|---|---:|---:|---:|---:|
| Screws 原 validation collection | 44 | 156 | 0 | 387 |
| FOD GOPR0183 | 12 | 12 | 0 | 0 |
| FOD unprefixed_Washer | 12 | 0 | 12 | 0 |
| FOD GOPR0181 | 12 | 0 | 0 | 12 |
| 总计 | 80 | 168 | 12 | 399 |

完整 579 ROI，主身份分母 **180**，开放集分母 **399**。顺序严格按既有 grouped detector `preflight.json.validation` 的 80 图顺序，再按每图 `ground_truth` 顺序；准备前先保存全部唯一 `(source_id, annotation_id)` 和 `input_id`。不读其他 split、FOD held-back、新 LOCO24 或 MANTA test 像素。

Screws 原数字类型 7/9/10/11 按已有教学映射计为 nut，各 44/36/38/38 个；不能写成作者直接标注英文 nut。FOD 是 `author_annotated_target_only`，不认证全图无其他目标。80 图曾用于三类检测器验证/选模等开发；579 ROI 不等于 579 个独立实物，原图/来源组数另报，无物理或 session 隔离保证。模型预训练曝光未知。

## 输入与一次执行

1. 解码前核对原图字节 SHA、已有标注/manifest SHA。原方向 RGB、原图尺寸必须与元数据一致，不自行 EXIF 旋转。解码后核对按原来源算法保存的 RGB 像素 SHA。
2. 使用已保存的原图连续 AABB `xyxy`；Screws 同时保留作者定向框和既有投影链。左/上 floor、右/下 ceil，再限制于图像边界；Pillow 右/下为排他边界。不加 margin、不旋转、不选中心、不过滤小物体。空框/几何不符报 E，不猜裁区。AABB 可能带邻件或背景，属于 **oracle author ROI**。
3. ROI RGB→L→RGB，`ImageOps.pad((224,224), LANCZOS, black, centering=(.5,.5))`。不套用 MANTA 五面板拆分或其最小尺寸准入条件。保存裁区、ROI/灰度/224 输入像素与 PNG 字节 SHA；ImageNet mean `[.485,.456,.406]`、std `[.229,.224,.225]` 不变。
4. 使用唯一第 10 轮 `final.pt` 完整 state，严格检查原 COCO 骨干/两类头来源。模型原始类别索引固定 `0=nut,1=yellow_green_washer`，诊断仅把后者语义投影为 `washer`，不更改模型类别名或顺序；eval、MPS、FP32、batch32、固定顺序，无增强、搜索、训练或重试。全体准备成功时为 19 批、末批 3 条。标签/作者坐标/来源名称只用于准备及离线评分，不作为 forward 输入。
5. 先物化全部 579 条 N。准备/张量/forward 失败逐条 E；停止后未尝试仍 N，不回填空 logits 或“安全拒答”。失败批的受影响成员完整保留。阶段尝试与实际 forward started/completed 分开记录；非完整运行不能声明完整结果。运行前后核对 source/model/data/environment 哈希，变化为完整性失败。

`tiny = min(x1-x0,y1-y0)<16`，依据已有连续 AABB、取整/上采样前计算，恰好 16 不算 tiny。固定元数据为 FOD washer 4/12、bolt 4/12；其余 0。`author_aabb_clipped` 保留 true/false/null：Screws nut 1 true/155 false、bolt 8 true/379 false；FOD 36 条全部 null。另存 `integer_crop_clamped`，不得把 null 当 false，也不得从没 clamp 推断物体完整可见。

推理前 root 已按固定 27 条布局 QA 查看 3 页；`roi-0002/0492/0515/0524` 等 Screws 旋转框 AABB 可含明显邻 nut/bolt 与背景，FOD tiny 有模糊目标。名单/裁区不变，全部 579 保留。因此 bolt 接收是“以作者 bolt 为目标的 AABB 被接收”的操作性指标，**不是干净单 bolt 图像的开放集准确率，也不能据此把所有接收归因为分类头认错纯 bolt**。原始选择、全 579 字节重裁核对与 27 条目视收据分别保留在 `test-results/v0.8-manta-transfer-root-layout-selection-v1.json`、`test-results/v0.8-manta-transfer-root-check-v1/`；目视范围不扩大到全 579。

## 独立评分约定

成功行必须有两个有限 logits、两个合法 probabilities、error=null；独立稳定 softmax 核验绝对差≤2e-6。**接收只按保存概率 max≥0.9，决策阈值不加容差。** argmax 并列取索引 0。E/N 不计算伪概率，仍保留分母。

主表 180 条分别计 C（接收且正确）、W（接收且错类）、U（max<.9）、E、N，和 nut→washer、washer→nut。报告每类、来源×类别、tiny、clipped 三态及 `source_group×class×tiny×clipped` 的分母与计数；零样本单元标 N/A。总正确覆盖 C/180 与 nut C/168、washer C/12、两类等权宏平均分开；另列三个非空来源×类别身份单元的宏平均，不让 156 个 Screws nut 掩盖仅 12 个 washer。置信分数不是校准正确概率，不把 ROI 当独立物理样本作泛化声明。

解析对照固定：强制 argmax 沿用真实成功行且保留 E/N；恒答 nut 为 168C/12W，恒答 washer 为 12C/168W；二者类别宏平均均 50%。全拒答为 180U。恒定/全拒答是不用模型的完整分母解析基线，和实际失败率分开。

bolt 独立表 399 条只计 `accepted_nut / accepted_washer / U / E / N`。任一 accepted bolt 是 **open-set false acceptance**，不混入主 180 的 W。误接收率为 `(accepted_nut+accepted_washer)/399`；另报 E/N 及已测试比例，失败/未测不表示正确拒绝。未知只表示弃权，不能称识别出 bolt。强制 argmax 对成功 bolt 全部接收；恒答任一身份为 399 次误接收；全拒答为 399U，但主身份正确覆盖为 0。

仅保存原运行的 decode/tensor、同步 batch forward、总 wall 时间及计时边界；不得逐行重复累加同一 batch 时间。它不是 MLX 全链路/订单端到端时延，也不与历史系统延时冒充同期公平对照。

## 简单独立审计与结论边界

推理前固定独立 `audit_manta_transfer.py` 及纯合成合同 SHA。审计不导入 runner/preparer 评分函数、不加载模型或解码图像：只读冻结 metadata、preparation、完整 raw logits/probabilities 和绑定文件哈希。核对 579 唯一顺序、80 图及各来源/类别分母；metadata→prepared→raw 身份与输入 SHA；模型、source snapshot、批准、完整运行状态/实际调用收据；独立重算上述两表、所有切片、对照与导出 analysis 一致性。输入文件仅按字节哈希核验，不宣称本审计重新生成裁图或模型返回。

审计失败保存原错误，不覆盖 run；先处理完整性问题再解释质量。该审计证明保存证据与计算一致，不认证历史硬件执行。没有自动生产晋升或追加调参规则：即使全部正确，也仅支持进一步研究；后续需单独冻结独立候选框召回/定位失败、全图开放类别与完整旧 51 开发回归。不得把 VLM 点称独立定位。

内部 256、迁移 180、bolt 399、旧 51、新 LOCO24 的分母始终分开。许可保留 MANTA 作者 CC BY-NC-SA 严格非商业条件与 Figshare 元数据冲突；FOD 仅按现有授权本地研究，不推导商业/再分发许可。

## 已确定绑定与待冻结字段

| 已确定证据 | SHA-256 |
|---|---|
| `training-runs/v0.8/manta_classifier_v1/final.pt` | `ea29bfcf33dcf680e1b3ac2afa26de366991d029a42a3b5fe7ef7a5be1b3f985` |
| `scripts/v08/train_manta_classifier.py` | `5f3475a5b911cada936eb62fae24890b1f4096153307a6b64a7e5619bca9057c` |
| 原 COCO `fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth` | `907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5` |
| `test-results/v0.8-manta-classifier-independent-audit-v1.json` | `b9df04653db0e0ded4b6db2e0165e74508cc2c02a20829f98f25a5f1a9c57afd` |
| `training-runs/v0.8/grouped_detector_v1/preflight.json` | `f3e31e0420ef5b18e731484d9e0da58f5f51ca3c0479d7cdc064917622e1b63e` |

其余原标注/source 元数据 SHA 见保留的 [草案来源表](MANTA_CLASSIFIER_CROSS_SOURCE_PLAN_DRAFT.md)。**新 prepare/runner/auditor/本协议、579 metadata/preparation、运行环境、根推理批准的路径与 SHA 均待 root 最终 freeze 填入外部回执**；本稿没有预填未产出的哈希或冒称已经执行。
