# v0.3 源码与复现范围

源码包包含本地工作台、严格观察/版本/证据逻辑、测试、冻结配置、逐例文本记录、模型/数据来源和制作脚本。另保存报告的本队作者内容、数据快照和样式，便于核对结论。`SOURCE_MANIFEST.json`列出每个文件的字节数与SHA。

权重、照片、SQLite、Python/Node环境和私人报名材料均不放入源码包。数据输入需要按来源清单重新获取；只有随独立演示证据ZIP交付的订单归一化照片被单独保留。没有照片时不能复算像素散列或重新推理，不能把文本评分复算称为完整模型复现。

工作台可从源码重建：

```bash
bash scripts/setup.sh
.venv/bin/python scripts/download_candidate_model.py
bash scripts/run.sh
```

模型下载脚本使用预先固定的模型仓库与revision，放到`~/Downloads/AI-Models/`共享。Mac M5 Pro 64GB为已使用的硬件；Linux/CUDA或另一台3080机器不属于本次实测。

CPU工程验收在项目根目录运行`.venv/bin/python -m pytest -q`。测试没有实际模型推理；需要未打包的外部输入的检查会明确跳过。首次完整环境安装需要联网，运行已安装的本地模型不需要云API。

独立检查实际ZIP可用`python scripts/verify_source_archive.py <源码ZIP路径> --output <新验证记录.json>`。它会在临时目录解压、核对清单和所有散列、读取HTTP路由并运行CPU套件；复用运行该脚本的Python环境，不下载依赖或启动GPU。源码分发的428项中，有5项需要未打包的照片/裁剪，将明确跳过；完整工作目录的同一套件仍执行全部428项。

重新对模型进行64图测量，必须使用一个新输出目录，保留首次冻结记录。该64集已经在v0.3中使用，再跑只能称为同集回归。运行命令见原`run.json`及`HOLDOUT_RUN_LAUNCH_V1.json`；不要把生产服务和评测同时放到GPU。

交互评估报告的完整可读版本以单文件HTML另行交付。本队可编辑的React内容与数据在`reports/self-evaluation/src/`，Data插件受保护的运行框架没有复制进源码包。重建该分析报告需要同版Codex Data插件及其正式构建流程，不能把这部分文件夹当作无需插件即可独立编译的React应用；这不影响核心工作台运行。PDF和演示文稿各自的制作依赖及CLI见对应脚本与v0.3制作计划。

文件散列用于完整性核对，不是数字签名、现场真实性证明或主办方认可。交付仍是本队内部审查版本，未自动报名或提交。
