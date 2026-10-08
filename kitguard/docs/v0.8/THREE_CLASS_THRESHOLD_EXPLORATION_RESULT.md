# 三类影子阈值探索：未找到同时保留正确结果与拦截三错的阈值

2026-10-02；**post-hoc / exploratory，已曝光开发集**。原0.5方法仍拒绝，冻结协议、原运行和默认产品均未修改；没有选择新正式阈值。

根在看过原失败叠框后提出高精度冲突拦截假设；本轮先保存[七档阈值计划](THREE_CLASS_THRESHOLD_EXPLORATION_PLAN.json)，再对完整旧51、643个已保存框复算。框是原score floor/NMS之后的返回值，不是全部网络proposal；不重新检测、不解码图片、不导入Torch/MLX。仅改变`score >= threshold`，复用冻结`fuse/outcome/panel`，保留跨类重复和原G未知/问题/动作。

| 阈值 | C/W/U/E/N | 原41C损失 | 原3W→U | LOCO原14C保留 | all_four AFR/51 |
|---|---|---:|---:|---:|---:|
| 0.5 | 25/0/26/0/0 | 16 | 3 | 0 | 0 |
| 0.7 | 26/0/25/0/0 | 15 | 3 | 0 | 0 |
| 0.9 | 28/0/23/0/0 | 13 | 3 | 1 | 0 |
| 0.95 | 37/0/14/0/0 | 4 | 3 | 10 | 0 |
| 0.99 | 41/3/7/0/0 | 0 | 0 | 14 | 3 |
| 0.995 | 41/3/7/0/0 | 0 | 0 | 14 | 3 |
| 0.999 | 41/3/7/0/0 | 0 | 0 | 14 | 3 |

来源支持窄面板AFR各档均0，不能代替四类面板。0.95仍损失LOCO validation020、train261/118/087四个原C；0.99及以上将三错全部恢复为W，回到原G的C41/W3/U7。分数不是经校准的真值概率。七档都是事后比较，不能将其中较好结果当预注册验证，更不能称新留出、独立泛化或生产晋升。

**复现与证据。** 在项目根目录、输出目录尚不存在的工作副本中运行：

```sh
.venv/bin/python scripts/v08/explore_shadow_thresholds.py
```

脚本先核验以下输入SHA，再检查0.5逐图detector/fusion及汇总与原记录完全一致；输出已存在会拒绝覆盖，复现须保留原输出。完整逐例转换、触发框索引与分层结果在[107KB结果JSON](../../evaluation-runs/v0.8/three_class_threshold_exploration_v1/analysis.json)，SHA `b0c0262c7ce96d205bed2f258ece30c5d8a74b6cfa7a7fa74e5f2c763e341bc5`。脚本SHA `9e07c065668493c3c5e25fcf642d1acd95a7b2a151a308251babf34830d25ffe`；计划SHA `cce87b0ba5c15a357eedab6979e1be47de883caada57fd16490c9416b24620dc`。

| 原输入（前四项在`evaluation-runs/v0.8/three_class_shadow_v1/`） | SHA-256 |
|---|---|
| run.json | `0bb84a0f85bc09d18893993f8849f5775db56f63cc61461b7b368d265a072802` |
| freeze.json | `6ba1690a369a90d73d39a8d4acc74547ee6b4f526149b54b0dcbb0167dbef1d1` |
| predictions.jsonl | `6ed0c022880d19fffebe32b58df11f1647c77435b5f10bd2441a9f1c4a78e18b` |
| analysis.json | `05e8fe81602fa67b60cca0db6cbdcb49001c4ee0bf65117d8f437cc94f503a9a` |
| docs/v0.8/three_class_shadow_freeze_v1/source_snapshot/probe_three_class_shadow.py | `11b0b8d72ee0671143a1a6cb290e0ba5a1423f337893d906ded2c9569e236cfd` |

另用不导入上述融合函数的直接算术实现核对357个“阈值×照片”组合，计数/转换/两面板均一致；[检查回执](../../test-results/v0.8/three-class-threshold-exploration-check-v1.json)明确这是同一agent内部计算交叉检查，不冒称独立同行审计。此次JSON计算约0.089秒，不能当检测器或端到端推理时延。
