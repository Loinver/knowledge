# 知识中台设计系统

正式工作区采用 A 方向：深绿模块轨道、横向模块导航、紧凑顶栏，资产列表结合域导航与对象检查器。当前尺寸为轨道 80px（小桌面 72px）、顶栏 52px、模块导航 40px、对象行 60px；以 [tokens.md](tokens.md) 与源码为准。

## 维护入口

| 主题                         | 文档                               |
| ---------------------------- | ---------------------------------- |
| token、主题与 CSS 分层       | [tokens.md](tokens.md)             |
| 共享组件、原语门面与真实消费 | [components.md](components.md)     |
| 表格、分页、固定列与滚动     | [table.md](table.md)               |
| 表单、输入与校验控件         | [controls.md](controls.md)         |
| 依赖版本、许可边界与升级     | [dependencies.md](dependencies.md) |

## 分层约定

`web/src/components/ui/` 存放 shadcn-vue 源码与 Reka 交互原语，负责尺寸、变体、键盘与焦点，不引入领域依赖。`web/src/components/business/` 跨业务复用表单、字段、操作栏、搜索与受控表格，通过 props/emits/插槽协作。跨域组合逻辑在至少两个业务域证实需求后才进入 `web/src/composables/`，其余留在 `web/src/views/<area>/`。应用壳、导航与滚动边界归 `web/src/layout/`，不承载领域请求或业务判断。完整目录职责以[架构规范](../../.agents/conventions/application-architecture.md)为准。

## 维护规则

Token 唯一值来源是 `web/src/styles/tokens.css`，Tailwind、业务组件与 SVG 只引用语义变量；续用 `useUiStore` 的 `ThemeMode` 与 `html[data-theme=dark]`，不新增主题 store。基础原语按官方 Vue/Reka 路线维护，项目门面只提供明确的尺寸、变体、受控输入与反馈契约，不模拟领域服务。升级依赖前比较上游变更，再应用本地 token、i18n 与焦点适配，并对实际消费页面做回归；版本与许可边界见 [dependencies.md](dependencies.md)。

## 当前实现

运行时界面覆盖工作台、语义资产、本体装配、数据接入、图谱与证据、治理、知识库、系统管理与认证页面。业务页面消费 `components/ui` 与 `components/business`，图谱与设计器使用自绘 SVG 和 d3 布局，Naive UI 已从运行时与依赖中移除。共享组件的契约与消费位置以 [components.md](components.md)、[table.md](table.md)、[controls.md](controls.md) 为准，不需要再读逐批次交接记录。

工作区现状与验证证据见[功能台账](../product/feature-catalog.md)、[核验记录](../maintenance/verification-2026-11-26.md)与[架构说明](../development/architecture.md)。当前启动见[部署指南](../operations/deployment.md)，文档同步要求见[文档同步规范](../../.agents/conventions/documentation.md)。2026-11-23 迁移任务的批次报告、截图与文件指纹已于 2026-11-27 删除，需要时按[文档盘点](../maintenance/document-inventory.md)从 Git 历史取回，不把旧快照当作当前验收。
