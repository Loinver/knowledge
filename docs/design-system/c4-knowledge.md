# C4 知识库与治理收尾

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](../README.md)。

执行日期：2026-11-23。执行者：花无缺 / EX-FRONTEND，当前专业执行者直接实施与自查；主会话 Chief 负责整合及独立复核，没有创建下级代理。

## 范围与规则

项目路径与 `/Users/linyer/Public/Linyer/knowledge/projects.json` 的 K 登记一致。
本轮只写入 `web/src/views/knowledge/**`、`web/src/views/governance/**`、
`e2e/design-system-c4-knowledge.spec.ts` 和本文。保留已有迁移修改。
未改共享 UI、语言包、依赖、API、生成类型、权限契约或冻结逻辑，未写开发数据库。

实际读取：

- `/Users/linyer/.agents/skills/linyer/SKILL.md`
- `/Users/linyer/Public/Linyer/experts/frontend.md`（EX-FRONTEND）
- `/Users/linyer/Public/Linyer/core/governance.md`
- `/Users/linyer/Public/Linyer/experts/collaboration.md`
- `/Users/linyer/Public/Linyer/knowledge/projects.json`
- `/Users/linyer/Public/Linyer/core/principles/{C02,C06}.md`
- `/Users/linyer/Public/Linyer/standards/frontend/{FE02,FE03,FE04,FE07}.md`
- `/Users/linyer/Public/Linyer/standards/quality/{QA01,QA02}.md`
- `/Users/linyer/Public/Linyer/standards/backend/BE03.md`
- 项目 `AGENTS.md`（任务提供）、`.agents/AGENTS.md`、`.agents/conventions/{code-style,i18n,application-architecture,testing}.md`
- `docs/design-system/README.md`、当前任务包及 Chief 提供的整合日志
- `/Users/linyer/.codex/skills/frontend-regression-testing/SKILL.md`
- `/Users/linyer/Public/Private/knowledge/.agents/skills/knowledge-code-style/SKILL.md`

生效规则：C02/C06、FE02/FE03/FE07、QA01/QA02、BE03，均为适用的 active/L1。
FE04 仅适用 X，实际读取后排除；未将 L4/proposed 当作标准。
按当前任务限制执行域检查，完整 lint/test/build 与浏览器串行验收交 Chief，未运行全仓自动修复。

## 本轮实际改动

| 位置                                                 | 已证实问题与修复                                                                                                               |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `governance/clauses/StandardClausesPage.vue`         | 修复机械迁移污染的 `UiORMATIVE` 与 `UiATURES`，恢复 `NORMATIVE` 值及其翻译、默认值和列表标签；消费生成的输入枚举类型。         |
| `knowledge/KnowledgeBaseDetailPage.vue`              | 上传原生文件控件改用 FormField 实际 slot 属性 `ariaLabelledby/ariaDescribedby/ariaInvalid`，修复整合日志中的三个类型错误。     |
| `knowledge/KnowledgeSearchPage.vue`                  | 高级搜索绑定展开状态；同一请求身份的刷新失败保留成功结果和本地分页；查询、知识库或检索模式改变不复用旧结果；清空显式释放快照。 |
| `knowledge/components/BaseEditor.vue`                | 编辑权限纳入 mutation 归属；权限失效使旧请求失效，验证完成后再次核对权限；无表单实例不写请求；只读字段与保存按钮禁用。         |
| `governance/{clauses,rules,exchange}`                | 实际表单显式消费共享 FormContainer/FormField；规则来源帮助关联到字段；权限失效仍保护原有草稿。                                 |
| `governance/exchange/components/OntologyRestore.vue` | 权限变化撤销预览授权和在途请求；过期 apply 收尾不清除新操作的 applying 状态，保留导入内容。                                    |
| 域测试                                               | 新增知识库、条款、规则行为回归及真实 Ui 控件双语 SSR；补导入权限变化与乱序收尾回归。                                           |
| `governance/exchange/components/OntologyHistory.vue` | 定向 ESLint 自动整理已有迁移导入，没有业务逻辑修改。                                                                           |

域 node 测试的 API 由受控夹具代替；真实 SFC SSR 使用生产模板和实际共享 Ui 控件。
SSR 检查不能证明浏览器焦点、Esc、滚动和响应式行为。

## 验证证据

域测试命令：

```sh
node --test web/src/views/knowledge/__tests__/*.test.mjs web/src/views/governance/clauses/__tests__/*.test.mjs web/src/views/governance/rules/__tests__/*.test.mjs web/src/views/governance/exchange/__tests__/*.test.mjs
```

结果：22 tests，22 pass，0 fail，0 skipped，退出 0。
日志：`/private/tmp/c4-knowledge-node.log`。
覆盖无效校验不写请求、重复提交、失败保留、旧请求不关新会话、验证期间权限变化、
查询与分页归属、导入预览/文件读入/应用失效、NOT_RUN 与 NA 显示语义、双语标签/帮助关联及数值 0。

```sh
pnpm exec eslint web/src/views/knowledge web/src/views/governance
pnpm -C web exec vue-tsc --noEmit -p tsconfig.app.json
pnpm exec playwright test e2e/design-system-c4-knowledge.spec.ts --list
```

域 ESLint 退出 0。E2E 发现检查退出 0，发现 3 个场景；没有启动 8123/5199。
项目 ESLint 未配置 `e2e/*.ts`，该文件不能称为 ESLint 已检验。
`vue-tsc --noEmit -p tsconfig.app.json` 退出 0。
本轮修改文件的 `prettier --check` 与域 `git diff --check` 均退出 0。
格式化后再次运行域 node 测试仍为 22 pass / 0 fail；域 ESLint 使用 `--max-warnings 0` 退出 0。
日志分别为 `/private/tmp/c4-knowledge-eslint.log`、`/private/tmp/c4-knowledge-types.log`、`/private/tmp/c4-knowledge-e2e-list.log`。

## 给 Chief 的串行验收与边界

```sh
pnpm exec playwright test e2e/design-system-c4-knowledge.spec.ts --workers=1
```

三个隔离场景包含：条款真实必填/错误关联、失败草稿与拒绝丢弃、NORMATIVE 请求和显示；
知识库真实上传与关键词检索、高级帮助和零阈值、失败保留及清空/重置；VIEWER 写入口禁用。
它们复用项目的隔离 identity/network 夹具，拒绝开发服务，数据只写 Playwright 临时数据库。
场景中包含 390×844 和 1280×720 溢出断言，尚未执行，不称为浏览器通过。

整合日志中的 `UiA` 实际位于 `ontology/validation/ValidationReportsPage.vue`，不属于本轮写入范围，
已交 Chief 恢复 `NA`。共享 UI 与 graph 整合失败同样交 Chief。
本执行者仅自查；独立 Quality、全仓检查与浏览器最终结论保留 INCONCLUSIVE / NOT_RUN，待 Chief 补证。
