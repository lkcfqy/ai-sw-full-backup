# KitGuard 韩语答辩 PPT

当前交付：[KitGuard_발표_v0.2.pptx](./KitGuard_발표_v0.2.pptx) — 9 页，韩语，可编辑文字和原生表格。实际开发日期为 2026-09-26；这是提交前审阅材料，未声明赛前实现已获主办方接纳。早期 v1–v3 草稿保留，不应作为最终成绩版本使用。

## 已写入的最终证据

- 工程回归 186/186；自然语言 24/24 是作者编写的开发案例，二者都不等于照片识别准确率。
- 27B 逐件空间清单方案：开发 15/16；事先固定的另外 48 张公开实拍图 46/48（95.8%），正常 23/24、数量异常 23/24。明确给出错误数量 2/48；相对固定正常工单，把异常误判为数量一致 1/24。
- 同模型直接报数对照：34/48（70.8%）；异常误判一致 2/24。所选方案在此集合高 25 个百分点，但处理中位数 14.62 秒，对照 8.99 秒。提示词、输出结构和 token 上限一起改变，不能称为孤立坐标消融实验。
- 页面 4、5 使用 `output/demo/01-real-inspection.png` 和 `03-audit.png` 的真实 Chrome/MLX/API 实录。订单 3→2 后重交同一公开照片，R1 失效，R2 数量一致；没有真实补件、重新拍摄实物或代用户完成确认。
- 数据源 MVTec LOCO AD，CC BY-NC-SA 4.0；图片、计数投影依据、分割和哈希保留。公开图片的预训练重叠未知，当前无正例 bracket/现场连续照片/真实工时对照。来源与限制同时写入幻灯片和对应页备注。

## 可复核文件

- [生成脚本](../../.presentation-build/build.mjs)：ArtifactTool JavaScript，含 9 页结构、原生表格和备注。
- [最终数字准备脚本](../../.presentation-build/prepare_final.mjs)：要求两个评测都完成 48/48，核对冻结的 case 顺序、模型 revision、输入协议、源码和 manifest，再从结果生成数字。
- [实际图片与披露输入](../../.presentation-build/final-assets.json)、[最终指标输入](../../.presentation-build/metrics.json)、[可编辑结构 JSON](../../.presentation-build/source-v4.json)。
- [最终来源与 SHA 记录](../../.presentation-build/final-sources.json)、[结构与导入验证](../../.presentation-build/validation-v4.json)、[逐页目视 QA](../../.presentation-build/visual-qa-v4.json)。
- [最终渲染图目录](../../.presentation-build/render-v4/)：从最终 PPTX 渲染出的 slide-1.png 至 slide-9.png，逐页查看，无观察到的裁切或重叠。
- [韩语答辩问答](../../docs/JUDGES_QA_KO.md)。

字体：Apple SD Gothic Neo（本机已安装）。包结构、9 页数量、页面几何、字体使用、6–8 页原生表格以及 ArtifactTool 重新导入均通过；最终 9 页渲染均目视复核。尚未做 Microsoft PowerPoint 或 Google Slides 的原生打开、编辑再保存兼容性验证，不能把结构检查称为这种验证。

PPTX SHA-256：`67a4d338fb912997889fed4f418b0e0ac45f59fba960373a614d57292647c019`；3,632,738 字节。

## 本机重现

工作目录为本项目根目录。使用 Codex bundled Node 和 ArtifactTool；不需要加载视觉模型或 GPU。重新导出前保留已有文件或选择新版本名称，不覆盖已记录的最终哈希。

```sh
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node .presentation-build/prepare_final.mjs .presentation-build/final-assets.json

RUNTIME_NODE_MODULES=/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node .presentation-build/build.mjs v4

RUNTIME_NODE_MODULES=/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node /Users/lkc/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations/container_tools/render_presentation.mjs --input output/presentations/KitGuard_발표_v0.2.pptx --output_dir .presentation-build/render-v4 --scale 1
```

重新生成会产生新的源时间记录，必须重新做 finalizer、渲染和逐页检查；不要沿用旧 SHA 和旧 QA。`prepare_final.mjs` 会从当前运行记录重新生成输入与基础来源记录，而最终 PPT/渲染/人工目视检查记录应在新输出之后重新补齐。

## 保留的历史草稿

- `KitGuard_발표초안_20260926_v1.pptx`：早期界面版本。
- `KitGuard_발표초안_20260926_v2.pptx`：韩语工程夹具界面版本。
- `KitGuard_발표초안_20260926_v3.pptx`：167 工程测试、8B 开发 9/16 的历史快照；不是最终 27B 留出成绩。

提交前仍须按 9 月 29 日发布的正式表格和 FAQ 核对资格、开发期和格式要求；不得只改开发日期来规避条款。
