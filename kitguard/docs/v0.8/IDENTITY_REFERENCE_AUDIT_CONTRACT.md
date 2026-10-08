# Identity-only 参考候选：独立审计合同

入口为 `scripts/v08/audit_identity_reference_guarded.py`。锁定正式 freeze SHA `2e0ef97133988a2ca00a36a08b82e4a42e2d97f61ae01ef38980fe7d72f8b19e`、runner SHA `6b7e39dc26dd2062c770c78168bf6091e6efff6ccaf0df3600f2459f46fdc7b7`。旧 reference51 审计器和证据不改。

只有 run completed、51/51、冻结源码未变且最终完整性通过后，才读取候选预测。核对原 51 清单、作者真值投影、旧 G、同图上传/JPEG、全部模型 payload、固定 nut297/washer057 及原像素裁剪；65 项源快照精确匹配，不允许额外运行数据库混入源码。结果目录的默认 app 数据库另以 immutable 只读检查七表全空、无 sidecar、前后 SHA 不变。

只导入冻结的观察工厂和 legacy 观察模块，不调用候选 analyzer/scorer。CPU 原文回放在 recorder 边界截获生成；`_load` 始终硬失败，实际模型生成函数不进入。原图、90° 旋转、身份裁剪和追加参考的每张实际字节、完整模型 JSON Schema、system/user、token budget、角色和点 ID 均独立核对。

前两轮必须是原 G 无参考的单图空间观察；身份阶段才可追加固定两参考，原目标/crop 前缀不变。完整 Observation 和观察诊断必须相同，只有顶层墙钟 latency 不重现。类别参考不产生新目标 ID，不参与计数。

生成阶段记录数与实际 model started/completed 分开统计。CPU 回放本身不重新生成实际调用标记：在验证“parsed/raw 返回必须 completed、completed 必须 started”等约束后，保留原始标记作为证据；候选重新生成的角色、schema、协议字段仍须逐项一致。不能把 legacy `identity.model_called` 的提前置位当成真实模型调用。

解析失败和 ID 契约失败由保存 raw 重现。加载/grammar/generate 等无 raw 的运行失败显式标为内部原因不可复现，保留 E。身份参考准备失败若尚无第三阶段记录，只重建已观察到的失败阶段及诊断，不声称复现原环境异常；绝不能把缺记录默认为安全成功。

C/W/U/E/N、旧 41 C 损失、原 3 W、原 LOCO 14 C、两种错误 ready 面板、全部时延与预登记门槛由 SHA 固定的独立纯函数复算。51 图来自已曝光开发集；历史 G 非同期；LOCO16 恒正常；同一相关 VLM、多视图或参考都不等于独立身份认证。

合成 CPU 合同最终 25 passed，1 个已有弃用 warning，4.86 s；Ruff 通过。涵盖成功/阻断/skip、加载/grammar/生成/解析/ID/参考准备失败、完整 schema/提示/角色/参考字节一致篡改、全分母、真实调用标记及数据库边界。日志为 `test-results/v0.8-identity-reference-audit-contracts-v4.{log,xml}`。v3 的新增数据库测试曾因测试变量遮蔽报错，原日志保留，修复只涉及该测试。

根通知完整 51 结束后，从新进程执行：

```sh
.venv/bin/python -I scripts/v08/audit_identity_reference_guarded.py \
  --output test-results/v0.8-identity-reference-independent-audit-v1.json
```

输出必须是运行目录外的新文件；审计失败也保留，不覆盖后重写。保存 raw/hash 仅能证明本地记录一致，不能证明原模型返回的真实性或重现真实耗时。本合同不是尚未执行的完整-run 审计通过声明。
