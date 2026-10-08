# 固定参考 51：工作版兼容回放约定

该步骤在本轮冻结版独立审计通过之后执行，使用同一批保存的原始模型返回。它是 CPU 行为兼容检查，**新增 MLX 观察为 0**，不能替代原实验审计、更新实验成绩或证明新的真实推理性能。

入口：`scripts/v08/replay_reference_workspace_compat.py`。输出目录新建且位于原运行目录外，保留当时工作版源码/静态资产快照、各文件 SHA、原冻结审计 SHA、完整每张回放凭证。源码复制前后检查一致；不把工作版改动混入原实验 snapshot。

进入前必须有 `status=passed` 且绑定当前独立审计器、原 freeze 和完整运行目录全部哈希的正式凭证。读取原 51 前仍要求 run completed/51。若只有中途记录或原冻结审计未通过，该步骤拒绝执行。

逐张重新执行当前工作版的上传预处理与观察路径，禁止模型加载；生成接口只消费已保存 raw。要求：

- 上传/JPEG、目标图、旋转图、两参考及身份裁剪的实际字节完全相同。
- system/user 提示、完整响应 JSON Schema、token budget、输入顺序完全相同。
- 原始返回重新严格解析，计数、行动、issues、逐物体证据、两方向及身份核查等语义内容和旧记录相同；失败诊断也相同。
- 只允许新增顶层 `reference_evidence`、观察协议/源码哈希、不可重现的顶层墙钟 `latency_ms` 差异。比较器不递归删字段，不放宽任何计数或决定差异。
- 新 `reference_evidence` 仍需通过完整新 Observation schema，并额外与固定参考原图/预处理哈希、尺寸、实际阶段完成/失败/跳过情况核对；identity 阶段参考列表必须为空。

产品新元数据的 `prepared_bytes_retained=false` 如实保留：工作版只保存哈希和描述，预处理 PNG 在正常产品流程是临时文件。本实验的原调用图片仍在独立的实验目录保留，两者不混称。

19 项合成合同（冻结审计 16＋工作版兼容 3）通过：`test-results/v0.8-reference-audit-and-compat-contracts-v1.{log,xml}`，3.96 s，1 个已有 Starlette/httpx 弃用提示；Ruff 通过。合成样例验证了完整新 schema、参考元数据、非 metadata 行为不变及篡改模型 JSON Schema 会被拒绝。测试没有读取本轮候选前缀。

完成冻结独立审计后执行：

```sh
.venv/bin/python -I scripts/v08/replay_reference_workspace_compat.py \
  --audit test-results/v0.8-reference-guarded-independent-audit-v2.json \
  --output test-results/v0.8-reference-workspace-compat-v1
```

最终结果存为目录内 `compatibility.json`。本文件只是执行约定，不是对未完成正式运行的通过声明。

完整运行后已用以上命令成功执行：原审计采用 v2（首次 v1 快照空库失败保留），51 张工作版 CPU 回放全部通过，新增 MLX 调用 0。凭证为 `test-results/v0.8-reference-workspace-compat-v1/compatibility.json`，SHA `32f7e44a28c8e967a6e6410c86a006a9a9ef73895f70c06f0591557f0426d3fa`。加入精确空库边界后的最终合成合同为 20 passed，见 v4 日志/JUnit；不覆盖前述 v1 19 项合同记录。
