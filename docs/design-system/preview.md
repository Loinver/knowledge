# 本机预览与视觉证据

最终构建预览：[http://127.0.0.1:8145/](http://127.0.0.1:8145/)。它使用独立复制的合成数据快照，关闭知识后台处理与外部模型；没有连接开发数据库。账号为 `e2e_admin`，密码为 `E2E-Admin-Password-2026!`。

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

## 重新启动

预览与画廊绑定127.0.0.1，属于本机临时服务，不是部署或共享网络服务。当前预览进程94786，画廊94788；停止前先核对PID仍属于这些服务，避免复用PID误停其他进程。临时目录被系统清理后，链接与数据需重新生成。

需要重新启动时，在项目根目录构建 `pnpm -C web build`，然后使用独立预览库：

```sh
KG_ENVIRONMENT=development \
KG_CREATE_TABLES_ON_STARTUP=false \
KG_DATABASE_URL=sqlite:////private/tmp/knowledge-design-system-preview/metadata.sqlite \
KG_KNOWLEDGE_WORKERS_ENABLED=false \
KG_ALLOW_PUBLIC_REGISTRATION=false \
KG_EXPOSE_RESET_TOKEN=false \
KG_PASSWORD_ITERATIONS=1000 \
KG_LLM_BASE_URL='' KG_LLM_API_KEY='' KG_LLM_MODEL='' \
KG_EMBEDDING_BASE_URL='' KG_EMBEDDING_API_KEY='' KG_EMBEDDING_MODEL='' \
./server/.venv/bin/uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8145
```

画廊单独启动：

```sh
python3 -m http.server 5260 --bind 127.0.0.1 --directory /private/tmp/knowledge-design-system-final
```

before/after专用库为 `/private/tmp/knowledge-e2e-design-pair`；只允许用于同数据渲染，不运行CRUD/故障测试。可复现after命令见 `e2e/design-system-visual.config.ts` 的环境契约。
