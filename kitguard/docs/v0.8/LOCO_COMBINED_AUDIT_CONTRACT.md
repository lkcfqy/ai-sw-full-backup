# LOCO24 G-only 独立审计合同

2026-10-02。针对根先选定再冻结的单臂24观察：freeze SHA `513b461a7574e6c68f1bdd6674769fe4b9fa95f3626b1302969f01c70b3deffd`、selection SHA `fe6efb0160ac82cce73423494446c793b2ef87bff8c29f0dee91ca6111071114`。本合同及合成测试不读取正在运行的24预测前缀。

入口 `scripts/v08/audit_loco_combined.py` 先检查 run completed、planned/completed=24、source_changed=false、完整性通过，再读取 `predictions.json`（不是 jsonl）。缺任何计划行、重复/错源/错mode/顺序改变均作为完整性错误；E 保留原文和未测风险，未完成运行不能发布通过凭证。N 的纯数学合同仍覆盖完整分母，不能用N冒充零风险。

独立部分包括：

- 根选择、完整 identity51 审计后的时间顺序、G-only 方法表与日程；源码69=原65+新增4，逐 SHA 严格核对，来源冻结和新协议分别绑定。源 snapshot 不允许运行时数据库。
- 从原作者 manifest、defects 配置、48 mask 的保存字节和已复核组合语义记录重算24真值；每图两种不同类别差量，各应用一次，四组各6。保留原 unresolved/null 清单；不按mask数量、面积或连通域推导实例数。所有源照片字节/RGB、canonical app-upload JPEG、1536准备PNG重建并核对，固定参考来源的精确重合检查仍保留，实际 G 输入没有参考。
- 真实调用目录 generation.json 与 ledger 的诊断逐字段一致；每张实际输入字节、system/user、完整 schema SHA、tokens/温度、raw、解析或执行失败均保留。调用 attempt 记录和 generate 实际 started/completed 分开；模型加载硬失败，CPU回放不允许任何新推理。
- 仅从冻结 runner 取得 `guarded_observer` 构造器，其他 runner preflight/freeze/run/analyze/scorer 均不调用。已审查独立51 auditor/更早纯工具函数按 SHA 固定复用文件核验、动态隔离载入和模型payload核验。回放重建实际原向、90°旋转、身份crop与完整Observation；同模型crop/身份skip边界保留。
- 独立数学枚举每图255主面板和63次面板，重新计算 C/W/U/E/N、四组各6、12匹配BOM/12 count4 N/A、标准订单正确差量及恒正常/全拒答分析对照。观察4仍合法，BOM上限3不变。该计算不导入或调用候选评分器；合成合同还对6种观察×255BOM与冻结真实 `decide` 交叉核对。
- 原16 normal 从已审计v0.7 manifest/predictions逐项核对和单独重算，不丢旧U、不合并成40新图、无同期时延比较。排除的I不进入新24或其normal报告。
- 每次前后 observer/source/model 身份与加载状态连贯；实际时延、cold/warm及模型调用合计独立复算。审计前后 run 全文件SHA不变，runtime DB 用 immutable只读检查固定7空表，无sidecar；当前工作版产品代码不进入回放。

CPU回放验证保存证据的自洽性，不能认证历史模型文本真实性、重测硬件时延、证明未曾看过/预训练未见、或获得实物会话独立性。每图255/63订单是相关规则回放，不是新增照片。没有自动晋升或现场安全声明。

完成通知后执行（当前编写时未执行正式审计）：

```sh
.venv/bin/python -I scripts/v08/audit_loco_combined.py --output test-results/v0.8-loco-combined-independent-audit-v1.json
```

任何首次失败另存 JSON/日志后报告根，不改已冻结来源、原运行或标签；必要修复仅审计器并另存后续版本凭证。
