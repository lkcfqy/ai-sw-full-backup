# v0.8.0.dev1 本地评委预览包：显式计划与构建合同

这是新开发预览的包装工具，不是最终提交或获奖记录。入口 `scripts/v08/build_delivery.py` 独立于封存 v0.7；不改旧脚本、旧产物或实验。本文和合成合同阶段不创建真实材料包，最终计划由根在报告、PPT 与源码 ZIP 完成后写入实际路径和哈希。

机器 schema 为 [DELIVERY_PLAN_SCHEMA.json](DELIVERY_PLAN_SCHEMA.json)。顶层仅允许 `schema=kitguard.v08.delivery-plan.v1`、`version=0.8.0.dev1`、`preview=true`、`output_directory`、`output_zip`、`files`。每项必须恰有 `role/path/sha256/destination/title`；哈希必须为实际 64 位小写 SHA-256，不能填待完成或虚构值。计划不包含自身或未来输出哈希。文件标题会 HTML 转义。

`report/technical/slides/source` 四主件由根指定 `output/` 下实际路径，分别 PDF≤5 页、PDF=1 页、PPTX≤8 页、源码 ZIP。`source_smoke` 必须是该 ZIP 的 `.verification.json` 侧件。报告的 SOURCE_EVIDENCE.json、PDF QA.json、PPT QA 回执也是必需角色。17个报告引用来源逐一加入显式文件表并验证原SHA，首页直接链接这些材料；结构检查与作者视觉QA回执分别绑定到最终PDF/PPT字节。其余必需角色从 builder 的 `FIXED` 表选择确切路径，不允许 arbitrary extra、通配符或目录树；schema 列出角色，工具校验路径。旧 143 秒视频可选，必须与原已完整解码的回执一起加入，标题固定“v0.7历史图库流程，未覆盖v0.8新入口”并含对应韩文，不能充当新功能视频。

每项主件进入 `materials/`，所有说明、数据和回执进入 `evidence/`，目的文件后缀必须保留。必需证据包括 README、研究索引、新双语指南、LOCO24 result/decision/run/analysis/predictions/freeze/selection/独立审计及原失败修复、旧51完整三方法统计/审计与冻结、真实资料 API plan/receipt/两代observer/源码前后/模型哈希收据/evidence ZIP、真实历史只读浏览器回执及下载凭证/两张截图、开发贡献MD/JSON、1,530项全套日志/XML/Ruff、MVTec两份许可来源说明。文档内部仓库链接仍可能引用未附大树；首页给全部实际附入文件直接可点击链接，不伪装自包含完整研究复现包。

校验分开进行，不能借新正结果放宽历史失败：

- 新24仅接受已注册冻结 `513b…effd` 与独立审计 `f9f1…0f263` 的实际字节；要求 completed24、源未变、全分母23C/0W/1U/0E/0N、四组各6、11/12匹配和另12 N/A、两个风险面板0/24。审计必须绑定对应原run/analysis/predictions/selection；正常16历史不合并，decision无自动晋升。
- 旧51使用**原封存 v0.7 严格验证函数**，先核其源码 SHA，再核完整153次/三方法/独立审计和原始预测哈希；只包装指定小文件，不把全部原raw/image树复制。原G41C/3W/7U仍保留，与新24分开。
- 真实API要求两次观察、六次开始/完成生成、零真人、零回放模型调用、源码前后相同，两代观察均有三份真实返回记录；模型哈希收据与计划绑定。ZIP只允许六成员：两代同一旧016归一JPG及证据JSON/离线HTML/索引/说明。照片源SHA、存档字节SHA、MVTec许可声明、数字来源及拒绝实物完成均核验，不接受任意自报“公开照片”。
- 源码必须 preview=true/0.8.0.dev1，原逐成员验证器确认其 manifest 全覆盖、CRC及文件哈希；与项目固定三张许可demo的完整元数据与字节哈希一致；排除私有数据库、模型、raw-generation、source_snapshot、其它图片。必须有实际该ZIP解压后的成功合成HTTP烟测侧件（新建入口201、换根409、实物完成409、ZIP一致、0模型/0真人）。烟测使用本机依赖，不能称纯净机器安装或实际识别通过。
- 主浏览器为已完成真实API历史的只读显示/下载，严格31 GET、零新增模型/意见/变更、零真人，绑定API回执与两代历史、源码无漂移；保留上传与file://策略限制，图片及下载收据必须被回执绑定。此前合成验收仅可选独立role，标题明确“synthetic/合成”，不能与真实API拼成一次完整真人流程。工程验证固定1,530 passed/2 warnings、XML零失败/跳过及Ruff成功；后写builder合同不算在这次1,530里。

构建先完成所有只读验证，再独占创建全新目录。输入路径、父目录或ZIP成员有symlink/越界/重复均拒绝，已有输出绝不覆盖。仅逐项复制；任何缺项、哈希变化或过大文件停止，保留失败产物供诊断，不静默丢弃。不得附DB、私照、模型、FOD/MANTA/新24原图、整个raw/source快照树。允许的照片只有源码三demo、API ZIP两代旧016归一图及两张真实历史只读UI截图。

最终生成 `START_HERE.html`（无网络脚本，可解压后双击）、原字节 `PLAN.json`、`BUILD_MANIFEST.json` 和 `SHA256.json`。manifest绑定计划SHA、builderSHA、复制文件及各验证结果；`SHA256.json`覆盖其余所有文件（包括manifest/plan/HTML），不包含自身及其单行 `.sha256`；后者单向绑定索引。外部ZIP `.sha256`绑定ZIP，避免循环。ZIP与目录逐成员/逐字节复验；全部材料的本地链接生成自同一文件表。哈希是完整性校验，不是数字签名。

根后续命令：

```sh
.venv/bin/python -m scripts.v08.build_delivery --plan <完成后的真实计划.json> --validate-only
.venv/bin/python -m scripts.v08.build_delivery --plan <同一真实计划.json>
```

`--validate-only`不会生成交付产物；不执行源码烟测或模型，只验证已经完成的回执。最终真实构建由根在审查并稳定所有材料后统一执行。
