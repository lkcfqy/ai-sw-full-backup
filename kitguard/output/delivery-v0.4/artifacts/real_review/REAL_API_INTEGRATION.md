# v0.4 真实 MLX 与验证记录台连接验收

**这是一轮真实 API 集成验收，不是新的模型准确率评测、现场实验或真人效率对照。** 只使用已经反复用于开发的 3 个公开样例。人工字段由脚本填入作者真值，所以人工正确率与毫秒级输入耗时均不能用于任何人工能力或效率主张。

执行记录位于 `test-results/browser/field-study-real-v04/`。隔离服务为 `127.0.0.1:8787`，隔离 DB 为该目录的 `data/`；没有写入生产数据。

## 实际结果

内部执行计划于 **2026-09-26 14:54:03 UTC** 冻结；实际 API 流程为 14:54:14–14:55:41 UTC。

| 既有开发样例 | 真实返回决策 | 观察结果 | 核验记录的模型时间 |
|---|---|---|---:|
| bag-revision | `correct` = 需要增减数量 | 螺栓2、螺母2、垫圈2、支架0，与作者真值一致；工单要求螺栓3 | 50.113 s |
| small-part | `recapture` = 需要补拍 | 螺栓2，螺母/垫圈不确定，支架0 | 20.605 s |
| mixed-screws | `ready` = 与工单数量一致 | 螺栓3、其他0，与作者真值一致 | 15.252 s |

3 次 `/inspect` HTTP 请求，分别连接到 3 个真实 field trial；没有重试、择优、替身或缓存预测注入。每个 `/inspect` 内部可能包含多阶段模型生成，不能把 HTTP 请求数当作生成次数。

这 3 例的记录是 2 次明确正确、1 次不确定、0 错误、0 执行失败；它们**不增加任何新的独立准确率样本**，不能与此前冻结 64 例合并。三种结果均成功进入关闭后的记录与证据包。

## 真值、方法与证据

- `bag-revision` 真值来自 `datasets/manifests/mvtec_loco_screw_bag/benchmark_v2.json` 中作者定义的标准组成。
- `small-part`、`mixed-screws` 来自 `datasets/manifests/v0.3/CANONICAL_NEW_SOURCE_BENCHMARK_V1.json` 的原始作者框计数及已固定类别投影。
- 三条清单均为 `development`，图片 SHA 与公开体验目录、清单、实际本地文件一致。
- 模型为 `mlx-community/Qwen3.6-27B-4bit`，revision `c000ac2c2057d94be3fa931000c31723aac53282`；模式 `spatial_guarded`，输入长边 1536。
- `PLAN_FREEZE.json` 保存固定三例、真值、来源清单 SHA、模型配置及 **34 个源文件**的哈希；`source_snapshot/` 保留这些实际字节。开始到结束源文件无变动。
- 批次 `study_0fe89d0da49944929c1a`，来源 `public_replay`，参与者 `scripted_replay`；每例均注明“自动输入作者真值，非真人人工基线、非现场实验、已用开发样例，不增加新准确率样本”。
- 完整请求体、响应体、HTTP 状态、耗时和响应 SHA 保存在 `http/` 与 `http-index.json`。不只保留最终结果。

## 可检查交付

- `result.json`：全部实际核验与关闭后记录。
- `public-replay.json`、`public-replay.html`：真实服务导出。
- `public-replay-evidence.zip`：真实导出的记录、报告、3 张归一化目标 JPEG 与全文件清单；这是公开开发图包，非现场照片包。
- `verification.json`：独立读取导出与原始记录的 **7 项**字节/绑定/流程核查；全部通过。核对 ZIP CRC、所有成员 SHA 与字节数、照片 ID/版本/哈希、模型身份、实际只发三次请求和完整源快照。
- `browser-result.json`：关闭后仅读取的 **10 项**真实 Chrome 检查，全部通过，零修改请求、零浏览器错误、离线零 HTTP 请求。320/390 宽度页面无溢出，三张归档照片离线可解码。
- `closed-real-study-1440.png`、`closed-real-study-390.png`、`closed-real-study-320.png`：实际闭合记录截图；没有重新录像或伪造交互。

## 运行与释放

启动前主 8765 旧进程报告 `model.loaded=false`；所有主工单无 `active_inspection`，无运行中的 benchmark / 真实推理 Python 进程。旧主健康接口不存在 `inference_busy` 字段，预检明确保留此事实，没有把“字段缺失”冒充显式 `false`。

准备阶段的第一次进程匹配误把准备脚本所属 shell 当成推理进程，因此在任何计划冻结或模型调用前退出；改为仅匹配 Python 可执行进程后通过。没有因此重复任何模型请求。

完成导出与只读浏览器检查后，实际 MLX 进程 **49481 已退出**，8787 端口释放，主模型仍未加载。`shutdown.json` 保存核对结果；GPU 已归还。

人工计数由自动程序填写且来源公开，即使界面按通用协议显示这些数值，也不能用来比较人工与模型速度或宣称真实生产收益。
