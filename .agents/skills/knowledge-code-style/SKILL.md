---
name: knowledge-code-style
description: 知识中台（Loinver/knowledge，本地 /Users/linyer/Public/Private/knowledge）的代码风格与工程规范入口。触发词：knowledge、知识中台、提交规范、git-cz、commitlint、eslint、prettier、ruff、mypy、代码风格、lint 报错。
agent_created: true
---

# 知识中台 · 工程规范入口

仓库 `.agents/` 是唯一真值源。本 skill 不复制规则。

1. 先读 `.agents/AGENTS.md`。
2. 只加载当前任务对应的 `.agents/conventions/` 文件。
3. 命令、硬规则、提交规范、国际化、API 枚举、demo 不入库、许可红线和已知坑都在那里。
4. 后端工具从 `server/.venv/bin` 运行。
5. 本 skill 与 `.agents/` 不一致时，以 `.agents/` 为准。
