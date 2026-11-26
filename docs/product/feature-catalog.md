# 全应用功能总览与台账

核验日期：2026-11-26；代码基线 `9222236f35ab5ff1df738eca2c438f7ad33c5c70` 加当前未提交工作区，包含已有A风格正式界面改动。隔离原型不计入产品能力。本次没有改变业务行为或接口。

## 如何使用台账

产品评估先看[产品介绍](overview.md)与[限制](limitations.md)；业务操作从[快速入门](../user-guide/quickstart.md)开始。下表按模块定位功能，每项详细记录角色、目标/价值、入口、前置条件、操作与输入输出、状态、关联/权限、实现/验证状态和限制。源码、测试及用户文档的关系同时维护在[机读登记](features.json)。

“已有实现”不等于“完整验收”；“测试存在”不等于“本轮测试通过”；仅入口可打开不等于该页全部操作通过。API/后台能力可没有独立页面，不因此省略。实测范围见[核验记录](../maintenance/verification-2026-11-26.md)。

| 模块                 | 功能范围                                              | 操作指南                                                                                      |
| -------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 工作台与应用壳       | APP-001～003，见本文                                  | [工作台](../user-guide/workbench.md)                                                          |
| 语义资产             | SEM-001～007，[资产台账](features-modeling.md)        | [建模与治理](../user-guide/modeling-governance.md)                                            |
| 本体建模             | ONT-001～006，[本体台账](features-modeling.md)        | [建模与治理](../user-guide/modeling-governance.md)                                            |
| 治理与交换           | GOV-001～006，[治理台账](features-modeling.md)        | [建模与治理](../user-guide/modeling-governance.md)                                            |
| 数据接入             | DAT-001～003，[数据台账](features-data-graph.md)      | [数据到图谱](../user-guide/data-graph.md)                                                     |
| 映射配置             | MAP-001～003，[映射台账](features-data-graph.md)      | [数据到图谱](../user-guide/data-graph.md)                                                     |
| 抽取与运行           | RUN-001～003，[运行台账](features-data-graph.md)      | [数据到图谱](../user-guide/data-graph.md)                                                     |
| 图谱与证据           | GRF-001～004，[图谱台账](features-data-graph.md)      | [数据到图谱](../user-guide/data-graph.md)                                                     |
| 知识库、检索与问答   | KNO编号，[知识台账](features-knowledge-system.md)     | [知识库与系统](../user-guide/knowledge-system.md)                                             |
| 账户、认证与系统管理 | ACC/SYS编号，[系统台账](features-knowledge-system.md) | [账户操作](../user-guide/knowledge-system.md)、[角色权限](../user-guide/roles-permissions.md) |

## APP-001 工作台与工作统计

- **角色与价值**：所有登录用户，快速确定当前图谱、运行隔离与建模进度，进入下一步工作。
- **入口/前提**：`/`；有效会话。空库也可访问。
- **操作/输入/输出**：加载/刷新统计、通过入口进入模块；输出资产、源、映射、运行、当前结果与草稿计数。只读，不改变发布状态。
- **关联与限制**：依赖各领域统计。隔离计数属于当前图谱关联运行；草稿数不是个人待办，不能解读为工单分配系统。
- **状态与验证**：已有实现；源码确认，M3浏览器多视口入口抽查通过，统计所有数据组合未逐一验证。
- **来源**：[页面](../../web/src/views/dashboard/DashboardPage.vue)、[API](../../server/app/api/v1/dashboard.py)、[服务](../../server/app/domain/dashboard_service.py)、[测试](../../server/tests/test_dashboard.py)；[用户指南](../user-guide/workbench.md)。

## APP-002 导航、页面搜索、语言与主题

- **角色与价值**：所有登录用户，在适合当前任务的模块与详情之间定位，保留本机阅读偏好。
- **入口/前提**：应用左轨道、模块内导航、顶栏；`/ontology`旧入口重定向实体类型。
- **操作/输入/输出**：选择模块/页面，Ctrl或⌘+K搜索入口、切换语言/明暗主题；输出目标页面与本地偏好，不修改业务对象。
- **关联与权限**：路由身份、菜单和搜索索引共享可见性；后端最终授权。搜索对象是页面入口，不是知识内容。
- **状态与限制**：已有实现；偏好保留在当前浏览器，不跨设备同步；标签翻译仍由业务维护。M3导航/响应式抽查通过，不代表全站可访问性认证。
- **来源**：[导航实现](../../web/src/layout/navigation)、[主题状态](../../web/src/stores/ui.ts)、[测试](../../web/src/layout/navigation/__tests__/navigation.test.mjs)；[用户指南](../user-guide/workbench.md)。

## APP-003 无权限、未知页面与健康接口

- **角色与价值**：用户识别无法访问的原因，运维确认服务能够响应。
- **入口/前提**：`/forbidden`、未知页面捕获路由；API `/api/v1/health`为独立健康入口。
- **操作/输出**：返回工作台或登录，必要时联系管理员；健康接口返回应用状态和版本标识。
- **权限与约束**：无权限不等于对象不存在；健康响应不检查所有外部源/模型，也不证明生产可用性。无业务写入。
- **状态与验证**：已有实现；403/404浏览器入口及隔离API health实际通过，外部依赖健康未验证。
- **来源**：[错误页](../../web/src/views/errors)、[路由](../../web/src/router/index.ts)、[服务入口](../../server/app/main.py)、[浏览器测试](../../e2e/m3-browser-flow.spec.ts)；[用户指南](../user-guide/workbench.md)、[运维](../operations/deployment.md)。

## 覆盖与维护

当前登记48组功能，覆盖42条正式路由及重定向、28个含端点的API模块。范围包括动态详情、认证、错误页及内部任务；后台任务归属相应功能，生成OpenAPI作为字段契约，不另复制第二套接口文档。

同一API文件的新端点、动态路由结构和共享实现仍需要人工检查；覆盖数不等于全部行为验证。新增、删除或改变功能时按[文档同步规范](../../.agents/conventions/documentation.md)更新相关编号、实现路径、指南与验证依据，编号不可复用。
