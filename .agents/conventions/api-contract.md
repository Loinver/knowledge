# API 契约约定

前后端一体，契约自动生成，不靠口头同步。

## 1. 单一真值源

FastAPI 自动生成 OpenAPI → CI 用 `openapi-typescript` 生成 `web/src/api/schema.d.ts` 与类型化客户端。
**前端禁止手写接口类型**，需要改契约就改后端，重新生成。

## 2. 统一响应外壳

新增及实质修改的普通 JSON 接口应包裹 `{ code, message, data }`，成功与失败结构同构。现有实现仍有例外，例如业务域发布未声明 `ApiResponse` 响应模型；集成时必须核对实际端点，不能把规范当作现有接口已全部统一的验收结论。文件下载等非 JSON 响应另行处理。

```json
{ "code": "KG.OK", "message": "OK", "data": { "...业务数据..." } }
```

```json
{ "code": "KG.REVISION_CONFLICT", "message": "...", "params": {}, "data": null }
```

约定：

- 成功固定 `code = "KG.OK"`，`data` 为业务数据；无数据时 `data` 为 `null`。
- 删除类接口返回 `200 + { code: "KG.OK", data: null }`，**不再用 204 空响应**。
- `status_code=201` 仍用于「资源已创建」语义，只是响应体同样带外壳。
- 后端实现只写 `response_model=ApiResponse[X]`（`app/schemas/response.py`），
  路由直接返回裸数据即可，外壳由 `model_validator` 自动补齐；**禁止在路由里手写 dict 外壳**。
- 前端在 `web/src/api/client.ts` 的响应拦截器里解包，业务代码继续用 `res.data` 拿 payload；
  blob 下载响应不是外壳，原样透传。

### 2.1 错误契约

失败时 `code` 表达具体原因，HTTP 状态码表达大类，`data` 恒为 `null`：

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

当前实现区分发布 `revision` 与工作内容 `edit_revision`，并非统一使用一个HTTP头：

- 类型编辑使用请求体 `if_match`，编辑修订字段的要求以schema为准；域、本体与映射使用请求体 `if_match` / `if_edit_match` 或端点规定的 `If-Edit-Match`。
- 规则、条款、枚举、模板的相关更新使用 `If-Match`；部分删除、改名、发布及布局端点没有强制客户端编辑令牌。
- 匹配失败使用 `KG.REVISION_CONFLICT` 等实际错误码与参数；前端刷新上下文后让用户重新确认，不自动重放覆盖。
- 新增或实质修改写接口应明确冲突策略并测试，不能把可选令牌描述为完整防并发覆盖。已有差异见[功能台账](../../docs/product/feature-catalog.md)与[限制](../../docs/product/limitations.md)，本次文档修订不改变接口兼容性。

## 4. 版本冻结

- **本体发布**：钉住全部成员资源的具体版本号（`ontology_revision.resource_versions`）。
- **映射发布**：钉住目标本体版本。
- 上游资源升级产生新版本时，**已发布的下游不随动**，需显式升级并生成差异报告。
- 画布布局（`canvas_layout`）单独存储，**不产生语义版本**——拖节点不触发版本号变化。

## 5. 分页、筛选与排序

当前同时存在数组返回、分页对象和有限/截断列表。治理等接口使用 `page`、`page_size` 和 `{items,total,page,page_size}`；部分语义资产列表返回数组，页面收集分页后本地处理；运行、样例与图谱有各自offset或截断边界。

以OpenAPI、前端请求模块和端点实际行为确定查询参数及分页模式，不能假设所有接口支持 `sort`、`q` 或总数。新增列表应明确筛选、排序、分页/截断契约及上限，避免前端对远程分页再次切页。

## 6. 只读数据源

- 源库凭据通过后端加密存储，读取响应不回传明文；创建/替换时浏览器提交用户输入的凭据，不能误写为浏览器从不接触输入。管理员必须保管好解密密钥，详见[配置](../../docs/operations/configuration.md)。
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
