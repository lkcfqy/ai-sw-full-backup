# KitGuard 实际本地模型演示

此目录保存真实浏览器录屏、接口响应和照片证据包。生成脚本为 `scripts/record_real_demo.cjs`，使用隔离的演示数据库，不污染主工作台。

演示照片来自 **MVTec LOCO AD / screw_bag / train/good/016.png**（开发集）。此图在27B结果出现前已选作演示，不用于证明留出成绩；评测结果另见 `docs/FINAL_EVALUATION.md`。

来源：[MVTec LOCO AD 作者数据页](https://www.mvtec.com/research-teaching/datasets/mvtec-loco-ad)，许可：[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。原始数据及标注属于原作者；此演示进行上传归一化、屏幕展示、字幕叠加和视频编码，未修改模型回答。照片使用不代表MVTec认可本项目。

顺序：创建需要3枚螺纹件的订单 → 上传公开照片 → 实际模型检查 → 韩文指令将需求改为2 → 人工批准版本 → 再次提交**同一公开照片** → 实际检查 → 查看历史 → 导出ZIP。没有实际移动物料，没有使用者实验，没有点击需要本人核对实物的完成确认。

- `KitGuard_real_local_demo.webm`：浏览器原始录制，无加速或删除推理等待。
- `KitGuard_real_local_demo.mp4`：同一录像的H.264编码版本；仅转换容器/编码，保持时长。
- `recording.json`：实际HTTP响应、时间、运行状态及错误。
- `video-verification.json`：编码与时长检查（生成后有效）。
- `PUBLIC_PHOTO_DEMO_evidence.zip`：只读订单证据，解压后打开 `OPEN_ME.html`；不需服务器或网络。

这些文件是内部展示材料，未代为上传、发布或提交。数据许可和正式比赛开发期要求仍须按实际用途遵守。
