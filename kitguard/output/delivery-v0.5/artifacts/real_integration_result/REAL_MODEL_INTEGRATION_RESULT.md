# v0.5 区域管线真实 MLX 连接验收

2026-09-27（韩国时间）。按事先固定的两个**已暴露开发输入**完成两次真实 `/inspect`，没有重试、没有实物完成操作。29个总HTTP请求包含创建、范围设置、照片读取、研究操作与导出；其中模型观察HTTP请求恰为2次，每次保存2个同模型方向观察阶段，共4个相关阶段。不存在新留出准确率或真人现场样本。

运行起止：`2026-09-26T15:42:56.691281+00:00`—`2026-09-26T15:43:25.087503+00:00`。结果 `completed`、`errors=[]`、`source_changed=false`。冻结38个实际代码/静态资源/配置与核验脚本；模型固定为 Qwen3.6-27B MLX 4-bit、revision `c000ac2c2057d94be3fa931000c31723aac53282`、`spatial_guarded`、1536px。没有替代测试后端或云API推理。

| 固定输入 | 根图像素范围，右下不包含 | 实际观察 | check计时 / HTTP计时 | 可解释范围 |
| --- | --- | --- | --- | --- |
| InO A41 作者目标范围 | `[436,511,606,627]`，根图1280×720 | bracket=1；其他三类模型输出0；ready | 13.046s / 13.052s | **仅作者class0角码计数有真值**。另三类未标注，不进行四类评分。 |
| mixed-screws完整边界region | `[0,0,768,576]` | bolt/nut/washer/bracket=3/0/0/0；ready | 15.173s / 15.179s | 既有公开开发样例的完整作者粗类别真值；只验证范围派生、实际MLX及field记录连接。 |

A41范围由原作者唯一class0框外扩短边10%、左上floor/右下ceil计算；这是作者定位区域，且该图在v0.4已运行并被查看。不能把这次选区1与上次整图3对比成准确率提升：两次的计数范围不同。A41未登记成四类真值研究；订单中的其他三类要求0仅是BOM，不是新增真值。

mixed-screws前置独立校验按作者说明的 `(row,col,width,height,phi)` 解析12个旋转框，使用原派生清单的16px边距，核对仅344001、344006、344010完整位于既有作者裁剪内，其他框不接触裁剪；直接从作者源图重建的像素与开发PNG相同。随后对整个开发PNG做全边界region，未选择性去除物体，不宣称去背景收益。

该例的 `public_replay` 案例先登记真值、冻结范围，然后**脚本**依次填人工栏作者数→实际MLX→关闭。报告中的人工6ms来自脚本调用，不能当成人工计时、人与AI效率比较或独立盲测。AI栏1例与作者真值相符仅是这个公开回放事实；错误ready分母为0，不表达错误放行率为0。

## 字节与输出核验

准备与运行后均由验收脚本独立使用Pillow重建根图归一化和声明范围JPEG，没有调用产品裁剪函数。根图/派生字节SHA如下：

| 输入 | 根JPEG SHA-256 | 派生JPEG SHA-256 |
| --- | --- | --- |
| A41 | `4df848a897627d659fa670fc76991f6f9c762dbfd7fced5cc4b961c7ffb3d72f` | `7e360c775c03b810b50a0d9e1c80e44d508fdd27da8084defce6eb3297e0b484` |
| mixed-screws | `b0da289149ca6352101fd5f8dbbb72522feb75d3c70a02f4a8ed03f374b74543` | `5d1ea6976927e6d3b0e723511afb7fde9d889fa1cb0c84c555accac0b492d6b5` |

全边界region重新编码JPEG，故mixed的派生SHA可以与根图不同；两者仍是同一照片来源族，不算两张物理新证据。两个工单ZIP及一个研究ZIP均通过CRC、成员长度/SHA、完整根图与派生图存在性核验。已关闭研究JSON通过独立 `verify_study_export.py` 的真值commitment、范围/照片/版本绑定、顺序、完整分母与报告重算。通过表示内部一致，不认证操作者声明、实物完整性或真实性。

验收脚本另以合成CPU工程夹具验证3项：请求失败原始body完整保存；两次503失败仍保留全部计划与研究分母并关闭导出；已运行目录禁止再次推理。工程替身没有进入上述真实结果。

## 可复核文件与退出凭据

- [SOURCE_PLAN.json](../../test-results/browser/inspection-region-real-v05/SOURCE_PLAN.json) 保留准备阶段状态；实际冻结另见 [PLAN_FREEZE.json](../../test-results/browser/inspection-region-real-v05/PLAN_FREEZE.json) 与 `source_snapshot/`。
- [result.json](../../test-results/browser/inspection-region-real-v05/result.json)，SHA-256 `a548129e652d3c8a9c2f4d9d5ddbbff7b10008da812db72337506e197f11129d`。
- [verification.json](../../test-results/browser/inspection-region-real-v05/verification.json)，SHA-256 `9a48d199edaca420e6238366b43ce02fad36db486ff35e82fdde3e3edc6bfab1`；包含result、freeze、HTTP索引、study导出及三份ZIP的绑定SHA。
- [public-replay.json](../../test-results/browser/inspection-region-real-v05/public-replay.json)、[独立study核验回执](../../test-results/browser/inspection-region-real-v05/study-export-verification.json)、[public-replay.html](../../test-results/browser/inspection-region-real-v05/public-replay.html)、[研究ZIP](../../test-results/browser/inspection-region-real-v05/public-replay-evidence.zip)。
- [A41工单ZIP](../../test-results/browser/inspection-region-real-v05/ino-A41-author-region/order-evidence.zip)、[mixed工单ZIP](../../test-results/browser/inspection-region-real-v05/mixed-screws-full-region/order-evidence.zip)。各子目录同时保存 `root.jpg`、`view.jpg`、`selected.json`、`order.json`，全部29次请求原始body/响应body/SHA位于 `http/`。
- [shutdown.json](../../test-results/browser/inspection-region-real-v05/shutdown.json) 在 `15:44:12 UTC` 确认PID53682不存在、8791端口关闭；[server.log](../../test-results/browser/inspection-region-real-v05/server.log) 保存应用shutdown complete及finished process。进程收到SIGTERM，shell返回143；`server-exit.json`没有生成，退出回执如实记录该缺项，没有补造服务finally记录。

验收后未重写真实result、freeze、HTTP证据或旧v0.4实验。GPU验收服务已退出，是否替换用户主服务由root另行决定。
