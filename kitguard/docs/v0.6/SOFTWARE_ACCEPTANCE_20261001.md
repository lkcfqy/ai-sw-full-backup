# KitGuard 0.6.0.dev2 软件验收

日期：2026-10-01（韩国时间）。这一轮完善主工作流的恢复与人工接手，并建立真实任务试用入口；没有更换冻结主模型、重新计算历史准确率或生成真实用户成绩。

## 已实现的行为

| 能力 | 现在的行为 | 验收重点 |
|---|---|---|
| 后台核验 | 创建持久任务，页面刷新后找回进度和结果；同一请求重试不会重复推理 | HTTP 响应丢失、并发重试、版本变化、超时后模型仍占用、启动中断恢复、关闭前后租约 |
| 人工复核 | 亲自输入实际数量，单独记录相符或未解决；保留 AI 原结论，不计 AI 成功 | 证据与版本绑定、重复提交、公开/测试来源拦截、离线证据页独立展示及 HTML 转义 |
| 结束与重开 | 完成或人工复核锁定当前版本的证据修改；同需求重核验须显式重开，真实需求变化仍可普通改版 | 新版本须新照片，旧结论不能完成新版本，保留历史回执 |
| 完整任务试用 | 3 位参与者＋独立主持人；人工/规则/KitGuard；9 或 27 个固定任务 | 开始后揭示订单、主持人双遍计数、全程计时、订单变更、独立终态核对、全部计划分母、令牌角色与下载 |
| 演示前检查 | 主工作台、检测实验或全部范围的只读检查，网页与 CLI 可保存报告 | 运行版本、资源、依赖、配置、目录权限、数据库、推理占用；未启用检测器不阻断主流程 |

试用指引：[你需要亲自做的事](你要做的事_20261001.md)、[完整任务规则（中韩）](FULL_TASK_TRIALS_KO_ZH.md)。实现细节：[人工复核](MANUAL_REVIEW_API.md)、[预检查](READINESS.md)。

## 软件验证

- 最终命令 `.venv/bin/python -m pytest -q`：**958 passed，2 warnings，23.15 秒**。警告分别为已有 Starlette/httpx 弃用提示和测试故意构造错误类型时的 Pydantic 序列化提示。日志保存在 [full-tests.log](../../test-results/browser/workflow-v06-dev2/full-tests.log)。使用 Python 模块方式运行，以便源码目录中的 `scripts` 可导入；直接调用虚拟环境 `pytest` 入口曾因模块搜索路径导致收集失败。
- 本次新增/修改的 Python 模块、相关测试及 `scripts/preflight.py` 通过 Ruff；`app/workflow/trials/readiness/camera.js` 通过 Node 语法检查；启动与预检查 shell 文件通过 `bash -n`。
- 浏览器检查主工作台、预检查、完整任务创建页的桌面与窄屏布局；桌面实际内容宽 1265px、窄屏 375px 均无横向溢出。临时测试视口已恢复。中韩语言入口和既有工单加载正常。
- 预检查报告、主持人私用入口文件、关闭后的完整任务报告，均通过真实浏览器保存文件验证。修复了原先临时 Blob 下载未落盘，以及表单下载遇到 `Origin: null` 被拒的问题；保留服务端跨来源拒绝，未放宽安全检查。入口密钥不收录到本验收材料。
- 正式源服务重启后，主工作台只读检查通过；已有任务与结果完整保留。预检查并不执行推理、验证全部权重字节、实际写入成功、摄像头权限或识别准确率。

## 一次真实本地模型恢复验证

在已曝光的 MVTec 公开开发照片（3 枚不同外形螺钉）上，从网页发起真实 MLX 核验，核验中刷新页面，页面找回运行状态并显示最终结果：观察 `bolt=3, nut=0, washer=0, bracket=0`，模型耗时 **23,176 ms**。仅产生 1 个任务和 1 条检查，实物完成回执 0 条。该结果属于联调，不增加独立评测样本数，也不代表新准确率或现场收益。

- 工单：`ord_d37281487f804c579b27`；任务：`job_ffd08d966a5f44b09bb1`；检查：`chk_8e5b25e55be544a28e3b`。
- 模型：`mlx-community/Qwen3.6-27B-4bit`，revision `c000ac2c2057d94be3fa931000c31723aac53282`；`spatial_guarded`，1536px；协议 SHA-256 `0f6d5a514d4e7b093e486ae585040e9506670a4a7e725f7471333ec103e75403`。
- [工单导出](../../test-results/browser/workflow-v06-dev2/real-model-order.json)、[持久任务](../../test-results/browser/workflow-v06-dev2/real-model-jobs.json)、[证据 ZIP](../../test-results/browser/workflow-v06-dev2/real-model-evidence.zip)、[桌面截图](../../test-results/browser/workflow-v06-dev2/real-model-zh-desktop.jpg)、[窄屏截图](../../test-results/browser/workflow-v06-dev2/real-model-zh-mobile.jpg)。

工程下载批次明确标记 `engineering_fixture`，9 个计划任务全部未开始；只用于验证关闭、全分母与真实附件下载。`physical_verified=false`，人员身份未验证，没有作为真实用户数据。当前服务使用独立 `data-preview-v06`；原始 `data`、历史评测、v0.5 交付和 v1 检测权重保持原样。

## 可安装软件包

[kitguard-0.6.0.dev2-py3-none-any.whl](../../output/dev-v0.6.0.dev2/kitguard-0.6.0.dev2-py3-none-any.whl)，250,629 字节，SHA-256：

`abac5e67eb4b610a30859793b8121097f9bff6a52e477bb6f15b55a6850cd85c`

52 个包文件（含 26 个静态资源）与最终源码逐字节一致；ZIP/RECORD 校验、独立解包导入、路由和静态响应检查通过。[完整打包验证](../../output/dev-v0.6.0.dev2/wheel_validation.json)。复用了现有依赖，未验证全新电脑安装或 CUDA 运行。wheel 不包含模型、数据、源码启动脚本及文档；现有 Mac 仍用项目内启动器运行。旧交付包保持冻结。

## 尚需真实验证

**真实用户试用仍为 0。** 需要人准备实物、运行试用、独立清点、留下原始反馈与连续演示。三位同学的小样本只支持探索性结论。四类粗计数不验证尺寸、材料、螺纹或 SKU；图片哈希不证明拍摄真实性。主工作流仍需人实际移动零件和最终确认。

`takeovers` 目前统计“由他人接管判断”勾选；操作者本人替代 AI 判断须在失败原因中记录，不能把这一计数称为所有人工接管率。无错误放行的公开样本结果不等于工业无错误保证。学校 GPU 型号、显存和可用权限确认后，才据实决定训练/部署方案。

[本轮验证索引](../../test-results/browser/workflow-v06-dev2/verification.json)保存报告与截图的文件散列，便于复核。
