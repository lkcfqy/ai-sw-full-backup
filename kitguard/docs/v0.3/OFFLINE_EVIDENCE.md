# v0.3 离线证据报告 / 오프라인 증거 보고서

完成日期：2026-09-26。`OPEN_ME.html` 已升级为中韩双语只读报告。解压证据 ZIP 后直接打开，不需要服务器、模型、JavaScript 或网络。报告帮助评审核对记录，不能执行订单操作、批准新任务或证明真实补件。

## 可核对的内容

- 每次检查分别显示版本、**导出时保存的** `valid`、原判断代码、时间、模型、后端与耗时。`ready` 明确显示“仍须本人确认实物”。`valid: null` 是未确认，不转换为否。
- 数量表只读该次 `requirements_snapshot` 与最终 `observed`，差值为“观察 − 当时需求”。历史快照缺失、`null` 或非合法数量显示未确认；不借用当前订单需求，也不借用另一方向观察补填。
- 动作与补证比较使用保存记录；无记录则标明缺失。补证显示前次检查/照片、已解除与剩余问题、观察数量变化，并明确不证明实体移动或现场纠正。
- 若有双方向核验，显示原图和逆时针 90° 的各轮数量、计数一致性、明确一致性、输入 SHA、坐标系与原始 JSON。它是相关的同模型调用，不是独立专家核验或新增拍摄。
- 原图首轮估计点可展开。仅当协议为 `spatial_inventory_v1`、坐标系为 `normalized_original`、检查照片 SHA 与包内照片 SHA 相同，且现有核验首轮为原图、对象列表一致时显示。只取原图对象；旋转图对象不叠在原图上。点位只是模型估计，不是真值或物体身份。
- `demo_source` 存在时显示公开照片演示、样例 ID、来源案例、网址文本、许可证、来源 SHA 和说明，明确不能记为实体完工。来源 URL 不自动变为外部链接。
- 每次检查的完整 JSON 与全部原始证据 JSON 均保留在原生 `<details>` 中。照片目录保留上传源 SHA 和归一化保存图 SHA。

## 完整性与安全边界

归档仍只导出本订单及其关联照片。照片原字节不改写，`SHA256.json` 继续逐文件记录字节数和 SHA-256；新 HTML 自身的哈希随内容改变。所有动态文本转义。图片只接受严格的 `photos/{safe_id}.jpg` 相对路径，元数据不能覆盖归档生成的安全路径。仅有 `evidence.json`、`SHA256.json`、`README.txt` 三个相对链接；无脚本、表单、按钮、远程字体、网络依赖或写操作。CSP 禁止脚本、连接、表单提交及外部默认资源。

哈希清单不是数字签名，也不证明照片真实性。HTML 没有运行时自动校验程序；审阅者可以独立核对 `SHA256.json`。本次升级没有重新运行模型，没有把工程夹具计入精度，没有补写历史推理或实物完成记录。

## 验证结果

执行 `.venv/bin/pytest -q tests/test_evidence_archive.py tests/test_evidence_archive_v03.py`：**14 passed**。新文件含 11 个参数展开后的工程用例，已有文件 3 个；不是 14 次实物试验。覆盖历史版本/缺失快照/null、ready 限制、补证语义、双方向分歧、旋转坐标隔离、哈希/坐标关联不符时隐藏叠点、来源演示提示、XSS/不安全资源、ZIP 照片原字节与各文件哈希。`ruff check` 通过。仅有原有 Starlette/httpx 弃用提示，无失败。

实际 Google Chrome **154.0.8037.58**，`file://`，浏览器上下文断网，`--disable-gpu`，桌面 1440×900 与手机 390×844 各运行真实历史副本和显式工程夹具：**4 个场景、54 个断言通过**。所有本地照片成功解码；文档、卡片、表格、JSON 展开后无横向溢出；零 HTTP(S) 请求、零写请求、零弹窗、零页面错误。14 张截图已逐张目视复核，表格、哈希换行、原图点位、手机布局无裁切/遮挡问题。手机检查是桌面 Chrome 的窄视口验证，不声称已在实体手机或 Safari 测试。

首次 QA 的图片解码等待被未进入视口的 lazy 照片阻塞；仅调整测试脚本在展开详情后将图片设为 eager，再跑完全部检查。产品的原生惰性加载保持不变。此调整不是新增用例，也不是模型运行。

证据目录：`test-results/browser/offline-evidence-v03/`。

| 文件 | 用途 |
|---|---|
| `engineering.xml` | 14 个归档/报告工程测试结果 |
| `browser-results.json` | Chrome 版本、视口、54 个断言、请求与解码/溢出检查 |
| `visual-qa.json` | 14 张截图的人工目视复核记录 |
| `preview-provenance.json` | 原 v0.2 文件哈希与未修改证明 |
| `build_previews.py` | 从旧演示证据复制并重渲染；创建明确标注的工程夹具 |
| `browser.cjs` | 可复跑的离线 Chrome QA 脚本 |
| `real-demo-copy/OPEN_ME.html` | 旧真实 MLX 历史记录的新查看器预览；公开照片，不是实物补件 |
| `synthetic-engineering/OPEN_ME.html` | 缺失快照、未知值、XSS、双方向分歧等工程夹具 |
| `desktop-real-r1.png` / `mobile-real-counts.png` | 历史 R1 缺一件及当时需求，桌面/手机 |
| `desktop-real-ready.png` / `mobile-real-ready.png` | R2 ready 仍待本人确认 |
| `desktop-synthetic-verification.png` / `mobile-synthetic-verification.png` | 明确标注的工程双方向分歧 |

预览使用旧 `output/demo/offline-evidence/evidence.json` 和原照片字节，新目录中的 `evidence.json` 与来源逐字节相同，仅重新生成查看器及其哈希清单。旧目录和旧 ZIP 均未改动。

- 原 v0.2 ZIP SHA-256：`90763bdd76fc4db21ce379ebc03f04f5a39bc43d2eaff5283a45a34600dbea28`
- 历史 evidence JSON SHA-256：`ea1abb190818384868068f9af11777ba64ff2cdebb532b6bfc97bfc1663f583a`
- 新预览 HTML SHA-256：`e2355afaf9115cfdcf1fb99def3f7e3c628f5f39a4795c9d54c5c39ce6a9ca00`

本次代码改动仅为 `kitguard/evidence.py` 与 `tests/test_evidence_archive_v03.py`；未改模型、状态机、在线 UI、旧冻结评测或旧交付件。
