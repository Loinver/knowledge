# 安装、部署与运行维护

核验日期：2026-11-26；适用 `9222236` 加当前未提交工作区。执行证据与未验证环境见[核验记录](../maintenance/verification-2026-11-26.md)。本文是现有代码的部署说明，不代表已经完成生产验收。

## 环境要求

| 项目         | 当前仓库要求                             | 依据                                                                                  |
| ------------ | ---------------------------------------- | ------------------------------------------------------------------------------------- |
| Node.js      | ≥22.18.0                                 | [package.json](../../package.json)                                                    |
| pnpm         | 11.7.0，使用仓库声明版本                 | [package.json](../../package.json)                                                    |
| Python       | ≥3.12；CI 使用 3.12，本轮本机为 3.13     | [pyproject.toml](../../server/pyproject.toml)、[CI](../../.github/workflows/lint.yml) |
| 开发元数据库 | SQLite，默认 `server/knowledge.db`       | [配置](../../server/app/core/config.py)、Makefile 工作目录                            |
| 生产元数据库 | PostgreSQL，额外安装 `production` 依赖组 | [生产配置校验](../../server/app/core/config.py)                                       |
| 浏览器回归   | Playwright Chromium                      | [测试配置](../../playwright.config.ts)                                                |

没有仓库自带的 Docker Compose、Kubernetes 或高可用部署包。不要把单端口启动命令当作高可用交付方案。

## 第一次本地启动

在仓库根目录执行以下步骤。安装依赖需要网络；Python 工具使用仓库虚拟环境。

```sh
make install
make seed-admin
make dev
```

`make seed-admin` 为**空账号库**创建首个管理员，默认用户名为 `admin`，不传密码时随机生成并仅在终端显示一次。保存该口令后登录，不存在通用默认密码。库内已有任意账号时脚本拒绝再次初始化，它不是密码重置工具。

开发页面为 `http://127.0.0.1:4010/`，API 为 `http://127.0.0.1:4000/api/v1`。Vite 代理 `/api` 到后端。公开注册默认关闭；后续账号由管理员在用户管理中创建。

需要指定管理员名时：

```sh
make seed-admin USERNAME=platform_admin EMAIL=platform_admin@example.org
```

这些邮箱是示例。避免把真实密码放进 shell 历史、README 或提交；优先使用初始化脚本随机生成的口令。

## 环境必须对应同一套数据

| 环境       | 页面/API             | 数据与账号                             | 用途                           |
| ---------- | -------------------- | -------------------------------------- | ------------------------------ |
| 默认开发   | 4010 / 4000          | 默认 `server/knowledge.db`，自行初始化 | 日常开发与手工操作             |
| 单端口启动 | 4000 / 4000          | 由相同后端配置决定                     | 检查构建产物、集成部署         |
| 默认 E2E   | 5199 / 8123          | 每轮临时元数据库、测试自建账号         | 回归测试，不复用开发服务       |
| 设计预览   | 由启动者指定临时端口 | 独立快照与独立账号                     | 查看设计，不能假设开发口令通用 |

历史记录中的 4156、8145 等预览地址仅属于相应本地会话。预览进程是否存在、数据是否保留都不构成长期运行保证。`web/prototypes/` 是隔离设计原型，不是正式业务入口。

配置从**进程当前工作目录**的 `.env` 和环境变量读取。`make dev`、`make start`、`make seed-admin` 的后端工作目录均为 `server/`；从根目录直接用 `--app-dir server` 启动时，不能假设它读取 `server/.env`。为隔离环境使用绝对 `KG_DATABASE_URL`，并在初始化、迁移和启动时保持一致。

## 单端口与生产准备

本地单端口检查可用：

```sh
make start
```

该命令构建前端并以 `0.0.0.0:4000` 启动，读取 `server/` 配置；它不会自动打开 production 配置。只需本机检查时，构建后从 `server/` 启动 `--host 127.0.0.1`。

生产环境需在完成目标数据库、网络与密钥准备后执行：

1. 在构建环境安装前端锁定依赖并运行 `pnpm -C web build`，保留 `web/dist` 与后端的相对布局。
2. 安装后端及 PostgreSQL 驱动：`server/.venv/bin/pip install -e './server[production]'`。
3. 由部署系统注入下列配置，或妥善保护 `server/.env`。值中的占位符必须替换，不提交真实凭据。

```dotenv
KG_ENVIRONMENT=production
KG_DATABASE_URL=postgresql+pg8000://<db_user>:<url_encoded_password>@<db_host>:5432/<db_name>
KG_CRYPTO_KEY=<独立生成并妥善保管的至少32字符密钥>
KG_CREATE_TABLES_ON_STARTUP=false
KG_ALLOW_PUBLIC_REGISTRATION=false
KG_EXPOSE_RESET_TOKEN=false
KG_TRUSTED_PROXY_COUNT=0
```

4. 先备份已有库，在 `server/` 运行 `.venv/bin/alembic upgrade head`。不要让自动建表替代迁移。
5. 新库执行管理员初始化，确认使用同一数据库配置。脚本内部仍会调用 `create_all`；先迁移，初始化只用于创建首个账号，不作为迁移替代方案。
6. 在 `server/` 启动 `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 4000`，由外部服务管理器管理进程；反向代理按实际拓扑配置 HTTPS 和转发。
7. 检查健康接口、登录、只读查询、受控样例运行与失败保护后再对用户开放。

当前启动代码在进程生命周期内管理知识库处理 worker。本文不推荐未经验证的多 worker 或多副本配置；分布式调度、目标 PostgreSQL 并发行为、容量和恢复时间需另行验收。

## 元数据库与源库不同

元数据库保存模型、账号、令牌摘要、运行和知识文档等平台数据；源库只用于读取业务数据。二者必须物理分离。

SQLite 源路径必须在**后端所在机器**可访问，并建议使用绝对路径。PostgreSQL 源连接器当前选择 `psycopg2`，MySQL 源连接器选择 `pymysql`；它们没有被当前默认依赖或 `production` 组完整声明。`production` 的 `pg8000` 只解决元数据库驱动，不代表 PostgreSQL 源已可用。实际对接前应单独完成驱动许可、安装、只读权限及连接验证，不能把额外驱动直接加入生产环境而跳过评估。

## 备份、升级与恢复

- 同时备份元数据库、用于解密连接和模型凭据的 `KG_CRYPTO_KEY`、部署配置及所需外部源数据。密钥与数据库分开安全保管；换密钥不会自动重加密已有数据。
- SQLite 开发快照建议先停写或使用数据库一致性备份机制，不把运行中随手复制文件当可靠备份。PostgreSQL 的备份恢复由目标环境工具完成并演练。
- 升级前记录代码提交、当前迁移版本和可恢复备份；停止写入和后台任务后迁移，再验证登录、配置解密、历史版本和主要业务链路。
- 数据库降级可能删除表和业务记录。应用回退不等于数据库可逆；恢复方案应以验证过的备份为准。
- 当前没有内置备份调度、历史知识索引清理、SLA 监控或自动灾备切换，不要按已有功能向客户承诺。

## 健康检查与停机

```sh
curl --noproxy '*' http://127.0.0.1:4000/api/v1/health
```

返回 `KG.OK` 和 `status=ok` 证明应用处理了请求，不代表外部数据源、模型服务或数据库恢复能力全部健康。健康响应版本来自 FastAPI `app.version`，当前为 `0.0.0`；包版本为 `0.1.0`，都不能单独作为已发布版本证据。交付时记录 Git 提交及部署配置。

通过启动终端 Ctrl+C 或服务管理器正常停止，给知识后台 worker 与数据库连接清理时间。不要用历史文档中的 PID 直接结束进程。
