# 韩语 v0.3 技术与结果补充 PDF 制作计划

2026-09-26。最终补充PDF已使用完整64张评测、独立审计、428项JUnit和v2真实API凭证生成并完成5页视觉验收。生成前没有读取留出中途成绩。现有v0.2 PDF与builder保持原样。

## 交付设计

最终输出 `output/pdf/KitGuard_검증보충_v0.3.pdf`，固定5页，附 `.sources.json`。

1. **业务价值与架构**：当前订单、照片与参考证据绑定；物体清单、程序计数、补证与人工确认；v0.3同内容照片、相机、公开演示与身份审计功能；默认采用资格与实际部署选择分别说明。
2. **完整结果与取舍**：开发LOCO16/Screws12与新评测正常16/异常16/Screws32分开；C/W/U/E；同次真实首轮对照；错答拦截、正确转弃权及新错答；三种规则误就绪分母。失败门槛照实展示，不要求结果“漂亮”才能出报告。
3. **实验路线与成本**：原图、旋转、条件身份复核；900/900/1800输出预算；OWLv2和GroundingDINO负面开发结果；实测候选分层时延；像素、坐标、类别证据的边界。
4. **真实API与工程证据**：3个公开开发样例/4次实际视觉检查及1次独立韩语指令提案，逐项保留HTTP、决策、时间，包括非ready或执行错误；JUnit实际通过/失败/跳过；独立schema和像素重建审计；哈希不是真实性签名。
5. **复现与限制**：实际Mac/MLX环境、冻结和重算脚本、无真人基线/物理补件证据、来源分组及阳性覆盖限制、公开模型/AI编程披露、赛前开发资格未决、可读来源索引。

不把旧48张当作新v0.3成绩，不添加官方评分权重或获奖概率。正文与页脚保留9月26日预开发/非正式提交状态。

## 已准备的生成器

`scripts/build_v03_korean_addendum.py` 使用标准库验证数据；真正生成时才导入ReportLab和pypdf。不导入模型、不推理、不打开评测图片、不调用评测器。

必需输入采用已有文件schema：

- `--gate`：最终完整64张 `gate_report_v1.json`，要求stage=holdout、complete=true、planned/completed=64、冻结protocolSHA一致，C/W/U/E及配对矩阵自洽。检查run、predictions、manifest的实际文件SHA及run完成状态。
- `--development-gate`：默认已完成28张开发gate。与holdout gate中记录的开发报告SHA一致；不通过开发或仅有开发证据不能写成默认采用。
- `--audit`：`scripts/analyze_consensus_run.py`已有产物。要求run/predictions/manifest哈希与gate对应、schema_revalidated=64、input_audit.verified=true，并核对C/W/E重算数。
- `--engineering-junit`：`test-results/engineering-v03-final.xml`；直接统计实际testcase与failure/error/skipped，不预置“428全部通过”。
- `--demo-receipt`：`test-results/browser/real-api-v03/runs/candidate-real-api-v2/browser/result.json`。采用实际status/outcomes/checks字段，要求全部3样本/4检查已记录、源码首尾一致。接受`completed_with_execution_errors`并保留失败，拒绝中断或不完整记录。HTTP成功须为真实mlx；不要求模型每次ready。
- `--deployment-mode`：root明确记录的`spatial_inventory`或`spatial_guarded`；报告不根据gate自动部署。

OWLv2和DINO的两份已完成开发run.json另作固定历史来源读入，校验完整28张和源码未变，数值从文件提取。

## 执行方式

先运行`--validate-only`。缺字段、不完整、哈希不符或分母矛盾会返回非零，不创建PDF，也不调用artifact marker。

```bash
PDF_PYTHON=/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
"$PDF_PYTHON" scripts/build_v03_korean_addendum.py \
  --gate <root提供的完整64张gate_report_v1.json> \
  --audit <root提供的完整64张独立audit.json> \
  --engineering-junit test-results/engineering-v03-final.xml \
  --demo-receipt test-results/browser/real-api-v03/runs/candidate-real-api-v2/browser/result.json \
  --deployment-mode <root最终明确的运行模式> \
  --validate-only
```

确认后用相同参数去掉`--validate-only`，必要时指定`--node`和`--output`。示例尖括号是待提供的文件参数，不是评测结果占位，也不会写入PDF。

## PDF skill与验收

已读取 `/Users/lkc/.codex/plugins/cache/openai-primary-runtime/pdf/26.905.11957/skills/pdf/SKILL.md`。

- 生成器在全部输入检查成功后、实际PDF authoring之前，从skill目录运行一次`node container_tools/mark_artifact_operation_started.mjs --operation-kind create --expected-output-count 1 --output-format pdf`。marker失败则终止。此时不要由操作者再重复调用一次。
- 韩语字体使用Arial Unicode；ReportLab绘制矢量业务流程与表格。仅使用ASCII连字符。
- 中间文件在`tmp/pdfs/`，最终文件在`output/pdf/`；拒绝覆盖已有PDF或sources sidecar。
- 临时PDF须恰好5页且每页有文字，才复制到目标名。sidecar记录所有完整输入SHA、builder/PDF SHA及`visual_qa=pending`。
- 最终必须以bundled `pdftoppm`逐页渲染，查看全部5张PNG，检查韩语字形、表格、页脚、行距、溢出、空白和source哈希断行；文字提取不能代替目视检查。
- 如版式需调整，仅改此builder并重生成新输出版本，不改评测core、gate冻结或数据。最终QA另存于test-results/audit，并核对PDF SHA。

最终状态：5页PDF已生成并逐页渲染、目视验收。PDF SHA-256为fb724e10ac6227ed9369720d8d4c323b8a330870a6896ee9e5d66cd4d85a9805；QA记录test-results/audit/korean_pdf_v0.3_qa.json，页面图像test-results/audit/korean-pdf-v0.3/。来源sidecar已标记visual_qa=passed。实际生成命令使用 --output output/pdf/KitGuard_검증보충_v0.3.pdf。
