# v0.4 可复核交付入口生成器

生成器 `scripts/build_v04_delivery.py` 只复制实际存在的资料并核验 SHA，不运行推理、不生成评测结果、不创建源码 ZIP，也不修改已有交付目录。

本轮仅创建 `tmp/v04-delivery-preview`，**没有创建 `output/delivery-v0.4` 或最终源码包**。当前预览自动纳入 21 份实际 field、runtime、真实 MLX 和独立验证资料。缺少最终测试、源码包与解压验证时明确显示等待，不引用中期 539 项当成最终成绩。

## 最终使用方式

等 root 完成最终测试、源码包与独立解压验证后运行：

```sh
.venv/bin/python scripts/build_v04_delivery.py \
  --output output/delivery-v0.4 \
  --final \
  --final-tests test-results/engineering-v04-final.xml \
  --source-archive output/KitGuard_source_v0.4.zip \
  --source-verification test-results/audit/source_v04_verification.json \
  --final-evaluation docs/v0.4/FINAL_EVALUATION.md
```

可选加入真实角码诊断的 `--partial-run`、`--partial-predictions`、`--partial-report`、`--partial-audit`。这些参数指定项目内已存在的文件；默认不猜测文件名。JSONL 实际行数按所有非空行计数，失败行同样保留；生成器不推断角码正确率。

其中 `--partial-predictions` 必须是 JSONL，`--partial-run` 为 JSON。报告和审计可为 JSON/Markdown/HTML 等支持的实际文本资料。无论结果如何，入口始终说明：**计划 20 例全是单个角码，恒定回答 1 也能 20/20，作者 ROI 单阳性诊断不证明计数泛化，也不能补齐四类准确率。**

若实际路径不同，传入相应文件路径即可。若最终目录已存在，生成器拒绝覆盖，应另选新目录，不能覆写旧交付。

## 生成与边界

- `index.html`：韩语优先、关键说明附中文，手机可读；所有入口链接均相对，资料复制进 `artifacts/<role>/`。
- `BUILD_MANIFEST.json`：真实来源相对路径、目标、SHA、字节数、实际读出的摘要和缺失角色。
- `SHA256.json` 与自身 `.sha256`：覆盖所有复制文件、HTML 入口和 manifest。
- 严格显示真人现场 N=0、这次 3 张既有开发图新增独立准确率 N=0；v0.3 冻结 64 例仅为历史。
- 不展示脚本输入作者真值的“人工”列为效率优势。明确 100% 和 0 秒不代表真人表现。
- `--final` 要求最终 JUnit 无失败/错误，实际源码解压收据 `status=passed` 且 ZIP SHA 对得上，解压测试总数与最终总数一致；真实 MLX 结果须完成且源文件未变，并有匹配该结果 SHA 的实际验证收据。
- 个人 QQ/Gmail 联系方式、韩国移动电话、报名资料、项目外路径、符号链接、数据库/模型权重 ZIP 成员均拒收。一般文献引用和官方来源链接仍保存在原始资料中；本入口不引入外部 HTTP 请求。

## 验收

- `tests/test_delivery_v04_builder.py`：6 项实质检查通过；覆盖无结果时不虚构、已有目录拒覆盖、final 缺件拒绝、JUnit 实际失败计数保留、partial 失败行不丢弃、路径与联系方式限制。
- Ruff：该生成器与测试文件均通过。
- `test-results/browser/delivery-v04-preview/result.json`：12 项真实 Chrome 只读检查通过；1440/390/320 无页面溢出，所有相对链接存在，真实回放 HTML 可离线打开，零外部 HTTP 请求、零 JS 错误。
- 最终交付尚未构建，需在最终输入产生后再执行上面的命令并验收其新目录。
