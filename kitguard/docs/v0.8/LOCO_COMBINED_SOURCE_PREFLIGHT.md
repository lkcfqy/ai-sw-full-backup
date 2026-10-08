# LOCO 24 来源预飞

2026-10-02。完整 24 张候选与既有曝光登记中的 112 张原图、当前 nut/washer 两参考的原图及裁剪四个角色之间，**未发现原字节或原方向 RGB 完全重复**。24 张内部也无完全重复。此结论只适用于所绑定登记范围；不是从未被任何人或模型看过、物理零件独立或预训练未见的证明。

本次只机器解码做完整性和精确重复检查，未显示图片、未作 AI/人工视觉目检、未调用模型、未改真值/方法、未最终冻结。全部 24 保留，没有用结果删选或替换。

| 核对项目 | 结果 |
|---|---:|
| 候选原图 | 24/24 |
| 固定旧登记原图 | 112/112 |
| 两参考 source/crop 角色 | 4/4 |
| 候选对登记及参考的成对比较 | 2784，全无匹配 |
| 候选内部成对比较 | 276，全无匹配 |
| 成功解码的独立文件 | 139 |
| 原字节与已登记 RGB 校验 | 140 个角色全部一致 |
| 完整性失败 / 运行间元数据变化 | 0 / 0 |

140 个角色对应 139 文件，因为 washer 参考原图 LOCO train/good/057 已在 112 登记集合内。机器解码使用 Pillow，保持原方向与尺寸，不做 EXIF 旋转、缩放或颜色增强；指纹为 `SHA256(str((width,height)).encode()+b'|RGB|'+RGB_bytes)`，同时记录原字节 SHA、像素字节 SHA、尺寸、原模式和 EXIF 方向。维度参与指纹，避免相同字节流不同形状被混为一图。此方法不检测有损重编码、缩放后近似图或同场景/同物件。

旧曝光登记保留其原始时间及 SHA，不因为后增语义文稿包含 24 张的源 SHA 就把纯文字阅读改记成图像曝光。回执包含 139 条注册来源路径绑定；有直接历史文件 SHA 的文本当前均一致，9 条只由旧父登记绑定，明确保留 `historical_sha256:null`，不为历史补造文件哈希。关联数据库沿用当时 `ordered_rows_sha256`，本次不读取订单正文；完整历史五库回执另存于结果中。逐张登记分类、所有匹配/无匹配/不可用列表均在 JSON 内。

实现：[preflight_loco_combined_sources.py](../../scripts/v08/preflight_loco_combined_sources.py)。六项合成 CPU 合同通过（同像素不同编码、尺寸绑定、失败不当无匹配、路径限制、旧登记不补写、禁止覆盖），Ruff 通过。

```sh
.venv/bin/python -m pytest -q tests/test_loco_source_preflight_v08.py
.venv/bin/python scripts/v08/preflight_loco_combined_sources.py --output <新的结果路径.json>
```

本次已执行一次；重跑必须使用新路径，不覆盖历史回执。结果：[v0.8-loco-combined-source-preflight-v1.json](../../test-results/v0.8-loco-combined-source-preflight-v1.json)，SHA `5a099cd576d4014c306beeb9183247953d7dea13303333d1d7e7b020b80e7cf4`。下一步仍停留在评测准备阶段，不消费这 24 张进行模型试错。
