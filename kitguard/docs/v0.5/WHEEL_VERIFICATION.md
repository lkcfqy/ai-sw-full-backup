# v0.5 实际 wheel 验收

通过。2026-09-26T15:42:46Z 使用 `/opt/homebrew/bin/uv build --wheel --no-build-isolation --python .venv/bin/python --out-dir output/wheels-v0.5-final` 构建；构建前该目录无 wheel，没有覆盖旧版本。实际产物：`output/wheels-v0.5-final/kitguard-0.5.0-py3-none-any.whl`，SHA-256 `04b98c1da25ffeba90e9da03d26d7879795ec21d372620d21429571d44059099`。

- wheel 内全部 34 个产品成员与当前 workspace 的实际字节 SHA 相同，既无遗漏也无多余产品文件；38 个 RECORD 条目及其文件大小、SHA 全部验证。METADATA 版本为 0.5.0。
- 提取到临时目录，在独立工作目录运行新 Python 子进程，清除 PYTHONPATH，并确认导入的 kitguard 位于解压目录内。使用已有依赖和新的临时 SQLite 数据目录。
- TestClient 验证 `/`、region.js/css、study.html/js/css、health、orders、studies 均返回 200；静态响应字节与解压文件相同，health/version 为 0.5.0。
- 实际执行新建工程工单、上传 160×120 合成图、保存 [20,20,120,100] 选区、读取派生照片，得到 100×80 视图并保持根图 ID。注入不可用分析器，未调用任何推理或 GPU。
- 核对最终 UI 冻结的 8 个静态文件 SHA 均未改变。临时解压目录与数据库已自动清理，没有触及生产 DB 或旧交付。

完整机器记录：`test-results/audit/v05-wheel-final-verification.json`；可复查脚本：`test-results/audit/verify_v05_wheel_final.py`。此项验证实际 wheel 内容及路由运行，不代表已在空白机器重新安装全部依赖或测试模型推理。
