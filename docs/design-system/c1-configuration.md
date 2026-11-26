# C1 配置域迁移交接

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](../README.md)。

日期：2026-11-23。项目 K，基线 `13b5a3a`。
执行者：真实通用 Worker，采用花无缺前端规范；Chief 保持主会话协调职责。
本执行者没有创建代理，独立 Quality 与浏览器验收由 Chief 整合。

## 写入范围与结果

仅修改 `web/src/views/semantic-assets/configuration/` 和本文，保留其他执行者的工作区改动。

| 文件（相对 configuration）                            | 改动                                                                                                                                                                    |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `enum-dictionaries/EnumDictionariesPage.vue`          | 所有 N 导入、kebab 模板和 h() 消费迁移 Ui；项目列类型；显式 remote/真实 total/page；历史、引用表 mode=none；右固定操作列；表单上下文与提交                              |
| `assembly-templates/AssemblyTemplatesPage.vue`        | Ui 门面、列类型、显式远程分页；搜索按钮/Enter/清空和类型筛选统一复位页码；同域编辑/实例化 session 与 operation 代次；提交成员快照；成员完整 IRI title；只读与提交上下文 |
| `assembly-templates/components/TemplateCoreCheck.vue` | Ui 表单/控件/表格；保留请求代次；等待条款加载；单独展示真实 standards_conformance；成员齐全不使用通过色，VIOLATION 使用错误色                                           |
| `__tests__/enum-dictionaries.test.mjs`                | 保留原 9 项断言；编译器补齐导入类型与无 script 原语支持；增加重复保存/冲突保留、关闭会话、实际远程第三页及双语四态呈现测试                                              |
| `__tests__/assembly-templates.test.mjs`               | 10 项定向业务回归，覆盖请求乱序、会话归属、重复写、快照、revision/pin、只读、动态选择、缺失版本和四态                                                                   |
| `__tests__/configuration-harness.mjs`                 | 同域业务测试夹具，修正共享夹具自定义 namespace 的绝对 UI 导入解析；没有修改共享测试工具                                                                                 |

页码/请求仍由页面管理，组件没有接入业务 API。
两列表的 API 固定每页 20 条，页面继续使用原分页控件，表格 `pagination=false` 防止重复分页条；remote 不二次切片。
历史与引用表不分页，不制造 total。操作列稳定 key=actions，fixed=right。
模板 metadata/member payload 在请求发出前取快照，旧操作不能覆盖新会话或清除新操作的 busy。
字典保留原 generation、校验、成功/冲突提示与草稿 guard。

没有修改 API、生成 model、If-Match/revision/edit_revision、权限规则、版本冻结、共享 UI/styles、语言包或依赖。
新增 UI 文案 key 清单：无；复用现有 `validation.*` 和 `entityType.validationState`。

## 已核对的契约与差异

`TreeOption` 由 `@/components/ui` 导出，来源 `selectionTypes.ts`：
key 为 string/number，label 为 string/渲染函数，children 为 TreeOption[]，保留 disabled/checkboxDisabled/isLeaf/prefix/suffix。

**当前基线及工作区 AssemblyTemplatesPage 没有 NTree/TreeOption 或层级模型消费。**
其资源来源是 `TemplateResourceOption[]`，成员为 resource_id/pinned_revision；页面以资源 Select 和成员 Table 呈现。
因此本批保留这些真实成员、版本与动态选择，没有创造新层级，也没有修改共享 Tree。
若 Chief 的“保留 typed Tree/层级”指向尚未合入的实现，需由 Chief 提供准确消费文件或先整合该实现后补充迁移验证。
当前内置模板通过 builtin 只读；API TemplateOut 没有发布状态字段，本批没有擅自添加发布判断或改变其契约。

## 验证边界

以下最终命令均已完成，退出 0：

| 命令                                                                                                            | 结果                                                                              |
| --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `node --test web/src/views/semantic-assets/configuration/__tests__/*.test.mjs`                                  | 23 passed，0 failed，0 skipped；13 项字典/相邻业务/SSR，加 10 项模板/核心检查业务 |
| `pnpm -C web exec vue-tsc --noEmit -p /private/tmp/knowledge-c1-configuration-tsconfig.json`                    | 本域 strict 类型及直接依赖通过                                                    |
| `pnpm exec eslint web/src/views/semantic-assets/configuration`                                                  | 0 error，0 lint warning                                                           |
| `pnpm exec prettier --check web/src/views/semantic-assets/configuration docs/design-system/c1-configuration.md` | 本域与本文格式通过                                                                |
| `git diff --check -- web/src/views/semantic-assets/configuration docs/design-system/c1-configuration.md`        | 无空白错误                                                                        |

pnpm 输出本机 globalShims 配置忽略提示，本批未修改该全局配置；不属于 ESLint/类型诊断。

测试通过受控 API 夹具验证业务方法，渲染测试编译真实页面、Ui 门面和原语，使用 Vue SSR。
业务夹具的子组件 render 置空，不能作为 DOM/焦点证据；SSR 不能证明 Chromium 布局、事件、键盘或弹层行为。
原实体属性断言继续覆盖字典 pin、edit_revision/if_match、发布只读与失败不覆写，并未修改该域源码。

没有启动 8123/5199 E2E，没有操作开发库，没有运行全仓自动修复、全量 make lint/test、构建或许可门禁。
这些整合检查及当前版本独立 Quality 由 Chief 串行完成。

临时类型配置 `/private/tmp/knowledge-c1-configuration-tsconfig.json` 继承项目 strict 设置，仅 include 本域 Vue 入口及其直接依赖，不修改项目 tsconfig。
日志均位于 `/private/tmp/knowledge-c1-configuration-{tests,types,eslint,format}.log`，额外 SSR 结果在 `knowledge-c1-render.log`。

## 实际读取依据

- `/Users/linyer/.agents/skills/linyer/SKILL.md`、知识源 frontend/governance/collaboration/projects，active K 的 FE01/FE02/FE07。
- 项目 AGENTS、.agents/AGENTS、code-style/application-architecture/testing/i18n 正文。
- `docs/design-system/README.md`、controls/table/components/verification/tokens/dependencies 当前规格；实时任务授权覆盖历史状态记录。
- frontend-regression-testing 与项目 knowledge-code-style 技能；本批按明确的写入及验收边界执行定向检查。
- Ui 门面入口、表单/选择/表格类型、FormContainer/FormField、useOwnedMutation，以及真实 templates/enum-dictionaries API 与生成类型。

本执行者直接实现和自查；没有将同一执行者的角色切换记录为独立审查。
