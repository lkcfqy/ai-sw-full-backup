# 旧验证集灰度诊断（待审查执行）

2026-10-02。**Post-hoc、exploratory 输入干预；不是新留出、训练实验或自动晋升。** 先提交独立脚本及合成 CPU 合同，当前不启动检测器。LOCO24、MANTA、FOD held_back 不读、不测；原 trainer、影子协议、原 RGB 结果和权重不改。

固定输入为三类训练已用的全部 80 张 validation，原顺序保留：Screws44，加 FOD36（GOPR0181 Bolt、GOPR0183 Nut、unprefixed_Washer 各12）。本集合已用于模型/阈值选择，结果只能作开发诊断。RGB 基线直接使用已保存的 best epoch7 全80原始返回，不再重推 RGB。

固定权重为 `training-runs/v0.8/grouped_detector_v1/best.pt`，SHA `2a70848fa26207fe8702e8d39e15794e8902212b8b439bfa536edf7d63a83613`；阈值 **score≥0.5**，不搜索其他阈值。先与原验证一致地 `convert('RGB')` 规范化，再仅添加 Pillow `convert('L').convert('RGB')`，之后仍是原验证链 `pil_to_tensor → float32 /255 → MPS`。不旋转 EXIF、不裁剪/放大/增强；原框与原尺寸不变。模型仍为 Faster R-CNN MobileNetV3/FrozenBatchNorm，min640/max960、内部底阈0.05、NMS0.5、最多100框；保存底阈后所有返回框，0.5只用于离线计分。无 warmup、无重试、无训练、无候选/参考更换。

灰度也固定 MPS，保持原设备路径；不可用时保留全80失败，不静默切 CPU。模型使用 eval/inference_mode，并在每次调用前后同步 MPS。MPS 不是逐位确定；历史 RGB 与新灰度非同期，不比较速度或宣称差异完全排除了数值波动。灰度保留部分亮度/外形、改变颜色分布，结果可显示此输入变化的行为敏感性，**不能证明训练因果或把误识别归咎于某个颜色捷径**。

计分复用训练时保存的、SHA 固定的纯评分代码：0.5 IoU 类别匹配 TP/FP/FN、三类计数完全一致、每类/平均 MAE、F1，分别报告全80、Screws、FOD和三个 FOD 组；每图给出历史RGB→灰度的正确/错误变化。另预定一种定位条件下的分类混淆：在 score≥0.5 的预测中按分数降序（同分按原索引），对尚未匹配 GT 取最高 IoU（同值按 GT 索引），IoU≥0.5 才一对一配对，配对不限制类别。计 FOD nut GT 被 washer 命中的次数/12，同时报告匹配明细、漏检以及类别正确匹配指标，避免将无定位重合的框直接叫 nut→washer 或重复计同一 GT。

每行保存原图 SHA、灰度 RGB 指纹、实际输入 CHW FP32 tensor SHA/尺寸/字节序、全部返回框/分数/类别、调用 started/completed、解码/转换与模型传输/调用时间。绑定原80清单、RGB原始结果/指标、权重、当前新脚本、冻结原评分代码、协议、Python/Pillow/Torch/Torchvision版本及原运行的库文件 SHA；源码/依赖/数据变化使完整性检查失败。模型时长只是本次新调用边界，非完整产品耗时。

计划包含全80显式 `not_attempted` 行；模型/解码/格式失败保留 `failed` 与原始返回或错误，不变成空预测、不丢分母。报告 completed/failed/not_attempted；错误/缺失图不计为零误差。完整80计数/定位指标只有80均成功时才适用，否则输出已测子集并标缺口、保留全计划正确数比例。旧RGB的80分母不缩水。

准备命令只校验字节和元数据，不解码照片、不导入 Torch 或加载权重；输出拒绝覆盖。根审查并结束其他 GPU 工作后，才可明确运行新80：

```sh
.venv/bin/python -m pytest -q tests/test_grayscale_validation_v08.py
.venv/bin/python scripts/v08/probe_grayscale_validation.py prepare --output test-results/v0.8-grayscale-validation-plan-v1.json
# 仅根审查批准后执行；输出目录必须不存在
.venv/bin/python scripts/v08/probe_grayscale_validation.py run --plan test-results/v0.8-grayscale-validation-plan-v1.json --output evaluation-runs/v0.8/grayscale_validation_v1
```

脚本：[probe_grayscale_validation.py](../../scripts/v08/probe_grayscale_validation.py)。所有原始记录留存。无论分数好坏，都不由本诊断自动改默认、改标签、选择阈值或消耗新来源做试错。

第一次 v1 运行在构建检测模型前因 checkpoint 中 `config.classes` 整数键与 JSON 协议字符串键的形式差异失败，80 行失败、0 次 forward；v1 run/plan及原字节源码副本完整保留。这不是灰度识别结果。CPU 载入固定 checkpoint 确认该字段为唯一差异，完整 selected 指标相等；修复仅将合法的三类键 1/2/3 规范化为字符串，再严格比较全部 config/selected，不采用通用 JSON 往返放宽其他结构。新合同直接核对此固定 CPU checkpoint，不构建模型或 forward。v2 必须新计划/新输出目录；启动前保存 runner/本文档的副本及来源 SHA→副本路径回执。顶层 `setup_error` 明示设置失败；未完成全部80成功或完整性失败时 CLI exit1，原始行仍完整保存。
