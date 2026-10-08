# v0.3 完整留出独立审计

复核时间：2026-09-26T13:25:10.720790+00:00。本审计在完整64张执行结束后进行，没有运行模型、修改core、gate、评分器或冻结规则。原始结果全部保留。

## 结论

独立调用冻结评分器重算64个逐例记录，candidate/baseline、分层、配对、规则面板及两种采用flag均与保存的gate逐字段一致。另直接根据每行实际观察的未知值、issues、action与作者真值重建互斥分类，得到 **C59 / W0 / U5 / E0**。没有用保存的success flag代替这次直接计算。

同次真实首轮为 **C62 / W2 / U0 / E0**。两项预先约定的选择flag均为true：stage_passed与default_adoption_eligible。这支持按事先冻结的内部标准采用研究默认，不代表现场有效、零风险、官方评分或获奖概率。

## 冻结与来源

- 权威canonical manifest SHA：`85f331c47d50256e1e98c3b346bef109e30a98e7e101da6ea3f46c9b7b3dcaf2`；按冻结顺序64张、64个唯一source_id，含LOCO正常16、数量异常16、Screws32。
- 最终门槛冻结：`2026-09-26T12:41:25.374371+00:00`；首次执行：`2026-09-26T12:42:33.200294+00:00`；结束：`2026-09-26T13:20:05.440854+00:00`。冻结在执行之前。
- 当前15个core/runner文件、run首尾source_hashes、保存的source_snapshot，逐个SHA均与最终freeze相同；source_changed_during_run=false。
- gate运行、预测、manifest实际文件hash通过核对；实际归一化输入文件与逐行model_input_sha256均匹配。
- 独立输入重建审计记录schema_revalidated=64、prepared_inputs_recreated=128、identity_crop_files_recreated=330、verified=true。该330是原像素crop与插值crop文件重建次数，不是330个独立物体、图片或新样本。
- 本轮没有新建人工视觉真值；使用冻结的作者标注派生真值和类别投影。逐例身份、来源、图像hash、ground_truth与manifest一致，不将AI意见改成真值。

## 分层与耗时

| 分层 | N | C | W | U | E | 首轮C/W | 候选中位 / 最大 |
|---|---:|---:|---:|---:|---:|---|---|
| LOCO正常 |16|16|0|0|0|16/0|47.271 / 49.113 秒|
| LOCO数量异常 |16|15|0|1|0|16/0|45.031 / 52.504 秒|
| Screws安全裁剪 |32|28|0|4|0|30/2|22.4045 / 41.594 秒|
| 全部，仅描述性汇总 |64|59|0|5|0|62/2|40.5795 / 52.504 秒|

C/全图=59/64（92.1875%）；可执行覆盖同为59/64；错误可执行/全图=0/64，错误可执行/已答=0/59；U=5/64（7.8125%）。不存在删除慢图、弃权或错误后的分母。候选时延包括真实app-upload与观察路径；同次首轮没有独立端到端时延，逐例及汇总均为null。模型各次内部时间不能相加或相减后冒称独立部署实测。

预先要求各组C至少13/16、13/16、27/32，每组W=E=0、中位不超过60秒；三组全部通过。开发门槛已有完整28张证据，不与这64张合并。

## 所有五个弃权与两个首轮错误

数量向量固定为 `(bolt, nut, washer, bracket)`；`?`为未知，不是0。

| 完整案例ID | 作者真值 | 实际首轮 | 最终观察 | 变化与实际触发 |
|---|---|---|---|---|
| `v03-screws-screws_343-db94a130dd55` |3,2,0,0|3,2,0,0|3,?,?,0|C→U；第二方向将两nut列成washer，得到3,0,2,0；未调用身份核验|
| `v03-screws-screws_127-3b1dbf13c1ae` |0,2,0,0|0,2,0,0|0,?,?,0|C→U；第二方向0,1,1,0；未调用身份核验|
| `v03-screws-screws_113-402caabbd5cc` |2,2,0,0|2,1,1,0|2,?,?,0|W→U；两方向同样错；身份复核将原washer候选判为nut，程序只将nut/washer置未知|
| `v03-screws-screws_243-aab2c04ba8a4` |3,3,0,0|2,3,1,0|?,3,?,0|W→U；两方向同样错；身份复核将原washer候选判为bolt、closed_recess，程序只将bolt/washer置未知|
| `v03-new-loco-screw_bag-test-logical_anomalies-055` |2,2,3,0|2,2,3,0|?,2,3,0|C→U；第二方向1,2,3,0；未调用身份核验|

**055口径澄清：**第一轮及保留的原始object_evidence清单数量正确，但最终观察bolt=null，所以最终`counts_exact=false`且`actionable_counts=false`。本次最终Observation的完整计数正确与C均为59/64；原始首轮清单完整计数为62/64。不能把保留的原始清单当成已经通过最终一致性核验的观察结果。

本64张中，旋转一致性检查导致3个C→U，身份检查拦下2个W。这是本批实际消融结果，不是两个阶段在总体上的贡献估计。开发28中旋转曾拦错；不能根据本次留出事后删除旋转或重新调规则后再宣称相同集合未见。

配对矩阵（行=实际首轮，列=候选）：

| 首轮\候选 | C | W | U | E |
|---|---:|---:|---:|---:|
| C |59|0|3|0|
| W |0|0|2|0|
| U |0|0|0|0|
| E |0|0|0|0|

候选没有把两个错误“修成正确计数”；它把错误答案转为补证。正确可执行数从62降到59，也不能写成总体准确率提升。

## 三种误就绪分母

| 规则测试 | 首轮 | 候选 | 固定分母 |
|---|---:|---:|---|
| 作者名义正常订单下的数量异常错误ready |0/16|0/16|LOCO数量异常16张|
| 每图一个固定扰动订单错误ready |0/64|0/64|64张|
| 四类全部255个合法BOM中存在任一错误ready的照片 |2/64|0/64|仍为64张，不是16320|

首轮Screws113对错误BOM(2,1,1,0)、Screws243对错误BOM(2,3,1,0)分别会ready；这两个BOM恰好不是既定单个扰动，所以固定扰动0/64不能证明首轮无误放可能。候选均因unknown进入补证，不会ready。以上是程序规则模拟，不是发生过真实出库；本评测不触发人完成。

## 实现与部署边界

正式候选明确传入spatial_guarded，模型27B、1536、900/900/1800、无参考/历史context，未向观察器提供订单目标或真值。主流程选择仅通过scripts/run.sh的`KITGUARD_OBSERVATION_MODE`启动默认改成spatial_guarded；15个冻结核心算法及runner不变。直接实例化LocalVision而没有模式或环境变量仍可能沿用spatial_inventory兼容默认，不能把两种入口混称完全相同。

本审计检查的是完整模型评测及其来源一致性。实际API/自然语言演示另有凭证，不与64张统计合并。第一次candidate-real-api-v1因浏览器harness读取导航后response body失效而中断，真实视觉及指令请求均未发生；记录保留。后续只修harness并新目录重录属于工程恢复，不是挑选模型答案；完整v2 receipt已核对：3个既有开发样例、4次真实视觉核验与1次独立韩语提案请求均HTTP200；视觉decision依次correct、ready、recapture、ready。correct表示需要数量调整，不表示识别正确。韩语提案2/2/2/0与意图相同，自动化UI显式批准且无fallback；86个工程断言、0 JS错误/请求错误、源码未变。该流程没有实际补件或人工完成，不增加64张的评测样本。最终来源为test-results/browser/real-api-v03/runs/candidate-real-api-v2/browser/result.json。

## 未关闭的限制

- 公开静态图、作者类别投影与裁剪，不证明实际补件、现场效率或最终出库安全；暂无真人基线。
- 来源不重复不等于新工厂/独立拍摄会话；预训练污染未知。无bracket阳性，Screws无washer阳性。
- 三次同模型调用相关；未知物体可能在两个列表共同漏掉；可见孔属性仍是模型判断。现有identity v2对nut的closed_recess语义限制已在开发审查披露，没有在留出后静默改规则。
- sourcehash是文件一致性证据，不是现场真实性签名；结果与hash一起被恶意重写不在此防护承诺内。
- gate对提供的development report验证字段与hash关联，但不递归重跑该报告指向的开发run；本次已对受控完成开发记录独立核查，今后若要抗手工报告伪造应另版加强，未修改已冻结方法。
- 全64已使用，后续修复或复跑属于回归，不再是新holdout。不得降低阈值、删除U或用新64事后选另一方法。
- 9月26日预开发资产正式参赛资格仍须主办方确认；本内部选择不替代比赛规则。

## 文件指纹

| 文件 | SHA-256 |
|---|---|
| `docs/v0.3/HOLDOUT_GATES_V1.json` | `563bf149286d6cacb7e14992b5ee9d1b1895752fae7f407a4da37ab11d65b8b6` |
| `evaluation-runs/v03_guarded_holdout_v1/run.json` | `4e28b4508f5c390ca663c230c5c8d6546fb9dc6913526b8f36cafb7138882280` |
| `evaluation-runs/v03_guarded_holdout_v1/predictions.jsonl` | `4a6ef7c976271cc3096bdd369b897b1db46bec21d2287699f55226308e7536a3` |
| `evaluation-runs/v03_guarded_holdout_v1/manifest.json` | `85f331c47d50256e1e98c3b346bef109e30a98e7e101da6ea3f46c9b7b3dcaf2` |
| `evaluation-runs/v03_guarded_holdout_v1/gate_report_v1.json` | `8f8fa784b9abca802ffab08e1fc8b23efd75407a2ede9cc235c3496b442f599f` |
| `test-results/audit/v03-guarded-holdout-analysis.json` | `76a878c1b75fc09dcbaf4ae5d3139c97f46cfdc859c8c0200f0014215c5b3408` |

审计复算没有改写上述文件，也没有重新推理或改变计分门槛。
