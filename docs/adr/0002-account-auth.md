# ADR 0002 · 账号体系与认证方案

- 状态：已接受
- 日期：2026-09-22
- 相关：`server/app/models/account.py`、`server/app/domain/account_service.py`、`docs/frontend-redesign-plan.zh-CN.md` 第 3 节

## 背景

平台此前没有用户概念：所有接口匿名可写。前端改版要加注册登录、个人中心与系统管理，
需要一套能自托管的账号体系，并且不能为此引入难以审计的重依赖。

约束来自项目既有约定：后端只返回错误码与枚举码、不返回中文句子；状态一律传枚举码；
依赖许可只允许 MIT / BSD / Apache-2.0 / PSF；Python 侧此前踩过「3.13 装 cryptography
需要 sdist 构建」的坑，新依赖必须确认 wheel 可用。

## 决策

### 1. 会话令牌用不透明随机串，不用 JWT

令牌是 32 字节 `secrets.token_urlsafe` 随机串，库里只存 sha256 摘要（`auth_token.token_hash`）。

- **登出可以真吊销**：JWT 在有效期内无法作废，除非再维护一张黑名单——那就等于又回到服务端存储，
  白白多背一套签名与密钥轮换逻辑。
- **刷新可以轮转**：每次刷新旧刷新令牌立即失效，令牌泄露的窗口被压缩到一次使用。
- **不需要签名密钥**：少一个必须妥善保管、定期轮换、配置错了就静默失效的秘密。
- 代价：每个请求多一次索引查询。当前规模下可忽略。

访问令牌 1 小时、刷新令牌 14 天、重置令牌 1 小时（`KG_*_TOKEN_TTL_SECONDS` 可调）。

### 2. 口令用 PBKDF2-HMAC-SHA256（标准库）

格式 `pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>`，每次独立 16 字节随机盐，
默认 260,000 次迭代，校验走 `hmac.compare_digest`。

放弃 bcrypt / argon2-cffi：两者都要新依赖，argon2 在部分平台仍可能落到源码构建，
而本项目已经因为 `cryptography` 的构建问题推迟过一次依赖引入。PBKDF2 是标准库能力，
可审计、可迁移，强度对自托管中后台足够。迭代次数做成配置项，测试里降到 1000 以免拖慢用例。

### 3. 公开注册默认关闭，首个管理员由脚本创建

- `KG_ALLOW_PUBLIC_REGISTRATION` 默认 `false`；关闭时 `POST /auth/register` 返回
  `AUTH.REGISTRATION_CLOSED`（403）。前端通过 `GET /auth/config` 决定是否展示注册入口。
- 新部署先跑 `make seed-admin` 建首个管理员；账号后续由管理员在用户管理里创建
  （`POST /users`）。
- `bootstrap_admin` 在库中已有账号时**拒绝执行**——否则这个脚本就是一个跑一次就能提权的后门。

理由：这是企业内部数据治理平台，账号应当由管理员发放而不是自助注册。默认关闭意味着
「忘记配开关」的结果是安全的一侧，而不是开放注册。

### 4. 重置口令：没有邮件服务时不假装能找回

> 2026-09-24 修订：原方案让 `KG_EXPOSE_RESET_TOKEN` 默认为 `true`，未显式关闭的部署里，
> 任何知道管理员邮箱的人都能拿到重置令牌并接管账号。现改为默认关闭，并在生产环境强制关闭。

- `KG_EXPOSE_RESET_TOKEN` 默认 `false`。开启时 `POST /auth/forgot-password` 把重置令牌直接放在
  响应里，只用于本地联调与端到端测试；`KG_ENVIRONMENT=production` 下开启会拒绝启动。
- 关闭时该接口对任何邮箱都返回 `AUTH.RESET_UNAVAILABLE`（503），不生成令牌，也不区分邮箱是否
  存在；`GET /auth/config` 下发 `password_reset_enabled`，找回页据此提示联系管理员，而不是谎称
  「邮件已发出」。
- 恢复途径改为管理员签发：`POST /users/{id}/password-reset`（仅管理员，不能对自己使用）返回
  一次性令牌，由管理员线下转交；复用同一张重置令牌表，签发与使用都记审计。接入邮件服务后，
  再由后端发信替代线下转交。

### 4.1 登录失败限流

按审计表中的 `LOGIN/FAILED` 记录计数，不新增表，多进程部署共享同一份计数：

- 窗口 `KG_LOGIN_FAILURE_WINDOW_SECONDS`（默认 900 秒）内，同一账号在同一来源失败
  `KG_LOGIN_MAX_FAILURES_PER_ACCOUNT`（默认 5）次，或同一来源失败 `KG_LOGIN_MAX_FAILURES_PER_IP`
  （默认 30）次，即返回 `AUTH.TOO_MANY_ATTEMPTS`（429）。被拦下的请求不校验口令，也不追加失败记录。
- 不单独按账号锁定：那样任何人都能反复输错，把指定用户锁在门外。代价是分散在大量来源地址上的
  慢速猜测只受单来源上限约束，需要时由网关或 WAF 补充。
- 来源地址只在 `KG_TRUSTED_PROXY_COUNT` 大于 0 时才读 `X-Forwarded-For`（取倒数第 N 段）；
  直连部署读这个头等于让客户端自报地址，限流与审计都会失效。

### 4.2 生产环境配置与驱动

生产元数据库使用 PostgreSQL。在 `server/` 运行 `.venv/bin/pip install -e '.[production]'`
安装 BSD-3-Clause 许可的 `pg8000` 驱动，连接地址使用 `postgresql+pg8000://` 前缀。
`cryptography` 使用 Apache-2.0 或 BSD-3-Clause 双许可。

设置 `KG_ENVIRONMENT=production`、`KG_DATABASE_URL`、独立的 `KG_CRYPTO_KEY`（至少 32 字符）、
`KG_CREATE_TABLES_ON_STARTUP=false` 与 `KG_EXPOSE_RESET_TOKEN=false`；密钥通过部署环境注入。
启动前需在备份后执行 Alembic 迁移，应用不会自动迁移生产库。安装驱动与配置加载检查不等同于
真实 PostgreSQL 连接、迁移或生产部署验收。

### 5. 角色是单角色枚举，权限判断留在后端

`ADMIN` / `EDITOR` / `VIEWER` 三档单角色。角色名与说明**不由后端下发**：
`GET /roles` 只返回 `{ code, member_count }`，文案由前端按 `code` 走 i18n——
这是「后端不返回中文句子」在账号模块的落地。

细粒度权限基线（M-11）留到后续里程碑，届时扩成多角色或权限点，不影响当前结构。

## 代价与已知边界

- **用户名与邮箱的唯一性按大小写不敏感判定**（查询用 `func.lower`），但数据库唯一索引是
  大小写敏感的。理论上并发注册 `Admin` 与 `admin` 可能都成功。当前由管理员建号，
  并发窗口极小；后续如需彻底闭合，应加 `lower(username)` 唯一索引。
- **管理员不能把自己降级或禁用**（`AUTH.FORBIDDEN`）。防的是最后一个管理员自锁后
  再无界面入口可恢复。副作用是「移交管理员」必须由另一个管理员操作。
- **禁用账号即吊销其全部令牌**，在线会话立刻作废：此时请求得到 `AUTH.TOKEN_EXPIRED`（401），
  重新登录才给出 `AUTH.USER_DISABLED`（403）的具体原因。
- **开发态元数据库不入库**：`knowledge.db` 含口令哈希与审计记录，已在 `.gitignore` 排除。
- 缺少的能力（不在本次范围）：验证码、会话列表与「登出其他设备」、
  邮件服务实现、多角色与权限点。
