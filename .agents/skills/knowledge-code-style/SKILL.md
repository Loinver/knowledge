---
name: knowledge-code-style
description: 知识中台（Loinver/knowledge，本地 /Users/linyer/Public/Private/knowledge）的代码风格与工程规范： lint 命令、git-cz 提交规范、i18n 与 API 枚举规则、demo 不入库、依赖许可红线、完工自检清单。触发词：knowledge、知识中台、提交规范、git-cz、commitlint、eslint、prettier、ruff、mypy、代码风格、lint 报错。
agent_created: true
---

# 知识中台 · 代码风格与工程规范

前后端一体的 monorepo：前端 Vue 3，后端 Python FastAPI。

> **真值源**：完整约定在仓库 `.agents/` 目录（`.agents/AGENTS.md` 为入口，`conventions/` 下分细则）。
> 本 skill 只保留高频操作要点；有冲突以仓库内 `.agents/` 为准，改动约定请改那里。

## 命令

```bash
make install      # 依赖 + git hooks
make dev          # 前后端一体（后端 :8000，前端 :5173 代理 /api）
make start        # 构建前端 + 单端口 :8000
make lint         # ESLint + vue-tsc + Prettier + Ruff + Mypy
make fix          # 自动修复
make test         # pytest
npm run commit    # 交互式提交，禁止 git commit -m
```

后端一律用 `cd server && .venv/bin/ruff|mypy|pytest`（全局可能没装）。

## 关键路径

| 用途                | 路径                                                |
| ------------------- | --------------------------------------------------- |
| 规范真值源          | `.agents/`（AGENTS.md + conventions/）              |
| 前端                | `web/`；ESLint 配置在**仓库根** `eslint.config.js`  |
| 后端                | `server/`（venv：`server/.venv`）                   |
| 提交配置            | `commitlint.config.cjs`（commitlint + cz-git 共用） |
| 本地 demo（不入库） | `demo/`                                             |

## 提交规范

只允许 git-cz。类型：`feat` `fix` `i18n` `refactor` `perf` `test` `docs` `style` `build` `ci` `chore` `revert`。
scope：`web` `server` `ontology` `mapping` `extraction` `graph` `evidence` `semantics` `catalog` `i18n` `deps`。
主题行 ≤72 字符，句号省略。

## 硬规则

1. 前端文案走 vue-i18n，禁止模板裸文本（`@intlify/vue-i18n/no-raw-text` 拦截）。
2. 后端只返回错误码（`KG.XXX`）+ 参数，不返回中文句子；状态传枚举码（`DRAFT`/`PUBLISHED`、`PASS`/`VIOLATION`/`NA`/`NOT_RUN`）。
3. 校验四态：未执行必须 `NOT_RUN`，不得显示成通过。
4. 版本冻结：本体/映射发布钉住上游版本；画布布局不产生语义版本。
5. `demo/` 不入库，别提交也别复制进仓库。
6. 依赖只准 MIT/BSD/Apache/PSF，禁 GPL/AGPL/LGPL；GB/T 正文不入库（只留条款编号 + 自撰描述）。
7. Python 必须写类型注解（Mypy `disallow_untyped_defs`）。

## 已知坑

- ESLint 9 flat config 只在 cwd 找配置 → 配置必须在仓库根；`ignores` 写 `**/dist/**` 才能忽略 `web/dist`。
- vue-i18n 规则前缀是 `@intlify/vue-i18n/...`；`no-raw-text` 只接受 `attributes / ignoreNodes / ignorePattern / ignoreText`。
- `vue-eslint-parser` 必须 ^10（与 `eslint-plugin-vue@10` 配套），降 9 会 ERESOLVE。
- RUF001/002/003 误伤中文全角标点，已在 ruff ignore 关闭。
- Python 3.13 装 `cryptography` 会 sdist 构建失败，M2 再引入。
- 本机有代理：`curl` 访问 127.0.0.1 需 `--noproxy '*'`。

## 完工自检

`make lint` 全绿 → `make test` 通过 → 双语 key 一致 → 无 demo/.venv/node_modules/dist 入暂存区 → 提交信息合规。
