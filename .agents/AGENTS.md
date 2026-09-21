# AGENTS.md · 给 AI Agent 的总纲

你是「知识中台」开源项目的协作者。这是一个**前后端一体的 monorepo**：前端 Vue 3，后端 Python FastAPI，
目标是端到端打通「本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯」。

动手前先读完本文，再按需要加载 `.agents/conventions/` 下的细则。

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
| 补测试                | `conventions/testing.md`                                    |
| 提交 / 开 PR          | `conventions/commit.md`                                     |
| 引入新依赖            | `conventions/security-and-license.md`                       |
| 任何改动收尾          | 本文第 5 节「完工自检」                                     |

## 3. 硬规则（不可协商）

1. **文案不硬编码**：前端模板禁止裸文本，一律 `vue-i18n`；ESLint 规则 `@intlify/vue-i18n/no-raw-text` 会拦截。
2. **后端不返回中文句子**：只返回错误码（如 `KG.REVISION_CONFLICT`）+ 结构化参数，由前端翻译。
3. **状态一律传枚举码**：`DRAFT`/`PUBLISHED`、`PASS`/`VIOLATION`/`NA`/`NOT_RUN`、`QUARANTINED`……不传中文状态串。
4. **四态校验不得失真**：校验项没跑就是 `NOT_RUN`，绝不能显示成通过。
5. **版本冻结**：本体发布冻结资源版本，映射发布冻结本体版本，上游改版不得静默影响下游。
6. **demo 不入库**：`demo/`（含 GB/T 标准 PDF、xlsx）是本地素材，已在 `.gitignore` 排除，不得提交或复制到仓库。
7. **依赖许可**：只允许 MIT / BSD / Apache-2.0 / PSF，禁止 GPL/AGPL/LGPL。
8. **Python 必写类型注解**：`disallow_untyped_defs` 已开启，缺注解即失败。

## 4. 常用命令

```bash
make install      # 装依赖 + git hooks
make dev          # 前后端一体启动（后端 :8000，前端 :5173 代理 /api）
make start        # 构建前端 + 单端口 :8000
make lint         # ESLint + vue-tsc + Prettier + Ruff + Mypy
make fix          # 自动修复可修复项
make test         # 后端 pytest
npm run commit    # 交互式提交（禁止手写 git commit -m）
```

后端工具必须用 venv 内的可执行文件：`cd server && .venv/bin/ruff|mypy|pytest`（全局可能没有）。

## 5. 完工自检（交付前逐条确认）

- [ ] `make lint` 全绿、`make test` 通过。
- [ ] 新增前端文案已进 `web/src/locales/zh-CN.json` 与 `en-US.json`，两份 key 集合一致。
- [ ] 新增后端返回值是错误码与枚举，不是中文句子；新状态码已同步前端 i18n 码表。
- [ ] 新增行为有对应测试；涉及抽取/图谱的改动不影响幂等性与失败保护断言。
- [ ] `git status` 中无 `demo/`、`.workbuddy/`、`node_modules/`、`.venv/`、`dist/`。
- [ ] 提交信息由 git-cz 生成，类型与 scope 正确。

## 6. 已知坑

- **ESLint 9 flat config 只在 cwd 查找配置**，配置文件必须在仓库根（已放在根），且 `ignores` 要写 `**/dist/**` 才能忽略 `web/dist` 产物。
- **vue-i18n 插件规则前缀**是 `@intlify/vue-i18n/...`，不是 `vue-i18n/...`；`no-raw-text` 只接受 `attributes / ignoreNodes / ignorePattern / ignoreText` 四个选项。
- **vue-eslint-parser 必须 ^10**，与 `eslint-plugin-vue@10` 配套，降到 9 会触发 ERESOLVE 依赖冲突。
- **RUF001/002/003 会误伤中文全角标点**，已在 ruff ignore 关闭，不要再打开。
- **Python 3.13 装 cryptography 会 sdist 构建失败**，等 M2 做凭据加密时再引入并确认 wheel 可用。
- **本机有 HTTP 代理**：`curl` 访问 127.0.0.1 要加 `--noproxy '*'`，否则 502 会被误判成服务没起来。
