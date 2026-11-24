# C4 账户、认证与系统收尾

日期：2026-11-23。项目 K：`/Users/linyer/Public/Private/knowledge`。
执行者：花无缺 / EX-FRONTEND，当前专业执行者直接实施并自查；Chief 保持唯一协调者，未创建子代理。

## 范围与依据

接续工作区现有迁移，保留其他执行者的全部修改。独占范围为
`web/src/views/account/**`、`web/src/views/auth/**`、`web/src/views/system/**`、
`e2e/design-system-c4-account.spec.ts` 与本文。

实际读取：

- `/Users/linyer/.agents/skills/linyer/SKILL.md`
- `/Users/linyer/Public/Linyer/experts/frontend.md`（EX-FRONTEND）、`core/governance.md`、`experts/collaboration.md`、`knowledge/projects.json`
- `/Users/linyer/Public/Linyer/standards/frontend/FE01.md`、`FE02.md`、`FE03.md`；`standards/backend/BE03.md`；`standards/quality/QA01.md`、`QA02.md`
- `FE04.md` 也已读取，但它只适用于 X，本项目不应用。
- 项目根 `AGENTS.md`（当前任务上下文）、`.agents/AGENTS.md`、`.agents/conventions/{code-style,application-architecture,testing,i18n,api-contract}.md`、`docs/design-system/README.md`
- `/Users/linyer/.codex/skills/frontend-regression-testing/SKILL.md`、项目 `.agents/skills/knowledge-code-style/SKILL.md`。按照本任务的独占范围和定向验证要求运行，完整检查由 Chief 整合。

FE01/FE02/FE03/BE03 是匹配 K 的 active L1；QA01/QA02 是通用 active L1。
项目身份由真实路径和 projects.json 核实，没有应用 L4/proposed 建议。

## 实际修复

| 位置                                              | 行为与边界                                                                                                                                                                                  |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `account/ProfilePage.vue`                         | 复用真实表单校验和 useOwnedMutation；失败保留输入，清空仍发送明确 null，旧身份完成不覆盖新输入。                                                                                            |
| `account/SecurityPage.vue`                        | 复用真实旧密码/新密码/确认字段校验；写请求 busy/error 归属当前账户，失败不清空密码，旧完成不清空新账户输入。                                                                                |
| `auth/ForgotPasswordPage.vue`                     | 移除重复 keyup Enter 路径，使用 native submit 和 useOwnedMutation；保留配置关闭/失败保护。                                                                                                  |
| `auth/ResetPasswordPage.vue`                      | 复用 useOwnedMutation；token 变更清空前一个 token 的密码草稿与校验，不让旧响应跳转新 token 页面。                                                                                           |
| `system/users/UsersPage.vue`                      | 新建和编辑复用 useOwnedMutation；成功编辑后刷新真实远程集合与 total。分页仅在当前页超过最后一页时回退，防止空页递归重载。                                                                   |
| 用户弹层与 AI 抽屉表单                            | 页脚按钮通过 `form` 属性和 `type=submit` 关联真实 FormContainer，让 Enter 和点击使用同一表单路径。                                                                                          |
| `system/ai-models/AiModelsPage.vue`               | Select 使用 `true`/`false` 字符串键，页面/API 保持 boolean/null。编辑和行操作复用 useOwnedMutation；补齐读取的会话检查，reset 避免双重读取，保留 revision 与密钥省略/null 的既有 API 契约。 |
| `system/audit-logs/components/AssetAuditLogs.vue` | 将机械误改的 `UiAMESPACE` 恢复为业务枚举 `NAMESPACE`。                                                                                                                                      |
| `system/audit-logs/AuditLogsPage.vue`             | 移除 unused imports；分页同样限制回退边界。                                                                                                                                                 |
| `account/__tests__/account-admin.browser.mjs`     | 清理旧 Naive 选择器，改用 dialog/combobox/option/menuitem 和当前字段容器。该旧文件不在默认 e2e testDir 中，本轮没有执行。                                                                   |

其他已迁移页面与本域 CSS 只做定向 ESLint/Prettier 整理。
认证 store/API、权限/安全规则、生成类型、语言包、共享 UI、依赖与工具配置均未由本执行者修改。
登录/注册仍复用既有 auth store 的会话代次流程，未另建认证流程。
没有需要 Chief 新增的共享组件或文案。

## 验证

本域实际挂载 FormContainer/FormField/Input/InputNumber；仅 Reka 依赖原生 DOM 的弹层、Select 和底层 Switch/Checkbox 使用有限替身。
API/令牌为受控夹具。它验证请求归属、真实字段校验与页面行为，不证明真实浏览器焦点陷阱或真实认证服务。

实际运行：

```bash
node --test web/src/views/account/__tests__/c4-forms.test.mjs \
  web/src/views/system/ai-models/__tests__/c4-models.test.mjs \
  web/src/views/system/users/__tests__/users-draft.test.mjs \
  web/src/views/system/audit-logs/__tests__/asset-audit.test.mjs
```

结果：退出 0，15 tests / 15 pass / 0 fail。
日志：`/private/tmp/knowledge-c4-domain-tests.log`。
覆盖账户清空、失败保留、确认密码、登录/注册无效输入、重置 token、找回配置开关、重复写、过期完成、AI boolean 查询、revision 与密钥清空/省略、用户草稿、审计 UTC/分页/失败与乱序读取。

`pnpm exec eslint web/src/views/account web/src/views/auth web/src/views/system --fix` 完成，退出 0。
`pnpm -C web exec vue-tsc --noEmit -p tsconfig.app.json` 完成，退出 0，无类型错误；没有重复运行全站 build/test。
`git diff --check` 定向自查无空白错误。
`pnpm exec playwright test e2e/design-system-c4-account.spec.ts --list` 完成，退出 0，成功收集 5 个用例；它不启动浏览器服务，也不表示用例通过。

## Chief 串行浏览器入口与剩余项

```bash
pnpm exec playwright test e2e/design-system-c4-account.spec.ts
```

5 个用例覆盖登录 Enter/错误/重复提交/缺 token、资料校验/失败/null 清空、用户远程搜索/分页/新建/角色状态编辑/Esc 焦点、AI 布尔筛选/失败/数值/抽屉、资产审计 NAMESPACE。
资料页覆盖 light/dark 和 1440×900、1280×720、768×1024、390×844，并检查英文标签；AI 抽屉覆盖 1280×720 与 390×844。
沿用隔离数据库 fixture 和受控失败/延迟注入，不访问或修改开发库。

本执行者未启动 8123/5199，浏览器执行为 **NOT_RUN**；键盘、焦点、主题、视口和真实后端结果等待 Chief 的实际运行证据。
当前是本域局部验证通过，整体实现验收与不同执行者独立复核仍为 **INCONCLUSIVE**。
