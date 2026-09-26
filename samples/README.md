# samples · 样例源库

M2 阶段的正式交付物，用于端到端验证与 CI。

## 要求（缺一不可）

样例库是一个**只读**的关系库，必须覆盖三类关系结构：

1. **外键**：如 `hr_employee.enterprise_id → enterprise.id`
2. **中间表**：如 `ct_contract_project`（仅两列外键）
3. **带属性关联表**：如 `pm_project_member`，且**必须包含同一对实体的两条参与记录**
   （用于验证带属性关系不会被三元组去重成一条，证据不丢失）

同时必须覆盖五类经营知识场景的源数据结构（缺一不可）：

| 场景     | 表                                                                             | 关键结构                                            |
| -------- | ------------------------------------------------------------------------------ | --------------------------------------------------- |
| 部门层级 | `org_department` / `org_position` / `org_employment`                           | `parent_id` 自引用（四层两棵树 + 孤儿 99）          |
| 股权架构 | `eq_shareholder` / `eq_equity_holding`                                         | `PERSON/ENTERPRISE` 多态股东；合计 160%/105% 异常   |
| 人物关系 | `person_relation` / `org_executive_role`                                       | 上下级/同事/亲属 + 高管任职                         |
| 客商     | `crm_customer` / `crm_supplier` / `crm_trade_transaction`                      | 双表共享信用代码 `91310000DEMA000006`（双角色融合） |
| 合同     | `ct_contract_party` / `ct_contract.handler_employee_id` / `parent_contract_id` | 签约方角色 + 经办人 + 补充协议自引用                |

## 交付内容

- `seed.sql`：建表 + 灌数脚本（可重放，先 DROP 后建）
- `enterprise_demo.sqlite`：可直接挂载的 SQLite 库（默认内置）
- 数据一律脱敏：域名用 `example.org`，信用代码用 `91310000DEMA000001` 形式的虚构值

## 用途

M3 的 8 步贯通测试跑在这份数据上：建类型 → 装配本体 → 配映射 → 跑抽取 → 验证幂等 → 制造失败 → 追溯证据。
五场景数据用于验收：多态股东判别映射、跨表业务键融合、部门无环/持股合计/签约方规则、组织树与股权穿透图谱形态。

> 注意：`enterprise_demo.sqlite` 是旧版六表快照。重建五场景完整库请执行
> `sqlite3 enterprise_demo.sqlite < seed.sql`。
