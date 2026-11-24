# C4-R1 五列表查询隔离

日期：2026-11-23。执行者：当前 C4 前端修复会话（花无缺 / EX-FRONTEND）。没有创建新代理。

## 范围与依据

复核输入为 `/private/tmp/knowledge-final-c4-review.md` 的 **C4-R1 / P2**。先读取复核记录，再追踪页面 load、SearchTable 的 rows/total 传参、认证 store 与 token 订阅契约。依据项目 `application-architecture.md` 的异步状态归属要求、`testing.md` 的失败保护要求，以及 FE01/FE02/FE03、QA01/QA02 的本任务适用约束。

仅修改下列五个顶层页及其相邻定向测试；本说明是唯一新增交付文档：

- `web/src/views/governance/clauses/StandardClausesPage.vue`
- `web/src/views/governance/rules/GovernanceRulesPage.vue`
- `web/src/views/system/users/UsersPage.vue`
- `web/src/views/system/ai-models/AiModelsPage.vue`
- `web/src/views/system/audit-logs/AuditLogsPage.vue`（账户审计列表）

保留接手时所有未提交迁移改动。未修改共享组件、locale、API/types、后端、E2E、权限规则或业务枚举。AssetAuditLogs 只参加相邻既有回归，没有修改。

## 根因与修正

原 load 失败分支保留 items/total，但没有记录它们属于哪个查询。alpha 成功后提交 beta，beta 失败时仍会展示 alpha 及其 total。单独检查请求取消或请求序号，只能阻止过期响应，不能隔离已经展示的成功快照。

五页现在以实际 API 查询参数和会话、用户 ID、role、status 构成列表身份。查询身份同步变化时清空 items/total/error、取消或作废旧请求并释放其 loading。搜索输入草稿不参与身份，只有提交后的 q 参与。同查询刷新不清空快照，失败时保留该查询最近一次成功结果。

| 页面       | 已纳入隔离的查询参数                          |
| ---------- | --------------------------------------------- |
| clauses    | q、page、page_size                            |
| rules      | q、page、page_size、source_kind               |
| users      | q、page、page_size、role、status              |
| ai-models  | q、page、page_size、capability、enabled、sort |
| audit-logs | q、page、page_size、action                    |

五页现有 page_size 均固定为 20，没有新增页大小交互；实际参数已纳入列表身份。AI enabled 保持 boolean/null 业务语义，false 与不筛选分别处理。

请求成功、错误、finally 都检查相同归属条件：页面存活、请求仍有效、查询身份和 session generation 仍相同。身份恢复或查询从 A 切到 B 再回 A，不会使已取消或作废的旧请求重新有效。订阅 token 事件用于捕获同用户的新会话；普通 token 轮转不改变 session generation，不清空或重复加载列表。卸载解除页面订阅并作废请求。

保留原有越界页回退方式。users/audit-logs 与 rules 在需要回退时先切页，不把越界页返回的数据和 total 暂时写入新页。管理员页面继续沿用既有 isAdmin 判定；治理页和审计页未新增角色授权策略。

## 定向行为回归

五个相邻 `__tests__/c4-query-isolation.test.mjs` 共注册 40 个用例，复用位于 `system/users/__tests__/c4-query-isolation.mjs` 的测试夹具。夹具编译真实页面脚本并运行 Vue watchers、Pinia 与路由，控制 API Promise 和 token 事件；只暴露观察所需状态，不替换产品判断。请求即使收到 abort 也可以继续成功或失败，以验证页面自身的结果归属检查。

覆盖内容：

- 同查询失败保留 rows/total，重试成功替换快照；未提交草稿不发请求、不清空结果。
- 新 q 在请求结束前即清空旧行和 total，失败后仍为空；有效空结果可正常接受。
- page、source_kind、role/status、action、capability、sort 单独变化；enabled 的 false/true/null 三态。
- 旧成功和旧失败分别在新请求 pending 期间、新请求成功之后完成，均不能污染 rows/total/error/loading。
- A→B→A 查询切换；用户 ID、角色、状态和会话变化；普通 token 刷新；卸载后的完成及 token 事件。

修复前页面内容保存在 `/private/tmp/knowledge-c4-r1-before.json`。通过仅用于回放的 `/private/tmp/knowledge-c4-r1-baseline-loader.mjs`，在内存中以该源码运行相同 40 个回归，得到 **10 pass / 30 fail**；五页都在跨查询旧行断言失败，同查询快照用例均通过。没有为回放改写工作区产品文件或削弱断言。日志：`/private/tmp/knowledge-c4-r1-red.log`。

## 验证结果

| 检查                   | 结果                                                                | 日志                                     |
| ---------------------- | ------------------------------------------------------------------- | ---------------------------------------- |
| 五页相邻 Node 定向测试 | **52/52 pass，0 fail，0 skipped**，含 40 个新增用例和 12 个既有用例 | `/private/tmp/knowledge-c4-r1-tests.log` |
| 前端应用 typecheck     | 退出 0                                                              | `/private/tmp/knowledge-c4-r1-types.log` |
| 五页及新增测试 ESLint  | 退出 0                                                              | `/private/tmp/knowledge-c4-r1-lint.log`  |

实际命令（仓库根目录，zsh）：

```sh
node --test --test-reporter=spec web/src/views/governance/{clauses,rules}/__tests__/*.test.mjs web/src/views/system/{users,ai-models,audit-logs}/__tests__/*.test.mjs
pnpm -C web exec vue-tsc --noEmit -p tsconfig.app.json
pnpm exec eslint web/src/views/governance/{clauses/StandardClausesPage,rules/GovernanceRulesPage}.vue web/src/views/system/{users/UsersPage,ai-models/AiModelsPage,audit-logs/AuditLogsPage}.vue web/src/views/governance/{clauses,rules}/__tests__/c4-query-isolation.test.mjs web/src/views/system/{users,ai-models,audit-logs}/__tests__/c4-query-isolation.test.mjs web/src/views/system/users/__tests__/c4-query-isolation.mjs
```

定向 Prettier 检查与 `git diff --check` 均退出 0，格式日志为 `/private/tmp/knowledge-c4-r1-format.log`。Chief 随后反馈全前端 **695/695 通过**，包含本次 R1 用例；该全量结果来自主会话，本会话没有重复执行。Chief 已开始完整浏览器回归，此时五页产品源码已停止写入。

已将产品变更与接手时保存的源码逐项自查；增量 diff 留在 `/private/tmp/knowledge-c4-r1-only.diff`，避免把其他既有迁移内容误算为本次改动。这是实施者自查，不代替独立复审。

## 交接边界

本任务不启动浏览器、8123/5199 服务，也不运行全量测试或 build。新增 Node 用例验证页面真实异步行为，子组件由既有行为 harness 提供替身，因此不声称浏览器验收通过；全站浏览器回归交由 Chief 串行执行。R1 之外的共享 P2 由主会话处理。

完成交接后，本会话停止产品写入；五页可由 Chief 继续统一 FormContainer/FormField 命名及整合。
