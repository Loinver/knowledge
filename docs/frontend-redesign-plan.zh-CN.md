# 前端中后台界面设计计划

> 编制：2026-09-22 · 状态：待评审 · 范围：`web/` 前端整体改版
>
> 背景：当前前端只有一条平铺菜单加白底头部，没有登录注册和个人中心，观感偏简陋。本计划定义一次面向中后台标准的完整改版，覆盖注册登录、用户相关页面、布局骨架与视觉体系。后端目前没有用户与认证接口，账号体系的前后端契约在本文一并定义，供后端排期参照。

## 1. 目标与范围

**目标**：把前端升级为专业、紧凑、可扩展的中后台界面，新增账号体系与用户相关页面，同时保持现有 19 个业务路由与项目硬规则（i18n、错误码、四态校验、版本冻结）不被破坏。

**范围内**：

- 新增注册、登录、忘记密码、重置密码页面（未登录独立布局）。
- 顶栏新增用户区：用户菜单、个人中心、账号安全（改密）、退出登录。
- 新增系统管理菜单：用户管理、角色管理、操作日志（按角色控制可见性）。
- 布局骨架重构：可折叠侧栏 + 顶栏 + 面包屑 + 内容区 + 全局反馈。
- 设计令牌升级：补齐间距、排版、控件尺寸与暗色主题变量。
- Naive UI 主题定制：浅色/暗色两套 themeOverrides 与 tokens.css 对齐。
- 页面模板化：列表页、表单页、详情页三种母版，存量页面渐进迁移。

**范围外**：后端账号模块实现、数据表迁移脚本；demo 素材；存量业务功能逻辑重构。

## 2. 信息架构

### 2.1 路由总表

新增路由（现有 19 个业务路由全部保留）：

| 路由                 | 页面                               | 布局        | 访问     |
| -------------------- | ---------------------------------- | ----------- | -------- |
| `/login`             | 登录                               | AuthLayout  | 公开     |
| `/register`          | 注册                               | AuthLayout  | 公开     |
| `/forgot-password`   | 忘记密码                           | AuthLayout  | 公开     |
| `/reset-password`    | 重置密码（邮件链接进入，带 token） | AuthLayout  | 凭 token |
| `/account/profile`   | 个人中心                           | AdminLayout | 登录     |
| `/account/security`  | 账号安全（改密/会话）              | AdminLayout | 登录     |
| `/system/users`      | 用户管理                           | AdminLayout | 管理员   |
| `/system/roles`      | 角色管理                           | AdminLayout | 管理员   |
| `/system/audit-logs` | 操作日志                           | AdminLayout | 管理员   |

### 2.2 管理端布局

| 区域                         | 说明                                                                                                                              |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 侧栏（220px，可折叠至 64px） | 一级菜单：工作台、本体、数据源、抽取、图谱、治理、系统管理（仅管理员可见）；折叠时只留图标加 tooltip，折叠状态记忆到 localStorage |
| 顶栏（56px，sticky）         | 左：折叠按钮 + 面包屑；右：语言切换、暗色模式开关、用户菜单（头像 + 昵称下拉）                                                    |
| 内容区                       | 24px 内边距，页面标题、描述、主操作按钮采用统一版式                                                                               |
| 全局反馈                     | 请求错误统一 message 并翻译错误码；危险操作统一 Modal 二次确认                                                                    |

菜单 key 与现有路由映射保留，新增 `system` 分组，子项为用户管理、角色管理、操作日志。

## 3. 账号体系前后端契约

后端目前无用户模块。以下为前端依赖的接口与状态约定，全部遵循现有 API 契约规范：只返回错误码加结构化参数，不返回中文句子；状态一律传枚举码。

### 3.1 数据模型

| 字段            | 类型                               | 说明                           |
| --------------- | ---------------------------------- | ------------------------------ |
| `id`            | UUID                               | 主键                           |
| `username`      | string                             | 唯一，3 到 32 位字母数字下划线 |
| `email`         | string                             | 唯一，用于登录与找回密码       |
| `password_hash` | string                             | 哈希存储，永不下发             |
| `role`          | 枚举 `ADMIN` / `EDITOR` / `VIEWER` | 单角色起步，后续可扩多角色     |
| `status`        | 枚举 `ACTIVE` / `DISABLED`         | 禁用账号登录被拒               |
| `last_login_at` | datetime                           | 个人中心展示                   |

后端落地情况：表结构见 `server/app/models/account.py` 与迁移 `0007_accounts`，
口令用 PBKDF2-HMAC-SHA256 派生、令牌只存摘要，方案理由见
[docs/adr/0002-account-auth.md](./adr/0002-account-auth.md)。首个管理员用
`make seed-admin` 创建，公开注册默认关闭。

### 3.2 接口清单

后端已按本表实现（见第 8 节 M2 后端进度），路径前缀均为 `/api/v1`：

| 方法      | 路径                    | 说明                       | 前端使用处                |
| --------- | ----------------------- | -------------------------- | ------------------------- |
| GET       | `/auth/config`          | 是否开放注册、口令长度下限 | 登录页、注册页            |
| POST      | `/auth/register`        | 注册，成功即建立会话       | 注册页（默认关闭）        |
| POST      | `/auth/login`           | 登录，返回双 token         | 登录页                    |
| POST      | `/auth/refresh`         | 刷新 access token（轮转）  | axios 拦截器 401 自动续期 |
| POST      | `/auth/logout`          | 服务端吊销本次会话令牌     | 退出登录                  |
| POST      | `/auth/forgot-password` | 申请重置（开发态回传令牌） | 忘记密码页                |
| POST      | `/auth/reset-password`  | 凭邮件 token 重置密码      | 重置密码页                |
| GET       | `/auth/me`              | 当前用户信息               | 布局用户区、路由守卫      |
| GET/PATCH | `/users/me/profile`     | 读取或更新昵称、头像       | 个人中心                  |
| PUT       | `/users/me/password`    | 修改密码，需旧密码         | 账号安全                  |
| GET       | `/users`                | 用户列表，分页与搜索       | 用户管理                  |
| POST      | `/users`                | 管理员建号                 | 用户管理                  |
| PATCH     | `/users/{id}`           | 修改角色或状态             | 用户管理                  |
| GET       | `/roles`                | 角色与成员数               | 角色管理                  |
| GET       | `/audit-logs`           | 全局操作日志，分页与筛选   | 操作日志                  |

契约细节与后端一致的两处调整：

- `GET /roles` 只返回 `{ code, member_count }`。角色名与说明是界面文案，按硬规则由前端
  `i18n` 渲染（`role.ADMIN.name` 等），后端不下发中文——原 mock 里的 `name_i18n`
  不再使用。
- 列表项字段：`AuditLog.id` 是整数、`ip` 可为 `null`；`AuditAction` 全集为
  `LOGIN` / `LOGOUT` / `REGISTER` / `PASSWORD_CHANGED` / `RESET_REQUESTED` /
  `PASSWORD_RESET` / `PROFILE_UPDATED` / `ROLE_CHANGED` / `STATUS_CHANGED`。

### 3.3 Token 与请求约定

- 登录、注册、刷新返回 `access_token`、`refresh_token` 与过期秒数；前端将两个 token 存 localStorage，key 区分。
- axios 请求拦截器附加 `Authorization: Bearer` 头；响应拦截器遇 401 且未重试过时先调 refresh，成功后重放原请求，失败则清 token 并跳 `/login?redirect=...`。
- 登出请求需带 `refresh_token`，否则服务端只能吊销访问令牌，刷新令牌仍可用。
- 路由守卫：未登录访问受保护路由时跳登录并记录 redirect；已登录访问 `/login` 时跳工作台。
- 错误码新增 `AUTH` 命名空间（`app/core/error_codes.py` 与两份语言包 key 集合一致）：
  `AUTH.INVALID_CREDENTIALS`、`AUTH.EMAIL_TAKEN`、`AUTH.USERNAME_TAKEN`、
  `AUTH.TOKEN_EXPIRED`、`AUTH.FORBIDDEN`、`AUTH.USER_DISABLED`、`AUTH.WEAK_PASSWORD`、
  `AUTH.OLD_PASSWORD_INVALID`、`AUTH.REGISTRATION_CLOSED`、`AUTH.RESET_TOKEN_INVALID`。
- 语义细节：登录被拒且账号已禁用时是 `AUTH.USER_DISABLED`（403）；**登录后被禁用**的会话
  因令牌被吊销而表现为 `AUTH.TOKEN_EXPIRED`（401），前端按「登录过期」处理即可。
- 账号策略：公开注册默认关闭，首个管理员由 `make seed-admin` 创建，其余账号由管理员
  在用户管理页创建。前端需按 `/auth/config` 的 `registration_enabled` 决定是否展示注册入口。
- 忘记密码：邮箱不存在也返回 200（`reset_token` 为 `null`），避免账号枚举。开发态
  （`KG_EXPOSE_RESET_TOKEN=1`）响应会带 `reset_token`，重置密码页可直接用它联调。

## 4. 视觉设计系统

### 4.1 设计语言定位

按 ui-ux-pro-max 技能库对内部数据/治理平台的匹配结果，产品方向为深色科技底色加状态语义色。落到本项目时收敛为克制的中后台风格，不做玻璃拟态等强装饰效果：

- 主色维持现有 `--pri: #315ee7`，存量页面已大量引用且对比度达标，改动成本最低。
- 暗色模式采用技能库返回的深蓝灰体系：`#0F172A` 页面底、`#1B2336` 卡片、`#94A3B8` 次级文字、`#475569` 边框，主色在暗色底上按对比度微调。
- 语义色沿用现有 success、warning、danger，暗色下由 Naive UI 暗色主题适配。
- 排版：界面用系统字体栈，正文 14px、行高 1.6，表格等数据密度场景 13px；ID、时间戳、枚举码用等宽字体。
- 禁止表情符号当图标，统一 SVG 线性图标；hover 过渡 150 到 300ms，焦点环可见。

### 4.2 设计令牌扩展

现有 `web/src/styles/tokens.css` 只有颜色和少量圆角阴影，扩展为完整体系；浅色变量保持现名不变，暗色新增 `-dark` 后缀变量：

```css
:root {
  /* 间距（4px 基准） */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  /* 排版 */
  --font-body: 14px;
  --font-small: 13px;
  --font-caption: 12px;
  --line-height: 1.6;
  /* 控件 */
  --control-height: 34px;
  /* 暗色 */
  --bg-dark: #0f172a;
  --bg-dark-card: #1b2336;
  --text-dark-primary: #f8fafc;
  --text-dark-secondary: #94a3b8;
  --border-dark: #475569;
}
```

### 4.3 Naive UI 主题定制

- `themeOverrides` 从 App.vue 内联对象提取到 `web/src/theme/naive.ts`，导出浅色与暗色两套。
- 组件 `borderRadius` 从 4px 放宽到 6px，观感更柔和。
- 暗色通过 `NConfigProvider` 的 `theme` 属性切换 `darkTheme`，`common` 变量与 tokens.css 暗色值对齐。

## 5. 布局骨架与页面模板

### 5.1 组件结构

```
web/src/layout/
  AdminLayout.vue        # 侧栏 + 顶栏 + 内容区（RouterView）
  AuthLayout.vue         # 居中卡片式，登录注册等共用
  components/
    AppSider.vue         # logo + 菜单 + 折叠
    AppHeader.vue        # 折叠按钮 + 面包屑 + 语言/主题/用户菜单
    UserDropdown.vue     # 头像 + 下拉
web/src/theme/naive.ts   # 浅/暗两套 themeOverrides
web/src/stores/auth.ts   # token、用户信息、登录态
web/src/stores/ui.ts     # 侧栏折叠、暗色开关（localStorage 持久化）
web/src/views/auth/      # Login / Register / ForgotPassword / ResetPassword
web/src/views/account/   # Profile / Security
web/src/views/system/    # Users / Roles / AuditLogs
```

App.vue 现有内联布局代码全部拆入 AdminLayout，App.vue 只保留 NConfigProvider 与路由出口。

### 5.2 页面模板

三种母版，新建页面必须套用，存量页面迁移时套用：

| 模板   | 结构                                                            | 适用                             |
| ------ | --------------------------------------------------------------- | -------------------------------- |
| 列表页 | 页头（标题、描述、主操作）到筛选区到表格到分页                  | 实体类型库、用户管理、操作日志等 |
| 表单页 | 分组卡片、字段说明、blur 内联校验、提交 loading、成功或失败反馈 | 注册、映射向导、个人中心资料     |
| 详情页 | 页头（标题、状态标签、主操作）到描述列表到相关模块 tab          | 实体详情、用户详情               |

存量 19 个业务路由的迁移策略：布局骨架与设计令牌先全量生效，页面内部按模板在后续迭代逐页迁移，不做一次性重写。

### 5.3 关键交互规则

- **登录注册（AuthLayout）**：居中卡片约 400px 宽，顶部 logo 与产品名；字段有可见 label，blur 时内联校验，提交按钮 loading 态；登录页底部提供忘记密码与注册入口；注册成功直接进入工作台；表单支持 Enter 提交，焦点环可见。
- **用户菜单**：无头像时用昵称首字符生成头像；下拉项为个人中心、账号安全、退出登录；退出需确认。
- **系统管理**：路由守卫按 `role === 'ADMIN'` 控制菜单可见性与访问，非管理员访问返回 403 页，复用 NotFound 风格。
- **暗色模式**：开关在顶栏，选择持久化；Naive UI 暗色主题与 tokens.css 暗色变量联动。
- **响应式**：不小于 1024px 双栏；小于 768px 时侧栏改为抽屉模式，表格允许容器内横向滚动，页面本身不出现横向滚动条。

### 5.4 无障碍与可用性基线

技能库 ux 域规则摘要，作为页面验收基线：

- 表单：label 关联输入框，错误信息靠近字段，blur 校验，提交必须有 loading 到成功或失败的反馈，不允许点击后无响应。
- 导航：固定顶栏不遮挡内容；键盘 tab 顺序与视觉顺序一致，无键盘陷阱；图标按钮必须有 aria-label。
- 性能：大表格与图谱列表虚拟滚动；占位固定高度避免布局跳动，CLS 小于 0.1。
- 动效：统一 150 到 300ms；`prefers-reduced-motion` 下禁用装饰性动效。

## 6. 实施里程碑

### M1：布局骨架 + 账号前端（无后端依赖，可立即开工）

- 产出：AdminLayout、AuthLayout、侧栏、顶栏、用户菜单、主题开关；tokens.css 扩展；Naive 浅暗双主题；路由守卫（接口未上线前按 token 存在性判断登录态）；auth store 与 ui store；登录、注册、忘记密码、重置密码四页（mock 提交）；个人中心与账号安全页（mock 数据）；系统管理三页（空态与骨架屏）。
- i18n：所有新增文案进 `zh-CN.json` 与 `en-US.json`，key 集合一致，`@intlify/vue-i18n/no-raw-text` 通过。
- 验收：未登录访问受保护路由跳 `/login?redirect=...`，登录成功回跳；侧栏折叠、暗色、语言偏好 localStorage 持久化；`make lint` 的 web 部分（vue-tsc 与 ESLint）通过。

### M2：对接真实后端（后端已就绪）

- 前置：后端账号模块已交付（见第 8 节），接口契约以第 3 节为准。
- 产出：登录注册忘记重置接真实接口；axios 拦截器 401 续期、失败清 token 跳登录；个人中心读写真实 profile；系统管理三页接真实接口，非管理员 403。
- 验收：注册、登录、刷新页面保持登录态、token 过期自动续期、退出清 token 全链路走通；错误码双语翻译正确。

### M3：存量页面按模板渐进迁移

19 个业务页面按三种母版逐页迁移，与账号体系解耦，不阻塞 M1、M2，每页迁移保持功能与 i18n 不回退。

## 7. 风险与开放问题

1. ~~**后端账号模块未排期**~~：后端账号模块已交付（第 8 节 M2），前端 `api/auth.ts`
   的 mock 分支已随 M2 一并删除，`VITE_AUTH_MODE` 开关与 `env.d.ts` 中的类型声明同步移除；
   接口类型单一真值源为后端 OpenAPI 生成的 `api/schema.d.ts`。
2. **邮件服务依赖**：忘记与重置密码依赖邮件发送。当前开发态由 `KG_EXPOSE_RESET_TOKEN`
   直接把令牌回传，生产接入邮件服务时改为发信并置 `KG_EXPOSE_RESET_TOKEN=0`，
   前端页面与校验逻辑不受影响。
3. **角色模型单角色起步**：路由守卫按 `ADMIN` 单角色判断，多角色与细粒度权限后续扩展，不影响前端结构。
4. **暗色模式与存量页面内联样式**：部分存量页面内联样式引用浅色变量，暗色下可能出现对比度问题，在 M3 逐页迁移时修复，不阻塞骨架上线。

---

## 8. 实施进度

### M1 已完成（2026-09-22）

| 项             | 落地                                                                                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 设计令牌       | `styles/tokens.css` 补齐间距、排版、控件尺寸与暗色变量；浅色变量名保持不变                                                                                                           |
| Naive 主题     | 提取到 `theme/naive.ts`，浅/暗两套 themeOverrides，`borderRadius` 统一 6px，与 tokens 对齐                                                                                           |
| 布局骨架       | `layout/AdminLayout.vue`（侧栏 220/64 可折叠 + 顶栏 + 内容区）、`layout/AuthLayout.vue`、`AppSider` / `AppHeader` / `UserDropdown`                                                   |
| 导航单一真值源 | `layout/useNavigation.ts`：菜单项 key 就是路由名，高亮与面包屑都从 `route.name` 派生，去掉旧的 key → path 硬编码映射                                                                 |
| 全局反馈       | `App.vue` 挂载 Message / Dialog / Notification / LoadingBar provider                                                                                                                 |
| 账号前端       | `api/auth.ts`（`VITE_AUTH_MODE` 切 mock 与 real）、`stores/auth.ts`、`stores/ui.ts`、`api/tokens.ts`、axios Bearer 注入与 401 续期                                                   |
| 新增页面       | 登录 / 注册 / 忘记密码 / 重置密码、个人中心 / 账号安全、用户管理 / 角色管理 / 操作日志、403 页                                                                                       |
| 路由与守卫     | 19 个业务路由全部保留并挂到 AdminLayout；非首屏页面全部懒加载（主 chunk 1.13 MB → 650 kB，按路由分包）；未登录跳 `/login?redirect=...`，非管理员访问 `adminOnly` 路由跳 `/forbidden` |
| 认证失效协作   | `api/client.ts` 只暴露 `registerUnauthorizedHandler`，401 后的跳转由 `main.ts` 启动处注册，客户端不依赖路由与页面（遵循应用架构约定第 3 节）                                         |
| 文案           | 新增 110 个 key，中英 key 集合一致（441 / 441）                                                                                                                                      |

浏览器实测结论：未登录访问 `/system/users` → `/login?redirect=/system/users`；登录后回跳；注册进入工作台；折叠状态、暗色、语言均写入 localStorage 并在刷新后恢复；非管理员访问系统管理跳 403 且侧栏不显示「系统管理」；切语言时 `<html lang>` 同步更新。

顺带修复的既有缺陷：

- `App.vue` 此前没有挂载任何反馈 provider，而 6 个页面调用 `useMessage()`，naive-ui 在无 provider 时直接抛错——这些页面运行时不工作。
- `EntityTypes.vue` 用 `window.location.hash` 跳详情，绕过路由，已改为 `router.push`。
- 页面各自带 `padding: 24px` 与内容区叠加成 48px，现在留白统一由 AdminLayout 提供。

尚未在 M1 范围内：主 chunk 分包后仍为 650 kB（Naive UI 与 Vue 核心），后续可按需再做 manualChunks 与组件级按需引入。M1 当时 `make lint` 的 Prettier 检查另有 5 个既有文件不合规（`api/dashboard.ts`、`api/validation.ts`、`components/GraphCanvas.vue`、`components/graphLayout.ts`、`stores/locale.ts`），属存量问题未混入本批；这批存量已在 M2 批次统一整理，见下。

另有两处已知待办，属约定要求但可放到 M3 逐页迁移时处理：现存 `views/*.vue` 仍是平铺目录，未按 `views/<area>/` 归置；新页面用手写 load 而非复用 `useAsyncData`，筛选切换时不做旧请求取消。

### M2 已完成（2026-09-22）

后端账号模块与前端对接同批交付。契约见第 3 节，技术决策与代价见 [`docs/adr/0002-account-auth.md`](./adr/0002-account-auth.md)。

后端（`server/`）：

| 项         | 落地                                                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 配置       | `core/config.py` 新增 `allow_public_registration`（默认关闭）、`expose_reset_token`（默认开启）、access / refresh / reset 三个 TTL、`password_iterations` |
| 错误码     | `core/error_codes.py` 新增 `AUTH.*` 命名空间共 10 个码并登记 HTTP 状态映射；`core/errors.py` 补 401 / 403 兜底码                                          |
| 口令       | PBKDF2-HMAC-SHA256，存储格式 `pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>`，比对走 `hmac.compare_digest`                                           |
| 令牌       | 不透明随机串（`secrets.token_urlsafe(32)`），库中只存 sha256 摘要；刷新即轮转，登出即时吊销，无需签名密钥                                                 |
| 领域服务   | `domain/account_service.py` 覆盖注册 / 登录 / 刷新 / 登出 / 忘记重置 / 资料 / 改密 / 用户管理 / 角色 / 审计，不导入 FastAPI、不自行 commit                |
| 路由与依赖 | `api/v1/auth.py`、`api/v1/accounts.py`、`api/v1/deps.py`，共 14 条路径挂在 `/api/v1`                                                                      |
| 种子脚本   | `scripts/seed_admin.py` + `make seed-admin`；库里已有账号即拒绝执行，避免成为提权入口                                                                     |
| 迁移       | `0007_accounts.py`，升降级与重放均有断言                                                                                                                  |
| 测试       | `tests/test_account.py` 29 项                                                                                                                             |

前端（`web/`）：

| 项             | 落地                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 类型单一真值源 | `api/schema.d.ts` 由后端 OpenAPI 重新生成；`api/auth.ts` 删除全部 mock 分支，类型一律取自 `components['schemas']`         |
| 认证四页       | 登录 / 注册 / 忘记密码 / 重置密码接真实接口；注册入口按 `GET /auth/config` 的 `registration_enabled` 决定是否展示         |
| 开发态重置     | 忘记密码拿到 `reset_token` 后直接跳重置页（`KG_EXPOSE_RESET_TOKEN` 开启时），与第 7 节风险 2 的约定一致                   |
| 系统管理三页   | 用户管理（新增建号入口，自己不可编辑）、角色管理（按 `code` 走 i18n）、操作日志（搜索 + 动作筛选）接真实接口              |
| 个人中心       | 资料更新用 `null` 表示清空，与后端 `exclude_unset` 语义对齐；改密后保留当前会话、吊销其他会话                             |
| 文案           | 中英 key 集合一致（455 / 455），补齐 `errors.AUTH.*`、`auth.registrationClosed`、`account.roleDescriptions.*`、`system.*` |

验证结果（2026-09-22）：

- `make lint` 全绿（仓库规范入口）：`pnpm run lint:web`（ESLint）与 `pnpm -C web typecheck`（vue-tsc）均无输出即通过；`pnpm run format:check` 报 `All matched files use Prettier code style!`；`make lint-server` 报 Ruff `All checks passed`、`111 files already formatted`、Mypy `no issues found in 83 source files`。
- `node scripts/check-i18n-keys.mjs` 报 455 / 455。
- `pytest tests/test_account.py` 29 passed；后端全量用例收集 345 项，除 30 项既有 `test_m4_rules.py`（`HEAD` 基线同样失败，本机 SHACL 相关）外全部通过。
- 进程内核对 OpenAPI：账号相关路径 14 条；`UserOut`、`TokenPair`、`AuthConfigOut`、`RoleOut`、`AuditLogOut`、`UserPage`、`AuditLogPage`、`ForgotPasswordResult`、`UserCreate`、`UserPatch`、`ProfileUpdate`、`PasswordChange` 全部存在。

顺带整理的存量问题：全仓 `make lint` 曾有 11 个既有 Prettier 不合规文件（8 个前端图谱 / 工作台组件与测试、3 个 `.github` 模板），本批统一整理，改动均为空白与折行，无逻辑变更。锁文件不进 Prettier：`pnpm-lock.yaml` 已按原先 `package-lock.json` 的同一约定加入 `.prettierignore`（仓库随后迁移到 pnpm，见 `ff74e5b`）。另把 `prettier --write` 串进 `web/package.json` 的 `gen:api`——`openapi-typescript` 默认输出 4 空格缩进，与仓库 `tabWidth: 2` 不符，不串这一步每次重新生成都会再次引入格式漂移。

尚未完成：浏览器端到端实测（登录、刷新保持登录态、401 自动续期、退出清 token、个人中心读写、系统管理三页、非管理员 403）未执行。前置条件是先跑 `make seed-admin` 建出首个管理员——公开注册默认关闭，库里为空时无法登录。
