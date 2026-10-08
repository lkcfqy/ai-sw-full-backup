# 离线报告交付

## 最终文件已验证

正式单文件：`../../output/report/KitGuard_中文交互评估.html`。官方导出原件：`.data-app-offline/exports/KitGuard_中文交互评估.html`，两者字节一致。文件大小 2,912,778 bytes；SHA-256 `df42ce036d291b77fde77fb9e3b5cba294bc635a3403488c2acf5dbeae0eff57`。绑定 reviewed snapshot SHA-256 `7bd6f797b022ad235c6f57138bdab83ad5bc297cd9b922b4c3260c3029bf5d2a`；共享 runtime SHA-256 `9e3ede84b28aded3c7379b6e6a5611f0d95b9977eb0f781e279ceefabfcbd27e`。

最终报告的 `buildStatus=complete`，包含 13 次视觉运行、4 次指令运行、工程和参赛证据边界。数据两项 48 图留出运行均已完成；现场验证和参赛资格仍保持未决，不因报告定稿改变。localhost:4173 与复制后的正式单文件均通过真实 Chrome 检查，合计 42 项界面/包装断言，来源面板能读取两个真实留出记录，手机无页面横向溢出，离线单文件 HTTP 请求为 0。结果见 `../../test-results/browser/report-release/final-result.json`。这些是同一报告的双表面回归，不是独立识别样本。

## 导出方法与阶段验证记录

当前 `dist/` 是分离数据构建，适用于本地 HTTP 服务。不要把 `dist/index.html` 单独复制或当作 `file://` 离线交付：真实 Chrome 已验证，即使旁边有 snapshot 文件，跨本地文件 fetch 仍会被浏览器 CORS 拒绝。不要降低浏览器安全配置规避。

使用框架内置命令从已验证构建导出单文件，不改共享 runtime：

```bash
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node /Users/lkc/.codex/plugins/cache/openai-curated-remote/data-analytics/1.0.11/scripts/data-app.mjs export-offline --project-dir '/Users/lkc/Downloads/AI·SW/kitguard/reports/self-evaluation' --output '/Users/lkc/Downloads/AI·SW/kitguard/reports/self-evaluation/.data-app-offline/exports/KitGuard-self-evaluation-preview.html'
```

命令输出 HTML、snapshot 与 runtime 的 SHA-256。生成的单个 HTML 内含数据，不需旁置 snapshot，不依赖本地服务器或外网。可复制该单文件到正式交付目录；正式导出应在最终 reviewed data 与内容构建完成后重新执行，并使用最终文件名。

2026-09-26 的阶段预览已在真实 Chrome 断网上下文用 `file://` 验证：报告渲染、全部 11 条视觉运行跨页保留、标准来源面板与原始数据预览可用、390px 手机无页面横向溢出、HTTP 请求 0、JavaScript 错误 0。结果与截图在 `../../test-results/browser/report-offline/`。这些结果只验证包装与界面；预览仍标 creating，不能作为最终留出结果版本。

最终数据刷新后必须：重新 build → localhost:4173 复验 → export-offline → file:// 断网复验 → 保存最终 HTML/数据哈希并复制单文件。旧预览不覆盖为新的证据，保持当前快照与测试结果可追溯。
