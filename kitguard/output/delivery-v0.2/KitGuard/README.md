# KitGuard · 키팅 검증 워크스페이스

供 **해피** 队迭代的本地备料核验工作台。流程是“确认订单版本 → 拍照 → 列出可见物体 → 程序核对数量 → 补证或调整 → 人工确认完成”。韩语为默认界面，可切换中文。无需云模型、API key 或 API 额度，照片和订单保存在本机。

当前选定 **Qwen3.6-27B / MLX 4-bit、1536px、单次空间清单协议**。配置与源码在留出评测开始前冻结，见 [RELEASE_EVALUATION_FREEZE.json](docs/RELEASE_EVALUATION_FREEZE.json)。集成开发集 16 张中完整计数正确 15 张，仍有 1 张错误明确计数；这是用于选型的开发结果。冻结后的 48 张公开图留出已完成：46/48 完整计数正确，2/48 为错误明确计数；正常和数量异常子组均为 23/24。固定正常订单下，数量异常图 **1/24 被错误判为就绪**，没有发生真实人工确认或出库；固定扰动订单的错误就绪为 1/48，分母与前者不同。中位测量耗时 14.62 秒，包含隔离上传及观察。相同模型、1536px 和同 48 张图的直接计数对照为 34/48（70.8%），主方案为 95.8%，高 25 个百分点；对照有 14/48 错误明确计数和 2/24 数量异常错误就绪。主方案中位耗时 14.62 秒，对照 8.99 秒，增加 5.63 秒。两者同时改变提示词/结构和输出 token 预算，不是单因素消融；完整结论见 [FINAL_EVALUATION.md](docs/FINAL_EVALUATION.md)。

这是本地竞赛原型。公开实拍图评测不等于现场物料操作验证；工程夹具、浏览器通过数也不等于识别准确率。没有完成真实人工基线、连续现场补证或工业可靠性验证。真实开发从 **2026-09-26** 开始，开发期及既有代码参赛要求仍以主办方解释为准。

## 直接运行

本机已配置 `.venv/`。双击 `启动KitGuard.command`，或在此目录执行：

```bash
bash scripts/run.sh
```

浏览器打开 <http://127.0.0.1:8765>。保持运行窗口打开，Ctrl+C 停止。端口占用时先查看同一地址，不重复启动。模型首次实际请求时加载；界面的“文件已就绪”与“已加载”是不同状态。单进程、单模型推理线程运行，不使用多个 Uvicorn worker，也不要同时启动另一个 GPU 推理任务。

选定模型保存在共享目录：

```text
~/Downloads/AI-Models/Qwen3.6-27B-4bit/
```

固定仓库为 `mlx-community/Qwen3.6-27B-4bit`，revision `c000ac2c2057d94be3fa931000c31723aac53282`。下载脚本将逐文件核对上游散列；模型来源清单位于 `~/Downloads/AI-Models/Qwen3.6-27B-4bit.manifest.json`，原模型卡及许可证在 `~/Downloads/AI-Models/licenses/Qwen3.6-27B/`。权重不复制进项目或提交包。

## 首次操作

1. 新建订单，设置螺栓、螺母、垫圈、角码四类数量。每类 0–3 件，总计 1–12 件。
2. 可上传各类参考照片。参考图只作类别示例，不计入待检照片数量；选定公开图评测没有证明参考图能带来收益。
3. 下载 12 格 A4 托盘，分开放置物件，每格一件，再上传完整照片或拍照。托盘是辅助摆放工具，模型点位编号不是托盘编号。
4. 运行核验。模型输出物体类别和估计中心位置，代码从列表计算数量及差异；不向视觉模型提供订单目标数量。
5. 证据不足时按提示分放或补拍，提交新照片后重新核验。需要增减物料时先实际调整，再拍照。图像观察变化不能证明操作者确实移动了同一批物料。
6. 数量相符后，操作者仍须核对实物并明确确认，系统才记录完成。模型不能代替这一确认。
7. 订单可手工改数量，或输入不超过 500 字符的韩/中/英文指令。自然语言只生成修改提案，批准后才形成新版本；旧检查随即失效。
8. 打开历史核验详情，查看当时需求、照片、数量差异、补证反馈、模型/耗时和实际程序步骤。空间清单记录可切换编号点位、展开只读物体清单；旧记录没有字段时不补造。
9. 导出 JSON 保存完整状态，或下载 **证据包 ZIP**，解压后打开 `OPEN_ME.html` 离线查阅。

单帧 JPEG、PNG、WebP 限制为每张 12 MB、1600 万像素，最短边至少 32px、最长边不超过 8192px。存档会剥离 EXIF 并将最长边缩至 2048px；选定模型观察输入最长边 1536px，参考图 512px。原始上传字节不永久保留，只保存其 SHA-256 及归一化图片。

## 当前架构与证据

- **界面**：原生 HTML/CSS/JavaScript，无 npm 或外部 CDN。FastAPI 提供本地 API，SQLite 保存状态与历史，MLX-VLM 串行执行本地推理。
- **观察与判断分开**：`vision.py` 获取最多 20 个物体的严格结构清单，`spatial.py` 按类别计数，`app.py` 比较订单约束。选定协议一次调用、900 输出 token、温度 0、关闭 thinking。未知类别数量为 `null`，不会当成 0；程序不自动去重、补齐或把观察数量截断到订单上限。
- **版本和证据保护**：新照片、参考替换、订单改版使旧检查失效。推理完成后和最终完成事务中均检查版本、最新证据与检查有效性；完成使用幂等键并回读记录。历史详情只能读，不能复用旧结果完成当前订单。
- **主动补证**：新的不同照片可比较前后不确定性与数量变化；相同照片重试不算新证据。连续不明确阶段达到两次追加照片预算后转人工。同样字节以新 ID 上传也不证明场景有变化。
- **可解释记录**：保存当时需求、参考 ID、照片 SHA、协议/模型身份、实际执行步骤及反馈。编号点位是模型估计，可能重复、遗漏或分类错误；没有定位真值评测，不能称定位准确率或实物状态证明。
- **证据 ZIP**：只包含本订单关联的存档照片、当前/历史参考图、`evidence.json`、离线只读页面、`README.txt` 和 `SHA256.json`；不包含其他订单、SQLite 数据库、模型权重或未保存的原始上传字节。导出前验证照片散列，缺失/损坏时失败。散列是追溯和完整性检查，不是数字签名或现场真实性认证。

程序不检验尺寸、材料、螺纹规格、长短型号或工业安全合规性。公开 LOCO 螺丝袋的映射把长短螺钉合并为 bolt，没有 bracket 阳性；结果不能外推到角码识别、任意套件或物理操作闭环。空间清单与直接计数对照同时改变提示词/输出结构和 token 预算，不能把差异单独归因于位置坐标。

接口默认 300 秒响应上限。超时、无效输出、模型不可用均不能完成订单；504 后底层 GPU 仍可能继续。长时间无响应时停止服务再启动，中断的检查会恢复为待处理。服务只监听 `127.0.0.1`，当前没有账号系统，适用于本机单操作者。

## 安装与配置

当前本机验证环境为 Apple M5 Pro、64 GB 统一内存、Python 3.12。重建环境及下载选定模型：

```bash
bash scripts/setup.sh
.venv/bin/python scripts/download_candidate_model.py
bash scripts/run.sh
```

`download_candidate_model.py` 名称沿用候选阶段，当前固定下载选定的 27B 模型；`download_model.py` 仍是早期 8B 下载器。不要在服务运行时下载或覆盖其正在使用的权重。`requirements-lock.txt` 保留依赖版本。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `KITGUARD_MODEL_PATH` | `~/Downloads/AI-Models/Qwen3.6-27B-4bit` | 共享模型目录 |
| `KITGUARD_MODEL_PROFILE` | 根据模型目录名解析 | 非标准目录名时指定已支持的固定 profile |
| `KITGUARD_OBSERVATION_MODE` | `spatial_inventory` | 选定物体清单协议；历史 `single` / `dual_orientation` 可用于对照 |
| `KITGUARD_IMAGE_MAX_SIDE` | `1536` | 模型主图最长边，支持 1024 / 1536 / 2048 |
| `KITGUARD_DATA_DIR` | 项目的 `data/` | SQLite 与照片目录 |
| `KITGUARD_PORT` | `8765` | 本地监听端口 |
| `KITGUARD_INFERENCE_TIMEOUT_SECONDS` | `300` | 请求响应上限 |

改变模型、协议、图像处理或参考图会改变评测条件，不能继续沿用冻结结果。选定默认不使用双方向调用或几何/亮度规则过滤。

## 数据、来源与验证

`data/kitguard.sqlite3` 保存订单和历史，`data/photos/` 保存归一化照片。备份前停止服务，再复制整个 `data/`。测试使用隔离目录，不将测试观察器或合成图片写入生产库。

公开数据来源与范围见 [PUBLIC_DATA_PLAN.md](docs/PUBLIC_DATA_PLAN.md)。已核验的 LOCO manifest 为 `datasets/manifests/mvtec_loco_screw_bag/benchmark_v2.json`；旧流式抽取到完整官方归档的对照保存在同目录 `pending_to_verified_audit.json`。每轮评测保存源 manifest 哈希、原图与上传处理 JPEG 的逐例哈希、源码快照、模型身份、逐图输出、异常与耗时。本次空间单次运行仅在最后一例元数据中保留实际 prepared PNG 哈希；其他 1536px 输入可从存档 JPEG 按冻结流程重建，不声称逐例都有该 PNG 摘要。相同开发图上的多轮调试不增加独立样本数；公开数据是否进入基础模型预训练未知。

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check kitguard tests scripts
node --check kitguard/static/app.js
node --check kitguard/static/audit.js
node --check kitguard/static/spatial.js
```

[API 与实现合同](docs/IMPLEMENTATION_CONTRACT.md)、[验证记录](docs/VALIDATION.md)、[浏览器工程证据](test-results/browser/README.md)、[自检报告项目](reports/self-evaluation/)、[现场验证计划](docs/REAL_WORLD_VALIDATION.md)、[开发记录](docs/DEVELOPMENT_LOG.md) 分别保留实现、测试和未完成的验证范围。完整视觉结论见 [最终技术评估](docs/FINAL_EVALUATION.md) 与 [独立审计](docs/FINAL_INDEPENDENT_AUDIT.md)，交互报告单文件为 [KitGuard_中文交互评估.html](output/report/KitGuard_中文交互评估.html)。不以工程测试通过数代替模型结果。

## 한국어 빠른 안내

`启动KitGuard.command` 실행 후 <http://127.0.0.1:8765>를 여세요. 현재 기본 설정은 로컬 Qwen3.6-27B 4-bit, 1536px, 단일 물체 목록 관찰입니다. 모델이 부품과 추정 위치를 나열하면 프로그램이 수량을 계산합니다. 목록의 번호는 트레이 번호가 아니며 누락·중복·분류 오류가 남을 수 있습니다. 보완 후 새 사진을 제출해 다시 검사하고, 수량이 일치해도 작업자가 실물을 확인한 뒤 완료해야 합니다. 과거 검사 상세와 증거 ZIP은 읽기 전용입니다. 공개 이미지 개발 평가와 현장 작업 효과는 별개이며, 최종 홀드아웃 결과와 사람 기준 비교를 혼동하지 마세요.
