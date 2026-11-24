# 设计系统依赖、许可与上游维护

核对日期：2026-11-23。本页以 [web/package.json](../../web/package.json)、[pnpm-lock.yaml](../../pnpm-lock.yaml)、[许可门禁脚本](../../scripts/check-web-licenses.mjs)、[THIRD_PARTY_LICENSES.md](../../web/src/components/ui/THIRD_PARTY_LICENSES.md) 及实际完成日志为依据。上游缓存和版权记录是维护来源；本轮只更新文档，不安装依赖或运行产品。

## 当前状态

- 当前 web 生产与开发依赖许可扫描已通过：`/private/tmp/knowledge-final-licenses.log` 记录命令 `node scripts/check-web-licenses.mjs --include-dev`，最终成功输出为 **Web production and development licenses OK: 172 packages**。本轮实际读取该完成日志，没有另行运行扫描；172 是门禁按 license/name 包记录统计的数量。
- 许可门禁已包含本任务批准的 tslib@2.8.1 / 0BSD，以及 lightningcss@1.33.0 与同版本官方平台包的 **仅开发扫描 MPL-2.0 例外**。旧文档“完整 web dev 未通过 / MPL 未准入”的结论已被这次批准与完成日志取代；精确边界见下节。
- Naive UI 已从 App Provider、theme、legacy.css、Vite chunk、web 包清单和锁文件移除。App.vue 使用 UiFeedbackProvider，main.ts 导入 global.css；Vite 当前使用 Vue + Tailwind 插件，manualChunks 为 vue-vendor 与 d3-vendor。项目 CSS 的旧语义 token 别名仍在，含义见 [tokens.md](./tokens.md)。
- 外层 workspace 既存 dev 许可缺口与 Pinia devtools peer 不匹配分别保留。web 的 172 项通过不等于整个 workspace 已准入，也不证明 peer 兼容、构建或浏览器验收。

## 精确依赖

| 类型    | 包                       | 版本   | 许可       | 消费依据                          |
| ------- | ------------------------ | ------ | ---------- | --------------------------------- |
| runtime | reka-ui                  | 2.11.0 | MIT        | 官方交互原语                      |
| runtime | cn                       | 0.5.2  | MIT        | utils/原语class合并               |
| runtime | class-variance-authority | 0.7.1  | Apache-2.0 | Button/Badge/Field/InputGroup变体 |
| runtime | @lucide/vue              | 1.77.0 | ISC        | 关闭/选择/分页图标                |
| runtime | @vueuse/core             | 14.1.0 | MIT        | reactiveOmit、useVModel等官方导入 |
| runtime | @tanstack/vue-table      | 9.3.1  | MIT        | UiDataTable 的类型化表格与行模型  |
| runtime | vee-validate             | 4.15.1 | MIT        | FormContainer 函数规则校验        |
| dev     | tailwindcss              | 4.3.5  | MIT        | 全局CSS编译                       |
| dev     | @tailwindcss/vite        | 4.3.5  | MIT        | web/vite.config.ts插件            |
| dev     | tw-animate-css           | 1.4.0  | MIT        | Dialog/Sheet/Select等动画utility  |

这些设计系统直接依赖在包清单中精确锁定；Vue、TypeScript、Vite、Pinia 等原有包的声明仍以 package.json 为准。当前安装的 Pinia@4.0.3 要求 @vue/devtools-api ^8.1.5，而安装路径/锁定 peer 实例为 7.7.10；因此 peer 范围问题仍存在。历史安装前的 6.6.4 同样不满足，不能归因于本次新增许可闭包，也不能因许可门禁通过而标记解决。

历史安装使用以下命令（此文档轮未执行）：

```sh
pnpm -C web add -E reka-ui@2.11.0 cn@0.5.2 class-variance-authority@0.7.1 @lucide/vue@1.77.0 @vueuse/core@14.1.0 @tanstack/vue-table@9.3.1 vee-validate@4.15.1 --ignore-scripts
pnpm -C web add -DE tailwindcss@4.3.5 @tailwindcss/vite@4.3.5 tw-animate-css@1.4.0 --ignore-scripts
```

没有新增 Zod、VeeValidate 适配器、Sonner 或 CLI 运行时依赖。原语目录共有 **24 组、149 个 Vue/TS 文件、24 份 upstream.registry 原始快照**，总计 173 个源码/快照文件。InputGroup 与 Textarea 属于 Combobox 的真实源码依赖；Toast 与 Tree 在当时 reka-nova registry 取证中返回 404，现由本地门面直接使用 Reka，不虚构上游缓存组。

## 源码来源与可复现快照

源码来自 reka-nova registry。每个 upstream.registry 保留当时下载的原始字节；下表 SHA256 针对快照，不是已做本地适配的 Vue 文件。此次用本地文件重新计算，24 份 hash 均与表中记录一致。源码头保留来源 URL/hash。CLI 2.9.0 是维护工具与 MIT 许可取证版本，不能将它或上游 main SHA 冒称站点组件的发布版本。

| 组件目录      | origin URL                                                       | 原始registry SHA256                                                | 本地源码文件                                                                                                                                                                                                                                                                                                                                                            |
| ------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| button        | https://www.shadcn-vue.com/r/styles/reka-nova/button.json        | `669f536a5d4cd520e5e0d0263e0e9f35064751b2c07358e48379d575ceb8d174` | Button.vue, index.ts                                                                                                                                                                                                                                                                                                                                                    |
| input         | https://www.shadcn-vue.com/r/styles/reka-nova/input.json         | `169dec8a6fe7086c781506a4a2d6db7873dc4b58b47032c1b5b4dd77a24a6d3f` | Input.vue, index.ts                                                                                                                                                                                                                                                                                                                                                     |
| label         | https://www.shadcn-vue.com/r/styles/reka-nova/label.json         | `f5fc8f62f50069c0f62bb83af04e0530aafb05d8c8852a3d03b289bdf6096aee` | Label.vue, index.ts                                                                                                                                                                                                                                                                                                                                                     |
| separator     | https://www.shadcn-vue.com/r/styles/reka-nova/separator.json     | `3067c4d7ff701976f93fbaf6b1b0949d72b02b5059c7c6e915fca10e00f4bf22` | Separator.vue, index.ts                                                                                                                                                                                                                                                                                                                                                 |
| field         | https://www.shadcn-vue.com/r/styles/reka-nova/field.json         | `118c9008651ead02e6e4cf683eccacce193d0bd98f982355e1dc4a44dc669bc2` | Field.vue, FieldContent.vue, FieldDescription.vue, FieldError.vue, FieldGroup.vue, FieldLabel.vue, FieldLegend.vue, FieldSeparator.vue, FieldSet.vue, FieldTitle.vue, index.ts                                                                                                                                                                                          |
| card          | https://www.shadcn-vue.com/r/styles/reka-nova/card.json          | `b92c5cb516bc2300fbedf10c9428a5fa2647b4a8a2516b0eb98ca840a80ff07d` | Card.vue, CardAction.vue, CardContent.vue, CardDescription.vue, CardFooter.vue, CardHeader.vue, CardTitle.vue, index.ts                                                                                                                                                                                                                                                 |
| badge         | https://www.shadcn-vue.com/r/styles/reka-nova/badge.json         | `3169a42c7c3723690b92044a47d8619f36840bb4a528cd9cf5c63c7c2e7b8bf4` | Badge.vue, index.ts                                                                                                                                                                                                                                                                                                                                                     |
| select        | https://www.shadcn-vue.com/r/styles/reka-nova/select.json        | `5c2568274e2ab9c42f373cbed8747d3fa4449bb18c0529cebebd5c2b15514b6c` | Select.vue, SelectContent.vue, SelectGroup.vue, SelectItem.vue, SelectItemText.vue, SelectLabel.vue, SelectScrollDownButton.vue, SelectScrollUpButton.vue, SelectSeparator.vue, SelectTrigger.vue, SelectValue.vue, index.ts                                                                                                                                            |
| combobox      | https://www.shadcn-vue.com/r/styles/reka-nova/combobox.json      | `fbe5e77d4dbee65a561026fcaa51d0735ab0aa42319741f009fe03cb69c13cd1` | Combobox.vue, ComboboxAnchor.vue, ComboboxEmpty.vue, ComboboxGroup.vue, ComboboxInput.vue, ComboboxItem.vue, ComboboxItemIndicator.vue, ComboboxList.vue, ComboboxSeparator.vue, ComboboxTrigger.vue, ComboboxViewport.vue, index.ts                                                                                                                                    |
| checkbox      | https://www.shadcn-vue.com/r/styles/reka-nova/checkbox.json      | `7e5b5360d2262e49b73affc37f6090eb207c017c70f6be63f842037fce36432c` | Checkbox.vue, index.ts                                                                                                                                                                                                                                                                                                                                                  |
| switch        | https://www.shadcn-vue.com/r/styles/reka-nova/switch.json        | `7751c2c85ba4e979e1f0be9aa59d8b9433960e2c6dad45491ff8dd39b351c2d9` | Switch.vue, index.ts                                                                                                                                                                                                                                                                                                                                                    |
| tabs          | https://www.shadcn-vue.com/r/styles/reka-nova/tabs.json          | `f2c275bc4026050f6d5b447a38a2e3802e55d8adfd27c172c73401339cb7b25f` | Tabs.vue, TabsContent.vue, TabsList.vue, TabsTrigger.vue, index.ts                                                                                                                                                                                                                                                                                                      |
| dialog        | https://www.shadcn-vue.com/r/styles/reka-nova/dialog.json        | `b1d0a48ef9dc6f71ad128761ceb1a957901306d2e097cd7ee20c703388c5db03` | Dialog.vue, DialogClose.vue, DialogContent.vue, DialogDescription.vue, DialogFooter.vue, DialogHeader.vue, DialogOverlay.vue, DialogScrollContent.vue, DialogTitle.vue, DialogTrigger.vue, index.ts                                                                                                                                                                     |
| sheet         | https://www.shadcn-vue.com/r/styles/reka-nova/sheet.json         | `50d9ab833ab47e1c15a81bfd4cf77736464b17a29c81a965ff20607054177cab` | Sheet.vue, SheetClose.vue, SheetContent.vue, SheetDescription.vue, SheetFooter.vue, SheetHeader.vue, SheetOverlay.vue, SheetTitle.vue, SheetTrigger.vue, index.ts                                                                                                                                                                                                       |
| popover       | https://www.shadcn-vue.com/r/styles/reka-nova/popover.json       | `3f33d437a9a8b8b9fcacf715da1509907301d509c51664a00ff6b2d577e6be45` | Popover.vue, PopoverAnchor.vue, PopoverContent.vue, PopoverDescription.vue, PopoverHeader.vue, PopoverTitle.vue, PopoverTrigger.vue, index.ts                                                                                                                                                                                                                           |
| tooltip       | https://www.shadcn-vue.com/r/styles/reka-nova/tooltip.json       | `fe056a94c99234c71b2e9e3f9db387510d371b8ce6d6c9975793fe0ceeda1e64` | Tooltip.vue, TooltipContent.vue, TooltipProvider.vue, TooltipTrigger.vue, index.ts                                                                                                                                                                                                                                                                                      |
| dropdown-menu | https://www.shadcn-vue.com/r/styles/reka-nova/dropdown-menu.json | `ef4ef416d50abe38e977e0384bae1125611cc3e67bb47cb7dee2ac36e64ee9e9` | DropdownMenu.vue, DropdownMenuCheckboxItem.vue, DropdownMenuContent.vue, DropdownMenuGroup.vue, DropdownMenuItem.vue, DropdownMenuLabel.vue, DropdownMenuRadioGroup.vue, DropdownMenuRadioItem.vue, DropdownMenuSeparator.vue, DropdownMenuShortcut.vue, DropdownMenuSub.vue, DropdownMenuSubContent.vue, DropdownMenuSubTrigger.vue, DropdownMenuTrigger.vue, index.ts |
| table         | https://www.shadcn-vue.com/r/styles/reka-nova/table.json         | `0a72dcee002588a7e031379ce632a65ff7eb0f4479ea87f75678db4f48e822a3` | Table.vue, TableBody.vue, TableCaption.vue, TableCell.vue, TableEmpty.vue, TableFooter.vue, TableHead.vue, TableHeader.vue, TableRow.vue, index.ts                                                                                                                                                                                                                      |
| pagination    | https://www.shadcn-vue.com/r/styles/reka-nova/pagination.json    | `fac92217aaf383274e3db4c0918db5ae13f17edb259529d9a7d8c9da193d6589` | Pagination.vue, PaginationContent.vue, PaginationEllipsis.vue, PaginationFirst.vue, PaginationItem.vue, PaginationLast.vue, PaginationLink.vue, PaginationNext.vue, PaginationPrevious.vue, index.ts                                                                                                                                                                    |
| collapsible   | https://www.shadcn-vue.com/r/styles/reka-nova/collapsible.json   | `4a6155a921abeabd0de8efbc944dde16bce47652a0a76e08e80fbfc765b132c2` | Collapsible.vue, CollapsibleContent.vue, CollapsibleTrigger.vue, index.ts                                                                                                                                                                                                                                                                                               |
| slider        | https://www.shadcn-vue.com/r/styles/reka-nova/slider.json        | `8342c7ff50661a1e6bcbb12e9dd8cf2780321935b86c8828cf204449c8195ee4` | Slider.vue, index.ts                                                                                                                                                                                                                                                                                                                                                    |
| radio-group   | https://www.shadcn-vue.com/r/styles/reka-nova/radio-group.json   | `c78b007aafb35cb8dfaa2265900f0883eb94369db6d2b295bd18c143c64ed77d` | RadioGroup.vue, RadioGroupItem.vue, index.ts                                                                                                                                                                                                                                                                                                                            |
| input-group   | https://www.shadcn-vue.com/r/styles/reka-nova/input-group.json   | `128d4c1d4a279152f73826699d795b0faa34d308851c92a39b739a5504ebc3e5` | InputGroup.vue, InputGroupAddon.vue, InputGroupButton.vue, InputGroupInput.vue, InputGroupText.vue, InputGroupTextarea.vue, index.ts                                                                                                                                                                                                                                    |
| textarea      | https://www.shadcn-vue.com/r/styles/reka-nova/textarea.json      | `d53ac9b8bb98d49b4fa494039a2c38beff25bb46bd8c3739e68c8a0461bc401f` | Textarea.vue, index.ts                                                                                                                                                                                                                                                                                                                                                  |

所有目录位于 `web/src/components/ui/primitives/<name>/`，每个目录另有 `upstream.registry`，未参与运行时import。复制只保留官方原语文件，未复制演示页面、demo素材或业务逻辑。

## 本地适配与版权

- 原语内部导入统一为 `@/components/ui/primitives/<name>`，cn/utils 指向 `@/components/ui/utils`。各目录 index.ts 是原语导出；项目公开 Ui/business 门面由 [ui/index.ts](../../web/src/components/ui/index.ts) 提供，两者分工不同。
- [components.json](../../web/components.json) 使用 style=reka-nova、TypeScript、cssVariables；CSS 入口为 src/styles/global.css，aliases.ui 指向 primitives，aliases.utils 指向 ui/utils。CLI 导入不能覆盖现有项目样式。
- 本地原语将上游 data-open/data-checked/data-active 等变体适配为 Reka 2.11 的 data-state；Tooltip 保留 instant-open/delayed-open。暗色使用 data-theme custom variant；不创建第二主题 store。
- Dialog/Sheet 使用 z-dialog，Popover/Select/Combobox/DropdownMenu 使用 z-popover，Tooltip 使用 z-tooltip；控件高度与圆角映射 control-height、radius-*，百分比/视口/Reka 可用尺寸保留结构含义。
- 关闭和分页默认文本通过 usePrimitiveI18n 调用全局 ds.primitives.close/first/last/next/previous/more。Pagination 导航按钮保留调用方显式 aria-label；业务标题/空态由插槽或门面提供。

完整版权与许可证继续保存在 [THIRD_PARTY_LICENSES.md](../../web/src/components/ui/THIRD_PARTY_LICENSES.md)，包括 shadcn-vue 的 Copyright (c) 2023 unovue、各精确依赖的声明、Lucide/Feather 双来源版权、type-fest 的 MIT/CC0 原文、tslib 的 LICENSE/CopyrightNotice 及 lightningcss 的 MPL 全文。复制/升级源码时保留来源头和这些声明；本页的准入状态描述以项目脚本为准。

## 许可例外的精确边界

门禁通用允许集仍是 MIT、BSD-2-Clause、BSD-3-Clause、Apache-2.0、ISC、PSF-2.0、Python-2.0。以下三项不扩大为新的通用许可族准入：

| 包 / 表达式                         | 当前脚本条件                                                                                                   | 范围                                                                   |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| type-fest / (MIT OR CC0-1.0)        | 包名精确为 type-fest，versions 非空且全部为 4.41.0，表达式精确匹配；本任务选择 MIT                             | 不接受 CC0-only、其他版本/包/组合，混合版本组仍拒绝                    |
| tslib / 0BSD                        | 2026-11-23 批准；包名精确为 tslib，versions 非空且全部为 2.8.1，license 精确为 0BSD                            | 不开放通用 0BSD，其他版本/包不受此例外覆盖                             |
| lightningcss 及官方平台包 / MPL-2.0 | 2026-11-23 批准；scope=development，包名在脚本显式集合内，versions 非空且全部为 1.33.0，license 精确为 MPL-2.0 | 仅本次 Tailwind 构建依赖；production 门禁仍拒绝 MPL，其他包/版本仍拒绝 |

MPL 例外的名称集合来自 lightningcss@1.33.0 的 optionalDependencies，并由脚本逐名列举，不是宽泛前缀匹配：lightningcss 本体，以及 lightningcss-darwin-x64、lightningcss-linux-x64-gnu、lightningcss-win32-x64-msvc、lightningcss-win32-arm64-msvc、lightningcss-darwin-arm64、lightningcss-linux-arm64-gnu、lightningcss-linux-arm-gnueabihf、lightningcss-linux-arm64-musl、lightningcss-linux-x64-musl、lightningcss-freebsd-x64、lightningcss-android-arm64，均限 1.33.0。

依赖链为 @tailwindcss/vite@4.3.5 → @tailwindcss/node@4.3.5 → lightningcss@1.33.0。第三方声明记录两份已安装包的 LICENSE 字节一致并完整保留一次。升级包名、版本、扫描 scope 或许可表达式时重新核验，不自动继承此次批准。

`--include-dev` 将 web 的生产与开发闭包一并送入 development 评估；不带此参数使用 production 评估。脚本对报告结构、非空版本组和未知许可保持失败关闭；读取 pnpm JSON 成功本身不等于准入成功。

## 外层 workspace 与历史记录

外层 workspace 既存 dev 依赖不在本次 web 扫描通过的结论内。上一次完整 workspace 报告记录下列未被此次精确例外覆盖的组；本轮未重新扫描，因此不把历史计数当作当前计数，也不宣称这些缺口已解决。

| 历史包/版本组                                                                                       | 当时许可            | 与当前 web 通过的关系                        |
| --------------------------------------------------------------------------------------------------- | ------------------- | -------------------------------------------- |
| jackspeak@3.4.3、minimatch@10.2.6、minipass@7.1.3、package-json-from-dist@1.0.1、path-scurry@1.11.1 | BlueOak-1.0.0       | 外层 workspace 原有 dev 闭包，未获新通用例外 |
| JSONStream@1.3.5                                                                                    | (MIT OR Apache-2.0) | 通用门禁不自动放行未单独核验的 OR 表达式     |
| type-fest@0.21.3,4.41.0                                                                             | (MIT OR CC0-1.0)    | 混合版本组不满足只含 4.41.0 的精确条件       |

| 历史阶段记录                                                                       | 当前解释                                                                         |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 首次 prod 扫描因 tslib/0BSD 失败；例外后 prod 122 项通过                           | 属于批准前后两次历史快照，122 不是当前含 dev 扫描数量                            |
| 旧 web 完整闭包 192 条记录、2 项 MPL 未准入                                        | 发生于 MPL 例外批准前及 Naive 移除前；当前已由真实 web 含 dev 172 项成功日志取代 |
| 旧 workspace 完整闭包 482 条记录、9 组失败                                         | 包含当时 MPL 拒绝与上述外层既存问题；不是当前复扫结果                            |
| 初期 UiDataTable 泛型/排序类型错误、缺语言键、断点 CSS 警告、临时 harness 构建失败 | 均为并行落地阶段的历史验证记录，不列为当前阻塞，也不据本轮静态检查宣称修复验收   |
| 早期 5 项原语测试、许可续接 6 项测试通过及 scoped 构建/类型通过                    | 只证明当时范围；不替代当前整站 build、suite 或浏览器验收                         |
| Pinia devtools peer 检查失败                                                       | 安装前已有；当前安装 peer 仍不满足范围，独立于许可问题保留                       |

旧证据目录为 `/private/tmp/knowledge-ui-phase-b/` 和其 `license-recovery/`：原始 registry manifest、安装前快照、历史 web/workspace stdout JSON 与 evaluation、LICENSE 及构建日志。当前许可结论取自 `/private/tmp/knowledge-final-licenses.log` 的最终成功输出。主会话负责在 [verification.md](./verification.md) 维护后续构建与浏览器的完成证据；本文不转述“测试已启动”为通过。

## 升级方式

```sh
# 在 web/components.json 契约下预览；CLI 会下载到缓存。本轮未执行。
pnpm dlx shadcn-vue@2.9.0 view button dialog field --cwd web
pnpm dlx shadcn-vue@2.9.0 diff button --cwd web
```

维护取证中 CLI 2.9.0 的 add --dry-run/--diff/--view 注册但未实现，不能把这些选项作为安全预览。不要使用 init、add --overwrite 或 --all 覆盖本地组件。

取得新 registry 原始快照后，以旧 upstream.registry、新快照和当前本地源码做三方比较，保留项目导入、i18n、Reka data-state、Portal 层级、尺寸/圆角、主题与交互适配；同步 URL/hash、版权和消费示例。库升级使用精确版本 pnpm add -E（dev 用 -DE）与 --ignore-scripts，同步锁文件，再核验对应许可边界及消费者。许可例外不自动延伸到升级版本。

本轮文档核对范围为包清单/安装 peer、许可脚本与声明、完成日志、Naive 入口移除、24 份快照 hash 与文档链接/格式。没有运行安装、build、组件测试、TS、浏览器或独立产品验收；许可闭包通过与这些验证结论分别记录。

最终依赖与Vite接线由独立执行者Laplace复核，限定PASS：`/private/tmp/knowledge-final-build-review.md`；锁文件与精确pins/安装版本一致，build8实际产物可检查，许可边界独立4/4。原有Pinia peer差异和未验证干净安装/远程CI保持上述限制。
