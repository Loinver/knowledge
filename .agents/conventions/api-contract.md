# API 契约约定

前后端一体，契约自动生成，不靠口头同步。

## 1. 单一真值源

FastAPI 自动生成 OpenAPI → CI 用 `openapi-typescript` 生成 `web/src/api/schema.d.ts` 与类型化客户端。
**前端禁止手写接口类型**，需要改契约就改后端，重新生成。

## 2. 错误契约

统一结构，HTTP 状态码表达大类，`code` 表达具体原因：

```json
{
  "code": "KG.REVISION_CONFLICT",
  "params": { "resource": "type:Employee", "expected": 7, "actual": 9 },
  "message": "Revision conflict"
}
```

| HTTP | 含义              | 典型 code                                         |
| ---- | ----------------- | ------------------------------------------------- |
| 400  | 请求本身不合法    | `KG.INVALID_IRI` `KG.INVALID_NAME`                |
| 404  | 资源不存在        | `KG.RESOURCE_NOT_FOUND`                           |
| 409  | **版本/状态冲突** | `KG.REVISION_CONFLICT` `KG.ALREADY_PUBLISHED`     |
| 422  | 语义校验违反      | `KG.VALIDATION_VIOLATION`                         |
| 503  | 外部依赖不可用    | `KG.SOURCE_UNREACHABLE` `KG.REASONER_UNAVAILABLE` |

规则：

- `message` 只是兜底英文，**界面永远用 `code` 走 i18n**，不要把 `message` 直接展示给用户。
- 未见过的 `code`，前端应显示「未知错误 + code」，不要吞掉。

## 3. 并发控制（乐观锁）

所有写资源接口必须带 `If-Match: <revision>`：

- 匹配失败 → `409 KG.REVISION_CONFLICT`，返回 `expected`/`actual`，前端提示「资源已被他人更新，请刷新」。
- 禁止「后打开的页面静默覆盖先写入的更新」。

## 4. 版本冻结

- **本体发布**：钉住全部成员资源的具体版本号（`ontology_revision.resource_versions`）。
- **映射发布**：钉住目标本体版本。
- 上游资源升级产生新版本时，**已发布的下游不随动**，需显式升级并生成差异报告。
- 画布布局（`canvas_layout`）单独存储，**不产生语义版本**——拖节点不触发版本号变化。

## 5. 分页、筛选与排序

统一查询参数：`page`、`page_size`、`sort`、`q`。
统一响应：`{ "items": [...], "total": N, "page": P, "page_size": S }`。
列表接口一律支持这些参数，前端表格组件依赖它做服务端分页（大数据量走 M-13 分级展示）。

## 6. 只读数据源

- 源库凭据**只存在后端**（后续加密存储），浏览器只拿可展示配置与健康状态。
- 连接器强制只读：不允许执行写语句，连接层拦截。
- 样例预览限制行数与时间；**密码不得进入页面存储、导出包与运行日志**。

## 7. 校验四态

校验结论必须是四态之一，且**未经执行的项必须返回 `NOT_RUN`**：

| 码          | 含义       | UI                      |
| ----------- | ---------- | ----------------------- |
| `PASS`      | 通过       | 绿                      |
| `VIOLATION` | 违反       | 红                      |
| `NA`        | 不适用     | 灰                      |
| `NOT_RUN`   | **未执行** | 橙 + 明确文案「未执行」 |

把「未执行」渲染成通过、或在未接入推理器时报 PASS，属于合规事故。
