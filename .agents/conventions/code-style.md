# 代码风格约定

工具是真值源，本文只补充工具规则之外的判断依据。

## 1. 工具与配置位置

| 范围          | 工具                                           | 配置                                              |
| ------------- | ---------------------------------------------- | ------------------------------------------------- |
| 前端语法/风格 | ESLint 9（flat config）                        | 仓库根 `eslint.config.js`                         |
| 前端类型      | vue-tsc（strict）                              | `web/tsconfig.app.json`、`web/tsconfig.node.json` |
| 全仓格式化    | Prettier                                       | `.prettierrc.json`、`.prettierignore`             |
| 后端语法/风格 | Ruff（lint + format，替代 black/isort/flake8） | `server/pyproject.toml` `[tool.ruff]`             |
| 后端类型      | Mypy                                           | `server/pyproject.toml` `[tool.mypy]`             |
| 编辑器一致性  | EditorConfig                                   | `.editorconfig`                                   |

## 2. 前端（Vue 3 + TypeScript）

- 格式：2 空格、**单引号**、**无分号**、行宽 100、尾逗号 `all`、LF。
- 组件统一 `<script setup lang="ts">`。
- `import` 由 `simple-import-sort` 自动排序；类型必须用 `import type`。
- 禁止 `var`；优先 `const`；相等比较用 `===`（`eqeqeq: smart`）。
- 允许 `console.warn/error`，禁止 `console.log`（会告警）。
- `@typescript-eslint/no-explicit-any` 是 warn：真要用请写注释说明理由，或用 `unknown` + 类型收窄。
- 前置 `_` 的参数/变量视为有意忽略。

### 自绘 SVG 优先

本体设计器画布、图谱浏览、映射图谱视图**一律自绘 SVG**，不引入流程图/图谱库：要表达「关联实体 + 派生边 + 同一对端点多条事实弯曲」，第三方库的语义表达能力不够。
自绘组件与 UI 库共用 `web/src/styles/` 下的同一份 CSS 变量，避免两套视觉。

## 3. 后端（Python 3.12 + FastAPI）

- 格式：4 空格、双引号、行宽 88、LF（`ruff format` 负责，不要手工纠结）。
- **所有函数必须写类型注解**（参数与返回值），Mypy 会拦。
- 导入由 ruff `I` 规则排序；模块开头用 `from __future__ import annotations` 保持注解写法统一。
- 规则集：`E W F I N UP B A C4 SIM RUF ASYNC`；已忽略 `B008`（FastAPI 依赖注入默认值）与 `RUF001/002/003`（中文全角标点）。
- 文档字符串用中文可以，但不要把校验/格式寄托在文档上——能写进工具规则就写规则。

### 分层纪律

| 层                | 允许                             | 禁止                      |
| ----------------- | -------------------------------- | ------------------------- |
| `app/api/v1/`     | 参数校验、调用领域服务、响应模型 | 写业务逻辑、直接写 SQL    |
| `app/domain/`     | 业务规则、编排                   | import FastAPI，感知 HTTP |
| `app/semantics/`  | RDF/SHACL/OWL 适配               | 领域规则                  |
| `app/models/`     | ORM 映射                         | 业务判断                  |
| `app/connectors/` | 源库读取，只读强制               | 写操作                    |

## 4. 命名

| 对象            | 约定                                 | 示例                             |
| --------------- | ------------------------------------ | -------------------------------- |
| 语义资源机读名  | PascalCase，**不翻译**，IRI 由它推导 | `ProjectParticipation`           |
| 语义资源显示名  | 双语，存 `label_i18n` JSONB          | `{zh-CN: 员工, en-US: Employee}` |
| 数据库表/列     | snake_case 复数表名                  | `resource_revision`              |
| 前端组件        | PascalCase 文件 + `<script setup>`   | `TypeDetailDrawer.vue`           |
| 前端 composable | `useXxx`                             | `useOntologyStore`               |
| i18n key        | 点分小写，按页面分组                 | `type.detail.basic.title`        |
| 错误码          | `KG.` 前缀 + 全大写下划线            | `KG.REVISION_CONFLICT`           |

## 5. 已自动化的部分

提交时 `lint-staged` 会按改动文件粒度跑：

- `web/**/*.{ts,tsx,vue,js,mjs}` → `eslint --fix` + `prettier --write`
- `*.{json,md,yml,yaml,css,html}` → `prettier --write`
- `server/**/*.py` → `ruff check --fix` + `ruff format`

CI（`.github/workflows/lint.yml`）对全仓库再跑一遍同样的校验外加 `vue-tsc` 与 `pytest`。
**本地通过 CI 就大概率通过**——不要依赖 CI 兜底。
