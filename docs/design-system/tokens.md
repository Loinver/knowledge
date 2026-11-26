# Token 语义与实际映射

本页尺寸与色值核对日期为 2026-11-26（9222236加未提交A风格工作区）。值与语义别名的真值源是 [tokens.css](../../web/src/styles/tokens.css)；[global.css](../../web/src/styles/global.css) 通过 `@theme inline` 暴露 Tailwind 名称。[ui.css](../../web/src/styles/ui.css)、业务 CSS 和 SVG 消费相同变量。

main.ts 只导入 global.css；该入口依次组织 Tailwind theme、项目 tokens、tw-animate-css、ui.css 与 Tailwind utilities，并显式定义 base 样式。Naive theme 与 legacy.css 已移除；下面仍存在的旧变量名是项目 CSS 语义别名。

## 颜色与语义

| 语义值/别名（CSS 变量省略 --）                                                                  | global.css 实际导出的 Tailwind 颜色名                                         | 使用含义                                     |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------- |
| surface-background → background；bg-base/bg                                                     | background                                                                    | 页面基础表面                                 |
| surface-panel → card；bg-surface/bg-panel                                                       | card、card-foreground                                                         | 卡片表面与正文                               |
| surface-overlay → popover；bg-elevated                                                          | popover、popover-foreground                                                   | 浮层表面与正文                               |
| foreground-primary → foreground；text/text-primary                                              | foreground                                                                    | 正文                                         |
| surface-muted / foreground-secondary → secondary / secondary-foreground                         | secondary、secondary-foreground                                               | 次级表面与内容                               |
| surface-muted / foreground-muted → muted / muted-foreground                                     | muted、muted-foreground                                                       | 弱化表面与内容                               |
| action-primary / action-foreground → primary / primary-foreground；accent/pri/cyan/on-accent    | primary、primary-foreground                                                   | 主操作与其前景                               |
| surface-hover → shadcn-accent；accent-foreground                                                | accent、accent-foreground                                                     | 悬停表面；与旧 CSS --accent 主操作色含义不同 |
| status-violation / action-foreground → destructive / destructive-foreground；danger/s-violation | destructive、destructive-foreground                                           | 危险或违规                                   |
| border-default → border/input；focus-ring → ring；border/focus                                  | border、input、ring                                                           | 边框、输入边框、焦点环；input 不是输入背景   |
| status-pass；s-pass/success                                                                     | success                                                                       | 通过                                         |
| status-not-run；s-notrun/warning                                                                | warning、not-run                                                              | 警告/未运行颜色；未执行不能标为通过          |
| status-na；s-na                                                                                 | na                                                                            | 不适用，与通过区分                           |
| graph-entity/relation/derived-color/evidence/quarantine；g-*                                    | graph-entity、graph-relation、graph-derived、graph-evidence、graph-quarantine | 图谱实体、关系、派生、证据、隔离             |
| semantic-ai；ai/violet                                                                          | ai                                                                            | AI 语义                                      |

surface-input/canvas/selected/raised/inset、foreground-disabled、border-muted/emphasis、status-info、graph-current/type-tint、semantic-ai-soft、overlay-scrim 等仍通过 CSS 变量使用。当前 global.css **没有**为它们导出 graph-canvas、selected、disabled-foreground、strong-border、graph-current 等 Tailwind 颜色名；也没有 neutral 代替 na 的映射。sidebar 系列变量存在于 tokens.css，但未在该 `@theme inline` 中导出。

浅色值在 :root，深色覆盖在 `[data-theme='dark']`；深色通过 global.css 的同名 custom variant 生效。两种主题共享语义，页面沿用 [ui.ts](../../web/src/stores/ui.ts) 的主题状态。色值与变量存在不构成对比度或视觉浏览器验收。

## 尺寸、排版与圆角

| 变量组                                                              | 当前值与映射                                                                  |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| space-1…8                                                           | 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48px                                         |
| font-display/h1/h2/h3/body/small/caption                            | 24 / 20 / 16 / 14 / 14 / 13 / 12px；line-height=1.5、line-height-heading=1.35 |
| font-sans / font-mono                                               | 系统中西文字体栈 / 系统等宽栈，完整列表以 tokens.css 为准                     |
| control-height / small / large                                      | 36 / 32 / 40px                                                                |
| table-row-height / object-row-height / header-height                | 44 / 60 / 52px                                                                |
| sider-width / sider-collapsed-width / inspector-width / page-gutter | 默认 80 / 64 / 344 / 24px，响应式覆盖见下                                     |
| radius-small/control/panel/overlay/pill                             | 4 / 6 / 10 / 12 / 999px；border-width=1px                                     |
| Tailwind radius-sm/md/lg/xl                                         | 分别映射 radius-small/control/panel/overlay                                   |
| shadow-low/raised/overlay                                           | 随明暗主题变化；shadow-sm/md 是 low/raised 的旧别名，elev-1/2/3 加上对应边框  |

空间、排版和 shell 尺寸使用这些 CSS 变量；不能把变量名直接当成已注册的 Tailwind utility。旧 r-sm/md/lg/xl/pill、radius-medium/large、shadow-sm/md 等仍指向同一语义值。

## 响应式与层级

Tailwind 的编译期 `@theme` 断点为 sm=48rem、md=64rem、lg=80rem；breakpoint-phone/tablet/desktop 是对应 CSS 别名。按默认 16px 根字号分别对应 768/1024/1280px。

| 源码条件                                          | 实际变化                                                                    |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| tokens.css：max-width:1279px                      | sider-width=72px、inspector-width=320px、page-gutter=20px                   |
| tokens.css：max-width:767px                       | page-gutter=16px                                                            |
| ui store、AdminLayout、AppSider：max-width:1023px | 导航进入窄屏遮罩抽屉模式；64px 折叠宽度 token 不代表 900px 必须显示固定窄栏 |

这些是已读取的断点声明，不表示所有页面都统一使用相同媒体查询；例如 QuickSearch 还有 max-width:1024px。页面视口行为以布局源码与实际验收为准。

| 层级变量                      | 值          |
| ----------------------------- | ----------- |
| z-sticky                      | 10          |
| z-nav-backdrop / z-navigation | 1000 / 1100 |
| z-dialog                      | 2200        |
| z-popover                     | 2300        |
| z-tooltip                     | 2400        |
| z-toast                       | 2500        |

Dialog/Sheet、Popover/菜单、Tooltip、Toast 使用对应层级变量；页面局部布局不应另造全局浮层层级。实际遮罩、滚动锁定和焦点仍须浏览器验证。

## 动效与维护

duration-fast/normal/graph 为 120/160/220ms，ease-out 为 cubic-bezier(0.22, 0.61, 0.36, 1)；dur-fast/base/graph 与 transition-base 是旧别名。global.css 的 prefers-reduced-motion 分支将动画/过渡时长压到 0.01ms，并改用 scroll-behavior:auto。

修改值同步 tokens.css，新增 Tailwind 语义同步 global.css；涉及主题、层级或导航断点时同步消费者与本页。此文档轮只核对源码和映射，未编译样式、运行浏览器或重新进行视觉验收。

## A方向应用壳补充

浅色页面背景 `#f6f8f6`、主操作 `#166b59`；深色页面背景 `#111c19`、主操作 `#84cdb0`。模块轨道使用独立 `rail-*` 语义（背景 `#142e29`），模块导航高度为40px。操作、校验状态、AI与图谱业务色仍分工使用，不用主色代替失败或未执行状态。数值来自当前源码，非对比度或全站视觉认证。
