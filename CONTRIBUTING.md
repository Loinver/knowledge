# 贡献指南

工程约定的**单一真值源在 [.agents/](./.agents/) 目录**，本文只做入口与最短摘要。

## 先读这些

| 你要做什么        | 读                                                                                           |
| ----------------- | -------------------------------------------------------------------------------------------- |
| 第一次贡献        | [.agents/AGENTS.md](./.agents/AGENTS.md)（骨架、硬规则、自检清单）                           |
| 写代码            | [.agents/conventions/code-style.md](./.agents/conventions/code-style.md)                     |
| 提交 / 开 PR      | [.agents/conventions/commit.md](./.agents/conventions/commit.md)                             |
| 涉及多语言        | [.agents/conventions/i18n.md](./.agents/conventions/i18n.md)                                 |
| 改后端接口        | [.agents/conventions/api-contract.md](./.agents/conventions/api-contract.md)                 |
| 补测试            | [.agents/conventions/testing.md](./.agents/conventions/testing.md)                           |
| 加依赖 / 引用标准 | [.agents/conventions/security-and-license.md](./.agents/conventions/security-and-license.md) |

AI Agent 协作者另见根目录 [AGENTS.md](./AGENTS.md)。

## 三句话版本

1. **提交**：`npm run commit`（Commitizen + cz-git，中文交互），**不要手写 `git commit -m`**，commitlint 会拦。
2. **校验**：`make lint`（ESLint + vue-tsc + Prettier + Ruff + Mypy）全绿、`make test` 通过；提交时 husky + lint-staged 自动校验改动文件。
3. **红线**：文案不硬编码、后端不返回中文句子（只返回错误码）、`demo/` 不入库、依赖禁 GPL/AGPL、GB/T 标准正文不入库。

## 本地环境

```bash
make install      # 依赖 + git hooks
make dev          # 前后端一体启动（后端 :8000，前端 :5173）
make start        # 构建前端 + 单端口 :8000
```

后端工具在 `server/.venv/bin/`（ruff / mypy / pytest / uvicorn），不要依赖全局安装。

## AI Agent 技能包

仓库内 `.agents/skills/knowledge-code-style/SKILL.md` 是同一套约定的 Agent Skill 版本，
可复制到你的 agent skills 目录使用；内容以本仓库为准。
