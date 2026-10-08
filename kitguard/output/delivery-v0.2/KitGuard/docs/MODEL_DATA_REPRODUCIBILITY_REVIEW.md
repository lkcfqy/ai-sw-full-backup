# 模型与公开数据的有限复现审查

审查日期：2026-09-26。独立于正在执行的 GPU 评测，仅做来源、文件元数据、轻量哈希、已完成运行记录及说明文档核查。本轮不加载模型，不重新运行推理，不重新下载权重，不重新测量性能，也不把审查当成干净机器上的完整安装测试。

## 结果

当前选定模型、下载脚本和启动脚本一致：`mlx-community/Qwen3.6-27B-4bit`，revision `c000ac2c2057d94be3fa931000c31723aac53282`，MLX affine 4-bit / group size 64。项目 `README.md` 已更新为 27B、1536px、单次逐物体清单与程序计数，下载命令为 `scripts/download_candidate_model.py`。旧 8B 下载器及既往开发记录保留为历史，不视为选定运行配置。

共享模型目录的 [README](/Users/lkc/Downloads/AI-Models/README_KitGuard_models.md) 已改为当前选型和实际运行状态。原始获取清单未被修改，SHA-256 仍为 `d4595e09a870f9cf9ed081bbf33971dc8948bfdecab547c9c39888129455e3b0`，原状态 `files_verified_runtime_not_tested` 是下载完成时的真实历史状态。新增独立的 [运行验证记录](/Users/lkc/Downloads/AI-Models/verification/Qwen3.6-27B-KitGuard-runtime-verification-v1.json) 提供后续证据，不追改获取历史。

## 实际核查

- 16 个社区模型文件的大小全部与固定版本元数据一致，3 个权重分片与索引对应。13 个非权重文件重新计算 SHA-256 全部一致。三个大权重文件核对原下载记录的 LFS SHA-256 与固定版本元数据一致，本轮未再次读取并哈希 16GB 权重，避免与进行中的评测争用资源。
- 重新通过匿名 HTTPS 获取固定版本的 [Qwen 原始 LICENSE](https://huggingface.co/Qwen/Qwen3.6-27B/resolve/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9/LICENSE) 与 [MLX 社区 README](https://huggingface.co/mlx-community/Qwen3.6-27B-4bit/resolve/c000ac2c2057d94be3fa931000c31723aac53282/README.md)，散列分别为 `50cbab8a892c5f2993b8c7351a99182507472def3b1374558308605d99b86b32`、`c2c18574ee7d11d043802d88542b68710021416cdfff3b4d8571cc845ce623bd`，均与已存原文完全一致。社区量化身份和 Apache-2.0 声明明确，不能称为 Qwen 官方 MLX 权重。
- `requirements-lock.txt` 与已完成语言运行记录中的 MLX 0.32.2、MLX-VLM 0.7.3、Transformers 5.17.0、Pydantic 2.13.5、Safetensors 0.8.0 一致。启动脚本选定本地模型、1536px、`spatial_inventory`，并启用离线 Hugging Face/Transformers 模式。没有运行安装或模型下载器。
- 从完整 `loco_development_release_v1` 的 16 条逐图记录复算为 15 张计数全对、1 张错误但明确、0 执行错误。与保存的 summary 一致，运行时源码未变化。`instructions_27b_v1` 的 24 条记录均满足预期，其中 9 个提案和 15 个澄清，0 执行错误。预期澄清包含已捕获的领域异常记录，不能把它们误算为 15 次系统失败。语言运行早于最终空间清单集成，只证明该次保存源码版本的行为。
- MLX-VLM 本地源码将 `mx.get_peak_memory() / 1e9` 放入 `GenerationResult.peak_memory`，KitGuard 保存该值。视觉开发运行最大记录值为 **19.114 GB**，语言运行最大为 **17.050 GB**；它是十进制 MLX 报告峰值，可在同一进程内累积，不能解释为整个电脑内存使用量或各图片独立新增内存。视觉开发调用中位数为 14.742 秒、最大 18.273 秒；不外推为所有未来照片的时延。
- 两套 MVTec 原始许可与数据文档一致，均为 **CC BY-NC-SA 4.0**。模型的 Apache-2.0 不覆盖这些图片及派生标签的许可。已完整校验的两个归档合计 7,488,659,064 字节，保留 1,145 张原始实拍图和 243 张 LOCO 掩码；来源证明、原类别名、粗类映射、标注数量差异及适用范围见 [DATA_PROVENANCE.md](DATA_PROVENANCE.md)。
- LOCO 后续整包验证与先前暂存的 1,007 个原件全部相同，64 个评测 case 的顺序、划分、真值、图片与掩码证据未变。历史 pending 清单、开发结果和创建时间未重写，正式来源审计补充原冻结时间与后续生成时间的区别。

机器可读轻量审查结果：[Qwen3.6-27B-reproducibility-review.json](/Users/lkc/Downloads/AI-Models/verification/Qwen3.6-27B-reproducibility-review.json)。数据归档摘要：[ACQUISITION_SUMMARY.json](../datasets/manifests/ACQUISITION_SUMMARY.json)。

## 复现边界

当前下载脚本会在再次调用时重新生成获取清单，因此本轮明确没有调用它；如果要保留这一次获取清单的字节身份，应先另存历史副本，再执行新的获取/验证操作。独立运行验证记录会固定引用当前历史获取清单 SHA，不应跟随新获取操作悄悄改写。

没有发现当前固定模型文件、许可声明或数据清单之间的不一致；这不等于已实测另一台干净电脑、RTX 3080/CUDA、GGUF/Ollama、并发推理、长上下文或另一软件版本。公共数据的预训练重叠未知，无 bracket 阳性，无连续现场操作或人类耗时基线。最终留出与同模型对照结果应在完整运行后另外报告。
