# 图谱交互验证记录

## 当前完成证据（2026-11-24）

正式 UI 已迁移到统一 shadcn-vue/Reka 体系，Naive 导入与内部选择器已删除。24 种正式布局、2 个多层关系用例和7个设计器用例合计33场，在 `knowledge-graph-final.log` 全部通过；设计器28次实际鼠标关系命中覆盖平行、反向、自环与VIEWER/冻结只读模式。图谱焦点修复由不同执行者独立复核，并在 `knowledge-final-focus-stress.log` 十轮键盘操作全部通过。真实200节点图谱/触摸协议与其余邻接浏览器证据见仓库 `docs/design-system/verification.md`。

以下为旧阶段取证，保留当时范围与限制；其中保留Naive及待审描述不代表当前状态。

## 历史实现阶段

执行者：黄药师 / EX-VISUALIZATION，直接实现与自查；独立 Quality 复核由主会话另行安排。
适用：正式 `/graph`、`/ontology/designer`。本阶段保留 Naive UI 导入/控件；不改 API、布局算法、共享 viewport、locale、主题、权限、冻结数据或结果集指针。

## 源码不变量

- marks 的视觉状态以 `mark.id` 关联 `markPositions`，业务选择仍用 `mark.iri`。拖动、取消与快照恢复不能写入节点坐标或 NaN/Infinity。
- `selectEdge(edge, aggregate)` 携带实际 renderer 边。聚合保留类型端点/count 与绘制 `kind:id`，不能回查成首条实例；单事实证据读取与文档 fact_id 不可用于聚合。
- 普通关系过滤与 timeline replay 只收窄实例，不能把实例事实标成聚合；DIRECT/DERIVED 同数字 ID、平行、反向与自环均保留各自身份。
- Esc 一次消费一个活动层：手势 → 局部图例/小地图 → 检查器；每层停止冒泡并回焦。Designer 聚焦、折叠与尺寸变化只改变相机，不能自动保存节点布局。
- Designer 无选择时检查器不占画布。断点按 `<1024` 侧栏浮层、`<768` 窄屏行为；聚焦和 ResizeObserver 共享已测区域，避免重复补偿。

## Node 与静态检查

```bash
node --test web/src/components/graph/__tests__/viewport.test.mjs \
  web/src/views/graph/browse/__tests__/*.test.mjs \
  web/src/views/ontology/designer/__tests__/designer-interactions.test.mjs

node_modules/.bin/eslint web/src/views/graph/browse/GraphBrowsePage.vue \
  web/src/views/graph/browse/components/GraphCanvas.vue \
  web/src/views/graph/browse/components/useGraphViewport.ts \
  web/src/views/graph/browse/__tests__/graph-canvas.test.mjs \
  web/src/views/graph/browse/__tests__/graph-workspace.test.mjs \
  web/src/views/ontology/designer/DesignerPage.vue \
  web/src/views/ontology/designer/__tests__/designer-interactions.test.mjs

node_modules/.bin/tsc --noEmit --target ESNext --module ESNext \
  --moduleResolution bundler --lib ESNext,DOM --types node --skipLibCheck \
  e2e/design-system-graph.spec.ts
```

本轮定向 Node 最终结果：126 tests / 126 pass / 0 fail / 0 skipped。方法 harness 使用真实 Vue script setup 与 mock API，不能代替浏览器。
ESLint 的项目配置只覆盖 web，E2E 文件另用上述 TypeScript 检查。全前端 vue-tsc 若受并行 Ui 门面错误影响，交主会话整合，不改范围外文件。

## Playwright 隔离运行

测试文件 `e2e/design-system-graph.spec.ts` 用正式路由，所有 `/api/v1/**` 请求受控；未识别请求失败，任何非 GET 请求记为失败。auth/me 是脱敏角色夹具；本轮是**真实浏览器 + 受控响应**，不宣称真实 API 或数据库主流程通过。

本机专用配置在 `/private/tmp/knowledge-graph-browser.config.mts`，仅启动独立 Vite `127.0.0.1:5207`，`reuseExistingServer=false`。API proxy 指向未使用的本地端口1，测试不启动 FastAPI，不复用开发服务、基线服务或数据库；JSON、trace、PNG 输出全部在 `/private/tmp`，不改48张基线截图。

配置的等价关键内容：

```ts
export default defineConfig({
  testDir: '<project-root>/e2e',
  testMatch: 'design-system-graph.spec.ts',
  outputDir: '/private/tmp/knowledge-graph-browser-results',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 8000 },
  use: {
    baseURL: 'http://127.0.0.1:5207',
    browserName: 'chromium',
    locale: 'zh-CN',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: './node_modules/.bin/vite --host 127.0.0.1 --port 5207 --strictPort',
    cwd: '<project-root>/web',
    url: 'http://127.0.0.1:5207/login',
    reuseExistingServer: false,
    env: { KG_API_PROXY_TARGET: 'http://127.0.0.1:1' },
  },
})
```

```bash
node_modules/.bin/playwright test --config=/private/tmp/knowledge-graph-browser.config.mts
```

该配置需要现有 Chromium 与本地监听能力；本轮沙箱 EPERM 后通过审批运行同一隔离配置。未安装工具或修改工具配置。

## 逐 renderer 矩阵

每个布局测试分别实际执行：普通 wheel 平移、Control/Meta 鼠标锚定缩放、方向键、Home fit、下表的模式专项。鼠标输入使用整数 client 坐标，避免把浏览器坐标取整误判成缩放漂移。每个通过的用例附独立 renderer PNG/JSON，记录业务 route、布局、viewport、Chromium 版本、locale、脱敏数据与哈希。

最终完成结果：31/31 浏览器场景通过（24布局 + 7 Designer），Chromium 153.0.8010.12。
完整矩阵 `/private/tmp/knowledge-ui-graph-matrix.json`；运行日志 `/private/tmp/knowledge-graph-browser-final.log`。
其中 supply_chain、timeline、bipartite 的近邻多事实点击先用真实 Ctrl anchored zoom 放大，测试 annotation 记录该条件；不以 force click 或合成 click 冒充命中。

层级模式使用星型父子夹具，验证同端点多业务ID与方向，不覆盖所有多层关系路由。
本轮另在多层链夹具的 equity_tree/clan_tree 发现 DIRECT:13 路径经过中间节点并与 DIRECT:12 完全共线，后绘制边遮挡前边；放大也无法命中。
该范围外布局/路由问题未修复（当前任务禁止修改layout），证据 `/private/tmp/knowledge-graph-collinear-hit-evidence.json` 和 `/private/tmp/knowledge-graph-collinear-hit-error.txt` 已交主会话。
星型矩阵通过不能作为这类多层共线路由通过的证据。

| layout          | renderer            | 模式专项                                                                                 |
| --------------- | ------------------- | ---------------------------------------------------------------------------------------- |
| type_grid       | node-edge           | 双平行事实、同数字派生ID、反向/双自环真实路径点击与Space选择                             |
| ring            | node-edge           | 同上                                                                                     |
| force           | node-edge           | 同上                                                                                     |
| org_tree        | node-edge           | 有效层级关系配置、双平行与同数字派生ID点击                                               |
| indent_tree     | node-edge           | 同上                                                                                     |
| equity_tree     | node-edge           | 同上                                                                                     |
| control_chain   | node-edge           | 同上                                                                                     |
| supply_chain    | node-edge           | 平行/派生/反向/自环点击                                                                  |
| timeline        | node-edge           | 有效时间字段，平行/派生/反向/自环点击；replay身份另有宿主方法测试                        |
| schema          | aggregate node-edge | 类型端点/count，DIRECT与DERIVED同数字ID分别点击；禁用单事实证据/文档fact_id              |
| clan_tree       | node-edge           | 有效层级配置、双平行与同数字派生ID点击                                                   |
| cycle_view      | node-edge           | 平行/派生/反向/自环点击                                                                  |
| bipartite       | node-edge           | 同上                                                                                     |
| community       | node-edge           | 同上                                                                                     |
| nary            | node-edge           | 同上；原有200节点容量验证仍是另一个验收范围                                              |
| sankey          | aggregate node-edge | 类型端点/count、两kind点击、禁用单事实证据                                               |
| chord           | aggregate node-edge | 同上                                                                                     |
| geo             | node-edge           | 配置经纬度；当前语义renderer无关系边，诚实断言edge数0                                    |
| impact          | node-edge           | 有效层级配置、双平行与同数字派生ID点击                                                   |
| sunburst        | sector marks        | 有效measure，IRI键盘选择；真实鼠标拖/完成、Esc、pointercancel、原生lostcapture、快照恢复 |
| treemap         | rect marks          | 同上                                                                                     |
| pack            | circle marks        | 同上                                                                                     |
| gantt           | bar marks           | 有效time，IRI选择与上述拖/取消/快照恢复                                                  |
| small_multiples | node-edge           | 有意采样/收窄后仍可命中的平行/派生/反向/自环                                             |

Designer 额外覆盖：1440、1024、1023、768、767宽度，空检查器空间、选择居中、折叠恢复、一次Esc逐层消费和回焦；relation IDs 3/4平行、5反向、6自环。另有 VIEWER 和冻结版本的只读选择/相机/取消，无保存动作。

pointercancel 在实际 renderer 上用明确的合成取消事件；lostpointercapture 通过浏览器原生 releasePointerCapture 触发，鼠标拖拽/键盘输入是真实浏览器输入。未测真实多点触摸或所有物理设备，不把这些命令推广为完整设备验收。

最终浏览器结果已核对本轮 `/private/tmp/knowledge-graph-browser-results.json` 的31条 completed passed status，进程退出0；测试文件存在/--list/启动不算通过。独立 Quality 尚未执行，保留 INCONCLUSIVE。

## 相邻业务与文案

`/extraction` 映射的 graph 按钮当前仅为 HTML 卡片、关系标签和装饰 SVG 箭头的静态概览；没有画布 wheel/zoom、关系命中或fit/focus。本批不替换它的图引擎，不伪装支持。

本阶段没有新增用户文案，复用现有 graph/designer i18n keys；待主会话的 `ds/graph.*` 缺键清单为空。Ui迁移稳定契约尚待主会话，当前补丁没有替换Naive导入。
