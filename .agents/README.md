# .agents · 工程约定与 Agent 操作手册

这个目录是**项目自治的规范中心**：既给人看，也给 AI Agent 看。任何参与者（人或 Agent）
改动本仓库前，先读这里的约定；约定有变化时，改这里而不是改口头习惯。

## 目录导航

| 文件                                                                           | 用途                                                                   |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| [AGENTS.md](./AGENTS.md)                                                       | **入口**。给 AI Agent 的总纲：先读什么、硬规则、常用命令、完工自检清单 |
| [conventions/code-style.md](./conventions/code-style.md)                       | 前后端代码风格、格式化参数、命名与目录约定                             |
| [conventions/commit.md](./conventions/commit.md)                               | 提交规范：git-cz、类型与 scope、分支与 PR                              |
| [conventions/i18n.md](./conventions/i18n.md)                                   | 三层国际化：界面文案 / API 消息 / 领域语义内容                         |
| [conventions/api-contract.md](./conventions/api-contract.md)                   | API 契约：错误码、枚举、版本冻结、OpenAPI 生成                         |
| [conventions/testing.md](./conventions/testing.md)                             | 测试分层、必测断言、从 demo 迁移的回归基线                             |
| [conventions/security-and-license.md](./conventions/security-and-license.md)   | 依赖许可、标准文本版权、数据脱敏、凭据隔离                             |
| [skills/knowledge-code-style/SKILL.md](./skills/knowledge-code-style/SKILL.md) | 可安装的 Agent Skill（同一套约定，供 IDE/助手加载）                    |

## 使用方式

- **人**：提 PR 前按 [AGENTS.md](./AGENTS.md) 的自检清单过一遍，`make lint` 与 `make test` 必须通过。
- **AI Agent**：会话开始时读取 [AGENTS.md](./AGENTS.md)，按其指引加载 `conventions/` 下相应文件。
- **安装 Konwledge skill**：把 `skills/knowledge-code-style/` 复制到你的 agent skills 目录，或让助手直接加载其中的 `SKILL.md`。

## 维护原则

1. **单一真值源**：工程约定只在这里定义一次，`CONTRIBUTING.md`、`README.md` 只做指向与摘要，避免多处失同步。
2. **可执行优先**：能写成工具规则（`eslint.config.js`、`pyproject.toml`、`commitlint`）的，不写成散文；文档只补充工具做不到的部分。
3. **踩坑入库**：遇到工具冲突或环境坑，追加到对应文档的「已知坑」小节，别让它第二次咬人。
