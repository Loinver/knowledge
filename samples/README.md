# samples · 样例源库

用于端到端验证与 CI 的虚构业务数据。核验日期：2026-11-26；当前随仓 SQLite 含17张表，不是早期六表快照。操作入口见[快速入门](../docs/user-guide/quickstart.md)。

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

## 当前表与安全重建

当前表：`enterprise`、`hr_employee`、`ct_contract`、`ct_contract_project`、`ct_contract_party`、`pm_project`、`pm_project_member`、`org_department`、`org_position`、`org_employment`、`org_executive_role`、`eq_shareholder`、`eq_equity_holding`、`person_relation`、`crm_customer`、`crm_supplier`、`crm_trade_transaction`。

样例包含异常与冲突记录，用于校验和失败处理，不保证零隔离。源库与平台元数据库必须分开。`seed.sql` 包含 DROP；需要重建时按[快速入门](../docs/user-guide/quickstart.md)创建新临时文件，不能对已有业务库或元数据库执行。后端读取路径必须指向后端机器可访问的文件。
