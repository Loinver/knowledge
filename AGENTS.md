# AGENTS.md

AI Agent 协作者请先读这里。本文件会被 Agent 自动加载，所以硬规则、常用命令与完工自检直接写在这里；
项目骨架、必读顺序与已知坑见 [.agents/AGENTS.md](./.agents/AGENTS.md)，细则按任务加载：

- [.agents/conventions/code-style.md](./.agents/conventions/code-style.md) — 前后端代码风格
- [.agents/conventions/application-architecture.md](./.agents/conventions/application-architecture.md) — 模块目录与依赖方向
- [.agents/conventions/commit.md](./.agents/conventions/commit.md) — 提交规范（git-cz）
- [.agents/conventions/i18n.md](./.agents/conventions/i18n.md) — 三层国际化
- [.agents/conventions/api-contract.md](./.agents/conventions/api-contract.md) — API 契约与错误码
- [.agents/conventions/testing.md](./.agents/conventions/testing.md) — 测试策略与必测断言
- [.agents/conventions/security-and-license.md](./.agents/conventions/security-and-license.md) — 合规红线

## 硬规则（不可协商）

1. **文案不硬编码**：前端模板禁止裸文本，一律 `vue-i18n`；ESLint 规则 `@intlify/vue-i18n/no-raw-text` 会拦截。
2. **后端不返回中文句子**：只返回错误码（如 `KG.REVISION_CONFLICT`）+ 结构化参数，由前端翻译。
3. **状态一律传枚举码**：`DRAFT`/`PUBLISHED`、`PASS`/`VIOLATION`/`NA`/`NOT_RUN`、`QUARANTINED`……不传中文状态串。
4. **四态校验不得失真**：校验项没跑就是 `NOT_RUN`，绝不能显示成通过。
5. **版本冻结**：本体发布冻结资源版本，映射发布冻结本体版本，上游改版不得静默影响下游。
6. **demo 不入库**：`demo/`（含 GB/T 标准 PDF、xlsx）是本地素材，已在 `.gitignore` 排除，不得提交或复制到仓库。
7. **依赖许可**：只允许 MIT / BSD / Apache-2.0 / ISC / PSF，禁止 GPL/AGPL/LGPL/SSPL，详见 `security-and-license.md`。
8. **Python 必写类型注解**：`disallow_untyped_defs` 已开启，缺注解即失败。
9. **模块边界必须清晰**：新增或实质修改的代码遵循 `application-architecture.md`；不以空目录、占位文件或大规模搬迁代替真实设计。

## 常用命令

```bash
make install      # 装依赖 + git hooks
make dev          # 前后端一体启动（后端 :4000，前端 :4010 代理 /api）
make start        # 构建前端 + 单端口 :4000
make lint         # ESLint + vue-tsc + Prettier + Ruff + Mypy + 架构边界测试
make fix          # 自动修复可修复项
make test         # 前端 node --test + 后端 pytest
make test-e2e     # Playwright 浏览器端主流程与响应式检查
pnpm run commit   # 交互式提交（禁止手写 git commit -m）
```

后端工具必须用 venv 内的可执行文件：`cd server && .venv/bin/ruff|mypy|pytest`（全局可能没有）。

## 完工自检（交付前逐条确认）

- [ ] `make lint` 全绿、`make test` 通过。
- [ ] 新增前端文案已进 `web/src/locales/zh-CN.json` 与 `en-US.json`，`node scripts/check-i18n-keys.mjs` 通过。
- [ ] 新增后端返回值是错误码与枚举，不是中文句子；新状态码已同步前端 i18n 码表。
- [ ] 新增行为有对应测试；涉及抽取/图谱的改动不影响幂等性与失败保护断言。
- [ ] 新模块位于复用范围相符的目录，前后端依赖方向符合 `application-architecture.md`。
- [ ] `git status` 中无 `demo/`、`.workbuddy/`、`node_modules/`、`.venv/`、`dist/`。
- [ ] 提交信息由 git-cz 生成，类型与 scope 正确。
