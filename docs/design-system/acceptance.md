# 需求与验收映射

> 历史资料说明（2026-11-26补注）：本文保留原日期、基线和当时结论，不代表当前能力或本轮验收；当前入口见[文档中心](../README.md)。

日期2026-11-24。原始目标为完整知识管理工作台迁移，当前规格仍是 [README.md](./README.md)。下表将用户要求映射到实现与直接证据；不会用源码盘点替代行为验收。

| 原始要求                 | 实际实现与产物                                                                                                                            | 验收证据                                                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| A盘点/规格/契约/迁移范围 | 源码基线13b5a3a；初始86文件；41route页；唯一规格README、组件/表格/控件/token/dependency文档、migration.json                               | 初始盘点与before截图；最终inventory0 runtime残留                                                          |
| 稳定官方Vue/Reka路线     | 精确Reka/Tailwind/TanStack/VeeValidate依赖；24组官方registry、源码hash/版权、本地适配；无CLI运行依赖                                      | 许可证web172通过、vue-tsc/构建通过、独立源码/来源审查；原有Pinia peer限制单独记录                         |
| 表单体系及至少两域复用   | FormContainer/Field、Section、字段帮助与错误、Actions、DialogForm/SheetForm；实体类型与知识库真实试点后共享；字段/权限/请求留域内         | pilot5场、C1动态/跨字段/精度、C2日期/布尔、C4失败/草稿/迟到响应；对应实际Node与浏览器日志                 |
| 受控搜索表格             | SearchPanel/SearchTable/TableToolbar/RowActions；rows/columns/total/page/pageSize/sort/filters/selection；local/remote/none契约明确       | 知识库实际远程total/排序页码、账号远程筛选、实体local、任务运行unknown total、查询隔离/乱序测试；共享20场 |
| 状态、失败保护与数据语义 | 必填首错关联、帮助和错误分离、无效零写、busy锁、失败留稿、revision/会话归属、0/false/null类型                                             | 真实请求payload和次数断言；四态报告/冻结M3/审计纠错、融合失败当前结果集保护与关系独立身份                 |
| 全局样式与token真值源    | tokens.css唯一语义值，global.css层级/reset，ui.css；accent主操作与shadcn accent表面分开；ThemeMode/偏好沿用                               | 明暗、shell几何、四档截图；按钮面与fixed列真实渲染检查；所有图renderer引用同token                         |
| 基础原语/业务边界与清理  | 官方Button/Input/Select/Combobox/Checkbox/Tabs/Dialog/Sheet/Popover/Tooltip/Menu/Table/Pagination；Toast用Reka；10 business+37 Ui真实消费 | components/controls/table实例与页面引用；架构175项；无Naive依赖/Provider/theme/CSS/测试挂钩/Vite分包      |
| 国际化三层               | 2180双语key；原语默认文案与ARIA使用vue-i18n，数量/日期Intl，机读名/IRI不翻译，缺译显式标记；英文留空不伪造                                | real i18n缺键/插值、标签setup3场、浏览器mapping/export/domain3场；独立R1–R3关闭                           |
| 响应式                   | 桌面优先，768/1024/1280统一断点；导航drawer、搜索换行、table bounded scroll、长form footer、空inspector折叠                               | 1440×900/1280×720/768×1024/390×844，DPR1/zoom1；48对无文档水平溢出；shell5场与领域长弹层                  |
| 图谱交互逐模式           | 保留SVG/D3，24布局；wheel pan/Ctrl-Meta anchored zoom、空白拖动、显式fit/恢复、节点/关系选择、Esc/键盘；aggregate与实例身份分开           | 正式33场、200-node nary、Designer28次鼠标关系命中、focus stress10、图导出/历史/扩展取消；每模式JSON/PNG   |
| 独立复核/每批PDCA        | Chief实施；不同执行者独立review；发现源码/查询/草稿/路径/焦点/只读/缺译后修复复验                                                         | Anscombe/Volta/James/Laplace完成报告，各限定PASS；上游502失败调用未算完成                                 |
| 完工命令与交付           | make lint/test、build、i18n/API/license；changes路径清单、preview和48对gallery                                                            | verification.md与browser-acceptance.json，实际本机服务8145/5260及六页构建smoke                            |

## 真实证据与边界

默认317场景逐项有completed pass，由分批保留成功场景和受影响复跑合成，不是一轮不中断运行。治理5、合成AI检索1、合成AI建模2、目录内9另外执行。真实API链使用每次独立临时数据库；控件/图模式/缺译/故障用受控响应时明确记录。

已验证范围包含新建/编辑/readonly/disabled/busy/成功/失败、字段路径/关联、动态/跨字段、键盘/首错焦点、草稿拒绝丢弃、保存失败/迟到响应、搜索重置/分页/排序、权限、冻结与四态。需要外部生产环境、CI/部署、物理触摸/读屏、所有浏览器引擎或外部模型质量的结论仍为未验证，不扩大本地证据。性能只保留测量数据，不声称迁移加速。

原始API、生成类型、后端策略与存储格式无改动。业务域空英文的省略使用现有DomainCreate/Update可选字典语义；历史数据和冻结快照不回写。完整日志、独立报告、临时截图、已知Pinia与外层workspace依赖限制在 [verification.md](./verification.md) 与 [dependencies.md](./dependencies.md)。
