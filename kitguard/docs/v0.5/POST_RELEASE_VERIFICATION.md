# v0.5 发布后只读验证

最终冻结交付：`output/delivery-v0.5/index.html`。源码包SHA256：`6b17561a2a81645db2436a604fef9b7e8581f01e8306e6eadd0fca7d280e5e3a`。1196个源码/文本文件，5,386,487字节ZIP。

最终工作区696测试通过，源码实际解压后690通过、6项明确因未随包提供原始公共照片/作者标注而跳过。没有使用解压测试来声称模型推理或全新机器安装已验证。实际wheel另以现有依赖独立导入和HTTP选区操作验收通过。

最终交付Chrome只读27项通过：40份资料、42项SHA、42个相对链接HTTP200；1440/390/320无水平溢出，0外部请求/JS错误。证据：`test-results/browser/delivery-v05-final/result.json`。QA脚本最初对verification_status预期拼写与实际schema不符，修正为verified并保留说明，没有改最终交付。

真实照片两个离线包另做52项Chrome检查，1440/390共4截图，整图、声明矩形和裁图可见，0外部请求/JS或console错误；原ZIP SHA前后不变。证据：`test-results/browser/inspection-region-real-v05/offline-browser/receipt.json`。该补充检查完成于源码打包后，作为独立sidecar保存，不修改已冻结的源码与交付。

主服务8765已经运行0.5.0（PID54068/session88556），切换前后订单集合一致。模型未提前加载，由下一次实际请求加载。交付页面4177（session58015）只提供本地只读文件。

最终实际源码包经过报名私密标识精确扫描，6项标识均无匹配。此扫描不认证任意个人信息的完全排除。

后续补充文档和演示稿保存在工作区docs/v0.5与output/presentations/v0.5，作为发布后材料；不回写历史v0.3/v0.4或已验收v0.5源码包。
