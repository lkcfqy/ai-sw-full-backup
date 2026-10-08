# 核验失败后的恢复提示

2026-10-02；**0.8.0.dev1 工作版，未发布。** 此改动只涉及 `workflow.js`、`workflow.css` 与一个 Node 合同，不修改后端任务状态、模型可用性、推理协议或已冻结实验。

原问题：核验失败后刷新页面，API 仍返回当前失败任务，但主流程的错误提示消失，页面回到“现在可以核验新证据”。原失败原因仍在历史与导出中，重试也可运行；这是恢复提示缺失，不是记录丢失。[初始只读复现](../../test-results/browser/workflow-readonly-v08/review-receipt.json)与原源码副本均保留。

修复后，中韩文页面从保存的最新任务派生失败／中断提示，显示实际原因、“模型状态”和明确的重试操作。提示必须匹配当前订单、版本、最新且当前所选照片、照片 SHA 与 `evidence_epoch`。新任务、新证据、版本变化、较新检查或完工状态使旧提示失效。刷新只读状态，不自动重试；用户重试使用新的请求键，成功后提示消失，旧失败记录仍保留。提示不把一次任务失败解释为模型不可用。

## 验证记录

- [针对性合同](../../tests/inspection_recovery_ui_contract.cjs)覆盖真正的空内存页面恢复、失败与中断、中韩文与错误文本转义、范围失配、较新同步检查、显式重试及成功后的清除。`node --check kitguard/static/workflow.js` 与 `node tests/inspection_recovery_ui_contract.cjs` 通过；另有公开上传与参考追溯 UI 合同通过。
- Chrome 隔离服务 `127.0.0.1:8782` 实际复验了初始失败、刷新后提示持续存在、语言切换、点击新提示的重试按钮、成功后清除。[修复阶段回执](../../test-results/browser/workflow-readonly-v08/fix-receipt.json)保留当时“等待同行审查”的状态，没有回写历史。
- 全过程只有 **4 次合成观察器调用（2 次失败、2 次成功）、0 次真实模型调用、0 位真人参与者**；使用明确标注的合成图片与 `backend=test`。这不是识别评测、真实模型时延或用户研究。没有查看新数据图片，没有产生实物完工记录。
- 独立 AI 同行审查复核了当前范围、陈旧失败失效、服务端文本转义与显式重试路径，并独立通过语法与针对性合同；未重复浏览器或模型运行。[最终回执](../../test-results/browser/workflow-readonly-v08/final-receipt.json)绑定源码、前后记录与本说明。
- [清理回执](../../test-results/browser/workflow-readonly-v08/cleanup-receipt.json)确认浏览器页签已关闭、隔离服务已停止、8782 不再监听。完整工程回归由主任务另行记录，本页不声称已运行全套测试。

从仓库根目录复现纯 CPU 合同：

```sh
node --check kitguard/static/workflow.js
node tests/inspection_recovery_ui_contract.cjs
node tests/public_upload_ui_contract.cjs
node tests/reference_evidence_ui_contract.cjs
```
