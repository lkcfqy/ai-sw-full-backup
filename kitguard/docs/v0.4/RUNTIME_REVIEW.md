# v0.4 本地运行可靠性审计与修复

审计日期：2026-09-26。范围是本地工作台 HTTP、线程调度、数据目录恢复和照片身份；没有调用真实模型、没有读取或修改生产数据库，也没有重跑或更改历史模型评测。以下三项均先用隔离临时目录复现，再修复。

## 结论

这次修改消除了演示中的过期请求积压、双实例错误恢复和照片文件身份错配三类实际问题。新增的 16 项运行时工程测试通过；原 428 项回归加这 16 项共 **444 项通过**。这些数字衡量工程行为，不是新的视觉样本或现场用户研究。

| 问题 | v0.3 实际复现 | v0.4 修复后验收 |
|---|---|---|
| HTTP 超时后仍积压过期推理 | 连续三次请求均 504；首个工作线程释放后，三次实际模型调度均继续执行，虽然三个请求早已结束 | 首次 504 后，三次重试立即 503，不新增检查事件，也不进入模型队列；实际线程结束后新请求可成功 |
| 第二实例误清除第一实例正在执行的核验 | 同一数据目录启动第二 lifespan 后，第一实例的 active token 被清除，原本可成功的请求返回 409 | 第二实例在恢复前被 OS 文件锁拒绝，第一实例的订单及 token 不变，原请求成功 200 |
| 保存照片被替换后仍可进入 ready/complete | guarded 模式的纯 bolt 路径：读取替换后的 JPEG，检查仍写旧照片 SHA、返回 ready，完工 200；只有导出 ZIP 才发现错配并 409 | 推理前、推理后、完工前校验当前照片和全部参考图；错配拒绝，不调用模型或不提交结果，不产生完工记录 |

## 1. 过期模型队列（高优先）

**根因。** 原 HTTP 路径的 `asyncio.wait_for(asyncio.to_thread(...))` 只结束等待。`LocalVision.observe()` 仍在独立的单工作线程池中提交任务并等待结果。订单 reservation 在 HTTP 超时后释放，因此用户连续重试会继续入队；排队中的请求即使又超时，之后仍消耗模型计算。旧超时测试检查了“迟到结果不能写回”，没有检查“过期重试不能继续入队”。

**证据。** `test-results/audit/v04-runtime/result.json` 的 `expired_queue` 记录三个 504、释放前 1 次执行、释放后 3 次执行，工作线程均为实际 `kitguard-mlx_0`；结果没有误写数据库。CPU 替身仅替换 `_observe`，保留真实 `LocalVision.observe` 的调度路径。

**修复。** `kitguard/runtime.py` 的 `InferenceGate` 为检查和韩语提案共享一个准入位置，不设置应用推理等待队列。工作线程实际结束时才释放位置，HTTP 超时或取消不提前释放；忙碌请求在修改订单状态前返回 503。`/api/health` 新增 `inference.busy`、`request_waiting`、`queue_capacity`。取消或超时后的异常会被消费，避免无人等待的 future 异常。

**范围。** 没有声称能抢占或中止正在执行的 MLX kernel。当前工作仍会运行结束，应用明确要求等待。直接调用 `LocalVision` 的研究脚本保留原调度方式，本次修改保护的是实际工作台 HTTP 路径。

## 2. 同一数据目录双实例恢复（高优先）

**根因。** 旧 lifespan 无条件执行 `store.recover_interrupted()`。SQLite 的事务锁只保证单次写入互斥，不代表该应用有权宣布另一个仍活跃实例的工作“已中断”。

**证据。** `result.json` 的 `second_live_instance` 记录首实例开始观察后，第二实例启动立即写入“应用重启”的失败事件并清除 token，首请求随后 409。

**修复。** `DataDirectoryLease` 在调用恢复逻辑前独占 `.kitguard-instance.lock`。macOS 使用 `flock`，另提供 Windows `msvcrt` 分支；锁由 OS 随进程关闭释放，锁文件残留不代表锁仍被持有。如果服务退出时仍有超时模型线程，租约延续到该线程真正结束。

**验证。** 测试覆盖同进程双 lifespan、另一真实 Python 进程抢锁、正常关闭后重启、拥有者进程终止后的锁释放，以及超时工作仍运行时不得提前释放数据目录。验证主机为当前 macOS；没有声称实机验证了 Windows 分支。

原 `test_restart_recovers_abandoned_inference_without_success` 事实上在旧 TestClient 仍活跃时启动第二实例。该测试已修正为先关闭旧 lifespan，再验证真正重启可恢复遗留 reservation；其原本的“不能伪造成功”断言保留。

## 3. 保存文件与照片元数据错配（高优先）

**根因。** 路径解析验证文件存在且位于照片目录，但推理前没有重验保存文件的 SHA。guarded 的身份复核路径会比对源图 SHA；没有 nut/washer 候选而跳过身份复核时，不经过该检查。最终 check 的 `photo_sha256` 直接复制元数据，因而不能证明模型实际看见同一文件。

**证据。** 隔离上传后将该保存 JPEG 替换成另一张有效 JPEG，保持数据库元数据不变。保留真实 guarded 图像准备和两次空间观察适配流程，仅用 CPU 合成的 bolt 输出替代生成。`changed_photo` 保存的 metadata SHA 为 `51bcc9b25cd8e05e5b083bceebab3e2d03ffd3613a3691a492b56e2697960a60`，实际文件 SHA 为 `74e72c5f0230971321472e1cef587ecc88e6174eec8fab98c91ac5749973c81e`，旧版本 inspect 和 complete 均 200，而 evidence.zip 为 409。

**修复。** 应用层在观察前、观察返回后、当前 ready 订单提交完工前，重验当前照片及参考照片。推理前发现错配不会发起生成；推理中被替换不会写入检查；ready 后被替换不会写入完工。旧完工幂等回放不重新创建结果，保持既有语义。

**范围。** 这保护偶发文件替换或损坏与普通本地数据操作；不是针对持续恶意改写整个数据库、文件及哈希的防篡改保证，也不是实景真实性认证。检查发生在有限时间点，没有宣称与外部任意文件写入原子互斥。

## 验证与可复现文件

- 原始修复前证据：`test-results/audit/v04-runtime/result.json`。
- 原始独立复现器：`test-results/audit/v04-runtime/reproduce.py`。它断言旧缺陷，因此应对 v0.3 源码快照运行，不应对修复后的工作区直接运行。
- 已从已交付 `output/KitGuard_source_v0.3.zip` 解压到临时目录，第二次独立重放三项旧缺陷：`test-results/audit/v04-runtime/baseline-archive-replay.json`。两次均记录 `mlx_imported=false`。
- 定向验证：`test-results/audit/v04-runtime/targeted-final.xml`，**68 passed**。
- 原基线及运行时新增回归：`test-results/audit/v04-runtime/baseline-regression.xml`，**444 passed，4.27 秒**；两个已存在警告分别为 Starlette httpx 弃用提示与刻意构造的 Pydantic 非法值测试提示。
- 此时并行开发中的现场研究 API 尚未接入，一次全量中间运行得到 444 passed / 12 failed，失败均为新 `/api/studies` 路由 404，保存在 `full-suite.xml`；它不是最终整版验收。上面的基线回归只排除当时尚未接入的 `test_field_study_review.py`。v0.4 整版集成后需由主任务执行包含这些测试的最终全套。
- `ruff check kitguard/runtime.py kitguard/app.py tests/test_runtime_admission.py tests/test_api_integrity.py` 已通过。
- 回归之后，对原取消测试补充“等待真实工作线程释放准入后再重试”的明确同步断言，消除释放事件与线程退出之间的调度竞态；该单项重新运行 **1 passed / 0.08 秒**，对应文件 Ruff 通过。测试总项数不变。

旧版本重放示例（`KITGUARD_AUDIT_SOURCE_ROOT` 指向已解压的 v0.3 `KitGuard` 目录；输出必须使用新文件名，保留已有证据）：

```bash
KITGUARD_AUDIT_SOURCE_ROOT=/absolute/path/to/extracted/KitGuard \
KITGUARD_AUDIT_OUTPUT=/absolute/path/to/new-replay.json \
.venv/bin/python test-results/audit/v04-runtime/reproduce.py
```

修复后回归示例：

```bash
KITGUARD_DATA_DIR=/absolute/path/to/isolated-import-data \
.venv/bin/python -m pytest tests/test_runtime_admission.py tests/test_api_integrity.py tests/test_guarded_review.py -q
```

## 历史评测与方法身份

`vision.py`、`spatial.py`、`consensus.py`、`identity.py` 与已交付 v0.3 源码 ZIP 逐字节一致，记录在 `test-results/audit/v04-runtime/protocol-preservation.json`。未修改观察提示词、分类规则、阈值、空间旋转、身份复核或模型输出协议；新的运行时文件不参与 observer protocol SHA。

v0.3 ZIP SHA-256：`072b1b685d3766cc28164ce1bfa17e8b409dacbe015055e46647807366c9e87e`。旧源码包、旧评测和原交付结果均未回写。新 API/运行时行为属于 v0.4 工程改进，不把过去 64 张图的结果冒充为一次新的 v0.4 模型实测。
