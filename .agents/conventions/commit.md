# 提交与协作规范

## 1. 提交方式

```bash
npm run commit     # git-cz 交互式提交（唯一推荐）
git commit         # husky 已接管，同样进入交互
```

**禁止 `git commit -m "..."`**：`commit-msg` 阶段的 commitlint 会强校验格式，手写容易不合规，也让 issue 引用缺失。

## 2. 提交信息格式

```
<type>(<scope>): <subject>

<body（可选）>

<footer（可选，如 BREAKING CHANGE: / Closes #12）>
```

- `type` 取值见下表
- `subject` ≤ 72 字符，**句末不加句号**，用中文或英文均可（保持同一提交内一致）
- `body` 每行 ≤ 100 字符，说明「为什么」而不是「改了什么」

### type 清单

| type       | 含义                           |
| ---------- | ------------------------------ |
| `feat`     | 新功能                         |
| `fix`      | 修复缺陷                       |
| `i18n`     | 国际化：文案、双语字段、语言包 |
| `refactor` | 重构，不改变外部行为           |
| `perf`     | 性能优化                       |
| `test`     | 测试                           |
| `docs`     | 文档                           |
| `style`    | 代码风格，不影响逻辑           |
| `build`    | 构建与依赖                     |
| `ci`       | CI 配置                        |
| `chore`    | 其他杂项                       |
| `revert`   | 回滚提交                       |

### scope 清单

`web` `server` `ontology` `mapping` `extraction` `graph` `evidence` `semantics` `catalog` `i18n` `deps`
可自定义，也可跳过（跨模块改动建议跳过）。

正例：

```
feat(ontology): 新增实体类型详情六页签抽屉
fix(extraction): 关联表端点未解析时不再静默丢弃整条记录
i18n(web): 补齐实体实例列表缺失的英文键
```

## 3. 提交粒度

- 一个提交一件事：不要「改功能 + 调格式 + 补文档」混在一起。
- 格式类改动单独提交（`style:` 或 `chore:`），便于 review 时跳过。
- 每个提交都应能通过 `make lint`（至少不让 CI 更差）。

## 4. 分支与 PR

- 分支命名：`feat/xxx`、`fix/xxx`、`i18n/xxx`、`chore/xxx`，从 `main` 切出。
- PR 描述三件事：**改了什么 / 为什么 / 怎么验证**，并附上 `make lint`、`make test` 的结果。
- 涉及行为变更必须有测试；涉及 API 变更要说明是否影响已发布的下游（本体/映射版本冻结）。
- squash merge，合并信息沿用 Conventional Commits 格式。

## 5. 发布

- tag 用语义化版本：`v0.1.0`（M3 主流程贯通）、`v1.0.0`（M4 规范符合性）。
- 每个 tag 附 CHANGELOG 摘要，**breaking change 必须显式标注**。
