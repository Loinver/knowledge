# 前端架构与交互实现只读审计

日期：2026-11-06。项目：`/Users/linyer/Public/Private/knowledge`。

基线与结束核对：`HEAD=3e729e4213db3cd61a2430aa49962f226e65f312`，开始与结束 `git status --short` 均为空，`git diff --stat` 为空。未修改业务代码、真实数据、仓库配置；未提交、部署或访问外网服务。临时报告、源码编译产物和隔离测试在 `/private/tmp/knowledge-audit-20261106/`。现有测试按其原有实现短暂使用并清理 `web/node_modules/.tmp`。

已读根 `AGENTS.md`、`.agents/AGENTS.md`、架构/代码风格/API/测试/i18n conventions，以及 `code-review-safe-refactor`、`frontend-architecture-review`。历史记忆仅提供定位提示，没有将历史文档或旧测试结果作为当前缺陷证据。

审查包括全部 37 个路由页面的入口、主要读取/写入、错误及空态分支、关键按钮绑定、路由上下文，以及 API/composables/stores 和图画布相关组件。只根据当前实现作结论，不从 CSS 推断视觉表现。浏览器截图、全量检查、产品需求覆盖和后端独立审计由主代理/其他代理负责。

## 结论与优先顺序

发现 **12 项确定缺陷**，其中 **5 项 P1、7 项 P2**；另列 4 个边界明确的风险，不把它们混入确定缺陷计数。没有 P0 证据，不为了数量列风格或目录偏好。下表 ID 与临时复现脚本的 F 编号不同，映射已明确标注。

| ID    | 优先级 | 确定缺陷                                             | 当前证据                                  |
| ----- | ------ | ---------------------------------------------------- | ----------------------------------------- |
| FE-01 | P1     | 会话失效清 token 后仍被视作登录，无法进入登录页      | F01：真实拦截器、store、路由守卫复现      |
| FE-02 | P1     | 快速切换映射后以旧映射版本创建抽取任务               | F02：响应乱序与请求载荷复现               |
| FE-03 | P1     | 本体编辑详情未就绪就保存，清空已有定义               | F04：提交载荷复现；后端替换语义核对       |
| FE-04 | P1     | 旧采样成功恢复发布资格，后来修改的草稿未经采样即发布 | F10：保存/采样/再编辑/发布顺序复现        |
| FE-05 | P1     | 设计器新建类型的后续装配写入后来选中的本体           | F14：创建挂起、关闭弹窗、切换本体复现     |
| FE-06 | P2     | 校验结果未绑定对象，跨本体/结果集显示旧 PASS         | F12 + F09：设计器与校验报告页分别复现     |
| FE-07 | P2     | 重开已有映射后第一次选数据源会清空保存的字段绑定     | F07：已保存草稿恢复流程复现               |
| FE-08 | P2     | 服务端首分页被当全量目录，画布遗漏实际引用的资源     | F13：第 51 个资源被过滤；当前后端分页核对 |
| FE-09 | P2     | 设计器新建类型后未更新资源索引，已加入的节点不可见   | F11：refs 有新资源、nodes 为空复现        |
| FE-10 | P2     | 图谱“总览”和清除结果集按钮不能删除 URL 参数          | F06：真实 memory router 参数保持不变      |
| FE-11 | P2     | 实体跳转后融合溯源仍显示上一个实体                   | F08：真实 reactive route 与组件状态复现   |
| FE-12 | P2     | 初次加载时离开抽取任务页，卸载后才注册轮询           | F03：计时器记录复现                       |

## 确定缺陷明细

### FE-01 · P1 · 会话失效后登录页被守卫挡回工作台

- 定位：`web/src/stores/auth.ts:23-30`；`web/src/api/client.ts:79-82,121-133`；`web/src/router/index.ts:224-236`；`web/src/main.ts:12-16`。
- 触发：用户已正常登录且 `auth.user` 非空；访问任意业务 API 时 access 和 refresh 均被拒绝。拦截器清理 token 并要求跳到登录页。
- 实现证据：token 订阅仅递增 epoch，不清 `user`；`isAuthenticated` 使用 `user !== null || hasSession()`。因此 token 被清空后结果仍为 true。公开路由守卫把访问 login 的“已登录”用户重定向到 dashboard。
- 影响：失效会话仍保留旧姓名/角色和工作台壳；登录重定向不能完成，用户必须刷新页面或主动退出才能恢复。**未据此声称后端权限可绕过**。
- 最小修复：凭据清除时原子清理用户/角色与会话状态；认证状态以有效会话凭据为依据；使失效处理先完成 store 清理再跳转。为 `loadMe`/refresh 引入会话代次，防止旧会话响应重新写回，保持网络错误与明确拒绝的区别。
- 验收：已加载 user 后模拟业务 401 + refresh 401；断言 token/user 清空、最终路由 login、原 redirect 保留、无重复跳转。另测 refresh 503 不踢登录。F01 当前输出：`token=null, user=ADMIN, isAuthenticated=true, route=dashboard`。
- 把握：高，真实客户端/store/守卫，HTTP 由 adapter 截断，无网络。

### FE-02 · P1 · 抽取任务的映射选择与提交版本错配

- 定位：`web/src/views/extraction/ExtractionTasks.vue:161-172,175-192,263-273`；`web/src/api/mappings.ts:25-26`。
- 触发：选择映射 A 后立即选择 B，A 的 published 请求较慢、最后返回。下拉在版本查询期间仍可操作，只由 `optionLoading` 禁用。
- 实现证据：`chooseMapping` 无取消、选择代次或 ID 校验，任一返回都写 `publishedRevisionId`；`createTask` 仅提交该 ID，不提交当前 selectedMappingId 供后端比对。
- 影响：下拉显示 B，任务实际按 A 的发布版本执行，可在用户未察觉时形成错误抽取产物。
- 最小修复：为 published 读取绑定 `{mappingId,generation,controller}`；选中值变化/清空/卸载时取消并清版本；只有版本的所属映射与选择匹配时启用提交。表单校验后再次检查/快照选中上下文。
- 验收：A→B、B先返回/A后返回；A→空；A→B→A；请求失败及卸载均不能恢复旧版本。创建任务载荷必须等于当前选择对应发布修订。F02 实测：selector=2，提交 revision=101（映射1）。
- 把握：高，响应乱序和真实创建函数载荷均复现。

### FE-03 · P1 · 本体编辑保存会清除尚未加载的定义

- 定位：`web/src/views/ontology/Ontologies.vue:262-286,289-310,450-456`；`server/app/domain/ontology_service.py:245-256`。
- 触发：已有定义的草稿本体点击编辑，只修改标签后在详情 GET 完成前保存；详情 GET 失败后保存同样可发生。
- 实现证据：抽屉先以空 `definitionZh/En` 打开；详情异步填充，失败吞掉；保存按钮未等待详情。`handleSubmit` 始终传 `definition_i18n:{}`。后端对非 null 的 definition 直接整体赋值，乐观锁并不能保护“同版本的空字段”。
- 影响：只想改标签却清空中文/英文定义；慢返回还可覆盖用户已输入的定义。
- 最小修复：增加 editorLoading/editorReady/error，详情成功且绑定当前编辑代次后才允许编辑与保存；关闭/重开使旧详情失效；载荷版本取与表单同一次详情，不能使用列表 token 与后来详情内容拼接。
- 验收：详情挂起/失败时不发 PUT；延迟响应不覆盖用户输入；A→B→A 旧详情不能初始化新会话；改标签应保留原定义。F04 已截获详情挂起时 `definition_i18n={}`。
- 把握：高，前端请求载荷复现及后端赋值语义确认；未对真实库执行写入。

### FE-04 · P1 · 过期采样结果使新草稿获得发布资格

- 定位：`web/src/views/extraction/MappingWizard.vue:259-270,949-968,976-992,1093-1099,1477-1551`；`server/app/domain/mapping_service.py:294-337`。
- 触发：对合法草稿运行采样，等待 compile 期间继续修改字段/转换/表（编辑器只按 PUBLISHED 禁用，并未按 working 禁用）；旧 compile 最后成功。
- 实现证据：深 watch 在修改时将 preview 清空，但 compile 回调只比较 selectionGeneration，未比较草稿内容代次；旧结果随后重新赋值 preview。`canPublish` 将该结果视为当前 clean preview，`publishMapping` 又保存最新本地草稿再发布。后端发布只冻结现有草稿，不重新执行样本编译。
- 影响：界面展示的是旧映射的成功样例，却发布未验证的新映射，破坏采样→发布确认链路。
- 最小修复：编译绑定 mapping/数据源/草稿内容 revision 或 fingerprint；任何映射内容变化即使 pending compile 失效；发布前要求成功采样与当前待保存内容一致。可额外禁用编译期间的编辑，但不能仅靠按钮禁用替代响应归属判断。
- 验收：编译 A 挂起→编辑 B→返回 A 成功，preview 不得恢复、canPublish 必须 false；重新编译 B 后才允许发布；覆盖变换参数、关系映射、数据源、切换后返回同 ID。F10 输出保存序列为 `name → unsampled_column → publish`，中间只采样了 name。
- 把握：高，真实组件读写流程和当前后端发布语义核对。

### FE-05 · P1 · 新建类型完成后装配到错误本体

- 定位：`web/src/views/ontology/Designer.vue:866-877,800-837,995-1004,1155-1166`。
- 触发：在本体 A 点“画布新建类型”，create 请求挂起时取消/关闭弹窗，再选本体 B；create 最后成功。
- 实现证据：`submitCreate` 在 await 前未捕获选择上下文；返回后 `addToCanvas(created.id)` 使用此时的全局 selection。`createLoading` 只用于正向按钮 loading，取消按钮和本体选择未受其保护；本地安装的 Naive Dialog 负向按钮也未隐式按该正向 loading 禁用。
- 影响：自动给 B 增加非预期资源引用，A 未得到预期资源。与已有 updateOntology 的写后回调保护不同，这是**创建之后才开始的第二次写请求选错了对象**。
- 最小修复：创建前捕获 OntologySelection；create 成功后校验原选择仍有效，明确把 ID 传给装配流程，禁止针对后来选择启动后续写。创建成功但无法装配时保留真实状态和手工加入路径，不把整个操作虚报成功。
- 验收：A 创建挂起→关闭→B→create 成功，B 不得收到 addRef；A→B→A 及卸载也不能继续过期链路；正常 A 创建后只写 A。F14 截获 `addRef(2,101,...)`。
- 把握：高，脚本状态迁移和实际后续写入参数复现；浏览器弹窗操作未执行。

### FE-06 · P2 · 校验结果与当前对象脱离

- 定位 A：`web/src/views/ontology/Designer.vue:554-571,926-944,1031-1059`。定位 B：`web/src/views/graph/GraphReports.vue:24-38,44-77,94-112,116-170`。
- 触发 A：本体 A 开始校验后切换 B；或看完 A 报告再切 B。触发 B：结果集 A 校验后选择 B，B 的校验尚未完成或失败；也可并发点击校验造成返回乱序。
- 实现证据：设计器只检 alive，不检 selection，切换也不清报告。GraphReports 只更新 selectedGraphId，不清 reportId/results；runValidation 无执行锁或代次，loadResults 直接赋值，且被 watcher 和 runValidation 重复调用。
- 影响：当前对象未通过校验时，页面仍展示其他对象的 PASS/VIOLATION；四态本身没有改码，但结果归属失真，会误导发布和数据质量判断。
- 最小修复：结果保存显式 subject ID/graph ID，切换时取消并清空；统一校验执行入口和报告读取，以对象+代次绑定 summary/results/error/loading。编辑装配后使已有报告失效或明确标旧版本。GraphReports 同步呈现 revisions.error/report.error，避免加载失败被当作空态。
- 验收：A→B 旧响应和旧错误均不能显示在 B；B 失败后不能保留 A PASS；连续校验较旧请求最后返回不能覆盖；summary/results 必须同一 report ID。F12：本体2显示本体1 PASS；F09：结果集2校验失败仍持有 report11 的 PASS。
- 把握：高，两页面分别复现。

### FE-07 · P2 · 已保存映射首次选择数据源就丢掉恢复的绑定

- 定位：`web/src/views/extraction/MappingWizard.vue:130-146,678-720,875-907,1247-1257,1481-1493`。
- 触发：重新打开页面，先选已有映射；页面恢复 revision 的表、字段、键。selectedDatasourceId 初始 null，用户随后到第二步选择用于预览/执行的数据源。
- 实现证据：`chooseDatasource` 无条件清空所有 entityMaps 的 table/schema/key_fields/source_field，以及关系的端点/候选/属性绑定；不区分第一次绑定数据源和主动迁移源。已发布映射也会被本地清空，而对应编辑控件被 PUBLISHED 禁用。
- 影响：草稿无法接着编辑/采样，必须重新配置或重新选择映射；已发布映射在界面出现空表字段且不能修改，虽后端冻结版本未被改写，预览路径被阻断。选择数据源后再次选择映射是现有绕行步骤，不是正常恢复流程。
- 最小修复：首次选择数据源先加载元数据并核对现有引用，保留保存的绑定；确实更换数据源时只标记不兼容项/要求明确转换，不无条件丢弃；已发布映射保持冻结配置，只允许切换运行上下文。
- 验收：重开草稿/已发布映射→首次选源，原 employees/name/id 保留；可继续采样/运行；真正换源时明确报告失效字段，不静默清空。F07 证明首次选源后三者均为空。
- 把握：高，标准恢复顺序已复现。

### FE-08 · P2 · 首分页当全量目录导致列表、装配及映射遗漏资源

- 定位：`web/src/views/ontology/Designer.vue:143-150,507-528`；`EntityTypes.vue:257-267,464`；`RelationTypes.vue:309-314,500-509,592`；`Domains.vue:148-150`；`Ontologies.vue:194-199,378`；`web/src/api/ontology.ts:51-54`；`MappingWizard.vue:573-605`。
- 契约：`server/app/api/v1/types.py:89-96`、`relations.py:96-102`、`domains.py:36-42` 默认 page=1/page_size=50；ontologyApi 默认 page_size=100；映射初始目录硬编码 page1/200。
- 触发：实体/关系/业务域超过50，本体超过100，或映射使用前200以外的资源。画布引用的资源本身可在后端 refs 中存在。
- 实现证据：没有后续分页读取；列表的 `{pageSize:20}` 只对已取回的首50/100项本地分页。设计器通过首批目录判定 refs 的资源类型，目录之外的有效 refs 被 `.filter` 直接剔除。MappingWizard 同样先用 entityBriefs/relationBriefs 过滤 refs 才取详情。
- 影响：列表不能遍历全量；下拉无法选择后面的类型；真实本体的已引用节点和关系被隐藏，映射缺失目标资源。不是单纯“显示少一点”的性能优化。
- 最小修复：列表按服务器分页/总数组织；需要全量选项的目录按页拉取或远程搜索；画布已引用资源必须按 refs 补齐，不能依赖首批全局目录。项目已有 templatesApi.resources/ontologies 和 OntologyExport 的分页迭代可复用思路。
- 验收：构造51实体/51关系/51域/101本体/201映射资源；尾项可列表访问和选择；本体引用第51个资源的 nodes/edges 必须保留；验证多页失败态和卸载取消。F13 使用真实默认分页语义：refs 包含51，但只发 list({})、nodes=0。
- 把握：高，当前前后端分页实现和画布复现共同确认。

### FE-09 · P2 · 画布新建类型后已持久化引用不可见

- 定位：`web/src/views/ontology/Designer.vue:124-145,866-878,574-609`。
- 触发：在设计器当前目录加载完成后用“画布新建类型”正常创建并装配。
- 实现证据：create 返回新资源，但不追加到 entityTypes；addToCanvas 只刷新当前 ontology 的 refs/canvas/relation details，不重新加载全局实体目录。nodes 依赖 typeById，所以新 refs 被过滤。
- 影响：请求成功、弹窗关闭，画布却看不到新节点或其属性，用户可能重复创建；刷新整个目录后才出现。这与 FE-08 同属索引覆盖不足，但即使空库也必现，修复点不同。
- 最小修复：把成功创建的类型写入当前目录/按新 ref 补齐后再装配展示；仍须保留 FE-05 的选择归属保护。
- 验收：初始实体目录为空→create101→addRef101 后，当前 nodes 包含101且可选、可定位；不需刷新页面。F11：refs=[101]、nodes=[]。
- 把握：高，真实组件 computed 和写后重载流程复现。

### FE-10 · P2 · 图谱总览与清空结果集按钮无效

- 定位：`web/src/views/graph/GraphBrowse.vue:96-117,539-568`。
- 触发：URL 已有 center 后点“总览”；已有 graph 后清空结果集数字输入；应用没有 center 的模板也受影响。
- 实现证据：updateQuery 先丢弃 patch 中 null/undefined，再与旧 route.query 合并。调用方正是用 undefined 表示删除，故旧键永远保留。
- 影响：无法通过总览按钮退出邻域；清空历史结果集不能回当前结果集，可能继续查看旧数据而误以为切换成功。
- 最小修复：先复制旧 query，再逐键处理 patch；null/undefined 明确 delete，对其他值赋值。selectGraph 根据业务明确是否同时清 center/layout。
- 验收：真实 router 中 graph12/centerA/layout=ring，explore(null) 应删除 center；selectGraph(null) 应删除 graph/layout；其他查询参数保留。F06 当前 URL 完全不变。
- 把握：高，真实 memory router 执行。

### FE-11 · P2 · 切换实体后展示旧实体融合来源与冲突

- 定位：`web/src/views/graph/GraphEntityDetail.vue:34-59,158-175,186-214`；可达跳转 `web/src/views/graph/components/GraphFactTable.vue:28-34`；路由出口 `web/src/layout/AdminLayout.vue:42` 无重挂载 key。
- 触发：实体A查看“融合”后，切到出边/入边并点击实体B链接，再打开B的“融合”。同一详情组件复用。
- 实现证据：主详情由 useAsyncData 随 route 变更；fusion 为独立 ref，仅 activeTab 变化且 fusion 为空时读取；没有随实体/graph 变化重置，也没有卸载/响应代次保护。
- 影响：B 的页面展示 A 的源行、属性冲突和隔离信息，破坏证据追溯可信性；回切 tab 也不会刷新。
- 最小修复：fusion 请求依赖 `(entity.iri,graph_revision_id,activeTab)`；更换实体/结果集时清理并取消；局部 controller 与响应身份检查；失败保留可重试入口。
- 验收：A fusion成功→出边B→B fusion，必须新请求并只显示B；A请求挂起→B→A晚返不得覆盖；卸载后不更新。F08：detail=B、fusion=A、API只读过A。
- 把握：高，源码导航链及 reactive route 复现。

### FE-12 · P2 · 卸载后创建抽取任务轮询，泄漏后台请求

- 定位：`web/src/views/extraction/ExtractionTasks.vue:117-134,222-233`。
- 触发：进入任务页初始列表/选项尚未完成时离开；卸载 abort 导致 loadOptions/loadTasks 捕获异常并正常 resolve，onMounted await 随后继续。
- 实现证据：卸载时 pollTimer 尚未赋值所以无法 clear；await 后无 alive 判断，仍 setInterval；后续 loadTasks 能重新创建 controller，文档可见时每2秒请求。
- 影响：离开页面后持续请求，重复进入/退出可累积轮询；会话失效时还会触发无关页面的认证错误处理。
- 最小修复：在首个 await 前注册轮询并统一清理，或 await 后校验 alive；入口 loadTasks/loadOptions 也应在 unmount 后不再启动。避免重叠轮询周期不断 abort 当前慢请求。
- 验收：初始请求挂起→卸载→请求完成/拒绝，两种情况下均无新 interval/请求；常规挂载卸载只创建/清理一次。F03：卸载后 interval=1、clearInterval=0。
- 把握：高，计时器桩复现；未等待真实2秒或接触服务。

## 风险与增强（不计入确定缺陷）

### R-01 · 条件性写错对象风险：实体基本编辑/重命名抽屉未绑定路由对象

`EntityDetail.vue:120-125` 只关闭属性 showEditor，不关闭 showBasicEditor/showRename；`saveBasic:248-268` 从最新 data 取 ID/版本，但沿用旧 basicForm；`submitRename:199-212` 同样使用当前 data。F05 通过直接 memory router 从 /entities/1 到 /entities/2 可复现更新2时提交1的文案。`AdminLayout.vue` 出口无 key，复用机制成立；但此页未发现普通界面的直接“实体A→实体B”导航按钮，尚未执行浏览器返回/前进触发链。因此将影响定位为条件性风险，**不按已经端到端复现的数据损坏定级**。修复方向：所有编辑会话绑定 id+generation，路由切换统一关闭；验收增加实际浏览器历史导航场景。

### R-02 · 图谱附加查询未统一绑定结果集

`GraphBrowse.vue:122-174,240-265,284-299,320-340` 的 recommendations/templates/quality overlay/path/diff 多使用临时 AbortController.signal，却没有保留 controller 或 cleanup/身份判断；`GraphEvidence.vue:70-88` 的 reverseTrace 也直接赋值。旧请求回写当前上下文的机制存在，但本次没有逐个复现所有业务损害，不重复拆成多项缺陷。建议修 FE-11/06 时仅对相关身份链补定向测试；不得因此宣称所有图谱请求已覆盖。

### R-03 · 简单列表仍缺少响应代次或取消后的状态隔离

`EntityTypes.vue:257-272`、`RelationTypes.vue:309-323`、`Ontologies.vue:194-204`、`Users.vue:144-162`、`AuditLogs.vue:82-105` 直接写最后返回数据。`StandardClauses.vue:90-112` 虽 abort，但 catch/finally 仅检查 alive，旧取消请求可污染当前错误/loading。源码有风险，未将每页都制造乱序或证明实质写损害，保留为回归范围，不充数。

### R-04 · 其他编辑就绪与上下文保护证据缺口

`Profile.vue:48-73` 等待 loadMe 前表单已可保存，存在用空初值覆盖简介的同类风险；`AiSuggestions.vue:34-54` 不随 targetId/datasourceId 变化失效，可能显示先前对象建议。AI 配置/服务未接通测试，未声称真实 AI 业务发生错误。`MappingWizard.vue:594-613` 取当前资源详情而非 refs 指定快照，需与后端冻结契约审计联核，不据此独自认定冻结数据已被改写。

增强项：未单独提出纯视觉、重排目录、重命名 API、统一所有实现等偏好。本轮不以“缺少某个抽象”作为缺陷。

## 37 个页面基础覆盖

“基础覆盖”表示读取当前入口、主要 script 与相关 template 事件/分支，并追踪直接 API；不是浏览器验收，也不是每条函数执行。无独立缺陷表示未发现达到本轮证据门槛的问题，不能外推为无缺陷。

| 路由页面（均在 web/src/views/）  | 已检查的基础链路与结论                                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| auth/Login.vue                   | 配置控制注册入口、字段校验、login及redirect；认证失效链见 FE-01                                            |
| auth/Register.vue                | registration_enabled/password_min_length、校验、注册后跳转；无独立高置信缺陷                               |
| auth/ForgotPassword.vue          | 配置开关、email校验、开发 reset token 跳转、失败反馈；未调用真实接口                                       |
| auth/ResetPassword.vue           | token缺失、密码一致性、reset与login；未验证后端口令策略                                                    |
| Dashboard.vue                    | 聚合 stats、error/loading/success分支、重试、导航；错误时不展示伪零计数                                    |
| ontology/Ontologies.vue          | list/create/edit/publish/delete/designer定位；FE-03、FE-08，列表异步 R-03                                  |
| ontology/Namespaces.vue          | 列表取消、受保护/引用阻删、创建与删除；NamespaceCreateModal字段校验核对                                    |
| ontology/EntityTypes.vue         | 搜索/域筛选、stats、创建/就地命名空间、删除/详情；FE-08、R-03                                              |
| ontology/EntityDetail.vue        | 路由代次、基本编辑/重命名/属性、字典版本钉扎、发布及引用页签；R-01                                         |
| ontology/RelationTypes.vue       | brief+详情缓存、端点、创建/编辑/重命名/发布/删除；FE-08、R-03                                              |
| ontology/RelationDetail.vue      | 路由详情、端点/基数、OWL、发布、引用/校验页签；主读有generation，辅助失败空态未浏览器验收                  |
| ontology/Domains.vue             | 域树/父域候选、成员增删、详情、基本编辑、发布检查/发布、写后版本刷新；已有选择保护定向测试通过；目录 FE-08 |
| ontology/Designer.vue            | 目录/本体选择、refs/canvas、拖动清理、保存/装配/发布、新建类型、校验/AI入口；FE-05/06/08/09                |
| datasources/DataSources.vue      | create/testStored/testConnection/edit/delete、masked凭据不回传、列表取消；未触真实源连接                   |
| datasources/DataCatalog.vue      | 目录/历史快照/capture/diff、选表references、预览跳转；catalog/reference generation及卸载清理存在           |
| datasources/SamplePreview.vue    | 元数据缺失/获取/采集、schema/table/limit切换、分页预览、abort与alive；入口可自动取元数据                   |
| extraction/MappingWizard.vue     | 草稿选择/创建/保存/删除、实体/关系映射、源/本体切换、采样/发布/执行；FE-04/07/08                           |
| extraction/ExtractionRuns.vue    | useAsyncData分页、unfinished、导出锁/取消/URL清理；无独立高置信缺陷                                        |
| extraction/ExtractionTasks.vue   | options、映射发布版本、校验、创建/取消、分页轮询；FE-02/12                                                 |
| extraction/AiAssist.vue          | 本体选项、文本校验、DOCUMENT_FACTS reviewOnly面板；跨target风险见 R-04                                     |
| graph/GraphBrowse.vue            | 主图useAsyncData、查询参数、筛选、模板/路径/差异/质量叠加/导出/矩阵/中心性；FE-10、R-02                    |
| graph/GraphEntities.vue          | 服务端分页/搜索/排序、实体详情携带graph；主请求useAsyncData；证据入口未携graph属于上下文增强候选，未单列   |
| graph/GraphEntityDetail.vue      | 主详情+证据、attrs/out/in/derived、fusion、证据跳转；FE-11                                                 |
| graph/GraphEvidence.vue          | entity/fact路由查询、reverse、冻结链字段、返回实体列表；反向查询 R-02                                      |
| graph/GraphReports.vue           | revisions/report/results、四态、执行校验与切换；FE-06；revisions/report错误没有模板出口                    |
| governance/GovernanceRules.vue   | 服务端分页/过滤、编辑/保存/测试/删除、dirty禁测、四态；主列表取消及写入口busy存在                          |
| governance/StandardClauses.vue   | 分页、筛选、表单必填/更新删除及版本；取消回调 R-03                                                         |
| governance/EnumDictionaries.vue  | 分页、editorReady/controller/generation、版本历史/引用、枚举校验/CAS；未发现同类旧编辑写回问题             |
| governance/AssemblyTemplates.vue | list/editor/copy/fromOntology/instantiate、资源修订与只读builtin；API资源/本体选项有分页迭代               |
| governance/OntologyExport.vue    | 全页拉本体、revision/format、blob下载、error与URL清理；未实际验证导出文件视觉                              |
| account/Profile.vue              | loadMe后填表、profile PATCH、user store同步；就绪风险 R-04                                                 |
| account/Security.vue             | 新旧密码校验/一致性、提交/错误/清表；后端口令和会话吊销不在本分工结论内                                    |
| system/Users.vue                 | 管理员路由、创建、列表、角色/状态修改、自身保护、reset签发/复制；R-03；未发送/签发真实链接                 |
| system/Roles.vue                 | 管理员路由、角色人数列表、空/错态、用户入口；未根据前端隐藏宣称授权安全                                    |
| system/AuditLogs.vue             | 管理员路由、action筛选、分页、error空态；R-03                                                              |
| Forbidden.vue                    | 403结果及返回工作台按钮已绑定                                                                              |
| NotFound.vue                     | catch-all及返回工作台按钮已绑定；未登录由守卫先送登录                                                      |

共享模块：`api/client.ts` 的认证续期、错误归一、JSON解包；`tokens.ts` 的持久化订阅；`auth/ui/locale` 三个 store；`useAsyncData/useApiError`；主 router/导航/布局入口均已读。API层按各页面直接调用逐域核对（auth、ontology、entity-types、relations、domains、namespaces、datasources、mappings、extraction、graph、validation、governance、clauses、enum-dictionaries、templates、ai、dashboard）。`GraphCanvas` 的 resize 注册/释放、缩放/小地图和边/节点数据流已查；未据CSS或布局源码作视觉结论。

## 验证与产物

1. 定向复现：`node --test /private/tmp/knowledge-audit-20261106/frontend-repro/repro.test.mjs`，退出码0，**14/14**。这些测试断言“当前缺陷确实存在”，不是修复验收测试；修复后应反转预期并迁入项目测试。F05只支持 R-01 条件性风险。
2. 现有定向回归：`node --test web/src/views/ontology/__tests__/selection-lifecycle.test.mjs web/src/views/extraction/__tests__/mapping-wizard.test.mjs`，退出码0，**34/34**（含子测试）。通过不覆盖本报告的新情形。
3. harness 从当前源码 compileScript/esbuild，不复制实现逻辑；注入 defineExpose、render:null、内存API/消息与计时器；涉及 router 的 F01 仅将 browser history 换成 memory history；F05/F08使用真实 reactive route.params，未改页面业务判断。HTTP请求全被桩/adapter替代；UI库完整渲染/浏览器可达性边界已逐项说明。
4. 最初 harness 在先设置 window 后导入 UI 库时遇到 `document is not defined`（环境问题），随后将UI库初始化放在window桩之前解决；只有最终退出码0的结果计入上述验证。
5. 未运行全量 lint/test/build/E2E、未浏览器操作、未访问真实数据源/AI、未验证实际部署。未将本次定向测试当全局证明。

产物：

- 本报告：`/private/tmp/knowledge-audit-20261106/frontend-audit.md`
- 页面清单：`/private/tmp/knowledge-audit-20261106/frontend-page-inventory.json`
- 独立 harness：`/private/tmp/knowledge-audit-20261106/frontend-repro/harness.mjs`
- 复现测试：`/private/tmp/knowledge-audit-20261106/frontend-repro/repro.test.mjs`
- 最终复现日志：`/private/tmp/knowledge-audit-20261106/frontend-repro/results.txt`
- 原有测试日志：`/private/tmp/knowledge-audit-20261106/frontend-existing-tests.txt`

建议主代理先复核 FE-01～05 的最小修复范围，再按“数据/身份正确性→校验归属→工作流恢复→目录完整性→资源释放”实施。此次阶段保持只读，没有开始修复。
