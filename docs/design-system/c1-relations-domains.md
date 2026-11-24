# C1 关系类型与业务域

执行日期：2026-11-23。项目 K；源码基线 `13b5a3a`。
执行者为真实通用 Worker，实际读取 linyer 入口及花无缺前端规范；Chief 在主会话整合。
命名专家追加任务的 CC Switch 502 由任务包说明，本执行者没有创建代理。

## 写入范围与实现

仅修改 `web/src/views/semantic-assets/relation-types/**`、`business-domains/**` 和本文件。
起始关系列表的 `NDrawer :trap-focus="!showNamespaceCreate"` 是已有临时兼容；迁移为 UiDrawer 后删除，嵌套弹层由 Reka 管理。
其余工作区授权改动全部保留；未修改其他页面、共享 UI/styles、语言包、API、依赖或开发库。

- `RelationTypesPage.vue`：运行时组件及类型使用 `@/components/ui`。API list 通过现有 listPages 得到完整匹配集合，表格 `rows + mode="local"`；页码/pageSize 受控，搜索按钮与 Enter 同走搜索，清空/重置/筛选/pageSize 回第 1 页。`actions` 固定右侧，IRI 的 title 保留完整值。加载/失败/空态保持区分。
- `RelationTypeDetailPage.vue`：描述、页签、反馈与规则表迁移；规则为非分页集合，显式 `mode="none"`。发布/新修订使用已有 useOwnedMutation 绑定路由身份，旧写入不能结束新写入的 loading；发布刷新后恢复可用状态并显示成功通知。
- `RelationSemanticFields.vue`：两个端点、四个基数边界、反向关系及 OWL 字段保持现有模型。每个数字/复选控件有独立字段路径/id，继承 FormContext 的 disabled/readonly/submitting；基数校验仍检查完整端点组合，0、max=-1 与 false 保持原类型。局部选择器改为实际 `.ui-field`/`.ui-number-input`。
- `BusinessDomainsPage.vue`：域树、抽屉、表单及反馈迁移；成员表 `rows + mode="none"`，member.id 为行身份，`actions` 固定右侧，长 IRI 完整 title。新建在校验前锁定并捕获字段快照；基础信息保存捕获选择上下文、字段、current_revision/edit_revision，关闭/重新打开/切换选择后旧校验或写入不得修改新草稿。切换时沿用草稿 guard。
- 同域测试及适配器：保留 relation-edit-lifecycle 的所有原断言，仅调整测试加载入口；新增新建/基础编辑、双端点校验、分页搜索、过期写入、真实 SSR 控件和成员行断言。

业务 API、生成模型、IfMatch/edit_revision、权限、四态及冻结版本契约未变。
关系列表、端点和成员数组未新增去重；相同端点的不同关系及相同资源的独立成员仍使用各自业务 id。
没有新增语言键，Chief 无需合并文案清单。

## 验证与证据

当前最终结果由下列命令完成后记录。所有请求由受控夹具替代；未接入开发库。

```bash
node --test web/src/views/semantic-assets/relation-types/__tests__/*.test.mjs web/src/views/semantic-assets/business-domains/__tests__/*.test.mjs
pnpm -C web exec vue-tsc --noEmit -p /private/tmp/knowledge-c1-relations-tsconfig.json
pnpm exec eslint web/src/views/semantic-assets/relation-types web/src/views/semantic-assets/business-domains
pnpm exec prettier --check web/src/views/semantic-assets/relation-types web/src/views/semantic-assets/business-domains docs/design-system/c1-relations-domains.md
git diff --check -- web/src/views/semantic-assets/relation-types web/src/views/semantic-assets/business-domains
```

临时 TS 配置继承 web/tsconfig.app.json 的 strict 设置，只 include 四个改动 SFC 及其真实依赖，没有降低类型选项。
业务方法测试只对 API 使用受控 deferred；组件渲染使用实际 SFC、项目 UI 与原语，通过 SSR 观察属性与内容。

共享旧测试入口存在独立的加载器问题：`selection-lifecycle.test.mjs` 缺 imported-type 的 compileScript fs 支持，并错误编译无 script 原语；`semantic-fields.test.mjs` 的独立 SSR 编译缺 UI 路径解析。共享 view-harness 的 UI virtual namespace 也不能解析绝对重导出。
这些共享文件不在本执行者的写范围；初始三套相关旧入口合跑为 12 passed / 28 failed，失败日志在 `/private/tmp/knowledge-c1-relations-existing.log`。
同域脚本测试通过等价 UI index 文件入口绕过 virtual namespace，未用 Naive 别名或改变断言。SSR 适配器提供 fs、模板原语和 ESM cva 正确入口，没有替换实际控件。
Chief 应修复共享测试加载器并重新执行对应旧入口。

未执行全站 lint/test/build、真实浏览器、默认 8123/5199 E2E、真实后端或不同执行者独立复核。
本域定向结果不能替代 C1 整批或浏览器验收；嵌套弹层焦点、主题、响应式与实际滚动交 Chief 串行验证。
