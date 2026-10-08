# 参考输入追溯工作版修复

2026-10-02；**0.8.0.dev1，未发布。** 修改当前工作目录，不修改封存的 v0.7 源码包、报告、历史结果，或正在运行的参考实验隔离快照。实验的历史观察协议不被此修复替换。

## 本次改动

`Observation.reference_evidence` 是宿主程序生成的可序列化元数据，不进入模型的提示词或输出约束。成功检查把它保存为 `check.reference_evidence`；失败尝试在 `observation_diagnostics.reference_evidence` 保留已经准备的输入及调用状态。

- `images`：按实际输入顺序记录 `part`、`stored_sha256`、`prepared_sha256`、`prepared_size`、`image_index`。Image 1 始终为待检图，参考从 Image 2 开始。两个 SHA 分别对应传给观察器的存储文件字节和实际生成的最大边 512px PNG。
- API 在本次检查的订单快照上核对全部类别与存储 SHA，再给每项绑定 `photo_id` 和上传前原文件的 `upload_source_sha256`。不从“检查完成时的当前参考”或另一请求的状态补全输入身份。
- `stages`：原向、旋转、条件身份检查的实际顺序及状态；成功观察的空间阶段必须为 `completed`，identity 的完成/跳过必须与保存的观察证据相符。失败诊断可保留 `attempted` / `failed`。identity 的参考索引恒为空；跳过分别写 `skipped_base_unclear` / `skipped_no_candidates`，不称已经身份复核。
- `observer_protocol_sha256`、`observation_mode`、预处理协议、Pillow 版本及 `max_side=512` 绑定生成过程。API 核对当前观察器协议与模式；工作版源码改变自然产生新的协议 SHA。
- `prepared_bytes_retained=false` 明确未新增 PNG 存储。记录可用来校验输入，不能直接提供历史预处理图片字节回放；重建需要相应存储文件、原版本预处理代码及依赖，并须与保存 SHA 相符。

历史检查没有该字段时继续表示“当时未记录”，不会用今日参考补写。原有参考历史、事件、`evidence_epoch`、旧检查失效和人工复核 SHA 绑定不变。参考对模型输入的存在不证明模型正确利用它，也不认证实物、内螺纹、尺寸或材质。

中韩参考提示增加“仅作类别示例，不计入待检数量”。历史详情与离线证据查看器呈现参与阶段、类别/顺序和可展开的 SHA，并对历史缺字段显示“未记录”。当前 Python 项目版本为 `0.8.0.dev1`，`index.html` 对修改的 app/audit 脚本使用新缓存标记；这不是一次发布或模型晋升。

## 验证与边界

只使用合成工程像素与注入式 CPU 观察器，未调用 MLX、训练模型或模拟真人反馈。检查实际 PNG SHA/顺序、身份阶段不含参考、失败留证、API 源与协议绑定、参考替换失效、旧记录不补写，并保留所有验证日志。

- [首轮 14 项合同](../../test-results/v0.8-reference-evidence-contract-01.log)通过。
- [相关状态/API 回归 174 项](../../test-results/v0.8-reference-evidence-contract-02.log)通过；没有运行整个项目测试套件。
- 同行审查在初稿中复现了“成功检查接受空/错误阶段状态”的元数据缺口；增加成功 Observation 的阶段顺序/完成状态/identity 跳过一致性约束，并增加篡改用例。[修复后 34 项合同](../../test-results/v0.8-reference-evidence-contract-04.log)通过。原 4 个篡改复现均返回 HTTP 503，未保存成功检查；[最初接受记录](../../test-results/v0.8/reference-trace-peer-review-v1/initial_malformed_acceptance.json)与[最终拒绝记录](../../test-results/v0.8/reference-trace-peer-review-v1/final_malformed_rejection.json)都保留。
- [Ruff](../../test-results/v0.8-reference-evidence-ruff-02.log)通过；`node --check kitguard/static/app.js` 通过。

模型 `_Observation` / `SpatialInventory` / `IdentityResponse`、system/user 文本、图像预处理、数量与决策规则不变。[独立同行差分](../../test-results/v0.8/reference-trace-peer-review-v1/observer_call_comparison.json)使用修改前可信原字节快照，覆盖 48 个配置、192 次前后合成观察，逐调用的提示词、模型 schema、输入字节 SHA、token 上限及原观察内容完全一致；未导入 MLX 等禁止模块。浏览器验收由根任务另行负责。

## 不受影响的实验

参考实验冻结文件 `docs/v0.8/reference_guarded_freeze_v1/freeze.json` 的 SHA 为 `6530e2341a60fd99fb758eac2c5f3d6010f7b8c973be71a800ad5ca0d2578462`。本次只读复核其 60 个隔离源码文件均与冻结 SHA 一致。正在运行的 51 图实验使用该隔离副本，其结果不能归因于本工作版追溯修复。
