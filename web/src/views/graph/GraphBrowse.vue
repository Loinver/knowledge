<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCheckbox,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NInputNumber,
  NPopconfirm,
  NPopselect,
  NSelect,
  NSlider,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { computed, h, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import {
  type EvidenceTrace,
  graphApi,
  type GraphDiff,
  type GraphPath,
  type GraphRecommendations,
  type GraphView,
  type SemanticViewConfig as SemanticConfig,
  viewTemplateApi,
} from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import { useAuthStore } from '@/stores/auth'
import EvidenceInspector from '@/views/graph/components/EvidenceInspector.vue'
import GraphCanvas from '@/views/graph/components/GraphCanvas.vue'
import { exportCsv, exportPng, exportSvg } from '@/views/graph/components/graphExport'
import GraphFactTable from '@/views/graph/components/GraphFactTable.vue'
import { LAYOUTS } from '@/views/graph/components/graphLayout'
import { relationLabels as frozenRelationLabels } from '@/views/graph/components/graphPresentation'
import { edgeKey, entityName, mergeNeighborhoods } from '@/views/graph/components/graphWorkspace'
import KnowledgeGraphReferences from '@/views/graph/components/KnowledgeGraphReferences.vue'
import {
  hasSemanticConfig,
  nodeTime,
  type SemanticContext,
} from '@/views/graph/components/layouts/semanticView'
import SemanticViewConfig from '@/views/graph/components/SemanticViewConfig.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const knowledgeReturn = computed(() =>
  typeof route.query.kbReturn === 'string' &&
  /^\/knowledge-bases\/[1-9]\d*\/search(?:\?|$)/.test(route.query.kbReturn)
    ? route.query.kbReturn
    : null,
)
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const center = computed(() => (typeof route.query.center === 'string' ? route.query.center : ''))
const graphId = computed(() => (route.query.graph ? Number(route.query.graph) : undefined))
const layoutId = computed(() =>
  typeof route.query.layout === 'string' ? route.query.layout : center.value ? 'ring' : 'force',
)
const depth = ref(1)
const excludedTypes = ref<string[]>([])
const includeDerived = ref(true)
const searchText = ref('')
let resolvedRevision: number | undefined
let pendingFocus: string | null = center.value || null
const base = shallowRef<GraphView | null>(null)
const branches = shallowRef(new Map<string, GraphView>())
// Expansion intent survives temporary filters. Keep it nonreactive so selecting an
// expansion does not cause the base read to refetch itself.
const expandedRoots = new Set<string>()
const data = computed(() =>
  base.value ? mergeNeighborhoods(base.value, branches.value.values()) : null,
)
const branchError = ref('')
const expanding = ref(false)
let branchController: AbortController | null = null
function cancelExpansion() {
  branchController?.abort()
  expanding.value = false
}
const {
  data: incoming,
  loading,
  error,
  reload,
} = useAsyncData(async (signal) => {
  // A refresh owns the branch snapshot. Late expansion responses must not be
  // applied between taking that snapshot and replacing it with refreshed data.
  cancelExpansion()
  const params = {
    graph_revision_id: graphId.value ?? resolvedRevision,
    center: center.value,
    depth: depth.value,
    excluded_types: [...excludedTypes.value],
    include_derived: includeDerived.value,
  }
  const roots = [...expandedRoots]
  const view = await graphApi.view(params, signal)
  if (!view) return null
  const refreshed = new Map<string, GraphView>()
  // Recompute every retained branch with the backend's exclusion rules; hidden
  // types must never act as invisible traversal bridges. Abort bounds the work.
  for (const root of roots) {
    if (signal.aborted) break
    const branch = await graphApi.view(
      { ...params, graph_revision_id: view.graph_revision_id, center: root },
      signal,
    )
    refreshed.set(root, branch)
  }
  return { view, branches: refreshed }
})
const canvas = ref<InstanceType<typeof GraphCanvas> | null>(null)
const selectedIri = ref<string | null>(null)
const selectedEdgeIdentity = ref<string | null>(null)
const selectedEdge = computed(
  () => data.value?.edges.find((edge) => edgeKey(edge) === selectedEdgeIdentity.value) ?? null,
)
const showEvidence = ref(false)
const traceButton = ref<InstanceType<typeof NButton> | null>(null)
const showSettings = ref(false)
const showFacts = ref(false)
const relationshipFilter = ref<string[]>([])
watch(
  [graphId, center, depth, excludedTypes, includeDerived],
  () => {
    cancelExpansion()
    branchError.value = ''
  },
  { deep: true, flush: 'sync' },
)
watch(
  [graphId, center],
  () => {
    expandedRoots.clear()
    branches.value = new Map()
  },
  { flush: 'sync' },
)
watch(
  graphId,
  () => {
    resolvedRevision = undefined
    base.value = null
    selectedIri.value = null
    selectedEdgeIdentity.value = null
    showEvidence.value = false
    relationshipFilter.value = []
  },
  { flush: 'sync' },
)
watch(incoming, async (result) => {
  if (!result) return
  const value = result.view
  if (base.value && base.value.graph_revision_id !== value.graph_revision_id) {
    expandedRoots.clear()
    clearSelection()
  }
  resolvedRevision = value.graph_revision_id
  base.value = value
  branches.value = result.branches
  if (pendingFocus && value.nodes.some((node) => node.iri === pendingFocus)) {
    selectedIri.value = pendingFocus
    await nextTick()
    canvas.value?.focus(pendingFocus)
    pendingFocus = null
  }
})
const selectedNode = computed(() =>
  data.value?.nodes.find((node) => node.iri === selectedIri.value),
)
const relationshipOptions = computed(() =>
  [...new Set(data.value?.edges.map((edge) => edge.predicate) ?? [])].map((iri) => ({
    value: iri,
    label: relationName(iri),
  })),
)
function selectNode(iri: string) {
  if (!data.value?.nodes.some((node) => node.iri === iri)) {
    explore(iri)
    return
  }
  selectedIri.value = iri
  selectedEdgeIdentity.value = null
  showEvidence.value = false
}
function selectEdge(edge: GraphView['edges'][number]) {
  selectedEdgeIdentity.value = edgeKey(edge)
  selectedIri.value = null
  showEvidence.value = false
}
function clearSelection() {
  selectedIri.value = null
  selectedEdgeIdentity.value = null
  showEvidence.value = false
}
function dismissInspector() {
  if (showEvidence.value) {
    showEvidence.value = false
    void nextTick(() => traceButton.value?.$el.focus({ preventScroll: true }))
  } else {
    canvas.value?.focusSelection()
    clearSelection()
  }
}
async function expandSelected() {
  const iri = selectedIri.value
  const revision = data.value?.graph_revision_id
  if (!iri || !revision || loading.value || expanding.value) return
  cancelExpansion()
  const controller = new AbortController()
  branchController = controller
  expanding.value = true
  branchError.value = ''
  try {
    const branch = await graphApi.view(
      {
        graph_revision_id: revision,
        center: iri,
        depth: depth.value,
        excluded_types: excludedTypes.value,
        include_derived: includeDerived.value,
      },
      controller.signal,
    )
    if (controller.signal.aborted || data.value?.graph_revision_id !== revision) return
    expandedRoots.add(iri)
    branches.value = new Map(branches.value).set(iri, branch)
  } catch (cause) {
    if (!controller.signal.aborted) branchError.value = toMessage(cause)
  } finally {
    if (branchController === controller) expanding.value = false
  }
}
function collapseSelected() {
  if (!selectedIri.value || loading.value) return
  cancelExpansion()
  const next = new Map(branches.value)
  next.delete(selectedIri.value)
  expandedRoots.delete(selectedIri.value)
  branches.value = next
  if (!data.value?.nodes.some((node) => node.iri === selectedIri.value)) clearSelection()
}
onBeforeUnmount(cancelExpansion)
const evidence = useAsyncData<EvidenceTrace>((signal) => {
  const revision = data.value?.graph_revision_id
  if (!showEvidence.value || !revision) return Promise.resolve(null)
  if (selectedEdge.value?.kind === 'DIRECT')
    return graphApi.factEvidence(
      {
        subject: selectedEdge.value.subject,
        predicate: selectedEdge.value.predicate,
        object: selectedEdge.value.object_,
      },
      revision,
      signal,
    )
  return selectedNode.value
    ? graphApi.entityEvidence(selectedNode.value.iri, revision, signal)
    : Promise.resolve(null)
})
const search = useAsyncData((signal) =>
  graphApi.entities(
    {
      graph_revision_id: graphId.value ?? data.value?.graph_revision_id,
      q: searchText.value,
      page_size: 20,
    },
    signal,
  ),
)
const searchOptions = computed(
  () =>
    search.data.value?.items.map((node) => ({
      value: node.iri,
      label: `${entityName(node)} · ${node.iri}`,
    })) ?? [],
)
const typeOptions = computed(
  () =>
    data.value?.type_counts.map((type) => ({
      value: type.type_iri,
      label: `${type.type_iri} (${type.count})`,
    })) ?? [],
)
const shortName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri
const layoutOptions = LAYOUTS.map((layout) => ({
  value: layout.id,
  label: t(`graph.layout.${layout.id}`),
}))

function updateQuery(patch: Record<string, unknown>) {
  const query = { ...route.query }
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === undefined) delete query[key]
    else query[key] = String(value)
  }
  void router.replace({ query })
}

function explore(iri: string | null) {
  if (iri && ['schema', 'sankey', 'chord'].includes(layoutId.value ?? '')) {
    excludedTypes.value = (data.value?.type_counts ?? [])
      .map((item) => item.type_iri)
      .filter((type) => type !== iri)
    updateQuery({
      graph: graphId.value ?? data.value?.graph_revision_id,
      center: undefined,
      layout: 'type_grid',
    })
    return
  }
  if (iri && data.value?.nodes.some((node) => node.iri === iri)) {
    selectNode(iri)
    canvas.value?.focus(iri)
    return
  }
  pendingFocus = iri
  clearSelection()
  updateQuery({
    graph: graphId.value ?? data.value?.graph_revision_id,
    center: iri || undefined,
  })
}

function selectGraph(id: number | null) {
  resolvedRevision = undefined
  excludedTypes.value = []
  updateQuery({ graph: id || undefined, center: undefined, layout: undefined, template: undefined })
  showHistory.value = false
  if (graphId.value === (id || undefined)) reload()
}

function selectLayout(id: string | null) {
  cancelTemplateRequest()
  legacyTemplate.value = false
  selectedTemplateId.value = null
  updateQuery({ layout: id || undefined, template: undefined })
}

// ===== 形态推荐（语义信号 → 形态 + 理由） =====
const recommendationRequest = useAsyncData<GraphRecommendations>((signal) =>
  data.value?.graph_revision_id
    ? graphApi.recommendations(data.value.graph_revision_id, signal)
    : Promise.resolve(null),
)
const recommendations = recommendationRequest.data
const reasonText = (reasonKey: string, params: Record<string, unknown>) => {
  if (reasonKey === 'graph.reason.hierarchy') {
    return t(reasonKey, { edge: shortName(String(params.hierarchy_edge ?? '')) })
  }
  if (reasonKey === 'graph.reason.measuredLink') {
    const assoc = (params.measured_link as Array<{ assoc: string }> | undefined)?.[0]?.assoc ?? ''
    return t(reasonKey, { assoc: shortName(assoc) })
  }
  if (reasonKey === 'graph.reason.dateAttr') {
    return t(reasonKey, { count: (params.date_attrs as unknown[] | undefined)?.length ?? 0 })
  }
  return t(reasonKey, params)
}

// ===== 视图模板（版本钉扎 + 失效提示） =====
const templateData = useAsyncData((signal) =>
  data.value?.ontology_id
    ? viewTemplateApi.list(data.value.ontology_id, signal)
    : Promise.resolve(null),
)
const templates = computed(() => templateData.data.value?.items ?? [])
const semanticFields = useAsyncData((signal) =>
  data.value?.ontology_id && data.value.ontology_revision
    ? viewTemplateApi.fields(data.value.ontology_id, data.value.ontology_revision, signal)
    : Promise.resolve(null),
)
const relationLabels = computed(() =>
  frozenRelationLabels(
    data.value,
    semanticFields.data.value,
    locale.value,
    t('enumDictionaries.untranslated'),
  ),
)
const relationName = (iri: string) => relationLabels.value[iri] ?? shortName(iri)
const semanticConfig = ref<SemanticConfig>({})
const legacyTemplate = ref(false)
const semanticContext = computed<SemanticContext>(() => ({
  config: semanticConfig.value,
  fields: semanticFields.data.value?.fields ?? [],
  instanceNamespace: data.value?.instance_namespace,
  legacy: legacyTemplate.value,
  pending: semanticFields.loading.value,
  stale: selectedTemplateId.value !== null && semanticFields.data.value?.stale,
}))
function configureSemantics(config: SemanticConfig) {
  cancelTemplateRequest()
  semanticConfig.value = config
  legacyTemplate.value = false
  selectedTemplateId.value = null
  updateQuery({ template: undefined })
}
const templateError = ref('')
const templateName = ref('')
const savingTemplate = ref(false)
const applyingTemplate = ref(false)
const selectedTemplateId = ref<number | null>(null)
const removingTemplate = ref(false)
let templateController: AbortController | null = null
let previousPin = ''
function cancelTemplateRequest() {
  templateController?.abort()
  savingTemplate.value = applyingTemplate.value = removingTemplate.value = false
}
function resetTemplateContext() {
  cancelTemplateRequest()
  semanticConfig.value = {}
  legacyTemplate.value = false
  selectedTemplateId.value = null
  templateError.value = ''
}
watch(graphId, resetTemplateContext)
watch(
  () => [data.value?.ontology_id, data.value?.ontology_revision],
  ([id, revision]) => {
    if (!id || !revision) return
    const pin = `${id}:${revision}`
    if (previousPin && previousPin !== pin) resetTemplateContext()
    previousPin = pin
  },
)
onBeforeUnmount(() => templateController?.abort())
function templateRequest() {
  templateController?.abort()
  const controller = new AbortController()
  templateController = controller
  savingTemplate.value = applyingTemplate.value = removingTemplate.value = false
  templateError.value = ''
  const owner = data.value?.graph_revision_id
  const routeOwner = graphId.value
  return {
    signal: controller.signal,
    current: () =>
      !controller.signal.aborted &&
      graphId.value === routeOwner &&
      data.value?.graph_revision_id === owner,
    active: () => !controller.signal.aborted && templateController === controller,
  }
}
const templateOptions = computed(() =>
  templates.value.map((template) => ({
    value: template.id,
    label: `${template.name_i18n[locale.value] || template.layout_id}${template.stale ? ` · ${t('graph.templateStale')}` : ''}`,
    disabled: template.stale || template.ontology_revision !== data.value?.ontology_revision,
  })),
)
async function saveTemplate() {
  const name = templateName.value.trim()
  if (
    !canWrite.value ||
    !name ||
    !data.value?.ontology_id ||
    !data.value?.ontology_revision ||
    savingTemplate.value
  )
    return
  if (semanticFields.data.value?.stale) {
    templateError.value = t('semanticView.stale')
    return
  }
  const request = templateRequest()
  savingTemplate.value = true
  try {
    const saved = await viewTemplateApi.create(
      {
        name_i18n: { 'zh-CN': name, 'en-US': name },
        layout_id: layoutId.value ?? (center.value ? 'ring' : 'type_grid'),
        config: {
          ...semanticConfig.value,
          semantic_version: 1,
          center: center.value || undefined,
          depth: depth.value,
          excluded_types: excludedTypes.value,
        },
        ontology_id: data.value.ontology_id,
        ontology_revision: data.value.ontology_revision,
      },
      request.signal,
    )
    if (!request.current()) return
    semanticConfig.value = { ...saved.config }
    legacyTemplate.value = false
    selectedTemplateId.value = saved.id
    updateQuery({ template: saved.id })
    templateName.value = ''
    templateData.reload()
  } catch (cause) {
    if (request.current()) templateError.value = toMessage(cause)
  } finally {
    if (request.active()) savingTemplate.value = false
  }
}
async function applyTemplate(id: number) {
  const listed = templates.value.find((item) => item.id === id)
  const graph = data.value
  if (!graph?.ontology_id || !graph.ontology_revision) return
  if (listed && (listed.stale || listed.ontology_revision !== graph.ontology_revision)) {
    templateError.value = t('semanticView.stale')
    return
  }
  const request = templateRequest()
  applyingTemplate.value = true
  try {
    const template = await viewTemplateApi.applicable(
      id,
      graph.ontology_id,
      graph.ontology_revision,
      request.signal,
    )
    if (!request.current()) return
    if (template.stale) {
      templateError.value = t('semanticView.stale')
      return
    }
    const config = template.config
    semanticConfig.value = { ...config }
    legacyTemplate.value = config.semantic_version == null && !hasSemanticConfig(config)
    selectedTemplateId.value = id
    depth.value = config.depth === 2 ? 2 : 1
    excludedTypes.value = Array.isArray(config.excluded_types)
      ? config.excluded_types.filter((item): item is string => typeof item === 'string')
      : []
    updateQuery({
      layout: template.layout_id,
      center: typeof config.center === 'string' ? config.center : undefined,
      template: id,
    })
  } catch (cause) {
    if (request.current()) templateError.value = toMessage(cause)
  } finally {
    if (request.active()) applyingTemplate.value = false
  }
}

// The explicit template query restores the same pinned configuration after a page reload.
watch(
  [() => route.query.template, () => data.value?.ontology_id, () => data.value?.ontology_revision],
  ([value, ontology, revision]) => {
    const id = typeof value === 'string' ? Number(value) : NaN
    if (
      Number.isSafeInteger(id) &&
      id > 0 &&
      ontology &&
      revision &&
      selectedTemplateId.value !== id
    )
      void applyTemplate(id)
  },
  { immediate: true },
)

// 模板此前只能创建和应用，已保存的视图无法删除；应用后出现删除入口。
const selectedTemplateName = computed(
  () =>
    templates.value.find((item) => item.id === selectedTemplateId.value)?.name_i18n[locale.value] ??
    '',
)
async function removeTemplate() {
  if (selectedTemplateId.value === null || removingTemplate.value || !canWrite.value) return
  const request = templateRequest()
  removingTemplate.value = true
  templateError.value = ''
  try {
    await viewTemplateApi.remove(selectedTemplateId.value, request.signal)
    if (!request.current()) return
    templateData.reload()
    selectedTemplateId.value = null
    updateQuery({ template: undefined })
  } catch (cause) {
    if (request.current()) templateError.value = toMessage(cause)
  } finally {
    if (request.active()) removingTemplate.value = false
  }
}

// ===== 质量叠加（G-28）：隔离命中节点标记 =====
const qualityOverlay = ref(false)
// Source identity is absent from GraphViewNode. Do not mark unrelated rows sharing a key.
const flaggedIris = computed(() => new Set<string>())

// ===== 关系路径（G-12）与版本差异（G-24）抽屉 =====
const showPath = ref(false)
const showDiff = ref(false)
const showMatrix = ref(false)
const showCentrality = ref(false)
function openAnalysis(mode: 'diff' | 'matrix' | 'centrality') {
  showSettings.value = false
  if (mode === 'diff') showDiff.value = true
  if (mode === 'matrix') showMatrix.value = true
  if (mode === 'centrality') showCentrality.value = true
}
const pathFrom = ref('')
const pathTo = ref('')
const pathHops = ref(3)
const pathResult = ref<GraphPath | null>(null)
const pathError = ref('')
const highlightIris = computed(() =>
  pathResult.value?.found ? new Set(pathResult.value.nodes) : undefined,
)
watch(center, (value) => {
  if (value && !pathFrom.value) pathFrom.value = value
})
const pathLoading = ref(false)
let pathController: AbortController | null = null
watch(
  [graphId, pathFrom, pathTo, pathHops, includeDerived],
  () => {
    pathController?.abort()
    pathResult.value = null
    pathError.value = ''
    pathLoading.value = false
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => pathController?.abort())
async function findPath() {
  const graph = data.value?.graph_revision_id
  if (!graph || !pathFrom.value || !pathTo.value) return
  pathController?.abort()
  const controller = new AbortController()
  pathController = controller
  pathError.value = ''
  pathResult.value = null
  pathLoading.value = true
  try {
    const result = await graphApi.path(
      graph,
      {
        from: pathFrom.value,
        to: pathTo.value,
        max_hops: pathHops.value,
        include_derived: includeDerived.value,
      },
      controller.signal,
    )
    if (!controller.signal.aborted && data.value?.graph_revision_id === graph)
      pathResult.value = result
  } catch (cause) {
    if (!controller.signal.aborted) pathError.value = toMessage(cause)
  } finally {
    if (pathController === controller) pathLoading.value = false
  }
}

const showHistory = ref(false)
const revisions = useAsyncData((signal) =>
  showHistory.value || showDiff.value ? graphApi.revisions(signal) : Promise.resolve(null),
)
const switching = ref(false)
const switchError = ref('')
const viewController = new AbortController()
onBeforeUnmount(() => viewController.abort())
async function switchCurrent(id: number) {
  if (switching.value || !canWrite.value) return
  switching.value = true
  switchError.value = ''
  try {
    await graphApi.switchCurrent(id)
    if (viewController.signal.aborted) return
    revisions.reload()
    selectGraph(id)
    reload()
  } catch (cause) {
    if (!viewController.signal.aborted) switchError.value = toMessage(cause)
  } finally {
    switching.value = false
  }
}
const diffBase = ref<number | null>(null)
const diffTarget = ref<number | null>(null)
// 打开抽屉时预填最近两个结果集，便于直接计算差异
watch(showDiff, (open) => {
  if (!open) return
  const target = data.value?.graph_revision_id
  if (target) diffTarget.value = target
})
const diffResult = ref<GraphDiff | null>(null)
const diffError = ref('')
const diffLoading = ref(false)
let diffGeneration = 0
watch(
  [diffBase, diffTarget, showDiff],
  () => {
    diffGeneration++
    diffResult.value = null
    diffError.value = ''
    diffLoading.value = false
  },
  { flush: 'sync' },
)
async function runDiff() {
  if (!diffBase.value || !diffTarget.value) return
  const generation = ++diffGeneration
  diffResult.value = null
  diffLoading.value = true
  diffError.value = ''
  try {
    const result = await graphApi.diff(diffBase.value, diffTarget.value, viewController.signal)
    if (!viewController.signal.aborted && generation === diffGeneration) diffResult.value = result
  } catch (cause) {
    if (!viewController.signal.aborted && generation === diffGeneration)
      diffError.value = toMessage(cause)
  } finally {
    if (generation === diffGeneration) diffLoading.value = false
  }
}

// ===== 导出（PNG/SVG/CSV） =====
const exportError = ref('')
function svgElement(): SVGSVGElement | null {
  return document.querySelector('.canvas-scroll svg')
}
async function doExport(kind: 'png' | 'svg' | 'csv') {
  exportError.value = ''
  const graph = visibleGraph.value
  if (!graph) return
  try {
    const stamp = `graph-${graph.graph_revision_id}`
    if (kind === 'csv') {
      exportCsv(
        graph.nodes as unknown as Record<string, unknown>[],
        ['iri', 'type_iri', 'row_key'],
        `${stamp}-nodes.csv`,
      )
      return
    }
    const svg = svgElement()
    if (!svg) throw new Error('svg_not_found')
    if (kind === 'svg') await exportSvg(svg, `${stamp}.svg`)
    else await exportPng(svg, `${stamp}.png`)
  } catch (cause) {
    exportError.value = toMessage(cause)
  }
}
const exportOptions = ['png', 'svg', 'csv'].map((kind) => ({
  value: kind,
  label: t(`graph.export.${kind}`),
}))

// ===== 邻接矩阵（G-20）与中心性排行（G-32）抽屉 =====
const centralityColumns = computed(() => [
  { key: 'name', title: t('common.name'), width: 160, ellipsis: { tooltip: true } },
  { key: 'in', title: t('graph.degreeIn'), width: 70 },
  { key: 'out', title: t('graph.degreeOut'), width: 70 },
  { key: 'total', title: t('graph.degreeTotal'), width: 80 },
  {
    key: 'go',
    title: '',
    width: 110,
    render: (row: { iri: string }) =>
      h(NButton, { size: 'tiny', onClick: () => explore(row.iri) }, () => t('graph.exploreShort')),
  },
])
const typeMatrix = computed(() => {
  const graph = visibleGraph.value
  if (!graph) return null
  const types = [...new Set(graph.nodes.map((node) => node.type_iri))].sort()
  const typeOf = new Map(graph.nodes.map((node) => [node.iri, node.type_iri] as const))
  const counts = new Map<string, number>()
  for (const edge of graph.edges) {
    const st = typeOf.get(edge.subject)
    const ot = typeOf.get(edge.object_)
    if (!st || !ot) continue
    const key = `${st}\u0000${ot}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const rows = types.map((row) => {
    const cells: Record<string, number | string> = { __type: row }
    for (const col of types) cells[col] = counts.get(`${row}\u0000${col}`) ?? 0
    return cells
  })
  return { types, rows }
})
const matrixColumns = computed(() => {
  const matrix = typeMatrix.value
  if (!matrix) return []
  return [
    { key: '__type', title: t('graph.matrixType'), width: 180, ellipsis: { tooltip: true } },
    ...matrix.types.map((type) => ({
      key: type,
      title: type.split(/[/#]/).filter(Boolean).at(-1) || type,
      width: 70,
    })),
  ]
})

function matrixRowKey(row: Record<string, unknown>): string {
  return String(row.__type)
}
function centralityRowKey(row: { iri: string }): string {
  return row.iri
}
const centralityRows = computed(() => {
  const graph = visibleGraph.value
  if (!graph) return []
  const stats = new Map<string, { in: number; out: number }>()
  for (const node of graph.nodes) {
    stats.set(node.iri, { in: 0, out: 0, ...stats.get(node.iri) })
  }
  for (const edge of graph.edges) {
    const outEntry = stats.get(edge.subject)
    if (outEntry) outEntry.out += 1
    const inEntry = stats.get(edge.object_)
    if (inEntry) inEntry.in += 1
  }
  return [...stats.entries()]
    .map(([iri, value]) => ({
      iri,
      name: String(graph.nodes.find((node) => node.iri === iri)?.attrs.name ?? iri),
      in: value.in,
      out: value.out,
      total: value.in + value.out,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 30)
})

// ===== 时间切片回放（G-23）：timeline 形态下按日期窗口过滤画布数据 =====
const replayRange = ref<[number, number] | null>(null)
const replayBounds = computed<[number, number] | null>(() => {
  const graph = data.value
  if (!graph) return null
  const times: number[] = []
  for (const node of graph.nodes) {
    const time = nodeTime(node, semanticContext.value)
    if (time !== null) times.push(time)
  }
  if (!times.length) return null
  return [Math.min(...times), Math.max(...times)]
})
watch(
  [() => data.value?.graph_revision_id, replayBounds] as const,
  ([revision, bounds]) => {
    replayRange.value = revision && bounds ? [...bounds] : null
  },
  { immediate: true },
)
const replayedGraph = computed(() => {
  const graph = data.value
  const bounds = replayBounds.value
  const range = replayRange.value
  if (!graph || !bounds || !range || layoutId.value !== 'timeline') return graph
  if (range[0] === bounds[0] && range[1] === bounds[1]) return graph
  const keep = new Set(
    graph.nodes
      .filter((node) => {
        const time = nodeTime(node, semanticContext.value)
        return time !== null && time >= range[0] && time <= range[1]
      })
      .map((node) => node.iri),
  )
  return {
    ...graph,
    nodes: graph.nodes.filter((node) => keep.has(node.iri)),
    edges: graph.edges.filter((edge) => keep.has(edge.subject) && keep.has(edge.object_)),
  }
})
const visibleGraph = computed(() => {
  const graph = replayedGraph.value
  if (!graph || !relationshipFilter.value.length) return graph
  return {
    ...graph,
    edges: graph.edges.filter((edge) => relationshipFilter.value.includes(edge.predicate)),
  }
})
function clearFilters() {
  excludedTypes.value = []
  relationshipFilter.value = []
  includeDerived.value = true
}
function onExport(kind: string) {
  void doExport(kind as 'png' | 'svg' | 'csv')
}
</script>

<template>
  <section class="graph-page">
    <div class="graph-heading">
      <PageHeader :title="t('page.graphBrowse')">
        <template #context
          ><span class="workspace-context"
            >{{
              data ? t('graph.resultSet', { id: data.graph_revision_id }) : t('graph.currentResult')
            }}
            · {{ t('ui.readOnlyLabel') }}</span
          ></template
        >
        <template #actions>
          <RouterLink v-if="knowledgeReturn" :to="knowledgeReturn">{{
            t('kb.backToSearch')
          }}</RouterLink>
          <NButton size="small" @click="showHistory = true">{{ t('graph.history') }}</NButton>
          <RouterLink :to="{ name: 'graph-entities', query: { graph: data?.graph_revision_id } }">{{
            t('page.graphEntities')
          }}</RouterLink>
        </template>
      </PageHeader>
    </div>
    <div class="graph-toolbar">
      <NSelect
        class="graph-search"
        :value="selectedIri || center || null"
        :options="searchOptions"
        :loading="search.loading.value"
        filterable
        remote
        clearable
        :placeholder="t('graph.searchHint')"
        :aria-label="t('graph.searchHint')"
        @search="searchText = $event"
        @update:value="explore"
      />
      <NSelect
        class="layout-select"
        :value="layoutId ?? (center ? 'ring' : 'type_grid')"
        :options="layoutOptions"
        :aria-label="t('graph.layoutLabel')"
        @update:value="selectLayout"
      />
      <NButton
        :type="excludedTypes.length || relationshipFilter.length ? 'primary' : 'default'"
        @click="showSettings = true"
        >{{ t('graphUi.filters') }}</NButton
      >
      <NButton :disabled="!data" @click="showPath = true">{{ t('graph.pathQuery') }}</NButton>
      <NButton :disabled="!data" @click="showFacts = true">{{ t('graphUi.facts') }}</NButton>
      <NButton :disabled="!center" @click="explore(null)">{{ t('graph.overview') }}</NButton>
      <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
    </div>
    <div v-if="error || branchError || search.error.value || exportError" class="graph-message">
      <NAlert type="warning"
        >{{ error || branchError || search.error.value || exportError
        }}<span v-if="data"> · {{ t('graphUi.retained') }}</span>
        <span class="alert-action"
          ><NButton
            size="small"
            @click="error ? reload() : branchError ? expandSelected() : search.reload()"
            >{{ t('ui.retry') }}</NButton
          ></span
        >
      </NAlert>
    </div>
    <div v-if="data?.truncated" class="graph-message">
      <NAlert type="warning">{{ t('graphUi.limited') }}</NAlert>
    </div>
    <div v-if="qualityOverlay" class="graph-message">
      <NAlert type="info">{{
        t('graphUi.qualityScope', { count: data?.quarantine_count ?? '—' })
      }}</NAlert>
    </div>
    <label
      v-if="layoutId === 'timeline' && replayBounds && replayRange"
      class="replay graph-message"
    >
      <span>{{ t('graph.replay') }}</span
      ><NSlider
        v-model:value="replayRange"
        range
        :min="replayBounds[0]"
        :max="replayBounds[1]"
        :step="1"
        :format-tooltip="(value: number) => new Date(value).toISOString()"
        :aria-label="t('graph.replay')"
      />
    </label>
    <div class="graph-workspace" :aria-busy="loading || expanding" @keydown.esc="dismissInspector">
      <main class="canvas-area">
        <p v-if="loading || expanding" class="loading-indicator" role="status">
          {{ t('common.loading') }}
        </p>
        <GraphCanvas
          v-if="data && visibleGraph"
          ref="canvas"
          :graph="visibleGraph"
          :neighborhood="!!center"
          :layout-id="layoutId"
          :semantic-context="semanticContext"
          :relation-labels="relationLabels"
          :flagged-iris="qualityOverlay ? flaggedIris : undefined"
          :highlight-iris="highlightIris"
          :selected-iri="selectedIri"
          :selected-edge-key="selectedEdge ? edgeKey(selectedEdge) : null"
          @select="selectNode"
          @select-edge="selectEdge"
        />
        <div v-if="!loading && !visibleGraph?.nodes.length" class="canvas-empty">
          <NEmpty :description="error ? t('graphUi.loadFailed') : t('graph.noVisibleNodes')"
            ><template #extra
              ><NButton @click="error ? reload() : clearFilters()">{{
                error ? t('ui.retry') : t('ui.clearFilters')
              }}</NButton></template
            ></NEmpty
          >
        </div>
      </main>
      <aside
        v-if="selectedNode || selectedEdge"
        class="graph-inspector"
        :aria-label="t('graphUi.inspector')"
      >
        <div class="inspector-heading">
          <strong>{{ showEvidence ? t('page.graphEvidence') : t('graphUi.inspector') }}</strong
          ><NButton size="small" quaternary @click="dismissInspector">{{
            showEvidence ? t('graphUi.backObject') : t('common.close')
          }}</NButton>
        </div>
        <div class="inspector-body">
          <template v-if="!showEvidence">
            <template v-if="selectedNode">
              <NTag size="small">{{ shortName(selectedNode.type_iri) }}</NTag>
              <h2>{{ entityName(selectedNode) }}</h2>
              <p class="object-iri">{{ selectedNode.iri }}</p>
              <NSpace
                ><NButton
                  type="primary"
                  :loading="expanding"
                  :disabled="loading || !!error || data!.nodes.length >= 500"
                  @click="expandSelected"
                  >{{ t('graphUi.expand') }}</NButton
                ><NButton
                  :disabled="!branches.has(selectedNode.iri) || loading"
                  @click="collapseSelected"
                  >{{ t('graphUi.collapse') }}</NButton
                ></NSpace
              >
              <dl class="attribute-list">
                <template v-for="(value, key) in selectedNode.attrs" :key="key"
                  ><dt>{{ key }}</dt>
                  <dd>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</dd></template
                >
              </dl>
            </template>
            <template v-if="selectedEdge">
              <NTag size="small" :type="selectedEdge.kind === 'DERIVED' ? 'warning' : 'default'">{{
                t(selectedEdge.kind === 'DERIVED' ? 'graph.derived' : 'graph.directRelation')
              }}</NTag>
              <h2>{{ relationName(selectedEdge.predicate) }}</h2>
              <dl class="attribute-list">
                <dt>{{ t('graph.subject') }}</dt>
                <dd>{{ selectedEdge.subject }}</dd>
                <dt>{{ t('graph.predicate') }}</dt>
                <dd>{{ selectedEdge.predicate }}</dd>
                <dt>{{ t('graph.object') }}</dt>
                <dd>{{ selectedEdge.object_ }}</dd>
                <template v-for="(value, key) in selectedEdge.props" :key="key"
                  ><dt>{{ key }}</dt>
                  <dd>{{ value }}</dd></template
                >
              </dl>
              <NAlert v-if="selectedEdge.kind === 'DERIVED'" type="info">{{
                t('graphUi.derivedEvidence')
              }}</NAlert>
            </template>
            <NButton
              ref="traceButton"
              block
              :disabled="selectedEdge?.kind === 'DERIVED' || loading || !!error"
              @click="showEvidence = true"
              >{{ t('graph.trace') }}</NButton
            >
          </template>
          <template v-else>
            <p class="evidence-context">
              {{
                selectedEdge
                  ? relationName(selectedEdge.predicate)
                  : selectedNode
                    ? entityName(selectedNode)
                    : ''
              }}
              ·
              {{ t('graph.resultSet', { id: data!.graph_revision_id }) }}
            </p>
            <p v-if="evidence.loading.value" role="status">{{ t('common.loading') }}</p>
            <NAlert v-else-if="evidence.error.value" type="warning"
              >{{ evidence.error.value
              }}<span class="alert-action"
                ><NButton @click="evidence.reload">{{ t('ui.retry') }}</NButton></span
              ></NAlert
            >
            <template v-else-if="evidence.data.value"
              ><p>{{ t('graph.totalEvidence', { n: evidence.data.value.total_count }) }}</p>
              <EvidenceInspector :items="evidence.data.value.evidences" /><NEmpty
                v-if="!evidence.data.value.total_count"
                :description="t('graphUi.noEvidence')"
            /></template>
          </template>
          <KnowledgeGraphReferences
            v-if="data && (selectedNode || selectedEdge?.kind === 'DIRECT')"
            :graph-id="data.graph_revision_id"
            :entity-iri="selectedNode?.iri ?? selectedEdge!.subject"
            :fact-id="selectedEdge?.kind === 'DIRECT' ? selectedEdge.id : undefined"
          />
        </div>
      </aside>
    </div>
    <footer class="graph-footer">
      <span v-if="data">{{
        t('graphUi.counts', {
          total: data.entity_total,
          loaded: data.nodes.length,
          visible: canvas?.displayCounts.nodes ?? 0,
          edges: canvas?.displayCounts.edges ?? 0,
        })
      }}</span>
    </footer>
    <NDrawer v-model:show="showSettings" :width="420"
      ><NDrawerContent :title="t('graphUi.filters')" closable
        ><div class="panel-form">
          <label
            ><span>{{ t('graph.revisionInput') }}</span
            ><NInputNumber
              :value="graphId ?? null"
              :min="1"
              :precision="0"
              clearable
              :placeholder="t('graph.currentResult')"
              :aria-label="t('graph.revisionInput')"
              @update:value="selectGraph"
          /></label>
          <label
            ><span>{{ t('graph.depth') }}</span
            ><NSelect
              v-model:value="depth"
              :options="[
                { label: t('graph.oneDegree'), value: 1 },
                { label: t('graph.twoDegrees'), value: 2 },
              ]"
              :aria-label="t('graph.depth')"
          /></label>
          <label
            ><span>{{ t('graph.hiddenTypes') }}</span
            ><NSelect
              v-model:value="excludedTypes"
              :options="typeOptions"
              multiple
              clearable
              :aria-label="t('graph.hiddenTypes')"
              :placeholder="t('graph.hiddenTypes')"
          /></label>
          <p class="scope-hint">{{ t('graphUi.typeScope') }}</p>
          <label
            ><span>{{ t('graphUi.relationships') }}</span
            ><NSelect
              v-model:value="relationshipFilter"
              :options="relationshipOptions"
              multiple
              clearable
              :aria-label="t('graphUi.relationships')"
              :placeholder="t('graphUi.allRelations')"
          /></label>
          <NCheckbox v-model:checked="includeDerived">{{ t('graph.showDerived') }}</NCheckbox
          ><NCheckbox v-model:checked="qualityOverlay">{{ t('graph.qualityOverlay') }}</NCheckbox
          ><NButton @click="clearFilters">{{ t('ui.clearFilters') }}</NButton>
          <h3>{{ t('graphUi.analysis') }}</h3>
          <p class="scope-hint">{{ t('graphUi.analysisScope') }}</p>
          <NSpace
            ><NButton @click="openAnalysis('diff')">{{ t('graph.diffQuery') }}</NButton
            ><NButton @click="openAnalysis('matrix')">{{ t('graph.matrix') }}</NButton
            ><NButton @click="openAnalysis('centrality')">{{ t('graph.centrality') }}</NButton
            ><NPopselect :options="exportOptions" trigger="click" @update:value="onExport"
              ><NButton :disabled="!data">{{ t('graph.export.title') }}</NButton></NPopselect
            ></NSpace
          >
          <h3>{{ t('graph.templates') }}</h3>
          <NAlert v-if="templateError || templateData.error.value" type="warning">{{
            templateError || templateData.error.value
          }}</NAlert>
          <NSelect
            :value="selectedTemplateId"
            :options="templateOptions"
            :loading="applyingTemplate || templateData.loading.value"
            :placeholder="t('graph.templates')"
            :aria-label="t('graph.templates')"
            @update:value="applyTemplate"
          />
          <SemanticViewConfig
            :layout-id="layoutId ?? (center ? 'ring' : 'type_grid')"
            :config="semanticConfig"
            :catalog="semanticFields.data.value"
            :loading="semanticFields.loading.value"
            :error="semanticFields.error.value"
            @change="configureSemantics"
            @retry="semanticFields.reload"
          />
          <div v-if="data && canWrite" class="inline-save">
            <NInput
              v-model:value="templateName"
              :placeholder="t('graph.templateName')"
              @keydown.enter.prevent="saveTemplate"
            /><NButton
              :loading="savingTemplate"
              :disabled="
                !templateName.trim() ||
                semanticFields.loading.value ||
                semanticFields.data.value?.stale
              "
              @click="saveTemplate"
              >{{ t('graph.templateSave') }}</NButton
            >
          </div>
          <NPopconfirm
            v-if="canWrite && selectedTemplateId !== null"
            @positive-click="removeTemplate"
            ><template #trigger
              ><NButton tertiary type="error" :loading="removingTemplate">{{
                t('graph.templateDelete')
              }}</NButton></template
            >{{ t('graph.templateDeleteConfirm', { name: selectedTemplateName }) }}</NPopconfirm
          >
          <NAlert v-if="recommendations?.recommendations.length" type="info"
            ><p>{{ t('graph.recommended') }}</p>
            <NSpace
              ><NButton
                v-for="item in recommendations.recommendations.filter(
                  (rec) => rec.reason_key !== 'graph.reason.generic',
                )"
                :key="item.layout_id"
                size="small"
                @click="selectLayout(item.layout_id)"
                >{{ t(`graph.layout.${item.layout_id}`) }}</NButton
              ></NSpace
            >
            <p>
              {{
                reasonText(
                  recommendations.recommendations.find(
                    (rec) => rec.reason_key !== 'graph.reason.generic',
                  )?.reason_key ?? 'graph.reason.generic',
                  recommendations.signals,
                )
              }}
            </p></NAlert
          >
        </div></NDrawerContent
      ></NDrawer
    >
    <NDrawer v-model:show="showFacts" width="min(960px, 100vw)"
      ><NDrawerContent :title="t('graphUi.facts')" closable
        ><p>{{ t('graphUi.analysisScope') }}</p>
        <NTabs v-if="visibleGraph" type="line"
          ><NTabPane name="direct" :tab="t('graph.directRelation')"
            ><GraphFactTable
              :items="visibleGraph.edges.filter((edge) => edge.kind === 'DIRECT')"
              :relation-labels="relationLabels"
              :graph-revision-id="visibleGraph.graph_revision_id" /></NTabPane
          ><NTabPane name="derived" :tab="t('graph.derived')"
            ><p>{{ t('graph.derivedHint') }}</p>
            <GraphFactTable
              :items="visibleGraph.edges.filter((edge) => edge.kind === 'DERIVED')"
              :relation-labels="relationLabels"
              :graph-revision-id="visibleGraph.graph_revision_id"
              derived /></NTabPane></NTabs></NDrawerContent
    ></NDrawer>
    <NDrawer v-model:show="showPath" :width="420">
      <NDrawerContent :title="t('graph.pathQuery')" closable>
        <div class="panel-form">
          <label>
            <span>{{ t('graph.pathFrom') }}</span>
            <NInput v-model:value="pathFrom" :input-props="{ 'aria-label': t('graph.pathFrom') }" />
          </label>
          <label>
            <span>{{ t('graph.pathTo') }}</span>
            <NInput v-model:value="pathTo" :input-props="{ 'aria-label': t('graph.pathTo') }" />
          </label>
          <label>
            <span>{{ t('graph.pathHops') }}</span>
            <NInputNumber v-model:value="pathHops" :min="1" :max="6" />
          </label>
          <NButton
            type="primary"
            :loading="pathLoading"
            :disabled="!pathFrom || !pathTo || !data || loading"
            @click="findPath"
            >{{ t('graph.pathFind') }}</NButton
          >
          <NAlert v-if="pathError" type="warning">{{ pathError }}</NAlert>
          <template v-if="pathResult">
            <NAlert :type="pathResult.found ? 'success' : 'warning'">
              {{
                pathResult.found
                  ? t('graph.pathFound', { hops: pathResult.hops })
                  : t('graph.pathNotFound')
              }}
            </NAlert>
            <ol v-if="pathResult.found" class="path-list">
              <li v-for="node in pathResult.nodes" :key="node">{{ node }}</li>
            </ol>
          </template>
        </div>
      </NDrawerContent>
    </NDrawer>
    <NDrawer v-model:show="showDiff" :width="520">
      <NDrawerContent :title="t('graph.diffQuery')" closable>
        <div class="panel-form">
          <label>
            <span>{{ t('graph.diffBase') }}</span>
            <NInputNumber
              v-model:value="diffBase"
              :min="1"
              :precision="0"
              :aria-label="t('graph.diffBase')"
            />
          </label>
          <label>
            <span>{{ t('graph.diffTarget') }}</span>
            <NInputNumber
              v-model:value="diffTarget"
              :min="1"
              :precision="0"
              :aria-label="t('graph.diffTarget')"
            />
          </label>
          <NButton
            type="primary"
            :loading="diffLoading"
            :disabled="!diffBase || !diffTarget || diffLoading"
            @click="runDiff"
            >{{ t('graph.diffRun') }}</NButton
          >
          <NAlert v-if="diffError" type="warning">{{ diffError }}</NAlert>
          <template v-if="diffResult">
            <p>
              {{
                t('graph.diffSummary', {
                  added: diffResult.triple_added_count,
                  removed: diffResult.triple_removed_count,
                  entityAdded: diffResult.entity_added_count,
                  entityRemoved: diffResult.entity_removed_count,
                  entityModified: diffResult.entity_modified_count,
                })
              }}
            </p>
            <NAlert v-if="diffResult.truncated" type="warning">{{ t('graph.truncated') }}</NAlert>
            <ul class="diff-list">
              <li v-for="iri in diffResult.entities_added" :key="'a' + iri" class="added">
                {{ t('graph.diffAdded', { iri }) }}
              </li>
              <li v-for="iri in diffResult.entities_removed" :key="'r' + iri" class="removed">
                {{ t('graph.diffRemoved', { iri }) }}
              </li>
              <li v-for="item in diffResult.entities_modified" :key="'m' + item.iri">
                {{ t('graph.diffModified', { iri: item.iri }) }}
                <pre>{{ JSON.stringify(item.before, null, 2) }}</pre>
                <pre>{{ JSON.stringify(item.after, null, 2) }}</pre>
              </li>
              <li
                v-for="(item, index) in diffResult.triples_added"
                :key="'fa' + index"
                class="added"
              >
                {{
                  t('graph.diffFact', {
                    change: '+',
                    kind: t(`graph.${item.kind === 'DERIVED' ? 'derived' : 'direct'}`),
                    subject: item.subject,
                    predicate: item.predicate,
                    object: item.object,
                    count: item.count,
                  })
                }}
                <pre v-if="item.props">{{ JSON.stringify(item.props, null, 2) }}</pre>
              </li>
              <li
                v-for="(item, index) in diffResult.triples_removed"
                :key="'fr' + index"
                class="removed"
              >
                {{
                  t('graph.diffFact', {
                    change: '−',
                    kind: t(`graph.${item.kind === 'DERIVED' ? 'derived' : 'direct'}`),
                    subject: item.subject,
                    predicate: item.predicate,
                    object: item.object,
                    count: item.count,
                  })
                }}
                <pre v-if="item.props">{{ JSON.stringify(item.props, null, 2) }}</pre>
              </li>
            </ul>
          </template>
        </div>
      </NDrawerContent>
    </NDrawer>
    <NDrawer v-model:show="showHistory" width="min(520px, 100vw)">
      <NDrawerContent :title="t('graph.history')" closable>
        <NAlert v-if="revisions.error.value || switchError" type="error">{{
          revisions.error.value || switchError
        }}</NAlert>
        <NButton :loading="revisions.loading.value" @click="revisions.reload">{{
          t('graph.refresh')
        }}</NButton>
        <ul class="diff-list">
          <li v-for="item in revisions.data.value ?? []" :key="item.id">
            <span>{{ t('graph.historyItem', { id: item.id, run: item.run_id }) }}</span>
            <NTag v-if="item.is_current" type="success">{{ t('graph.currentRevision') }}</NTag>
            <NButton size="small" @click="selectGraph(item.id)">{{ t('common.view') }}</NButton>
            <NPopconfirm
              v-if="canWrite && item.publishable && !item.is_current"
              @positive-click="switchCurrent(item.id)"
            >
              <template #trigger
                ><NButton size="small" :disabled="switching">{{
                  t('graph.setCurrent')
                }}</NButton></template
              >
              {{ t('graph.setCurrentHint') }}
            </NPopconfirm>
          </li>
        </ul>
      </NDrawerContent>
    </NDrawer>
    <NDrawer v-model:show="showMatrix" :width="560">
      <NDrawerContent :title="t('graph.matrix')" closable>
        <NAlert v-if="!typeMatrix" type="info">{{ t('graph.matrixEmpty') }}</NAlert>
        <NDataTable
          v-else
          :columns="matrixColumns"
          :data="typeMatrix.rows"
          :row-key="matrixRowKey"
          :max-height="560"
          :scroll-x="120 + typeMatrix.types.length * 70"
          size="small"
        />
      </NDrawerContent>
    </NDrawer>
    <NDrawer v-model:show="showCentrality" :width="520">
      <NDrawerContent :title="t('graph.centrality')" closable>
        <p class="centrality-hint">{{ t('graph.centralityHint') }}</p>
        <NDataTable
          :columns="centralityColumns"
          :data="centralityRows"
          :row-key="centralityRowKey"
          :max-height="560"
          size="small"
        />
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.graph-page {
  height: calc(100dvh - 56px);
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.graph-heading {
  padding: 12px 20px 8px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
.graph-heading :deep(.page-header) {
  margin-bottom: 0;
}
.graph-heading :deep(h1) {
  font-size: 18px;
}
.workspace-context {
  color: var(--text-secondary);
  font-size: 12px;
}
.graph-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.graph-search {
  width: 280px;
  flex: 1;
  min-width: 200px;
  max-width: 360px;
}
.layout-select {
  width: 155px;
}
.graph-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  position: relative;
}
.canvas-area {
  flex: 1;
  position: relative;
  min-width: 0;
  min-height: 0;
  background: var(--canvas);
}
.canvas-area :deep(.canvas-panel) {
  height: 100%;
}
.canvas-empty {
  position: absolute;
  inset: 70px 0 32px;
  display: grid;
  place-items: center;
  pointer-events: none;
}
.canvas-empty :deep(.n-empty) {
  pointer-events: auto;
  padding: 20px;
  background: var(--canvas);
}
.loading-indicator {
  position: absolute;
  z-index: 3;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 20px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 7px;
}
.graph-message {
  padding: 6px 16px;
}
.graph-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  color: var(--text-secondary);
  font-size: 12px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
}
.graph-inspector {
  flex: 0 0 340px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border);
  background: var(--bg-surface);
}
.inspector-heading {
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.inspector-body {
  padding: 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.inspector-body h2 {
  font-size: 18px;
  margin: 0;
  overflow-wrap: anywhere;
}
.object-iri,
.evidence-context {
  font-size: 12px;
  color: var(--text-secondary);
  overflow-wrap: anywhere;
  margin: 0;
}
.attribute-list {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 12px;
  margin: 0;
}
.attribute-list dt {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: var(--text-secondary);
}
.attribute-list dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
}
.scope-hint {
  color: var(--text-secondary);
  font-size: 12px;
  margin: 0;
}
p {
  margin-top: 0;
}
@media (max-width: 1100px) {
  .graph-inspector {
    position: absolute;
    z-index: 5;
    top: 0;
    bottom: 0;
    right: 0;
    width: min(340px, 90vw);
    box-shadow: -4px 0 20px #0001;
  }
  .graph-footer {
    flex-wrap: wrap;
  }
}
/* 筛选字段：标签在左、控件在右，横向一行读完 */
label {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
label > span {
  flex: none;
  color: var(--text-secondary);
  font-size: var(--font-caption);
  white-space: nowrap;
}
label :deep(.n-select),
label :deep(.n-input-number),
label :deep(.n-input) {
  flex: 1;
  min-width: 0;
}
.inline-save {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.recommendation-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.recommendation-row .reason {
  color: var(--text-secondary);
}
.replay {
  display: flex;
  gap: 8px;
  align-items: center;
}
.replay > span {
  flex: none;
  color: var(--text-secondary);
  font-size: var(--font-caption);
}
.replay :deep(.n-slider) {
  flex: 1;
}
.panel-form {
  display: grid;
  gap: 12px;
}
.path-list {
  max-height: 320px;
  overflow: auto;
}
.diff-list {
  max-height: 320px;
  overflow: auto;
  font-size: var(--font-caption);
}
.diff-list .added {
  color: var(--success, #18a058);
}
.diff-list .removed {
  color: var(--danger, #d03050);
}
@media (max-width: 900px) {
  .controls {
    grid-template-columns: 1fr;
  }
}
</style>
