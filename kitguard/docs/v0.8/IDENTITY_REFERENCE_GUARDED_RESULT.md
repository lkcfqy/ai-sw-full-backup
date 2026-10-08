# 身份阶段固定参考：完整 51 图结果与独立审计

2026-10-02。**候选拒绝，生产默认不变。** 完整 51 张的独立原文回放审计通过，但质量门槛未通过：C40/W3/U8/E0/N0。它没有解决旧 G 的任何明确错误，并使 1 张原本正确的正常袋装图变为不确定。不能把“审计通过”写成“模型质量通过”。

## 全量结果

C=正确明确观察，W=明确错误，U=不确定/拒答，E=执行失败，N=未执行；每行完整分母均为 51。

| 方法 | C | W | U | E | N | 主面板 any false-ready |
|---|---:|---:|---:|---:|---:|---:|
| 历史无参考 G | 41 | 3 | 7 | 0 | 0 | 3/51 |
| 仅身份阶段固定参考 I | 40 | 3 | 8 | 0 | 0 | 3/51 |

I 的 Screws35 为 C27/W3/U5；LOCO 正常16 为 C13/W0/U3。完整配对为 C→C40、C→U1、W→W3、U→U7。旧 41 个 C 保留 40，旧 LOCO14 个 C 保留 13；所有旧 U 均未改善为 C。

预注册门槛：51 全覆盖、W/E/N=0、C≥41、主 all_four 错误就绪=0、旧 LOCO14C 全保留。实际仅全覆盖及 E/N=0 通过；W、C、主面板和正常保留门槛失败。因此不晋升，也不能称参考证明了安全改善。根事前规定只有此质量门槛通过才可将 I 加入下一次 LOCO24；按该规则 I 不符合纳入条件，最终方法选择由根另存，不由本报告自动冻结。

主 all_four 面板仍有 3/51 张可对某个合法但错误的 BOM 给出 ready。次 source_supported 面板为 0/51；它把 Screws 支持类限制为 bolt/nut，不能覆盖本次 nut→washer 误判，**不能用次面板的零替代主面板的 3**。E/N 未测风险为 0，但可见明确错误仍为 3。

## 三个旧错误与一个新增拒答

下列真值保持预先冻结的作者类型投影；作者原标注为 type ID，本文不将其说成作者直接标注 nut，也不按本轮视觉结果回改真值。

| case ID | 冻结真值 bolt/nut/washer/bracket | I 明确输出 | 转换 |
|---|---|---|---|
| v07-screws-screws_120-3e86c9ca51d9 | 1/1/0/0 | 1/0/1/0 | W→W |
| v07-screws-screws_024-07f4bcf5c349 | 1/1/0/0 | 1/0/1/0 | W→W |
| v07-screws-screws_172-53dacfde39d4 | 2/1/0/0 | 2/0/1/0 | W→W |

三个实例在两次空间清单中均被列为 washer；身份阶段实际接收完整目标、该目标裁剪、nut297 与 washer057 两张固定参考后，仍返回 washer / independent_object / through_hole、空 issue，原身份规则未否决。它们是同模型的相关复核共同错误，不是独立证据相互确认。此处来自已保存原文和完整 schema 回放，不追加模型推理或重选参考。

新增损失为 `v07-loco-screw_bag-train-good-144`：作者正常真值 2/2/2/0；两空间轮均列出正确的 2/2/2/0，身份返回中 p006 仍为 washer、independent_object、through_hole，但 issue 为 `split`。既定规则因此将 washer 置未知并要求 recapture，最终 2/2/unknown/0。这里报告实际规则触发，不断言该参考是唯一成因；本次空间轮也重新执行，历史基线不是同期对照。

## 调用、时延和实际审计边界

运行于 2026-10-02 10:42:13–11:05:22 KST，51 次观察完整结束，source_changed=false、final_integrity_verified=true。原冻结源码 65 文件、模型 payload 16 文件、51 张上传归一输入均由独立审计核验。

- 133 条 generation records = 133 次实际 generate 开始 = 133 次实际完成 = 133 个保存并成功解析的原文；无缺失原文运行错误。
- 两空间轮共 102 次；31 张进入条件身份阶段、20 张按原条件跳过。不是每张都接受身份参考检查。
- 274 张实际调用输入逐字节核验；79 个身份目标裁剪重建。前两轮各只有目标图片，身份轮才追加 nut/washer 固定参考；图片角色、原向/90°旋转、crop、schema、system/user、token 预算和温度均重建比对。
- 每次最终完整 Observation 与诊断同冻结原文回放一致；独立重算分母、转换、两面板及门槛，不以 runner 自己的 summary 证明正确。

全 51 次实际观察时延 P50 **21,982ms**，P90 **47,767ms**，最大 **51,425ms**，总计 **1,388,699ms**。冷首例计入全分母。额外 warm50：P50 21,626.5ms、P90 47,491ms、总计 1,337,274ms。旧 G 历史 P50 21,814ms、P90 46,231ms、总计 1,352,628ms，仅供非同期记录对照；不声称速度改善或参考位置的因果效应。

本次独立审计一次成功，未改原 run、raw、预测、冻结源码或标签；没有新增 MLX/模型调用。CPU 回放验证保存输入、原文解析和后处理一致性，不能证明历史模型返回真实性或重做硬件计时。独立 runtime-app-data 的 SQLite 按 immutable 只读核验为固定 schema、7 表全空；源 snapshot 无新增数据库，避免先前空间参考实验的快照副作用。

## 适用范围与证据

这是已曝光 51 张开发回归：35 Screws 同域裁剪 +16 LOCO 正常图，不能称新留出。LOCO16 全部 2/2/2/0，恒定输出也可得到 16/16 精确计数，不能据此宣称数量异常识别能力。无 bracket 阳性；同一实物/采集会话隔离及模型预训练曝光未知。固定参考的类别依既定作者/项目映射，AI 只核过裁剪对象与边界，未代替真人实物螺纹认证。仍无实际现场安全放行或真人效益证据。

关键不可变凭证：

- [冻结](identity_reference_guarded_freeze_v1/freeze.json)，SHA `2e0ef97133988a2ca00a36a08b82e4a42e2d97f61ae01ef38980fe7d72f8b19e`。
- [原运行](../../evaluation-runs/v0.8/identity_reference_guarded_v1/run.json)、[完整预测](../../evaluation-runs/v0.8/identity_reference_guarded_v1/predictions.jsonl)、[原分析](../../evaluation-runs/v0.8/identity_reference_guarded_v1/analysis.json)。预测 SHA `3c7474fbdb6c4b8befa03d50a5ccbfd0b1216e8225152416015442bd9908e5b6`；分析 SHA `42d8cffb5e634775e76bb862241be4707ea2721bc6830a362c60852ea7b1b7ef`。
- [独立审计](../../test-results/v0.8-identity-reference-independent-audit-v1.json)，SHA `51e38affdf7c226d37377c5de8ac39df23c0e756159d11438290e47a0874bec4`；[执行日志](../../test-results/v0.8-identity-reference-independent-audit-v1.log)。
- [预先审查的独立审计合同](IDENTITY_REFERENCE_AUDIT_CONTRACT.md) 与 [实验协议](IDENTITY_REFERENCE_GUARDED_PLAN.md)。独立审计入口 SHA `a2be00fc3d12583583e03eb06265248550a7f085ee4019d5c88f2b35d4e4ac5c`。
- [判定与完整文件 SHA 绑定](IDENTITY_REFERENCE_GUARDED_DECISION.json)。原 v0.7 和其他 v0.8 实验、提交 PDF/PPT、生产默认均不改。
