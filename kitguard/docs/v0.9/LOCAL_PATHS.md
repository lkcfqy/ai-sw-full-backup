# 项目本机文件目录

2026-10-03 按用户要求，将独立放在 Downloads 下的模型及 KitGuard 下载文件归入项目。

项目本身仍在 `/Users/lkc/Downloads/AI·SW/kitguard`。路径前缀含 Downloads 是当前项目的位置，不代表文件散落在项目外。

| 内容 | 项目内路径 |
| --- | --- |
| 当前模型、历史模型、来源与许可证 | `models/` |
| 数据集与下载压缩包 | `datasets/raw/`、`datasets/archives/` |
| 报告、视频、PPT、参赛包 | `output/` |
| 从浏览器下载的本项目文件 | `output/browser-downloads/20261003/` |
| 运行工单与照片 | `data-competition-v09/`，普通启动默认 `data/` |
| 测试和原始验证记录 | `test-results/` |

`scripts/run.sh` 和应用入口默认使用项目内模型；四个模型下载器默认写入 `models/`。`KITGUARD_MODEL_PATH` 或下载器的 `--root` 仍可用于显式指定位置。

旧 `~/Downloads/AI-Models` 兼容链接已按用户要求删除。模型实际保存在项目 `models/` 中，当前应用和启动器直接使用此目录。冻结的观察代码与旧实验记录保留原样；复现旧脚本时应显式设置 `KITGUARD_MODEL_PATH` 或脚本支持的模型路径参数。

浏览器“下载”由浏览器控制，网页不能随意指定本机保存目录。后续脚本下载应直接写项目；通过浏览器执行的项目下载在完成后归档进 `output/browser-downloads/`。不改变整个浏览器的全局下载设置，也不移动其他下载文件。

迁移清单位于 `test-results/v0.9/path-migration-20261003/`。模型目录在同一文件系统中移动，核对文件大小、inode和时间戳，未复制或重下载权重；零散下载文件另核对SHA-256。模型和个人运行数据不进入源码包。之前的参赛完整包继续保持封存。旧封包运行时应显式指定当前项目内的模型路径。
