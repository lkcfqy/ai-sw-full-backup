# 新51图三方法独立完整性审计

本审计器是新文件，不修改原冻结 runner/analyzer。只在 `run.json.status=completed` 且153次完整记录时接受；检查完成状态之前不打开预测账本。正式评测结束前没有运行它分析真实结果。

运行命令（153次全部结束后）：

```bash
.venv/bin/python scripts/v07/audit_public_paired.py \
  --run evaluation-runs/v0.7/public_paired_v1 \
  --freeze docs/v0.7/public_paired_freeze_v1/freeze.json \
  --output test-results/v0.7/public-paired-audit-v1.json
```

输出存在则拒绝覆盖。审计输出必须在原运行目录之外，原始数据与模型目录只读。CLI在独立Python子进程中导入经过hash验证的冻结源码，CPU重新执行上传归一化、图像准备、原始输出解析和后处理；禁止模型加载，不运行MLX。

审计范围：

- 固定freeze SHA、全部冻结源码、manifest原件及运行副本、来源筛查记录与真值元数据；不将当前工作区后续UI修改误认为冻结推理代码变化。
- 51个源原件的文件/解码像素hash，以及35个确定裁剪视图；每个来源重新执行冻结app上传，核对153份实际归一图。
- 精确执行顺序、每图三方法、153完整分母、每方法在各顺位17次。
- 模型repo/revision、观察协议与源码hash、实际方法和模型标签。
- 每次原始生成的prompt/schema/budget、持久化图片字节、raw文本与解析结果；用原图重做旋转与局部裁剪，逐字节核对实际模型输入。
- 用保留的原始响应在冻结观察链CPU回放，核对最终Observation、成功/失败诊断、identity目标/响应/裁剪元数据。完整记录内无原始响应的运行失败明确单列，不伪造模型结果。
- 独立重算C/W/U/E/N、全分母、合法BOM面板的false-ready、各层P50/P90/总时长和预注册门槛，最后才与原runner汇总交叉核对。
- 审计前后所有运行文件hash必须一致；输出保留逐次审核和全部文件hash索引。

记录器为每次调用创建唯一`call-NN`目录，不能跨调用覆盖。每个`generation.json`在同一调用内按pending/returned/parsed或failed更新，最终保留返回文本；没有保存每次中间写入版本。guarded的未缩放原始局部像素曾位于临时目录，现可用归一源图、裁剪几何/hash和保留的实际模型输入重建核对。候选同时保留原始局部像素与缩放输入。

文件hash不是签名，也不能独立证明模型运行的真实性。本审计验证代码、记录与像素间的一致性，不重新生成模型答案，不重新散列大型模型权重，也不认证预训练未见过这些资料。

合成CPU合同测试：`tests/test_public_paired_audit_v07.py`。25例已通过（0.22秒），覆盖三种方法、原始解析失败、合法JSON但身份ID错误、第二次调用解析失败、输入图/解析内容/终态/失败诊断篡改、无原文运行失败、全分母重算、执行顺序和嵌套计时边界。没有读取实际进行中的前缀成绩，没有运行模型或整套项目测试。

## 完整结果与首次失败说明（2026-10-02）

153次完成后，独立审计首次在第3次候选观察失败：`single_direction_base.latency_ms` 原记录为14,645ms，CPU原文回放为91ms。冻结 `probe_selective_identity.py` 将第一轮 `LocalVision._observe_passes` 返回的观察做深拷贝，其中包含该轮 `perf_counter` 墙钟耗时。纯CPU回放不能重现模型运行耗时；原审计已排除最终观察的顶层耗时，却遗漏这个嵌套位置。

只修复审计器：明确限定路径 `single_direction_base.latency_ms` 单独校验，原值完整保留到逐次审计记录。它必须为非负整数，不超过外层完整观察耗时，不短于其包含的首个生成调用（仅允许2ms计时舍入）。其余诊断字段仍精确比对；没有递归删除所有时间字段。新增回归同时检查长原始耗时与短CPU回放可兼容、负数/布尔值/超过总时长/短于生成耗时均拒绝，嵌套观察内容篡改仍拒绝。

保留的失败证据：`test-results/v0.7/public-paired-audit-diagnostic-failure-01.log` 与 `test-results/v0.7/public-paired-auditor-before-timing-fix.py`。修复后的完整审计日志是 `test-results/v0.7/public-paired-audit-run-02.log`。原运行记录、预测、冻结代码与数据均未修改。

完整审计输出 `test-results/v0.7/public-paired-audit-v1.json` 状态 **passed**，SHA256 `94c71e45341a5065ee90fe601e606cd3a54242094d5dcc08770f6aae8c588fe9`：62份冻结源码/资源、51个来源、153份归一输入、272次原始生成、444份实际模型输入和172份身份裁剪重建核对。运行目录所有文件审计前后哈希一致，未加载或调用模型。

独立重算 C/W/U/E/N：inventory 46/5/0/0/0；guarded 41/3/7/0/0；candidate 46/4/1/0/0。四类别BOM面板 any-false-ready 分别5/51、3/51、4/51；来源支持类别面板均0/51，两者定义不同，不能用后者覆盖跨类别错误。完整观察P50分别8.962、21.814、15.625秒；P90分别14.550、46.231、31.896秒。guarded和candidate均未通过预注册门槛，候选不晋升，也不能据此宣称已证明安全优势。
