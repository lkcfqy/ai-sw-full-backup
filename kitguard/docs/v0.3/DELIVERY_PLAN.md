# KitGuard v0.3 本地交付计划 / 산출물 구성

当前状态：生成器准备完成，最终交付须等待完整 64 张冻结留出测试、门槛判定、实际 API 演示和最终评估。此文档不报告运行中的部分结果，也不把开发集或 v0.2 历史结果当作 v0.3 新留出结果。

## 构建命令

在 `kitguard` 项目根目录运行：

```bash
.venv/bin/python scripts/build_v03_delivery.py --write-template tmp/v03-delivery-manifest.draft.json
```

模板为 `status: "draft"`，包含全部必需角色、目标路径和占位 SHA。生成器拒绝以 draft 状态构建。完整评估与实际演示完成后，填写真实路径、准确的文件范围说明、SHA-256、已验证的 JSON 断言及最终默认方法，另存完成版清单，然后运行：

```bash
.venv/bin/python scripts/build_v03_delivery.py \
  --manifest tmp/v03-delivery-manifest.completed.json \
  --output output/delivery-v0.3
```

相对来源路径以输入清单所在目录为基准；生成模板使用绝对路径。目的路径以新交付目录为基准。已存在的输出目录一律拒绝覆盖，v0.2 目录不得用作输出。

生成器不调用模型、不修改应用、不改写评分门槛、不生成结论、不代为报名或提交。门槛未通过仍可如实交付，页面会显示未达到门槛；只有 `default_adoption_eligible: true` 才允许将 `spatial_guarded` 声明为默认方法。

## 必需输入

| role | 文件及完整性要求 |
| --- | --- |
| `final_evaluation` | 最终中文评估 `.md` 或 `.pdf`，结论由已完成测试支持 |
| `offline_report` | 单文件离线交互报告 `.html`；由正式报告导出流程生成 |
| `source_archive` | 新源码 `.zip`，必须含 `KitGuard/SOURCE_MANIFEST.json`；全部成员与清单 SHA、字节数匹配，无照片、权重、数据库、私人报名表 |
| `demo_video` | 实际本地模型/API 操作录像 `.mp4` 或 `.webm`；文件类型与哈希检查不取代真实录制、解码和视觉验证 |
| `demo_evidence` | 实际公开开发图订单导出的证据 ZIP；可重复此 role 以带齐不同订单，但 `destination` 须唯一 |
| `demo_verification` | 实际演示验证 `.json`，必须提供非空 `assertions`，例如 `/status` 等于 `passed`；应绑定实际录像和证据文件 |
| `source_verification` | 新源码验收 `.json`，必须提供非空 `assertions`，例如 ZIP CRC、各文件 SHA、启动验证均已通过 |
| `holdout_run` | 完成的冻结 `run.json`；`status=completed`、`split=holdout`、有结束时间，64 个唯一 case id，计划数与完成数均为 64 |
| `gate_report` | 完整留出门槛报告；`complete=true`、`stage=holdout`、计划数与完成数均为 64，绑定上述 run.json 的 SHA，C/W/U/E 总和为 64 |

韩文评委问答、技术说明、发布说明等可作为其他 role 附加。所有 artifact 均要求 `title`、`note`、`path`、`destination` 和完整 `sha256`。额外 ZIP 仅接受 `source_archive` 或 `demo_evidence` 角色，避免混入未审查的原始数据整包。

JSON 断言采用 JSON Pointer；布尔值必须是真正的 `true`，不是字符串或数字。示例：

```json
{
  "role": "source_verification",
  "title": "源码验收记录",
  "path": "/absolute/path/to/source-verification.json",
  "destination": "verification/source-verification.json",
  "note": "新版本实际 ZIP 解压、逐文件校验与干净启动验证",
  "sha256": "填写64位真实SHA256",
  "assertions": [
    {"pointer": "/zip_crc_verified", "equals": true},
    {"pointer": "/all_file_digests_verified", "equals": true}
  ]
}
```

断言字段必须来自真实验证文件，不能为了满足生成器而补写不存在的验证结果。断言可按真实文件结构调整；生成器只检查声明的字段，并不替代外部 QA 或保证记录真实。

## 公开照片与证据包边界

允许随包携带**本次公开示例订单已经归一化的照片**。证据 ZIP 必须是 `schema_version=2` 的 KitGuard 导出，保留 `demo_source` 的来源与许可，有实际 check、MLX 模型版本与观察方法，以及所关联的 `photos/<id>.jpg`。不得含实物完成记录，不得塞入原始数据集、模型权重或 SQLite 数据库。已有文件和照片 SHA 必须与导出清单一致。

源码 ZIP 不携带任何栅格照片。源码中的来源/本机路径是研发记录，不代表源图片或权重已被随包复制。所有素材使用仍按原许可执行；哈希只能验证文件一致性。

## 历史引用

`historical_references` 中每项必须提供真实本地 `path`、`title`、解释历史范围的 `note` 和 `sha256`。历史文件只生成相对链接、记录字节数和哈希，**不会复制到新版本并标作新测量**。例如 v0.2 原始交付入口、旧 48 张评测报告和旧录像可保留历史标签。

历史链接依赖原项目同级目录；单独移动 v0.3 目录后，此类链接可能不再可用。交付入口明示这一点。本次文件均在目录内部，可整体搬移。

## 生成结果与验证

生成器先检查全部输入，再写临时目录，复制后重新计算 SHA，成功才将临时目录改名为最终目录。失败时清理临时输出，不留下看似完成的交付。

- `index.html`：中文导航、关键韩文标题、全部 64 张的 C/W/U/E、默认方法与门槛结论、文件入口、边界与历史引用。响应式排版，不用外部 CDN。
- `BUILD_MANIFEST.json`：实际来源、输入清单 SHA、文件范围与构建时间。
- `SHA256.json`：覆盖所有随包文件（包括 index 和构建记录），逐项列出相对路径、字节数、SHA；历史引用独立标注，不算随包文件。
- `SHA256.json.sha256`：清单文件自身的独立 SHA。此文件不自哈希，以避免无限循环。

本子任务验证使用 `tmp/v03-delivery-fixture/` 内自造小型文本/ZIP 数据，全部显式标注 **TEST FIXTURE — NOT MODEL OR COMPETITION EVIDENCE**。这是打包链接与哈希逻辑测试，不是实际项目评测、录像验收或最终交付。最终 bundle 尚需 root 在上述真实输入全部就绪后构建，并用浏览器检查桌面/手机视图和最终链接。

已完成的生成器验证：41 项 fixture 校验通过，包括全部链接、逐文件哈希、清单覆盖、历史不复制，以及草稿、缺项、输入被改动、未完成运行、失败门槛却选择 guarded、路径越界、错误断言、重复目的路径、已存在目录与数据库 ZIP 成员的拒绝。另以真实 Chrome 检查 1440px 和 390px 的 fixture 页面，无横向溢出、JavaScript 错误或外部网络请求，并查看了手机截图。结果在 `tmp/v03-delivery-fixture/fixture-verification.json` 与 `browser-fixture-verification.json`；这些验证不代表最终实际交付已验收。
