# 配置说明

核验日期：2026-11-26。配置源为 [Settings](../../server/app/core/config.py)、[Vite](../../web/vite.config.ts) 和[应用启动入口](../../server/app/main.py)。环境变量优先于当前工作目录的 `.env`。下表描述当前代码，不是推荐所有部署使用默认值。

## 服务与数据库

| 配置                           | 默认                       | 作用与使用约束                                                      |
| ------------------------------ | -------------------------- | ------------------------------------------------------------------- |
| `KG_ENVIRONMENT`               | `development`              | production 会检查数据库、密钥、自动建表与重置令牌暴露               |
| `KG_DATABASE_URL`              | `sqlite:///./knowledge.db` | 相对进程工作目录；隔离环境用绝对地址；生产需 PostgreSQL             |
| `KG_CRYPTO_KEY`                | 固定开发值                 | 生产必须换成独立且至少32字符值；用于连接/模型凭据解密，必须稳定保存 |
| `KG_CREATE_TABLES_ON_STARTUP`  | `true`                     | 开发自动建表；生产必须 false，并使用 Alembic                        |
| `KG_KNOWLEDGE_WORKERS_ENABLED` | `true`                     | 是否启动知识库后台处理；关闭会使新任务不能自动完成                  |
| `KG_TRUSTED_PROXY_COUNT`       | `0`                        | 直连忽略 X-Forwarded-For；只有真实可信反向代理拓扑才设置层数        |
| `KG_API_PROXY_TARGET`          | `http://127.0.0.1:4000`    | Vite 开发代理变量，非后端 Settings 字段；独立预览指向对应 API       |

`KG_API_PREFIX`、`KG_LOG_LEVEL` 虽可被 Settings 解析，当前路由注册常量仍为 `/api/v1`，Uvicorn 日志级别也需核对启动参数。不要仅修改这些字段就宣称 API 前缀或服务日志已变更。

## 账号与会话

| 配置                                | 默认      | 意义                                                 |
| ----------------------------------- | --------- | ---------------------------------------------------- |
| `KG_ALLOW_PUBLIC_REGISTRATION`      | `false`   | 关闭公开注册，后续账号由管理员发放                   |
| `KG_EXPOSE_RESET_TOKEN`             | `false`   | 本地联调开关；生产禁止 true，不等于邮件服务          |
| `KG_ACCESS_TOKEN_TTL_SECONDS`       | `3600`    | 访问令牌有效期                                       |
| `KG_REFRESH_TOKEN_TTL_SECONDS`      | `1209600` | 刷新令牌有效期，默认14天                             |
| `KG_RESET_TOKEN_TTL_SECONDS`        | `3600`    | 一次性重置令牌有效期                                 |
| `KG_PASSWORD_ITERATIONS`            | `260000`  | 口令派生迭代；测试低值只用于隔离夹具，不能照抄到部署 |
| `KG_LOGIN_FAILURE_WINDOW_SECONDS`   | `900`     | 登录失败统计窗口                                     |
| `KG_LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5`       | 同账号与来源组合在窗口内的失败阈值                   |
| `KG_LOGIN_MAX_FAILURES_PER_IP`      | `30`      | 同来源窗口内失败总阈值                               |

修改环境后需要重启使用该配置的进程。数据库只保存口令派生值，不能从库中读出管理员原密码；初始化脚本不是重置工具。

## 模型配置

运行时模型在「系统管理 → AI 模型」维护，CHAT 与 EMBEDDING 分别显式选择可用默认配置。保存模型或切换默认不会主动调用外部服务。真实调用会向所配置服务发送该操作所需内容，实施时需确认网络、数据处理范围和服务授权。

`KG_LLM_BASE_URL`、`KG_LLM_API_KEY`、`KG_LLM_MODEL`、`KG_LLM_TIMEOUT_SECONDS` 以及 `KG_EMBEDDING_BASE_URL`、`KG_EMBEDDING_API_KEY`、`KG_EMBEDDING_MODEL`、`KG_EMBEDDING_VERSION`、`KG_EMBEDDING_TIMEOUT_SECONDS` 是保留解析的旧字段，不能用它们代替管理界面的模型配置。迁移时不要把密钥复制进文档。

API Key 后端加密保存，界面只表示是否存在。更换服务 origin 时需明确替换或清除密钥；更换向量模型或版本后需检查向量过期并重处理文档。操作步骤见[知识库与系统指南](../user-guide/knowledge-system.md)。

## 固定限制与配置的区别

知识文档额度、解析格式、SQL 连接与查询超时、图谱展示边界由各模块代码定义，并非都暴露为环境变量。限制清单见[产品限制](../product/limitations.md)与模块功能台账；新增配置必须同步这里、部署指南和相关操作说明。
