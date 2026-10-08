# MANTA 两类身份组件 V1：固定准备协议

2026-10-02。仅作者 train 的非商业研究准备；**不训练、不推理、不修改生产默认**。冻结目录与准备输出均使用新路径，已有目录禁止覆写。本文及准备器、合同测试必须在首次新图解码前保存原字节快照。本协议不是作者 test 或新物理件独立评测。

## 问题与边界

旧 G 的 024、120、172 三错中，两个空间轮及同一 VLM 身份轮都给出 washer。type_007 按项目早于评测的教学映射归入 nut，不是 MVTec 作者直接命名 nut。独立视觉分类权重可能提供不同类别证据，但不能认证真值或独立错误。MANTA 的 nut 与黄绿 washer 存在颜色/形状差异；高内部成绩不能证明银色混放识别改善。四个 MANTA 开发记录的 G=4C 只是已有接口检查。

作者正常训练记录为 nut 2148、yellow_green_washer 2072，共 4220 composite；每 composite 含同件五视角，但无持久实物/session ID。全部五视角、mask 和派生物绑定同一记录。相邻编号分组仅为保守代理，不能声称物理隔离。预训练曝光未知。作者数据页明确 CC BY-NC-SA 4.0、非商业；Figshare 的 CC BY 元数据冲突未消除。保留来源声明，本准备不授权原图或派生材料发布/商用。

## 1. 在任何新像素读取之前冻结

固定源：`datasets/manifests/v0.8/manta-identity-v1/record_metadata.jsonl`，SHA `0758a4a35caed254e0de9d0d8c60cbdf301f2d9bbfc373f9d808680c869f7dbc`；source manifest SHA `7164d37e7ac6b716983bb081243d0e471deb6bbaf16d18c6dfa7a5ac3008b46b`。绑定已下载完整包 SHA、成员表、四例原准备/布局凭证、许可凭证及 Pillow/Torch/Torchvision 本地实现。冻结只读 metadata、文件哈希，不导入模型库、不解码。

固定种子为 `kitguard-manta-classifier-v1-20261002`。每类连续编号按 `(record_number-1)//32` 组成代理块；只取完整 32 条的块。块 0（包含原已曝光 00001/00002）强制入选，其他完整块按 `SHA256(seed|select|class|block)` 排序取前 15，合计每类 16×32=512，两类总 **1024**。排除尾部不完整块只是事前预算规则，不依据画面质量或输出。没有候补、替换或重试。

每类非零入选块按 `SHA256(seed|partition|class|block)` 排序前 4 暂列 validation，其余 train，初始为 768 train/256 validation。四个旧开发记录始终 train。先保存完整 1024 名单、32 块、角色、QA 名单和全部参数到 `protocol.json`，再保存脚本/本文/测试原字节到 `source_snapshot`，最后写 `freeze.json` 绑定二者。准备只能由该快照脚本加明确 freeze SHA 启动。

## 2. 作者 train 的唯一像素处理

归档先全文件 SHA 核对。以流式 tar 只对冻结的 train/good 精确路径调用 `extractfile`；不提取/解码 test、mask、未选 train。压缩流为了跳过成员会顺序解压字节，这不等于把 test 作为图像读取。禁止 `extractall`，拒绝链接、重复路径、字节数差异。

每个选中成员记录原字节 SHA、PNG 类型、尺寸、mode、frame、EXIF 和完整 RGB 像素 SHA。只接受单帧 RGB PNG、空 EXIF、宽度可被 5 整除、单面板宽和高均 64–2048、单面板宽高比 0.5–2。该宽松几何规则来自已固定横排处理假设，不证明每张物体完整。异常原样记失败，不猜轴、不换视角。

唯一输入是 `[0,0,width/5,height]` 第 0 面板；RGB→L→RGB；保持比例用 Pillow LANCZOS 缩放并居中补黑到 224×224。无随机裁剪、颜色增强、翻转、阈值分割或根据标签选视图。保留 5 面板各自 RGB/灰度像素 SHA、最终输入文件和像素 SHA；像素指纹包括 mode/尺寸，不能把尺寸不同但字节碰巧一致当同图。输入文件名只为中性 `record-XXXX.png`，标签单列 metadata。

每个计划记录始终留在 `records.json`，状态 prepared/failed/not_attempted，原始错误和逐条 append-only `attempts.jsonl` 保留。任何读取/布局失败、未尝试、源码/数据变化、类别重复冲突都会阻断训练准备；不会只用成功子集。

## 3. 精确重复连通分组与最终角色

对选中 1024 条计算：原字节、完整 composite RGB、五个面板的 RGB/灰度（允许跨面板位置比较）、最终 224 灰度输入的精确像素重复。与同一代理块的关联共同建立连通分量。**不比较作者 test/未选 train，不声称感知重复或物理身份已排除。**

同一连通组不能跨 train/validation。若组连接任何初始 train 或四例曝光，则整个组归 train；不补选 validation，所以最终分母可以变小。若组含两个作者类别，整个组标记 `quarantined_label_conflict` 并阻断准备，不把矛盾标签偷偷移到 train。所有重复行和边均保留，后续报告同时给记录数与组数，主验证须按类内连通组 macro，不能把重复帧当独立样本。每类最终至少 train 256 条、validation 64 条，且各角色至少两个连通组，否则阻断，不补选。

## 4. 冻结抽样视觉 QA

固定每个入选 32 块的第 16 条，共 32 条，另加原 4 个开发记录，总 **36 条**；不依据预测或图像质量挑选。机器检查覆盖全部 1024，contact sheets 展示选中 36 条的原 composite 缩略图与实际 224 灰度输入。36 中含初始 validation 的 8 条，明确属于预声明布局 QA 曝光，validation 不能再叫图像盲测。QA 只核五面板、坐标、完整性、颜色去除是否按协议，不允许据观察调整超参、换样本或更换视角。

准备结果保持 `prepared_pending_visual_review`；AI reviewer 将 sheet SHA、逐条结论、范围及限制另存不可覆写 `visual_review.json`。异常留存并阻断，不追写旧准备收据。不得把抽样正确扩大成 1024 条逐图视觉认证。根审阅之前，`training_authorized` 始终 false。

视觉回执精确契约：`schema=kitguard.v08.manta-classifier.visual-review.v1`、`created_at_utc`、`status=passed|blocked`、`reviewer={kind:AI,name:progress_audit,human_participants:0}`、`freeze_sha256`、`preparation_sha256`、`records_sha256`、`grouping_sha256`、`sheets=[{path,sha256,record_ids}]`、`reviewed_records=[{input_id,member_path,role,input_sha256,accepted,notes}]`、`limitations`、`training_authorized=false`。成功时 36 条必须与冻结 QA 名单逐项相同、均 accepted，6 张 sheet 与 preparation 的路径/哈希/记录表相同；这里的 accepted 只表示抽样布局处理可用。根训练批准是另一个绑定这些收据的显式文件，不能由本 AI 视觉回执替代。

## 5. 下一阶段唯一候选（本轮不实现运行）

可用的本地初始化文件为 `~/.cache/torch/hub/checkpoints/fasterrcnn_mobilenet_v3_large_320_fpn-907ea3f9.pth`，77,844,807 B，SHA `907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5`。下一阶段先构造相同 91 类原 COCO Faster R-CNN、严格加载权重，再只取 `backbone.body` 最后输出 key `1` 的 960 通道特征，全局平均池化接 Linear(960,2)。这不是 YOLO、不复用已经学过 FOD 的三类头，不新增下载。正式实现必须再验证实际 feature contract；不匹配报错，不猜 layer。

骨干固定 eval、所有参数冻结，只有新两类头可训练。输入按 ImageNet mean `[.485,.456,.406]` / std `[.229,.224,.225]` 标准化；seed 20261002、MPS/FP32、batch32、worker0、SGD lr .01/momentum .9/weight_decay .0001、固定 10 轮、无增强。最终第 10 轮固定评估，不根据 validation 选 epoch 或扫描参数。每轮训练/完整验证、checkpoint/optimizer、输入/软件/源码 SHA 全保留。

固定 softmax 最大值≥.9 才给两类身份，其余 unknown；该值不是校准正确概率，更不提供 bolt/背景的开放类别拒绝保证。每类/每来源组给 C/W/U/E/N 全分母、双向错类、group macro 覆盖、拒答率；另报强制 argmax 和总答 nut/总答 washer 基线。继续研究门槛为每类正确覆盖≥75%、W/E/N=0，不自动晋升。任何内部结果都只是同装置两类组件证据。

## 6. 可检查的独立定位接口，暂不集成

准备器暴露纯合同 `validate_proposal`：原图 SHA、原尺寸、proposal ID、原图像素空间 bbox、独立 detector 权重/配置 SHA 和 proposal score。明确拒绝 VLM 点、作者 GT/BOM/计数答案字段作为提议来源。将来区域提议必须由独立 detector/RPN 给出全部框，不能把 VLM 点映射框说成独立定位；将类别分数与定位召回分开审计。

先在已曝光且有作者框的数据按来源组报告每类 proposal recall（1:1 IoU≥.5）、未匹配 GT、额外/重复提议、所有原始框、组件 C/W/U/E/N 与额外时延。LOCO 缺作者实例框，新增标注需独立来源/审核，不用 detector 自产框当真值。定位召回不够或类别仍跨域失效就停在组件，不接混合 BOM。

若再进入系统阶段，只允许冲突→unknown，不自动改成 nut、不补数。完整旧 51 只作一次冻结开发回归：C≥41，W/E/N/主全四类 AFR=0，14 个旧 LOCO C 全保留；不能用这批图修阈值再叫留出，不能用新 LOCO24 成绩选参数。未来新真实来源验证另立协议。默认产品、已冻结模型/工具/证据全部不改。
