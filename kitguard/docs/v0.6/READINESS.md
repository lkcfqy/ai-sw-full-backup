# 演示前检查 / 시연 전 점검

2026-10-01。只读检查运行服务，不加载模型、不启动推理、不修改工单或训练产物。页面默认韩语，支持中文；语言偏好沿用工作台。检查结果是当时状态，不是准确率或现场验证证明。

先启动相应服务，再打开 `/static/readiness.html`，选择工单工作台、检测实验或两者。点击“立即检查”后可用“保存最新检查报告”重新检查同一范围，并通过服务器附件下载带服务器时间的 JSON；下载的是保存时的新快照。主工作台检查不受未启用检测实验影响。

```bash
# 主工作台：先在另一终端执行 bash scripts/run.sh
.venv/bin/python scripts/preflight.py --port 8765 --mode main
# 检测台：先执行 bash scripts/run_detector_lab.sh
.venv/bin/python scripts/preflight.py --port 8767 --mode detector
# 显式保存；文件存在即拒绝覆盖
.venv/bin/python scripts/preflight.py --port 8765 --mode all --output /tmp/kitguard-readiness-new.json
```

双击项目根目录 `启动前检查.command` 可检查已运行的主服务。可通过 `KITGUARD_PORT` 和 `KITGUARD_READINESS_MODE` 调整检查端口/范围。该入口不会替用户启动服务。CLI 保留既有 `--port`、`--output` 参数；退出码 0 表示所选范围的必需只读检查均通过，1 表示需处理，2 表示参数或输出文件错误。

检查应用运行版本、全部页面资源、目录权限、依赖安装文件、模型文件状态、冻结配置、推理占用。主流程增加 SQLite 只读 `quick_check`。模型文件齐备、依赖文件存在、模型已在内存加载分别呈现；未加载不会阻止只读预检查通过，但首次推理仍有加载时间。未执行 import 的后端依赖、模型加载和实际推理成功均不能由这次检查证明。

默认主身份固定为 `mlx-community/Qwen3.6-27B-4bit`、revision `c000ac2c2057d94be3fa931000c31723aac53282`、`spatial_guarded`、1536。协议 SHA-256 为 `0f6d5a514d4e7b093e486ae585040e9506670a4a7e725f7471333ec103e75403`，来自已有 `test-results/browser/inspection-region-real-v05/public-replay.json` 的真实联调 `runtime_identity`；不是较早的 `spatial_inventory` 冻结文件，也不是运行时用当前值自动认可当前值。模型 repo/revision 是配置身份，文件存在/大小不等于权重内容已全量散列核验。

检测范围确认 v1 权重 SHA-256 `2022c203a3b3b36dd146534c8bcfc538739cf8bf643066fc14a5b9611ebeb62c`、阈值 0.5、CPU 子进程、依赖文件及接收状态。该散列来自检测服务状态，不在每次预检查重新散列权重；本检查不验证权重能够加载。v2 不晋升为默认模型。

目录权限检查使用只读权限判断，不创建试写文件、不保证磁盘空间/配额或实际写入成功。SQLite 使用 `mode=ro` 和 `query_only`，不改用户记录、不修复数据库。检查不能代替实际推理、相机权限、现场数据、操作计时或全量权重校验。缺少服务、旧版服务、错误模式、错误模型配置、资源缺失、依赖缺失或忙碌状态均附可执行处理建议；不自动下载或修复。

## 集成接口

`kitguard.readiness.create_readiness_router(store=store, engine=engine, inference_gate=gate, package=PACKAGE, detector_status=None, expected_identity=None)` 返回路由，根路径为 `GET /api/readiness?mode=main|detector|all`。`store` 提供 `directory/path`；`engine` 和 gate 只调用 `status()`；`detector_status` 可为字典或零参数同步/异步回调。只读取所选范围的 provider。可显式传新的期望身份，报告标注 `caller_supplied_expectation`，不会隐式改变既有冻结身份。

返回 `kitguard.readiness.v1`，包含 `checked_at`、`ready`、逐项双语说明/处理建议、主/检测独立 `scopes` 和能力边界。CLI 优先读取该 API；旧服务仅作诊断回退，不能通过新版预检查。页面使用相同报告结构；`GET /api/readiness?mode=main|detector|all&download=true` 重新检查指定范围并返回带时间文件名的 JSON attachment，不把失败项隐藏掉。

## 保留的下一轮事项

- 检测台目前只下载 `job.json`；worker 的原始 `model-result.json` 中版本、数据指纹和代码 SHA 未完整随下载保留。可另做经路径筛选的完整证据包。
- 检测台先将最长边缩至 2048，单图 CLI 只转正；两者不能仅凭相同权重/阈值认定为同一预处理协议。后续应冻结预测协议标识，保持人工真值先锁定的评测边界。本轮不改检测台、训练或历史评测。
