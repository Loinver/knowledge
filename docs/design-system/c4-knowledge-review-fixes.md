# C4-R2 / C4-R3 定向补修交接

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](../README.md)。

日期：2026-11-23。执行者：花无缺 / EX-FRONTEND，当前专业执行者直接实施、定向验证与自查；主会话 Chief 负责整合。未创建下级代理。

本轮依据 `/private/tmp/knowledge-final-c4-review.md` 的 C4-R2/R3 修复。**产品源码写入已结束，可交 Chief 进行控件纯更名和后续浏览器回归。**

## 范围与实际改动

| 文件                                                             | 改动                                                                                                                                                                                                |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `web/src/views/knowledge/components/DocumentDrawer.vue`          | 文档动作 owner 纳入稳定的用户 ID、role、status、会话代次和知识库归档状态；撤权、切用户、切会话与切对象作废旧动作。读请求 loading/error 不参与 owner。                                               |
| `web/src/views/knowledge/components/EvidenceDrawer.vue`          | 保留 kbId/chunk 身份匹配的成功证据快照；同身份刷新期间及失败后保持真实 GraphLinkForm 实例；撤权通过禁用状态表达，不再用 `v-if=canWrite` 卸载草稿。保留换证据/关闭时的 confirmClose。                |
| `web/src/views/knowledge/components/GraphLinkForm.vue`           | 接收知识库归档和临时 disabled 状态；禁用表单、搜索和保存，保留草稿。动作 owner 纳入稳定 actor；同身份读刷新不作废在途写操作，撤权或会话变化使旧完成失效。                                           |
| `web/src/views/knowledge/composables/useKnowledge.ts`            | 仅新增域私有 `useKnowledgeActor`，订阅既有 token 通知并读取 session generation；普通 token 轮转不改变身份，卸载时清理订阅。既有读、写 composable 行为未改。                                         |
| `web/src/views/knowledge/__tests__/c4-drawer-harness.mjs`        | 域私有实际模板挂载夹具，使用真实 Vue Router/RouterView、生产父子 SFC、FormContainer/FormField、SearchPanel、草稿与动作逻辑；API 受控，弹层和 select 使用有限替身。临时编译产物位于 `/private/tmp`。 |
| `web/src/views/knowledge/__tests__/c4-drawer-ownership.test.mjs` | 新增 9 项 R2/R3 行为回归，包含实际子组件身份与卸载断言。                                                                                                                                            |

未修改共享 UI/composable、locale、API、生成类型、backend、E2E 或其他执行者独占的五张列表；未写开发数据库、启动浏览器服务器或回退既有迁移。

## 已执行验证

```sh
node --test web/src/views/knowledge/__tests__/c4-drawer-ownership.test.mjs
node --test web/src/views/knowledge/__tests__/*.test.mjs
pnpm exec eslint web/src/views/knowledge/components/DocumentDrawer.vue web/src/views/knowledge/components/EvidenceDrawer.vue web/src/views/knowledge/components/GraphLinkForm.vue web/src/views/knowledge/composables/useKnowledge.ts web/src/views/knowledge/__tests__/c4-drawer-harness.mjs web/src/views/knowledge/__tests__/c4-drawer-ownership.test.mjs --max-warnings 0
pnpm -C web exec vue-tsc --noEmit -p tsconfig.app.json
```

- 新增回归：9 tests / 9 pass / 0 fail / 0 skipped，退出 0。
- 格式整理后知识域回归：23 tests / 23 pass / 0 fail / 0 skipped，退出 0。
- 定向 ESLint：退出 0；vue-tsc：退出 0。
- 上述 6 个代码/测试文件的 Prettier 检查：退出 0；4 个产品文件的 `git diff --check`：退出 0。
- 日志：`/private/tmp/c4-review-drawer-tests.log`、`/private/tmp/c4-review-fixes-knowledge-tests.log`、`/private/tmp/c4-review-fixes-eslint.log`、`/private/tmp/c4-review-fixes-types.log`、`/private/tmp/c4-review-fixes-format.log`。

覆盖边界：

1. 文档 archive 撤权后，旧成功/失败不 reload、不 emit changed、不写 actionError，也不释放恢复权限后新操作的 busy；撤权时零新写。
2. 文档写请求在同身份刷新成功/失败和普通 token 通知期间保持归属；切用户、切会话、切文档和卸载均使旧动作失效。
3. 实际 EvidenceDrawer 模板中，编辑 → 撤权 → 恢复、同身份刷新成功/失败，GraphLinkForm 引用保持同一实例；open/query/graph/entity/fact 全部保持，临时禁用期间零写。
4. 关联保存的旧成功/失败不关草稿、不触发父级刷新、不清除新 busy；正常新保存完成后仍关闭自己的表单并刷新证据。
5. 真实 Router 更新在撤权后仍能拒绝换证据，关闭也遵守拒绝丢弃；接受后断言旧子组件确已卸载，新证据实例无旧草稿。
6. 知识库或证据归档保留草稿并禁写；实际卸载会 abort 在途关联写请求。

首次测试的一个失败来自夹具：会话切换后真实 auth store 清空 user，夹具未补回新会话用户。修正夹具后通过，没有弱化产品断言。测试文件的三个 lint 表达式问题也已修正。

## 规则与证据范围

项目 K 已由当前路径和 `knowledge/projects.json` 核实。本任务续接复用先前已读规则与 Skills；本轮实际重读 frontend、governance、collaboration、项目总纲及任务报告，核对目标组件、直接共享依赖、auth/tokens 和测试夹具。

- `/Users/linyer/.agents/skills/linyer/SKILL.md`
- `/Users/linyer/Public/Linyer/experts/frontend.md`（EX-FRONTEND）、`core/governance.md`、`experts/collaboration.md`、`knowledge/projects.json`
- `/Users/linyer/Public/Linyer/core/principles/{C02,C06}.md`
- `/Users/linyer/Public/Linyer/standards/frontend/{FE02,FE03,FE07}.md`
- `/Users/linyer/Public/Linyer/standards/quality/{QA01,QA02}.md`、`standards/backend/BE03.md`
- 当前用户替换后的 AGENTS.md；项目 `.agents/AGENTS.md`、`.agents/conventions/{application-architecture,testing,code-style,i18n}.md`、`docs/design-system/README.md`
- `/Users/linyer/.codex/skills/frontend-regression-testing/SKILL.md`、项目 `.agents/skills/knowledge-code-style/SKILL.md`

适用规则 ID：C02、C06、FE02、FE03、FE07、QA01、QA02、BE03；未将 L4/proposed 当强制规则。知识域 helper 保持 API 层调用和现有生成类型，未改变服务端权限或事务语义。

## 交接状态与剩余限制

定向实现及上述回归已完成，停止产品写入。浏览器焦点、Esc、原生弹层/下拉交互、布局、全站回归均未在本轮执行；没有启动 8123/5199。后续按 Chief 的统一控件更名和浏览器计划推进，不重复扩大本轮测试。

本执行者的验证是直接验证与自查；修复后独立 Quality 复核仍为 INCONCLUSIVE，不能将原只读审查或本轮通过扩大为全站验收。已发出的写请求即使前端 abort，仍可能由服务端完成，本轮保证的是前端完成、错误、busy 与刷新归属。
