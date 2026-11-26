---
name: knowledge-code-style
description: 知识中台仓库的交付前完工自检：按顺序跑 lint、测试、i18n key 校验，核对硬规则与 git 暂存内容。在知识中台（web/ + server/ monorepo）中完成改动、准备提交或开 PR、排查 make lint / make test / commitlint 失败时使用。
---

# 知识中台 · 完工自检

硬规则与自检清单的真值源是仓库根 `AGENTS.md`；本 skill 只给执行顺序。两者不一致时以 `AGENTS.md` 为准。

## 步骤

先按[文档同步规范](../../conventions/documentation.md)确认适用步骤；纯文档与文档工具任务直接执行相应结构、格式、内容及工具行为验证，不运行全仓自动修复。业务改动在仓库根目录依次执行以下适用步骤，前一步失败先修复再继续：

1. **自动修复**：`make fix`（ESLint --fix、Prettier、Ruff），然后确认没有顺带改动无关文件。
2. **静态检查**：`make lint`。包含 ESLint、vue-tsc、Prettier、Ruff、Mypy 与 `server/tests/test_architecture.py` 架构边界测试。
3. **测试**：`make test`（前端 `node --test` + 后端 pytest，后端约 5 分钟）。只改一端时可先跑 `make test-web` 或 `make test-server` 快速迭代，交付前仍跑全量。
4. **i18n**：改了 `web/src/locales/` 或新增文案时跑 `node scripts/check-i18n-keys.mjs`。
5. **接口契约**：改了后端路由或 Pydantic schema 时跑 `make check-api`；不一致则 `pnpm -C web gen:api` 重新生成，禁止手改 `web/src/api/schema.d.ts`。
6. **主流程**：改动涉及抽取、映射、图谱或页面主流程时跑 `make test-e2e`（首次需 `pnpm exec playwright install chromium`）。
7. **新依赖**：跑 `pnpm run check:licenses:web` 或 `pnpm run check:licenses:server`，并按 `.agents/conventions/security-and-license.md` 在 PR 描述中写明许可。
8. **人工核对**：逐条过根 `AGENTS.md`「完工自检」，重点是后端不返回中文句子、未执行校验返回 `NOT_RUN`、`git status` 中没有 `demo/`、`.workbuddy/`、`node_modules/`、`.venv/`、`dist/`。
9. **文档影响**：按 [文档同步规范](../../conventions/documentation.md)核对功能编号、实现和指南，运行 `pnpm run check:docs`；提交前运行 `pnpm run check:docs:staged`。交付写明文档更新或具体无需更新依据。纯文档任务执行相关结构、格式和内容核验，不重复全量业务测试；检查脚本变化补定向行为测试。
10. **提交**：`pnpm run commit`，不要 `git commit -m`。

## 汇报

如实列出每一步的结果：通过、失败（附关键输出）或跳过（附原因）。没跑的步骤不要写成通过。

## 常见失败

- 后端命令找不到：必须用 `server/.venv/bin/` 下的 ruff / mypy / pytest。
- `curl` 本地服务返回 502：本机有 HTTP 代理，加 `--noproxy '*'`。
- 其余已知坑见 `.agents/AGENTS.md`「已知坑」。
