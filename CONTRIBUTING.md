# 贡献指南

工程约定的**单一真值源在 [.agents/](./.agents/) 目录**，本文只做入口与最短摘要。

## 先读这些

| 你要做什么          | 读                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| 第一次贡献          | [AGENTS.md](./AGENTS.md)（硬规则、自检清单）+ [.agents/AGENTS.md](./.agents/AGENTS.md)（骨架、已知坑） |
| 写代码              | [.agents/conventions/code-style.md](./.agents/conventions/code-style.md)                               |
| 新增模块 / 调整目录 | [.agents/conventions/application-architecture.md](./.agents/conventions/application-architecture.md)   |
| 提交 / 开 PR        | [.agents/conventions/commit.md](./.agents/conventions/commit.md)                                       |
| 涉及多语言          | [.agents/conventions/i18n.md](./.agents/conventions/i18n.md)                                           |
| 改后端接口          | [.agents/conventions/api-contract.md](./.agents/conventions/api-contract.md)                           |
| 补测试              | [.agents/conventions/testing.md](./.agents/conventions/testing.md)                                     |
| 加依赖 / 引用标准   | [.agents/conventions/security-and-license.md](./.agents/conventions/security-and-license.md)           |

AI Agent 协作者从根目录 [AGENTS.md](./AGENTS.md) 开始。

## 三句话版本

1. **提交**：`pnpm run commit`（Commitizen + cz-git，中文交互），**不要手写 `git commit -m`**，commitlint 会拦。
2. **校验**：业务改动执行 `make lint`（ESLint + vue-tsc + Prettier + Ruff + Mypy + 架构边界测试）与 `make test`（前端 + 后端）；纯文档及文档工具任务按下方文档同步规范定向验证。提交时 husky + lint-staged 自动校验改动文件。
3. **红线**：文案不硬编码、后端不返回中文句子（只返回错误码）、`demo/` 不入库、依赖禁 GPL/AGPL、GB/T 标准正文不入库。

## 本地环境

```bash
make install      # 依赖 + git hooks
make dev          # 前后端一体启动（后端 :4000，前端 :4010）
make start        # 构建前端 + 单端口 :4000
```

后端工具在 `server/.venv/bin/`（ruff / mypy / pytest / uvicorn），不要依赖全局安装。

## AI Agent 技能包

仓库内 `.agents/skills/knowledge-code-style/SKILL.md` 是交付前的完工自检 Skill。
Codex 等工具直接识别 `.agents/skills/`，Claude Code 通过 `.claude/skills/` 下的软链加载同一份文件。

## 功能与文档同步

按[文档同步规范](.agents/conventions/documentation.md)定位[功能编号](docs/product/feature-catalog.md)，核对用户行为、权限、状态、配置与限制是否变化。PR说明同步了哪些文档，或给出具体无需更新依据。

运行 `pnpm run check:docs`；选择暂存内容后运行 `pnpm run check:docs:staged`。提交钩子读取暂存区并执行结构检查及影响提示，未暂存的文档不能替代待提交文档。脚本变更还应运行 `pnpm run test:docs`。语义是否准确仍由开发者与审查者核对；纯文档任务按相应结构、格式与内容验证范围执行。

首次管理员初始化和各环境区别见[部署指南](docs/operations/deployment.md)；接口、目录和测试入口见[开发指南](docs/development/architecture.md)。
