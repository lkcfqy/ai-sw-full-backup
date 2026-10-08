# AI、代码和数据来源披露草稿

实际开发日期：2026-09-26（韩国时间）。本文件是项目来源记录，不替代主办方待发布的“별지2”，也不表示赛前代码已获接纳。

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
