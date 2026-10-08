# AI、代码和数据来源披露草稿

实际开发日期：2026-09-26—2026-09-27（韩国时间）。本文件是项目来源记录，不替代主办方待发布的“별지2”，也不表示赛前代码已获接纳。

| 项目 | 实际使用及新增部分 | 原始来源/限制 |
| --- | --- | --- |
| Codex | 根据队伍指示生成、修改、审查项目代码、测试、研究文档、韩语材料和演示脚本；多代理交叉检查仍属于AI辅助审查 | 未称全部代码为队员逐行手写；未虚构人类标注、使用者或访谈 |
| Qwen3-VL-8B-Instruct | MLX社区8-bit转换，用于早期视觉/自然语言真实推理 | [原模型](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)、[MLX版本](https://huggingface.co/mlx-community/Qwen3-VL-8B-Instruct-8bit)；Apache-2.0；固定revision见models.py/共享目录manifest |
| Qwen3.6-27B | MLX社区4-bit转换；冻结后选为v0.2默认，1536px逐件空间清单，程序计数（详见冻结记录） | [原模型](https://huggingface.co/Qwen/Qwen3.6-27B)、[MLX版本](https://huggingface.co/mlx-community/Qwen3.6-27B-4bit)；Apache-2.0；保留原始LICENSE/README及权重SHA |
| MVTec Screws | 原始实拍和作者COCO标注；匿名类别映射为项目粗类别，用于压力测试 | [作者数据页](https://www.mvtec.com/research-teaching/datasets/mvtec-screws)；CC BY-NC-SA 4.0；不是本队拍摄，不能作现场收益证据 |
| MVTec LOCO AD | screw_bag原始实拍；正常构成和单一数量缺陷标签派生计数真值；排除混合、损伤、长度替换等不适配病例 | [作者数据页](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad)；CC BY-NC-SA 4.0；不能把螺丝粗类计数称为长短/SKU验证 |
| FastAPI / Uvicorn / SQLite / Pydantic / Pillow / MLX-VLM | HTTP接口、事务、输入验证、图像清理、本地推理 | 使用公开依赖，具体版本见requirements-lock.txt；第三方软件许可证各自有效，未将其声称为自研基础设施 |
| 测试照片和固定观察结果 | PIL生成的显式合成工程夹具，以及注入的确定性测试后端 | 只验证软件分支；不进入公开实拍模型成绩，不用于冒充真实模型 |
| 报告/幻灯片工具 | Codex Data报告框架、ArtifactTool可编辑幻灯片、ReportLab PDF、Chrome/Playwright实录 | 工具生成的外观和工程检查不等于视觉识别准确率 |

本队新增的是：逐件空间清单与计数一致性检查、订单/证据版本约束、原文数量校验、受控补证上下文与反馈、动作选择、完成事务、只读审计、离线证据包、真实模型适配、固定评测及相应界面。没有训练或微调基础模型，没有调用收费云模型API处理用户照片。

模型权重、完整数据归档、实际订单数据库和环境目录不塞进源码ZIP。复现应根据来源和固定哈希单独获取；公开数据的非商业、署名、相同方式共享等条款仍须遵守。此记录不自行裁定奖金竞赛、后续商业展示或再分发是否获授权。

公开图片可以支持静态输入验证；当前没有同一批实物的补件前后连续照片、真实工人对照或企业试点。实录不点击需要本人核对实物的完成确认。正式开发期外的既有实现及来源须如实披露，不能改日期规避条款。


## v0.3 新增的开发实验与材料

- `google/owlv2-base-patch16-ensemble`，固定 revision `cfd3195ba4ea9592eec887ded089f4c08eff231d`；`IDEA-Research/grounding-dino-tiny`，固定 revision `a2bb814dd30d776dcf7e30523b00659f4f141c71`。两者按原仓库 Apache-2.0 许可证下载至共享模型目录，原模型卡、LICENSE、下载清单及上游元数据复制到 `third_party/models/`。仅做固定 CPU 开发对照，结果不支持接入默认核验链，没有把这些基础模型称为自研。
- Screws 新增视图由作者原始照片按完整作者旋转框裁切，不拼贴、不修补、不删除画面内部分物体。先按来源图划分，再选择一个完整视图；保留原图坐标及逐像素复算。沿用原数据署名/许可，不能把派生视图称为团队现场拍摄。
- 新增的候选 `spatial_guarded` 使用同一 Qwen 模型的原向、旋转及局部身份/孔形观察。第三次调用只收到源图与模型选出的坐标裁剪，没有工单目标数量或真值；代码只将无法确认的类别保留为未知，不依据真值修正数量。
- 相机预览、公开实拍图库、相同照片内容去重、身份复核表及新的离线报告由 Codex 实现和工程审查。新候选的默认采用由预先冻结的完整评测决定，开发通过不自动等于已采用。


## v0.4 新增来源与验证范围

- [作者 InO-10-190 仓库](https://git.sztaki.hu/emi/sim2real-object-detection)，固定 revision `c733a3543157135c591cbe3f9de27e209964af63`。作者仓库 README 与 MIT LICENSE、引用信息及全部 1,141 个下载文件 SHA 保存于 `third_party/datasets/ino-10-190/`。原始归档在本机 datasets/raw 下；760 张 PNG 与作者 LFS SHA 一致。
- origin/cropped 为同一批 190 个来源，不重复计算独立样本。作者说明 920 个标注，实际保存文件各有 919 个，未私自补标签。
- 在推理前固定筛选规则形成 20 个不同来源：4 张完整图、16 张作者框派生 ROI，全部只有 1 个作者 class 0 L-bracket。仅有 bracket 真值，bolt/nut/washer 未标注，不能填 0。恒定预测 1 即可得到 20/20 单类计数一致；本验证只研究阳性单角码输出和弃权，不证明通用计数能力。
- 新增现场验证记录器、照片证据 ZIP 与内部一致性独立核验脚本。工程夹具与 3 个既有公开开发样例用于端到端检查；人工栏由脚本填作者真值，不是真人能力或效率实验。真实人员现场实验数量仍为 0。
- 运行时队列、进程租约和图片字节核验修复均保存复现和回归记录。未修改 v0.3 冻结视觉协议；历史 64 例不能改称 v0.4 新评测。
