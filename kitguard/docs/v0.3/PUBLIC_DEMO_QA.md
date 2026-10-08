# v0.3 公开照片图库浏览器验收

2026-09-26：隔离真实 API 与 Chrome 浏览器的 **39 项流程断言全部通过，JavaScript 错误为 0**。桌面与手机截图均已目视检查，未发现阻塞问题。未执行任何模型调用，没有接触新 64 张留出集，也没有修改生产数据或 v0.2 成果包。

## 范围与证据

运行地址为 `http://127.0.0.1:8772`，采用真实 `create_app`、独立 SQLite/照片目录和 `NoInference` 适配器；8772 测试服务已关闭，主服务 8765 未受影响。

本次读取且展示的只有固定公开开发样例：

| 卡片 | 源案例 | 视图 | 验证 |
|---|---|---|---|
| bag-revision | mvtec-loco-screw_bag-train-good-016 | LOCO 原图 | 返回 PNG 的 SHA-256 与 catalog 一致 |
| small-part | v03-screws-screws_222-56eea59f64ca | Screws 完整零件裁剪 | 返回 PNG 的 SHA-256 与 catalog 一致 |
| mixed-screws | v03-screws-screws_344-8d389e404b12 | Screws 完整零件裁剪 | 返回 PNG 的 SHA-256 与 catalog 一致 |

三张卡片分别显示固定 catalog 的作者来源链接和 `MVTec · CC BY-NC-SA 4.0` 标识；页脚注明为已使用的开发样例、裁剪未拼贴或删除物体。工作台继续显示公开照片演示横幅、许可和来源链接。

- [机器可读结果与源码 SHA](../../test-results/browser/public-demo-v03/result.json)
- [浏览器脚本](../../test-results/browser/public-demo-v03/browser.cjs)
- [隔离无推理服务](../../test-results/browser/public-demo-v03/server.py)
- [桌面图库截图](../../test-results/browser/public-demo-v03/01-desktop-gallery.png)
- [桌面演示工单截图](../../test-results/browser/public-demo-v03/02-desktop-created-order.png)
- [390px 手机图库截图](../../test-results/browser/public-demo-v03/03-mobile-gallery.png)
- [390px 手机演示工单截图](../../test-results/browser/public-demo-v03/04-mobile-created-order.png)

桌面 viewport 为 1440×1050，手机 viewport 为 390×844。以上为完整页面截图，长页面的高度可能大于 viewport。

## 已验证行为

1. 图库加载三张真实图像，图片可解码，完整返回字节符合 catalog 的源 SHA。浏览图库及预览不会新建订单或发出任何 POST。
2. 点击三张卡片分别调用对应的真实创建 API；每次仅生成一个公开演示工单和一张经过真实上传流程归一化的照片。源 SHA、版本和 `demo_source.physical_completion_allowed=false` 均被保存。
3. 创建后跳转到 URL 指定的工单。三个工单都存在时，再访问第一张旧工单 URL，仍选中该旧工单，验证了 `?order=` 选择逻辑。
4. 工单创建后没有任何 `checks`、`latest_check` 或完工记录。无推理适配器使核验入口明确不可用，浏览器未自动请求 inspect、propose-revision 或 complete；适配器也没有收到调用尝试。
5. 对演示工单直接发送明确确认的 complete 请求，真实后端返回 409 和“公开照片演示不能记录实物完工”。修改订单后仍保留来源标记，再次请求完成依然被拒绝。
6. 中韩公开演示横幅正确显示。一个只在内存中生成 HTML 字符串的工程条件检验确认：即便传入 ready 形状的当前核验记录，也没有完成按钮且 `openComplete()` 不打开对话框。此记录未显示、未持久化、未被计为真实观察。
7. 桌面图库、手机图库与手机工作台均无水平溢出。手机图片、来源文字和按钮完整可读，工作台主要动作可使用。
8. 一次显式模拟的创建请求 503 验证了错误显示和可用卡片按钮恢复。该拦截仅测试异常恢复，没有替换真实样例数据、生成识别结果或新增工单。
9. 浏览器请求始终位于独立本地 origin，未向作者网站发送图片或背景请求。源码哈希及完整请求清单保存在 `result.json`。

## 修复复验与限制

只读审查曾指出校验源图后再次读取路径的本地文件变更竞态。根代理已修改 helper，使照片 GET 与订单 POST 复用同一份已通过 SHA 校验的字节，并加入两项读取后替换文件的 CPU 回归。本次最终浏览器验收在重启 8772 后运行，已覆盖修复后的实现；本子任务没有修改核心代码。

两次早期自动化尝试分别因测试脚本读取跳转前响应体的时机、使用过期图片选择器而停止；属于 QA 脚本问题。其隔离数据保留在 `attempt-data-01/` 与 `attempt-data-02/`，不累计为额外通过样本。最终成功运行数据位于本测试目录的 `data/`。

39 项是同一轮流程的断言，涉及三个开发例图，并非 39 个独立用户或识别样本。本次没有运行真实 VLM、测量识别准确率、验证硬件摄像头、进行人类可用性研究或证明现场物料操作。

最终三笔工程工单：

- `ord_b098c1f880934c668d11`
- `ord_2bfe3ccf3b874bf999c8`
- `ord_40346ea3118e4192a23b`

## 复现

工作目录为项目根 `kitguard/`。重跑前先归档本测试专用 `data/`，脚本要求独立空数据库；不要操作生产 `data/`。

```sh
.venv/bin/python test-results/browser/public-demo-v03/server.py
```

另一个终端运行：

```sh
/Users/lkc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node test-results/browser/public-demo-v03/browser.cjs
```

脚本使用本机已安装的 Chrome 和已配置的 Playwright；不安装模型、不下载数据、不调用 GPU。
