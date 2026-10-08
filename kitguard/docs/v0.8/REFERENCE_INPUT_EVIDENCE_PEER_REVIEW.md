# 参考输入追溯同行复核

2026-10-02；当前工作版 `0.8.0.dev1`。结论：本轮有界 CPU 合同通过，可进入浏览器验收。这不是识别准确率、真实模型运行或发布结论。

以作者修改前保存的原字节快照为基准，比对五种观察模式、0/1/2 个参考、上下文开关、不同 BOM 和 guarded 成功/跳过/失败分支，共 48 种配置、192 次合成观察。system/user 文本、模型 schema、输入图像字节 SHA 与次序、token 上限、调用数量与顺序，以及除时延和新增追溯字段之外的原观察内容全部一致。改变 BOM 没有改变调用或图像观察。脚本未导入 torch/MLX，未加载模型。可信快照为证据目录的 `author_before/`；早期 `before/` 取到补丁中间状态，已明确标为无效比较基线，保留而不使用。

同行初审发现成功检查可接受空阶段、错误模式、伪造 identity 跳过、失败原向阶段四类元数据。作者补充阶段顺序/完成状态、identity 证据一致性以及 runtime 模式约束后，四个相同 API 复现全部从 HTTP 200 变为 HTTP 503，`latest_check` 为空。初次失败证据与最终拒绝记录都予以保留；初次执行的精确时间未记录，不补造时间。

补充的审查详情与离线 HTML 仅读取该检查保存的 `reference_evidence`，显示原向、旋转和 identity 的实际状态及参考索引。identity 无参考输入，跳过状态不称已执行；历史无字段明确“未记录”，不借用今日参考图。技术 SHA、预处理和尺寸位于第二层折叠区。保存了输入标识不代表保存了预处理 PNG 字节，也不证明模型实际利用参考。显示变更不修改订单状态或历史数据。

34 项相关 Python 合同通过；Node 中韩历史/阶段/折叠/转义合同、JS 语法和 Ruff 通过。主线另行负责浏览器及全套工程回归。源 SHA、命令、初次缺口和最终复现详见[复核回执](../../test-results/v0.8/reference-trace-peer-review-v1/review_receipt.json)与[逐调用比较](../../test-results/v0.8/reference-trace-peer-review-v1/observer_call_comparison.json)。

```sh
.venv/bin/pytest -q tests/test_reference_evidence_display_v08.py tests/test_evidence_archive_v03.py tests/test_reference_evidence_v08.py
node tests/reference_evidence_ui_contract.cjs
node --check kitguard/static/audit.js
.venv/bin/ruff check kitguard/evidence.py tests/test_reference_evidence_display_v08.py
```

逐调用比较脚本位于上述证据目录，输出使用排他创建；复现应在保留可信原快照、但尚无该结果文件的工作副本执行，勿删除或覆盖本次记录。封存的 v0.7、参考实验隔离快照、模型参数、默认策略和原有否决决定均不由此复核改变。
