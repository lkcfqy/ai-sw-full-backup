# AI·SW 项目备份恢复说明

本次备份分为 GitHub 中可浏览的项目文件，以及 Release 中的加密项目归档。归档保留原项目根目录名 `AI·SW`。实际备份范围由同一 Release 的 `backup-manifest.json` 和 `file-manifest.jsonl` 说明；其中 `excluded_paths` 列出按照用户要求省略的路径及原因。请以这些清单核对保留的源码、报名材料、训练成果和运行结果。省略的可下载基础模型等内容需要从原渠道重新获取。

## 保存私钥

恢复私钥为本地文件 `RESTORE-KEY-KEEP-PRIVATE.agekey`。请将它单独妥善保存；私钥不会放入源码仓库或 Release。没有此私钥便无法解密项目归档。工具不会上传、显示或删除私钥。

## 下载与依赖

从同一个备份 Release 下载全部附件，保持文件名和文件内容不变。归档文件名由 `backup-manifest.json` 的 `archive_name` 指定；分卷在该名称后添加 `.part-000001`、`.part-000002` 等。例如归档名 `AI-SW-project-20261008.tar.zst.age` 对应第一卷 `AI-SW-project-20261008.tar.zst.age.part-000001`。同时需要 `SHA256SUMS.txt`、`backup-manifest.json`、`file-manifest.jsonl` 和恢复工具。

恢复环境需要 Bash、Python 3、`age`、`zstd`、`tar`，以及 `sha256sum` 或 macOS 的 `shasum`。所有备份附件应放在同一个下载目录中，校验文件内使用相对附件路径。恢复工具可从源码仓库的 `backup` 目录获取，也可使用 Release 附件中的脚本。macOS 可用 Homebrew 安装 `age` 和 `zstd`：`brew install age zstd`。

## 恢复

下面的下载目录、私钥和目标路径均为示例；将它们换成实际绝对路径。目标目录必须为空；目录不存在时脚本会创建它。

```bash
bash '/路径/backup/restore-backup.sh' \
  '/路径/备份附件' \
  '/单独保存私钥的路径/RESTORE-KEY-KEEP-PRIVATE.agekey' \
  '/路径/恢复结果'

python3 '/路径/backup/verify-restored.py' \
  '/路径/备份附件/file-manifest.jsonl' \
  '/路径/恢复结果'
```

脚本先按照 `SHA256SUMS.txt` 校验全部附件，从已校验的 `backup-manifest.json` 读取归档名，再按连续的分卷序号拼接、使用私钥解密、解压并提取。恢复后项目位于目标目录中的 `AI·SW`。如果流程中断，目标目录可能留下部分文件；请保留这些文件用于排查，并使用另一个空目录重新恢复。脚本不会覆盖非空目录或自动删除恢复结果。

内容校验工具逐项检查普通文件的大小和 SHA-256，并检查清单中符号链接的指向。它会拒绝普通文件路径及其父目录中的意外符号链接。校验通过说明清单所列文件的内容一致，不代表它们已经在新环境中完成运行测试。

## 原主机依赖

归档中保留的符号链接按原指向恢复。如果清单中包含 `.venv` 的 Python 绝对路径链接、字体链接或指向 Codex 运行时的 `node_modules` 链接，它们依赖原主机对应路径，在其他电脑上可能无法使用。需要在新环境中按项目的依赖文件重新创建虚拟环境，并安装或重新配置字体和 Node.js 依赖。其余系统工具和硬件环境也需要按项目说明准备。归档保存纳入范围内的文件内容、权限、修改时间和链接，未包含 macOS 扩展属性、ACL 或链接指向的项目外系统资源。
