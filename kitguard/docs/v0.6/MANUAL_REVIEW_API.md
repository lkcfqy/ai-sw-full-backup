# 人工复核与明确重开

新增能力不改变既有 AI 完成接口、视觉模型或冻结评测。`manual_reviewed` 表示已记录人工处置，与 `completed` 的 AI 核验后确认路径分开。

`POST /api/orders/{id}/manual-review` 输入：`expected_revision`、`expected_evidence_epoch`、`photo_id`、`check_id`（当前有效同版本同照片检查，否则 null）、`actual_counts`（四类严格整数0–100）、`operator_code`（1–40字符）、`reason`（1–1000字符）、`confirmed_physical:true`、`confirmed_current_bom:true`、`idempotency_key`。服务器从人工数量与当前 BOM 推导 `matches_requirements` 和 `outcome: matched|unresolved`，两者均将订单置为 `manual_reviewed`，不把 AI 改成 ready，不记入 AI completions。

响应为 `{order,manual_review}`。记录保留当时需求、人工数量、人员代号、理由、版本、照片及散列、检查ID/结论、证据epoch、范围、参考图及确认时间。人工身份与实物真实性仍属操作者声明；不是工业出库授权。无成功 AI 检查的当前照片可人工复核。已知公开演示来源（包括可追溯的重新上传）与工程替身观察照片不可升级为实物人工终态。

`POST /api/orders/{id}/reopen` 输入：`expected_revision`、`reason`、`confirmed:true`、`idempotency_key`。只允许从 `completed` 或 `manual_reviewed` 明确重开。BOM保持不变、版本加一、旧检查失效，要求新版本重新拍照。响应 `{order,reopening}`，旧完工和人工记录保留。既有改版接口仍可修改BOM并开始新版本。

已结束订单禁止直接上传照片/参考图、运行核验或改检查区域。人工复核与重开拒绝运行中的核验，并拒绝尚未关闭的固定照片验证批次登记订单。既有普通改版行为保持兼容，仍会使固定试验的旧版本绑定无法继续。

两种新操作在SQLite事务内检查版本、当前证据及幂等键。同键同请求返回原回执（`replayed:true`），跨订单、跨操作或改内容复用键返回409。旧回执回放不会将后续版本改回旧状态。旧数据库可自动增建回执表；既有订单缺少新数组时按需补齐。

应用挂载：`create_manual_review_router(store, verify_evidence_files)`。工单JSON和证据包中的完整订单自动包含新记录；离线页面展示由主任务同步扩展。
