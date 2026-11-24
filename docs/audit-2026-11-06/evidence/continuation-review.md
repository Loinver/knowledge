# PC09 / PC13 / PC14 / PC15 / PC16 独立只读复核汇总

日期：2026-11-07。仓库：`/Users/linyer/Public/Private/knowledge`。

**结论：PASS，限定于本报告列明的实际变更和已完成验证。此前报告的阻塞均已关闭，当前没有待修的已复现阻塞。** 此结论不代表生产 PostgreSQL 已实测，也不代替主线程仍在执行的最终整体门禁。

本报告汇总既有证据，没有扩大复核、重跑全量或修改仓库文件。Reviewer 的独立性来自独立上下文与只读职责；不声称使用了异构模型。未使用缺失的 coordinated-coding-workflow 历史备份增加流程。

| 项目                | 结论                   | 已完成的验证范围                                                                                                    | 已关闭问题                                                                                                       |
| ------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| PC09 完整恢复       | PASS                   | 保守拒绝已有资源；预览绑定与重检；API 提交/回滚；跨库 RDF 导出→恢复→再导出；SQLite 并发恢复窗口；不支持语义拒绝     | namespace 重检后错误复用、同 IRI 本体在重检与提交间并发插入、不支持的 union/intersection role 被接受后无法再导出 |
| PC13 历史与冻结     | PASS                   | 新 history schema/domain/API；三层 GET；成员和 pin 绑定；规则快照与发布边界；owned 递归闭包；历史面板及异步结果归属 | 显式 pin 与缺省引用混淆、共享 owned 节点重复产生版本、独立 datatype property 明细缺失                            |
| PC14 资产审计       | PASS，限已标注直接端点 | 成功审计同事务；失败先回滚再独立写；相关 ID；权限；敏感载荷排除；迁移；SQLite 同资产并发版本链                      | 并发编辑导致 version_before 仍为旧版本，形成 0→1、0→2 的失真审计链                                               |
| PC15 语义视图       | PASS                   | 冻结 ontology 身份、运行 namespace、关系 predicate、继承属性匹配；实际节点/边与模板重载                             | mapping.id 错作 ontology_id、冻结语义与实例命名不匹配、同名继承属性错误回退                                      |
| PC16 融合与保存入口 | PASS，限本轮范围       | 决策与原始输入证据稳定性；空业务键及关系失败保护；FK 来源绑定；AI 追加保存旧映射完整性                              | 转换后相同值吞掉不同原值、拒绝行复活为 stub、FK 跨表同号误隔离/错误转连、AI 保存丢失 fusion/转换/候选字段        |

**PC09：恢复窗口的原子性与语义保留。**

Reviewer 独立执行 `test_ontology_restore_concurrency.py` 与 `test_ontology_restore_apply.py`，共 **21 项通过**。并发覆盖 SQLite DELETE/WAL、独立进程的普通 namespace/ontology 写入及另一恢复请求：恢复先获取事务写锁，再重检，锁持续至调用方 commit/rollback；竞争提交发生在预览之后时重检拒绝；锁冲突能够回滚并重试。namespace 复用还会刷新已有对象并核对 IRI。

两个独立数据库的 Turtle/JSON-LD 往返测试比较语义图，仅归一化本地版本、枚举 ID 和内部 shape 名。apply 失败回滚所有新建资源；预览失效及不支持规则均拒绝。Reviewer 另外显式注入 `union_of`、`intersection_of`，两种格式共 **4 个组合均在预览拒绝，资源计数为零**。

当前修复通过数据库事务锁保护恢复的重检—写入—提交窗口，不需要新增依赖。**普通 create_ontology 在恢复提交后仍可创建同 IRI、不同名称的本体**：这是明确保留的既有边界，当前没有全局 ontology IRI 唯一性保证，本次未修改全局 schema 或创建契约。

**PC13：历史读取与冻结闭包。**

前轮独立执行历史、规则与依赖相关 **20 个定向用例通过**。explicit pin map 仅纳入真正设置 pinned_revision 的引用；owned 发布使用同遍历 memo，并在 checksum 与 payload 相等时复用旧版本；独立 DATATYPE_PROP 以 self 明细冻结，历史默认值可显示。

历史读取按所属本体版本、成员和 pin 取快照，不以当前资源补历史缺口。新本体发布才允许按约定冻结父类/端点的显式 pin 或已发布 current；旧 owner 缺 owned pin 时必须有显式本体 pin，否则拒绝。主应用三层历史 GET 已有缺失/过期会话 401、禁用用户 403、VIEWER 200 以及 SELECT-only 证据。复核范围包括发布规则快照差异、history 挂载及前端迟到响应/选择归属。

历史页授权 E2E **1/1 通过**；这是主线程浏览器证据，Reviewer 未重复运行浏览器。

**PC14：直接 HTTP 写端点的审计边界。**

前轮完成权限、禁用/过期会话、管理员检索、敏感载荷排除、成功审计写失败时业务回滚、失败独立留痕、提交后响应异常及迁移检查。迁移验证包括升级、空表降级再升级、非空审计表拒绝降级、无 actor/object 外键和 correlation 唯一约束；主线程迁移日志另有 **4 项通过**。

锁修复后，Reviewer 使用两个独立 DBAPI 连接和受控线程调度：A 取得锁并读到版本 0，B 尝试读取时等待，释放 A 并提交后 B 读到版本 1。两请求均成功，审计为 **0→1、1→2**。同时独立通过新增并发测试及 **4 项事务/失败保护回归**。主线程后续报告锁相关回归 **24 passed**，本报告不将该报告计作 Reviewer 的额外重跑。

覆盖范围仅为实际标注 `@audit_asset`、经业务授权依赖进入审计上下文的直接写端点：命名空间、实体类型、关系类型、业务域、本体（含直接导入与完整恢复）、映射、数据源、规则、装配模板、枚举字典、标准条款，以及手动切换当前图版本。其中只覆盖已标注的具体动作，不等于这些模块的所有写操作均自动审计。

**后台自动操作、AI 间接写入、图谱视图模板不在此审计通过结论内。** 装配模板与视图模板是不同范围。PC16 的 AI 保存回归证明字段保留，不证明该间接入口已经产生 PC14 资产审计事件。

**PC15：真实实例身份与继承字段。**

`_ontology_id` 已返回 mapping.ontology_id，并有 mapping/ontology ID 不同的回归。图输出使用冻结运行的 instance_namespace；字段目录提供冻结 type_name；关系匹配支持精确冻结 IRI、实例 namespace+name 及真实存储的 catalog relation.name，不用 suffix 猜测。

属性先筛适用实例类型的 PROPERTY，精确 IRI 属性优先；名称回退仅在该实例类型目录中对应唯一不同属性 IRI 时允许。Parent/Child 同名字段与 instanceNamespace 回归已纳入，Reviewer 独立运行语义测试 **23/23 通过**，vue-tsc 通过。

主线程真实 UI 联合 E2E **2/2 通过（1.3m）**，包含实际 **2 节点、1 条边**及模板重载后的关系断言、跨库恢复语义等价、管理员审计检索；不以 SVG 元素存在作为语义成功证据。

**PC16：失败保护、FK 身份与 AI 保存。**

原始候选去重键包含 input_value。Reviewer 用非回文排列验证 `'01'` 与 `'1'` 同转为 1 时都保留，出现次数分别为 2 和 1，输出与顺序无关；source_values 冲突仍按转换结果判断。

空业务键 null/empty × FK/JUNCTION/ASSOCIATIVE **6 个组合独立通过**：整批无合法实体时运行 FAILED，零实体、零关系，原 current graph 保持。拒绝标记及两端预检阻止关系将被拒来源重建成 stub。

最后的跨表同号阻塞已关闭。Reviewer 独立运行新增真实 FK 双向用例与上述空键用例，共 **8/8 通过**，另跑 **5 个探针通过**：

- 真实 FK 指向合法 good 表时，即使存在多个同号实体也准确连接 good；无关坏 a.id=1 不污染它。
- 真实 FK 指向被拒 a 表时，不转连同号 good 实体。
- 无 FK 元数据时，唯一合法目标可以使用；多个同号合法候选或只有拒绝记录时隔离。
- 上述拒绝路径不生成额外 stub。

AI 追加映射改用 EntityMapCreate/RelMapCreate.model_validate 重建已有 draft，新建议构造逻辑未变，保存继续经过版本冲突检查。Reviewer 独立运行新增真实 apply 保存回归及 AI 套件 **8/8 通过**，断言已有 entity/relationship maps 精确相等，涵盖 fusion、转换参数、空值策略和候选 ref_field。主线程报告融合/AI/快照约束合计 33 项通过，未在此报告阶段重跑。

**生产 PostgreSQL 与证据限制。**

PC09 的 PostgreSQL READ COMMITTED 检查、namespace/ontology SHARE ROW EXCLUSIVE NOWAIT 表锁及错误转换，只完成源码复核。PC14 的 PostgreSQL 对象 FOR UPDATE 与全局图指针表锁，同样没有生产等价实库并发证据。SQLite 的通过结果不代表 PostgreSQL 的锁等待、隔离级别、驱动异常映射和提交/回滚行为已验证。

不把此前定向测试、浏览器日志或单项 PASS 扩写为全局覆盖；本报告没有新增范围或重复跑全量。

**最终门禁状态：主线程报告，尚待最终完成。**

- 前端全量：173 通过。
- 后端上一轮：986 通过、1 失败；主线程说明失败是新增 DomainRevision.pinned_revision 后精确期望未同步，已修测试期望，未改生产代码，随后 2 个定向用例通过。
- 最终整体门禁正在重跑。本报告写入时没有最终完成结果，不能将上次后端全量记录为全绿。

**证据位置与复现入口。**

- 历史初轮：`/private/tmp/knowledge-continuation-20261107/restore-history-first.log`
- 历史授权 E2E：`/private/tmp/knowledge-continuation-20261107/e2e-history-authorized.log`
- 联合真实 UI E2E：`/private/tmp/knowledge-continuation-20261107/e2e-three-capabilities-retry.log`
- 审计迁移：`/private/tmp/knowledge-continuation-20261107/pc14-migration-final.log`
- 原阻塞探针：`/private/tmp/knowledge-continuation-20261107/reviewer-probes/review_probes.py`
- 原阻塞输出：`/private/tmp/knowledge-continuation-20261107/reviewer-probes/baseline.stdout.jsonl`
- 当前恢复并发回归：`server/tests/test_ontology_restore_concurrency.py`
- 当前恢复 apply 回归：`server/tests/test_ontology_restore_apply.py`
- 当前审计行为/锁回归：`server/tests/test_asset_audit.py`
- 当前融合、FK 与 AI 保存回归：`server/tests/test_fusion_attributes.py`

原 baseline 是修复前历史证据，不代表当前仍失败。旧探针的嵌套竞争调度会被新锁阻止，roles 所依赖夹具也发生过变化；当前结论采用受控等待调度、显式注入 role 和新增定向回归。部分 Reviewer 探针通过临时内存脚本执行，输出保留在本会话工具记录，未另存为独立日志；不得把上述 baseline 当成这些新探针的输出。
