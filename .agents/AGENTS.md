# AGENTS.md · 给 AI Agent 的总纲

你是「知识中台」开源项目的协作者。这是一个**前后端一体的 monorepo**：前端 Vue 3，后端 Python FastAPI，
目标是端到端打通「本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯」。

动手前先读根目录 [AGENTS.md](../AGENTS.md) 与本文，再按需要加载 `.agents/conventions/` 下的细则。

## 1. 项目骨架

```
web/            前端 Vue 3 + Vite（构建产物 web/dist 由后端托管，实现单端口）
server/         后端 FastAPI（venv 在 server/.venv）
  app/api/v1/   HTTP 路由
  app/domain/   领域服务（不依赖 Web 框架，可单测）
  app/semantics/语义适配层：RDF / SHACL / OWL，可替换实现
  app/models/   SQLAlchemy ORM      app/schemas/  Pydantic 模型
  app/connectors/ 只读数据源连接器   app/core/ 配置、错误码、加密、日志
samples/        只读样例源库（M2 交付）
docs/           开发计划与 ADR
.agents/        工程约定（本目录）
```

**根目录只放治理文件**，业务代码一律写进 `web/` 或 `server/`。

## 2. 必读顺序

| 你在做的事            | 先读                                                        |
| --------------------- | ----------------------------------------------------------- |
| 写前端页面 / 组件     | `conventions/code-style.md` + `conventions/i18n.md`         |
| 写后端接口 / 领域逻辑 | `conventions/code-style.md` + `conventions/api-contract.md` |
| 新增模块 / 调整目录   | `conventions/application-architecture.md`                   |
| 补测试                | `conventions/testing.md`                                    |
| 提交 / 开 PR          | `conventions/commit.md`                                     |
| 引入新依赖            | `conventions/security-and-license.md`                       |
| 任何改动收尾          | 根目录 `AGENTS.md`「完工自检」                              |

## 3. 硬规则、常用命令与完工自检

这三部分写在仓库根 [AGENTS.md](../AGENTS.md)，它会被 Agent 自动加载；这里不重复，避免两处失同步。

## 4. 已知坑

- **ESLint 9 flat config 只在 cwd 查找配置**，配置文件必须在仓库根（已放在根），且 `ignores` 要写 `**/dist/**` 才能忽略 `web/dist` 产物。
- **vue-i18n 插件规则前缀**是 `@intlify/vue-i18n/...`，不是 `vue-i18n/...`；`no-raw-text` 只接受 `attributes / ignoreNodes / ignorePattern / ignoreText` 四个选项。
- **vue-eslint-parser 必须 ^10**，与 `eslint-plugin-vue@10` 配套，降到 9 会触发 ERESOLVE 依赖冲突。
- **RUF001/002/003 会误伤中文全角标点**，已在 ruff ignore 关闭，不要再打开。
- **cryptography 50.x 在 macOS + Python 3.13 上没有 wheel**，会退回 Rust 源码构建而失败；`server/pyproject.toml` 已钉 `>=44,<50`，升级前先确认 wheel 可用。CI 用 Python 3.12，本地 3.13 同样可用。
- **本机有 HTTP 代理**：`curl` 访问 127.0.0.1 要加 `--noproxy '*'`，否则 502 会被误判成服务没起来。
