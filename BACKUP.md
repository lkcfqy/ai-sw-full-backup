# AI·SW 项目完整备份

快照时间：2026-10-08 15:22（韩国时间，UTC+9）。原始项目目录未修改。

本仓库 `main` 保存可浏览的项目源码、文档、参赛材料和交付文件。模型、数据集、环境、缓存、临时文件、历史运行记录等保存在同一仓库的完整备份 Release 中；克隆 `main` 本身不会获得完整项目。

完整备份覆盖原目录下 **53,566 个普通文件、7,244 个目录、6 个符号链接**，文件内容总计 **47,882,042,338 字节（约 47.9 GB）**，没有排除任何原项目路径。包含 `.venv`、模型权重、数据集、报名证明、签名、所有历史交付、运行结果和会话下载证据。

完整归档使用 zstd 压缩和 age 加密，共 **42,975,391,030 字节（约 43.0 GB）**，切分为 **41 卷**，每卷最大 1 GiB。完整归档仅在保留本地恢复私钥时能够解密。私钥不在仓库或 Release 中，应另外保存到安全的独立位置。

- 完整备份：[Releases](https://github.com/lkcfqy/ai-sw-full-backup/releases/tag/backup-20261008)
- [恢复说明](backup/RESTORE-README.md)
- [完整备份元数据](backup/backup-manifest.json)
- [源码副本选择规则](backup/backup-stage-selection.json)
- [恢复脚本](backup/restore-backup.sh)
- [逐文件核验脚本](backup/verify-restored.py)

请下载备份 Release 的全部分卷、SHA256SUMS.txt、backup-manifest.json 和 file-manifest.jsonl，按恢复说明在空目录中恢复并逐文件核验。归档保存原文件权限、时间和符号链接；未归档 macOS 扩展属性、ACL 或项目目录之外的系统依赖。`.venv` Python、字体和两个 `node_modules` 目录中的绝对路径链接在其他电脑上可能需要重建。

此仓库必须保持私有。完整归档加密是为了保留可能含会话信息的原始文件；可浏览副本中也有个人报名材料。
