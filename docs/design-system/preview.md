# 本机预览与视觉证据

2026-11-23迁移任务的历史构建预览：[http://127.0.0.1:8145/](http://127.0.0.1:8145/)。它使用独立复制的合成数据快照，关闭知识后台处理与外部模型；没有连接开发数据库。历史预览使用独立测试账号；不在文档提供可复用口令。重新启动时按部署指南在新的隔离库初始化账号。

已实际打开的页面：

- [工作台](http://127.0.0.1:8145/)
- [实体类型库](http://127.0.0.1:8145/ontology/entity-types)
- [知识库](http://127.0.0.1:8145/knowledge-bases)
- [本体设计器](http://127.0.0.1:8145/ontology/designer?ontology=1)
- [图谱浏览](http://127.0.0.1:8145/graph?graph=1)
- [映射工作台](http://127.0.0.1:8145/extraction?mapping=1)

上述入口使用生产构建，登录与六页访问证据在 `/private/tmp/knowledge-final-preview-smoke.log`。正常操作会写入这个独立预览副本，业务验收使用另外的每轮临时库；不要将预览写回开发库或截图专用库。

## 前后截图

[打开48对截图画廊](http://127.0.0.1:5260/)。本机文件为 `/private/tmp/knowledge-design-system-final/index.html`。包含工作台、实体类型、知识库、设计器、图谱、映射六类真实页面×4视口×明暗主题，共96张图像。

before来自HEAD `13b5a3a`，after来自最终迁移工作区。两阶段使用同一专用隔离数据库，after逐项验证代表性API响应与before相同。数据SHA256为 `b0aac39cb127a9c0721fb3a8ede141018bc647f2811f2b1bbaeb9f81dec6800b`。

视口1440×900、1280×720、768×1024、390×844；DPR1、浏览器scale1、CSS zoom1。`before/manifest.json` 与 `after/manifest.json` 记录URL、主题、尺寸、品牌/顶栏几何与页面宽度；`pair-verification.json`记录配对结果，`SHA256SUMS`记录96图像指纹。截图不是像素自动回归基线；功能、四态、冻结、权限与失败保护请同时查看 [verification.md](./verification.md)。

## 当前访问与重新准备

这些地址、截图目录和日志属于当时本机会话，可能已停止或被清理；本轮没有重新验收该历史预览，不能视为正在运行的服务。不得沿用历史PID停止进程，也不要把历史测试账号当作默认部署账号。

当前初始化、配置隔离和构建启动步骤见[部署指南](../operations/deployment.md)。需要复现旧截图时参阅当时的 `e2e/design-system-visual.config.ts` 与版本记录，使用新临时数据库并核对数据配对条件；不要向开发库写入视觉测试数据。
