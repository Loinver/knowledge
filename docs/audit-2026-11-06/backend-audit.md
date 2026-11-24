# 后端只读审计第一版 — 2026-11-06

## 结论与边界

独立读取当前代码并完成隔离反例：**8 项可执行问题，6 项 P1、2 项 P2**。以下编号供主代理顺序修复；B04 与产品审计 R01 是同一问题，请合并去重。

- 基线 HEAD：`3e729e4213db3cd61a2430aa49962f226e65f312`；开始时工作区干净。
- 已读根 `AGENTS.md`、`.agents/AGENTS.md`，以及架构、API、测试、安全约束。旧记忆只用于定位规则，没有用旧审计结论作证据。
- 本次没有修改业务文件，没有连接真实库或外部服务。仅写本目录报告、复现脚本与日志。收尾时 HEAD 不变，出现其他任务生成的未跟踪目录 `docs/audit-2026-11-06/`，未触碰。
- 用户提供的既有基线：lint/契约/i18n 通过、90 前端与 715 后端测试通过、3 个 API 预置的 E2E 通过；本次未重跑，也不将其称为完整 UI 验收。
- 本次验证：`repro_backend_audit.py`，**11 passed in 1.94s**。这些断言故意确认当前错误行为，PASS 表示缺陷被复现，不表示产品验收通过。日志：`backend-repro.log`。
- 数据均在临时内存 SQLite 中，启用外键；源读取替换为独立内存源库；调度线程禁用。并发问题使用两个 Session 的确定性事务交错，不是 PostgreSQL 多进程压力验证。无后台测试仍在运行。

## 已证实问题

### B01 [P1] 刷新令牌没有原子消费，同一旧令牌可生成两个有效后继会话

- 位置：[account_service.py:475](/Users/linyer/Public/Private/knowledge/server/app/domain/account_service.py:475)，重点 477–484；有效性读取在 157–168；HTTP 提交边界在 `server/app/api/v1/auth.py` 的 `refresh`。
- 触发：两个刷新请求在任一提交前，都完成旧刷新令牌有效性检查。
- 证据：`test_refresh_token_consumed_twice` 中两个独立 Session 调用真实 `refresh_session`，随后依次提交，得到不同的后继刷新令牌；两个访问令牌都能通过真实 `resolve_session`。没有模拟令牌检查结果。
- 原因/影响：先 SELECT 再无条件设置 `revoked_at`，缺少条件更新/行锁；轮转的一次性语义失效，旧令牌的并发使用者可同时保留有效会话。未声称能在完全不持有令牌时登录。
- 修复：在签发新会话前，通过带未吊销/未过期条件的原子消费取得所有权；失败分支不签发后继令牌，消费与签发同事务。
- 验收：同一刷新令牌并发使用恰好一次成功，另一请求返回令牌失效；库中只存在一组有效后继凭据。补 PostgreSQL 独立连接验证；不要只测串行重放。

### B02 [P1] 任务没有独立提交的抢占状态，重复调度且已取消任务仍可发布

- 位置：[extraction_task_service.py:196](/Users/linyer/Public/Private/knowledge/server/app/domain/extraction_task_service.py:196)，重点 198–219；调度 152–175；取消 102–115；最终覆盖 252–258。
- 触发：工作任务已读到 PENDING 并在内存中置 RUNNING，但尚未提交；另一个请求/调度轮询读取相同任务。
- 证据：`test_uncommitted_running_state_requeues_and_loses_cancel` 在真正 `start_run` 首次 flush 前插入确定性交错。观察 Session 仍读到 PENDING；两次轮询提交同一 task_id 两次；取消 Session 成功提交 CANCELLED；随后原执行继续真实抽取，最终状态 SUCCESS 且图谱发布。
- 原因/影响：RUNNING 与整个抽取结果共用长事务，仅结束时提交；调度也不原子认领。取消分支只根据已提交状态行动，工作会话没有重新确认。正常运行期间状态/进度也不能可靠对外反映。数据库锁等待、多进程重复执行的具体表现尚未实测。
- 修复：先以短事务原子认领并提交任务所有权，再执行候选图事务；将取消请求持久化并在阶段边界及发布前确认；重复调度者不能覆盖活动取消标志。
- 验收：运行中 GET 能看到 RUNNING；连续轮询不重复认领；取消成功后不得将候选图设为 current；以受控交错验证启动、排队、取消、发布各边界，再在实际元数据库上验证锁行为。

### B03 [P1] 增量抽取把增量候选图当完整当前图发布，旧实体从当前结果集消失

- 位置：[extraction_service.py:378](/Users/linyer/Public/Private/knowledge/server/app/domain/extraction_service.py:378)（水位过滤）；203–209（全新空候选图）；[extraction_service.py:1014](/Users/linyer/Public/Private/knowledge/server/app/domain/extraction_service.py:1014)（切换 current）。任务水位传入见 `extraction_task_service.py:178–193, 219–227`。
- 触发：第一次成功抽取 id=1，源新增 id=2，第二次使用第一次输出的水位做增量。
- 证据：`test_incremental_replaces_current_with_delta` 两次调用真实 `start_run`，均 SUCCESS；第二次 current 只含 `Item/2`，`Item/1` 消失。旧图历史仍在，没有声称物理删除历史。
- 原因/影响：仅抽取新行，却既不合并上一成功图，也没有查询时组合增量层；仍无条件把该图当全量结果集切换。
- 修复：先明确并落实“完整版本”或“可组合增量层”的一致语义；当前完整图模型下，以前一成功版本为基底合并增量，同时保留事实来源批次。完成前应阻止不完整增量覆盖 current。
- 验收：新增一行后当前图同时可见旧、新实体及正确属性/关系/证据；空增量保持 current；重复增量不重复事实；失败不前移水位或 current。

### B04 [P1] AUTO SHACL/OWL 规则没有输出 NOT_RUN，直接从运行报告消失（产品 R01）

- 位置：[extraction_rule_stage.py:67](/Users/linyer/Public/Private/knowledge/server/app/domain/extraction_rule_stage.py:67)，69–70 在 71–80 记录未执行原因之前跳过非 DATA；120–122 明明已为 SHACL/OWL 返回未执行原因。
- 触发：本体存在 AUTO SHACL 或 OWL 规则，正常执行抽取。
- 证据：`test_non_data_auto_rules_disappear` 分别验证两种语言；真实 loader 返回 `language_not_executed_in_pipeline`，完整抽取后的 `rule_results=[]`，run=SUCCESS。夹具只构造规则挂载，不运行 SHACL 引擎，反例针对报告漏项。
- 影响：未执行规则不能被审计发现，不符合四态“未执行必须 NOT_RUN”的契约。此处是漏报，不是直接将该规则的 state 写成 PASS。
- 修复：区分交由第四阶段执行的 DERIVATION，与管线不支持但必须留下 NOT_RUN 的语言；不要在记录未执行结果前统一跳过非 DATA。
- 验收：AUTO SHACL、OWL 各有一条 NOT_RUN 与原因；正常 DATA 仍执行；DERIVATION 不重复执行；变更后不可执行的派生规则也应明确呈现未执行状态。

### B05 [P1] 实例属性校验对小数、无效日期及缺失必填属性给出 PASS

- 位置：[instance_validation_service.py:363](/Users/linyer/Public/Private/knowledge/server/app/domain/instance_validation_service.py:363)，366–373 把任意 float 当 integer、任意 str 当 date；[instance_validation_service.py:196](/Users/linyer/Public/Private/knowledge/server/app/domain/instance_validation_service.py:196)，205 只遍历已出现的属性。
- 触发：冻结属性定义分别为 integer、date、nullable=False；实际值为 1.5、`not-a-date`，或属性缺失。IDENTITY 映射和未映射必填属性都可以到达这类输入。
- 证据：`test_i03_false_pass` 三个参数例，直接执行 I03，全部得到 PASS。使用完整候选图与合法资源快照结构，针对定义和值构造反例。
- 原因/影响：检查只验证宽松 Python 类型，且缺少按冻结定义检查必填属性；运行的实例质量报告会产生假通过。
- 修复：依据项目冻结 datatype 定义校验实际词法/数值；整数排除非整数小数，日期验证实际日期；遍历必填定义检查缺失字段，保持 nullable 与空列表语义。
- 验收：上述三例均 VIOLATION；合法整数、合法日期、允许缺失的 nullable 属性保持预期结果；补字段缺失与显式 null 的独立用例。

### B06 [P1] 新增属性约束未进入发布快照，历史约束与条款依据永久缺失

- 位置：[status_service.py:157](/Users/linyer/Public/Private/knowledge/server/app/domain/status_service.py:157)，157–174 的属性快照字段集；当前明细写入在 `type_service.py:210–214`；快照 DTO 在 `ontology_snapshot.py:24–32`；RDF 约束转换在 `semantics/ontology_rdf.py:291` 起。
- 触发：属性配置 min/max cardinality、min/max value、source_clause_ref，然后发布资源。
- 证据：`test_numeric_constraints_dropped_from_frozen_snapshot` 经真实创建/发布服务配置 1..1、0..100 及条款引用；发布 payload 的该属性缺失全部五个字段。
- 影响：定义当前表中有这些约束，冻结历史却没有；后续版本、历史证据与导出无法还原发布当时的约束。资源更新后不能用当前值安全补齐过去。
- 修复：将这些字段纳入不可变快照、解析模型及对应导出/校验契约；旧快照缺字段须显式按未知/未记录处理，不回读当前可变定义，不猜测历史值。
- 验收：创建→发布→改草稿→再次发布后，v1/v2 分别保留各自完整约束；历史导出不随动；缺字段旧快照不会被标为完整约束证据。

### B07 [P2] 阶段取消被当成源库故障，任务最终 FAILED 且未关联已生成 run

- 位置：[extraction_service.py:147](/Users/linyer/Public/Private/knowledge/server/app/domain/extraction_service.py:147)，147–155 捕获所有 Exception；任务的专门取消分支在 `extraction_task_service.py:229–237`，实际进入 238–244；run_id 直到 252 才赋值。源连接上下文 `connectors/sql.py:169–172`、`source_service.py:82–86` 也会包装从 yield 内传播的非 KGError。
- 触发：任务已经开始，实体阶段结束后取消标志置位，下一个阶段边界抛 `ExtractionCancelledError`。
- 证据：`test_cancel_becomes_failed_and_orphan_run` 仅在真实实体阶段完成后置 Event，执行真实 `_run_task`；得到 FAILED、`KG.SOURCE_UNREACHABLE`、`task.run_id=None`，库中已有 FAILED run；没有发布 current。
- 影响：取消状态与诊断失真，用户无法通过 task.run_id 定位已有失败记录。此次验证确认失败保护没有因该分支移动 current。
- 修复：让取消信号穿过各上下文到达任务编排层；区分连接器错误与业务异常；候选 run 产生后立即在任务中建立关联，并保证事务一致性。
- 验收：各阶段边界取消均得到 CANCELLED；task/run 可追溯；current 不变；正常源库故障仍映射源错误，不误判取消。

### B08 [P2] 删除带属性的新草稿先删子资源后删父引用，触发外键失败

- 位置：[resource_lifecycle.py:134](/Users/linyer/Public/Private/knowledge/server/app/domain/resource_lifecycle.py:134)，140 仅删子资源发出的引用，144 删除子资源；父资源指向子资源的引用到 148–155 才删除。`ResourceRef.target_id` 有非级联外键，真实 SQLite 配置也启用了外键。
- 触发：新建一个含数据属性的实体类型，未发布、无任何外部引用，然后删除。
- 证据：`test_deleting_draft_with_property_violates_fk` 使用真实创建/删除服务、`foreign_keys=ON`，得到 `FOREIGN KEY constraint failed`。HTTP 的 SQLAlchemy 错误映射会将此作为数据库错误返回。
- 修复：先核对整个删除子树的外部引用，再按引用/明细/子资源/父资源顺序删除；不能为了通过删除关闭外键或吞掉异常。
- 验收：有属性的实体草稿与含关联属性的关系草稿可完整删除；存在外部引用时返回 RESOURCE_IN_USE 且不删数据；外键开启；事务失败保持原数据。

## 已查范围与局部核验

| 主题          | 本次证据覆盖                                                                                         | 保留边界                                                               |
| ------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 四态          | 资产 A01–A08、实例 I01–I06、规则/派生阶段调用顺序；B04/B05 已复现                                    | 未重跑全部 RDF/SHACL/OWL 组合与性能测试                                |
| 冻结/历史     | resource/ontology/mapping 发布，快照解析，证据摊平，run 导出；B06 已复现                             | 规则完整历史内容、模板演进、复杂闭包未完成定向验证                     |
| 抽取/失败保护 | 四阶段、候选图/current 切换、水位；B03/B07 已复现                                                    | 大规模幂等、多源融合、FK 多表同键尚未定向验证，不能宣称通过            |
| 取消/并发     | 任务创建、调度、取消、提交边界；B02 已复现                                                           | 多 worker/进程、进程重启恢复、真实 PostgreSQL 锁行为未验证             |
| 连接器只读    | SQLite ro/query_only/authorizer/deadline，PG/MySQL 连接选项、NullPool/dispose；静态读取完成          | 未连接任何真实源库；本次内存反例绕过连接器，不能用于证明远端只读性     |
| 授权/脱敏     | business router 鉴权、VIEWER 写请求限制、管理员依赖、认证/刷新、凭据密文与展示、预览清洗；B01 已复现 | 权限矩阵本次未重跑；脱敏边界与重置令牌并发仅局部阅读，无全链路安全证明 |
| 引用删除      | resource/ontology/mapping/source/rule/template 服务与 ORM 外键；B08 已复现                           | 复杂外部引用与删除并发尚未全面验证                                     |

已按用户要求停止扩展；未完成项为后续续接范围，不计入已确认问题数量。没有重复前端问题或产品审查结论。

## 复现命令

```sh
cd /private/tmp/knowledge-audit-20261106
PYTHONDONTWRITEBYTECODE=1 KG_DATABASE_URL=sqlite:// KG_ENVIRONMENT=development KG_CREATE_TABLES_ON_STARTUP=false KG_PASSWORD_ITERATIONS=1000 PYTHONPATH=/Users/linyer/Public/Private/knowledge/server /Users/linyer/Public/Private/knowledge/server/.venv/bin/python -B -m pytest -p no:cacheprovider -q -s /private/tmp/knowledge-audit-20261106/repro_backend_audit.py > /private/tmp/knowledge-audit-20261106/backend-repro.log 2>&1
```

建议修复顺序：B01 → B02/B07（同任务状态链，分步验证）→ B03 → B04 → B05 → B06 → B08。认证、并发与冻结修复按项目高风险约束安排独立复核；此报告本身仅审计，不代表修复获验收。
