<script setup lang="ts">
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
import {
  FormContainer,
  FormField,
  SearchTable,
  UiAlert,
  UiButton,
  UiCheckbox,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiInputNumber,
  UiPopconfirm,
  UiPopselect,
  UiSelect,
  UiSlider,
  UiSpace,
  UiTabPane,
  UiTabs,
  UiTag,
} from '@/components/ui'
import type { FormRules } from '@/components/ui/formTypes'
import type { DataTableColumns } from '@/components/ui/tableTypes'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import { useAuthStore } from '@/stores/auth'
import EvidenceInspector from '@/views/graph/browse/components/EvidenceInspector.vue'
import GraphCanvas from '@/views/graph/browse/components/GraphCanvas.vue'
import { exportCsv, exportPng, exportSvg } from '@/views/graph/browse/components/graphExport'
import { LAYOUTS } from '@/views/graph/browse/components/graphLayout'
import KnowledgeGraphReferences from '@/views/graph/browse/components/KnowledgeGraphReferences.vue'
import {
  hasSemanticConfig,
  nodeTime,
  type SemanticContext,
} from '@/views/graph/browse/components/layouts/semanticView'
import SemanticViewConfig from '@/views/graph/browse/components/SemanticViewConfig.vue'
import GraphFactTable from '@/views/graph/components/GraphFactTable.vue'
import { relationLabels as frozenRelationLabels } from '@/views/graph/components/graphPresentation'
import { edgeKey, entityName, mergeNeighborhoods } from '@/views/graph/components/graphWorkspace'

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
const renderedEdge = shallowRef<GraphView['edges'][number] | null>(null)
const selectedAggregatedEdge = ref(false)
const selectedEdge = computed(() =>
  selectedAggregatedEdge.value
    ? renderedEdge.value
    : (data.value?.edges.find((edge) => edgeKey(edge) === selectedEdgeIdentity.value) ?? null),
)
const showEvidence = ref(false)
const inspectorOpen = ref(true)
const traceButton = ref<InstanceType<typeof UiButton> | null>(null)
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
    clearSelection()
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
  inspectorOpen.value = true
  if (!data.value?.nodes.some((node) => node.iri === iri)) {
    explore(iri)
    return
  }
  selectedIri.value = iri
  selectedEdgeIdentity.value = null
  renderedEdge.value = null
  selectedAggregatedEdge.value = false
  showEvidence.value = false
}
function selectEdge(edge: GraphView['edges'][number], aggregate = false) {
  inspectorOpen.value = true
  selectedEdgeIdentity.value = edgeKey(edge)
  renderedEdge.value = edge
  selectedAggregatedEdge.value = aggregate
  selectedIri.value = null
  showEvidence.value = false
}
function updateSelectedEdge(edge: GraphView['edges'][number] | null, aggregate: boolean) {
  if (!selectedEdgeIdentity.value) return
  if (!edge) {
    if (selectedAggregatedEdge.value) clearSelection()
    return
  }
  if (edgeKey(edge) !== selectedEdgeIdentity.value) return
  renderedEdge.value = edge
  selectedAggregatedEdge.value = aggregate
}
watch(layoutId, clearSelection)
function clearSelection() {
  selectedIri.value = null
  selectedEdgeIdentity.value = null
  renderedEdge.value = null
  selectedAggregatedEdge.value = false
  showEvidence.value = false
}
function dismissInspector() {
  if (showEvidence.value) {
    showEvidence.value = false
    void nextTick(() => traceButton.value?.$el.focus({ preventScroll: true }))
  } else {
    inspectorOpen.value = false
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
  if (!showEvidence.value || !revision || selectedAggregatedEdge.value) return Promise.resolve(null)
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
const layoutOptions = computed(() =>
  LAYOUTS.map((layout) => ({
    value: layout.id,
    label: t(`graph.layout.${layout.id}`),
  })),
)

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
const templateModel = computed(() => ({ name: templateName.value }))
const templateRules = computed<FormRules>(() => ({
  name: {
    required: true,
    type: 'string',
    message: t('common.required'),
    trigger: ['blur', 'input'],
  },
}))
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
    label: `${template.name_i18n[locale.value]?.trim() || `${template.layout_id} (${t('enumDictionaries.untranslated')})`}${template.stale ? ` · ${t('graph.templateStale')}` : ''}`,
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
async function applyTemplate(id: number | null) {
  if (id === null) return
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
    templates.value
      .find((item) => item.id === selectedTemplateId.value)
      ?.name_i18n[locale.value]?.trim() || t('enumDictionaries.untranslated'),
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
const pathHops = ref<number | null>(3)
const pathModel = computed(() => ({ from: pathFrom.value, to: pathTo.value, hops: pathHops.value }))
const pathRules = computed<FormRules>(() => ({
  from: {
    required: true,
    type: 'string',
    max: 640,
    message: t('graphUi.invalidPathIri'),
    trigger: ['blur', 'input'],
  },
  to: {
    required: true,
    type: 'string',
    max: 640,
    message: t('graphUi.invalidPathIri'),
    trigger: ['blur', 'input'],
  },
  hops: {
    required: true,
    type: 'integer',
    min: 1,
    max: 6,
    message: t('graphUi.invalidHops'),
    trigger: ['blur', 'input'],
  },
}))
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
  [graphId, pathFrom, pathTo, pathHops, includeDerived, showPath],
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
  if (
    !graph ||
    !pathFrom.value.trim() ||
    !pathTo.value.trim() ||
    pathFrom.value.length > 640 ||
    pathTo.value.length > 640 ||
    !Number.isSafeInteger(pathHops.value) ||
    pathHops.value === null ||
    pathHops.value < 1 ||
    pathHops.value > 6
  )
    return
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
const diffModel = computed(() => ({ base: diffBase.value, target: diffTarget.value }))
const diffRules = computed<FormRules>(() => ({
  base: {
    required: true,
    type: 'integer',
    min: 1,
    message: t('graphUi.invalidRevision'),
    trigger: ['blur', 'input'],
  },
  target: {
    required: true,
    type: 'integer',
    min: 1,
    message: t('graphUi.invalidRevision'),
    trigger: ['blur', 'input'],
  },
}))
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
  if (
    !Number.isSafeInteger(diffBase.value) ||
    !Number.isSafeInteger(diffTarget.value) ||
    diffBase.value === null ||
    diffTarget.value === null ||
    diffBase.value < 1 ||
    diffTarget.value < 1
  )
    return
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
const exportOptions = computed(() =>
  ['png', 'svg', 'csv'].map((kind) => ({
    value: kind,
    label: t(`graph.export.${kind}`),
  })),
)

// ===== 邻接矩阵（G-20）与中心性排行（G-32）抽屉 =====
const centralityColumns = computed<
  DataTableColumns<{ iri: string; name: string; in: number; out: number; total: number }>
>(() => [
  { key: 'name', title: t('common.name'), width: 160, ellipsis: { tooltip: true } },
  { key: 'in', title: t('graph.degreeIn'), width: 70 },
  { key: 'out', title: t('graph.degreeOut'), width: 70 },
  { key: 'total', title: t('graph.degreeTotal'), width: 80 },
  {
    key: 'go',
    title: t('common.actions'),
    width: 110,
    fixed: 'right',
    render: (row: { iri: string }) =>
      h(UiButton, { size: 'tiny', onClick: () => explore(row.iri) }, () => t('graph.exploreShort')),
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
function onExport(kind: string | number) {
  if (kind === 'png' || kind === 'svg' || kind === 'csv') void doExport(kind)
}
</script>

<template>
  <section class="graph-page">
    <div class="graph-heading">
      <PageHeader
        :title="t('page.graphBrowse')"
        :eyebrow="t('studio.graphStudio')"
        :identity="data ? t('graph.resultSet', { id: data.graph_revision_id }) : undefined"
      >
        <template #context
          ><span class="workspace-context">{{ t('ui.readOnlyLabel') }}</span></template
        >
        <template #actions>
          <RouterLink v-if="knowledgeReturn" :to="knowledgeReturn">{{
            t('kb.backToSearch')
          }}</RouterLink>
          <UiButton size="small" @click="showHistory = true">{{ t('graph.history') }}</UiButton>
          <RouterLink :to="{ name: 'graph-entities', query: { graph: data?.graph_revision_id } }">{{
            t('page.graphEntities')
          }}</RouterLink>
        </template>
      </PageHeader>
    </div>
    <div v-if="data" class="observation-binding">
      <span
        >{{ t('graph.chainRun') }} <code>{{ `#${data.run_id}` }}</code></span
      >
      <span v-if="data.ontology_id"
        >{{ t('page.ontologies') }} <code>{{ `#${data.ontology_id}` }}</code></span
      >
      <span v-if="data.ontology_revision"
        >{{ t('designerUi.frozenContent') }} <code>{{ `r${data.ontology_revision}` }}</code></span
      >
      <span v-else>{{ t('graph.chainUnpinned') }}</span>
      <span class="spacer" />
      <RouterLink :to="{ name: 'graph-reports', query: { graph: data.graph_revision_id } }">{{
        t('page.graphReports')
      }}</RouterLink>
    </div>
    <div class="graph-toolbar">
      <UiSelect
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
      <UiSelect
        class="layout-select"
        :value="layoutId ?? (center ? 'ring' : 'type_grid')"
        :options="layoutOptions"
        :aria-label="t('graph.layoutLabel')"
        @update:value="selectLayout"
      />
      <UiButton
        :type="excludedTypes.length || relationshipFilter.length ? 'primary' : 'default'"
        @click="showSettings = true"
        >{{ t('graphUi.filters') }}</UiButton
      >
      <UiButton :disabled="!data" @click="showPath = true">{{ t('graph.pathQuery') }}</UiButton>
      <UiButton :disabled="!data" @click="showFacts = true">{{ t('graphUi.facts') }}</UiButton>
      <UiButton :disabled="!center" @click="explore(null)">{{ t('graph.overview') }}</UiButton>
      <UiButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</UiButton>
      <UiButton :aria-expanded="inspectorOpen" @click="inspectorOpen = !inspectorOpen">{{
        t('graphUi.inspector')
      }}</UiButton>
    </div>
    <div v-if="error || branchError || search.error.value || exportError" class="graph-message">
      <UiAlert type="warning"
        >{{ error || branchError || search.error.value || exportError
        }}<span v-if="data"> · {{ t('graphUi.retained') }}</span>
        <span class="alert-action"
          ><UiButton
            size="small"
            @click="error ? reload() : branchError ? expandSelected() : search.reload()"
            >{{ t('ui.retry') }}</UiButton
          ></span
        >
      </UiAlert>
    </div>
    <div v-if="data?.truncated" class="graph-message">
      <UiAlert type="warning">{{ t('graphUi.limited') }}</UiAlert>
    </div>
    <div v-if="qualityOverlay" class="graph-message">
      <UiAlert type="info">{{
        t('graphUi.qualityScope', { count: data?.quarantine_count ?? '—' })
      }}</UiAlert>
    </div>
    <label
      v-if="layoutId === 'timeline' && replayBounds && replayRange"
      class="replay graph-message"
    >
      <span>{{ t('graph.replay') }}</span
      ><UiSlider
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
          @selected-edge-updated="updateSelectedEdge"
        />
        <div v-if="!loading && !visibleGraph?.nodes.length" class="canvas-empty">
          <UiEmpty :description="error ? t('graphUi.loadFailed') : t('graph.noVisibleNodes')"
            ><template #extra
              ><UiButton @click="error ? reload() : clearFilters()">{{
                error ? t('ui.retry') : t('ui.clearFilters')
              }}</UiButton></template
            ></UiEmpty
          >
        </div>
      </main>
      <aside
        v-if="inspectorOpen && (selectedNode || selectedEdge)"
        class="graph-inspector"
        :class="{ 'inspector-idle': !selectedNode && !selectedEdge }"
        :aria-label="t('graphUi.inspector')"
      >
        <div class="inspector-heading">
          <strong>{{ showEvidence ? t('page.graphEvidence') : t('graphUi.inspector') }}</strong
          ><UiButton size="small" quaternary @click="dismissInspector">{{
            showEvidence ? t('graphUi.backObject') : t('common.close')
          }}</UiButton>
        </div>
        <div class="inspector-body">
          <UiEmpty v-if="!selectedNode && !selectedEdge" :description="t('studio.selectObject')" />
          <div v-if="data && (selectedNode || selectedEdge)" class="inspector-binding">
            <span>{{ t('graph.resultSet', { id: data.graph_revision_id }) }}</span>
            <code v-if="selectedEdge">{{ edgeKey(selectedEdge) }}</code>
            <span>{{ t('ui.readOnlyLabel') }}</span>
          </div>
          <template v-if="!showEvidence && (selectedNode || selectedEdge)">
            <template v-if="selectedNode">
              <UiTag size="small">{{ shortName(selectedNode.type_iri) }}</UiTag>
              <h2>{{ entityName(selectedNode) }}</h2>
              <p class="object-iri">{{ selectedNode.iri }}</p>
              <UiSpace
                ><UiButton
                  type="primary"
                  :loading="expanding"
                  :disabled="loading || !!error || data!.nodes.length >= 500"
                  @click="expandSelected"
                  >{{ t('graphUi.expand') }}</UiButton
                ><UiButton
                  :disabled="!branches.has(selectedNode.iri) || loading"
                  @click="collapseSelected"
                  >{{ t('graphUi.collapse') }}</UiButton
                ></UiSpace
              >
              <dl class="attribute-list">
                <template v-for="(value, key) in selectedNode.attrs" :key="key"
                  ><dt>{{ key }}</dt>
                  <dd>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</dd></template
                >
              </dl>
            </template>
            <template v-if="selectedEdge">
              <UiTag size="small" :type="selectedEdge.kind === 'DERIVED' ? 'warning' : 'default'">{{
                selectedAggregatedEdge
                  ? t('graphUi.aggregatedRelation')
                  : t(selectedEdge.kind === 'DERIVED' ? 'graph.derived' : 'graph.directRelation')
              }}</UiTag>
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
              <UiAlert v-if="selectedEdge.kind === 'DERIVED'" type="info">{{
                t('graphUi.derivedEvidence')
              }}</UiAlert>
            </template>
            <UiButton
              ref="traceButton"
              block
              :disabled="
                selectedAggregatedEdge || selectedEdge?.kind === 'DERIVED' || loading || !!error
              "
              @click="showEvidence = true"
              >{{ t('graph.trace') }}</UiButton
            >
          </template>
          <template v-else-if="showEvidence">
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
            <UiAlert v-else-if="evidence.error.value" type="warning"
              >{{ evidence.error.value
              }}<span class="alert-action"
                ><UiButton @click="evidence.reload">{{ t('ui.retry') }}</UiButton></span
              ></UiAlert
            >
            <template v-else-if="evidence.data.value"
              ><p>{{ t('graph.totalEvidence', { n: evidence.data.value.total_count }) }}</p>
              <EvidenceInspector :items="evidence.data.value.evidences" /><UiEmpty
                v-if="!evidence.data.value.total_count"
                :description="t('graphUi.noEvidence')"
            /></template>
          </template>
          <KnowledgeGraphReferences
            v-if="
              data && (selectedNode || (selectedEdge?.kind === 'DIRECT' && !selectedAggregatedEdge))
            "
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
      <span v-if="data?.truncated" class="truncation-readout">{{ t('graphUi.limited') }}</span>
      <span>{{ t('designerUi.gestures') }}</span>
    </footer>
    <UiDrawer v-model:show="showSettings" :width="420"
      ><UiDrawerContent :title="t('graphUi.filters')" closable
        ><div class="panel-form">
          <label
            ><span>{{ t('graph.revisionInput') }}</span
            ><UiInputNumber
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
            ><UiSelect
              v-model:value="depth"
              :options="[
                { label: t('graph.oneDegree'), value: 1 },
                { label: t('graph.twoDegrees'), value: 2 },
              ]"
              :aria-label="t('graph.depth')"
          /></label>
          <label
            ><span>{{ t('graph.hiddenTypes') }}</span
            ><UiSelect
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
            ><UiSelect
              v-model:value="relationshipFilter"
              :options="relationshipOptions"
              multiple
              clearable
              :aria-label="t('graphUi.relationships')"
              :placeholder="t('graphUi.allRelations')"
          /></label>
          <UiCheckbox v-model:checked="includeDerived">{{ t('graph.showDerived') }}</UiCheckbox
          ><UiCheckbox v-model:checked="qualityOverlay">{{ t('graph.qualityOverlay') }}</UiCheckbox
          ><UiButton @click="clearFilters">{{ t('ui.clearFilters') }}</UiButton>
          <h3>{{ t('graphUi.analysis') }}</h3>
          <p class="scope-hint">{{ t('graphUi.analysisScope') }}</p>
          <UiSpace
            ><UiButton @click="openAnalysis('diff')">{{ t('graph.diffQuery') }}</UiButton
            ><UiButton @click="openAnalysis('matrix')">{{ t('graph.matrix') }}</UiButton
            ><UiButton @click="openAnalysis('centrality')">{{ t('graph.centrality') }}</UiButton
            ><UiPopselect :options="exportOptions" trigger="click" @update:value="onExport"
              ><UiButton :disabled="!data">{{ t('graph.export.title') }}</UiButton></UiPopselect
            ></UiSpace
          >
          <h3>{{ t('graph.templates') }}</h3>
          <UiAlert v-if="templateError || templateData.error.value" type="warning">{{
            templateError || templateData.error.value
          }}</UiAlert>
          <UiSelect
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
          <FormContainer
            v-if="data && canWrite"
            :model="templateModel"
            :rules="templateRules"
            :disabled="
              savingTemplate || semanticFields.loading.value || semanticFields.data.value?.stale
            "
            class="template-form"
            @submit="saveTemplate"
          >
            <FormField path="name" :label="t('graph.templateName')">
              <UiInput v-model:value="templateName" :placeholder="t('graph.templateName')" />
            </FormField>
            <UiButton
              attr-type="submit"
              :loading="savingTemplate"
              :disabled="semanticFields.loading.value || semanticFields.data.value?.stale"
              >{{ t('graph.templateSave') }}</UiButton
            >
          </FormContainer>
          <UiPopconfirm
            v-if="canWrite && selectedTemplateId !== null"
            @positive-click="removeTemplate"
            ><template #trigger
              ><UiButton tertiary type="error" :loading="removingTemplate">{{
                t('graph.templateDelete')
              }}</UiButton></template
            >{{ t('graph.templateDeleteConfirm', { name: selectedTemplateName }) }}</UiPopconfirm
          >
          <UiAlert v-if="recommendations?.recommendations.length" type="info"
            ><p>{{ t('graph.recommended') }}</p>
            <UiSpace
              ><UiButton
                v-for="item in recommendations.recommendations.filter(
                  (rec) => rec.reason_key !== 'graph.reason.generic',
                )"
                :key="item.layout_id"
                size="small"
                @click="selectLayout(item.layout_id)"
                >{{ t(`graph.layout.${item.layout_id}`) }}</UiButton
              ></UiSpace
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
            </p></UiAlert
          >
        </div></UiDrawerContent
      ></UiDrawer
    >
    <UiDrawer v-model:show="showFacts" width="min(960px, 100vw)"
      ><UiDrawerContent :title="t('graphUi.facts')" closable
        ><p>{{ t('graphUi.analysisScope') }}</p>
        <UiTabs v-if="visibleGraph" type="line"
          ><UiTabPane name="direct" :tab="t('graph.directRelation')"
            ><GraphFactTable
              :items="visibleGraph.edges.filter((edge) => edge.kind === 'DIRECT')"
              :relation-labels="relationLabels"
              :graph-revision-id="visibleGraph.graph_revision_id" /></UiTabPane
          ><UiTabPane name="derived" :tab="t('graph.derived')"
            ><p>{{ t('graph.derivedHint') }}</p>
            <GraphFactTable
              :items="visibleGraph.edges.filter((edge) => edge.kind === 'DERIVED')"
              :relation-labels="relationLabels"
              :graph-revision-id="visibleGraph.graph_revision_id"
              derived /></UiTabPane></UiTabs></UiDrawerContent
    ></UiDrawer>
    <UiDrawer v-model:show="showPath" :width="420">
      <UiDrawerContent :title="t('graph.pathQuery')" closable>
        <FormContainer
          id="graph-path-form"
          :model="pathModel"
          :rules="pathRules"
          class="panel-form"
          @submit="findPath"
        >
          <FormField path="from" :label="t('graph.pathFrom')">
            <UiInput v-model:value="pathFrom" />
          </FormField>
          <FormField path="to" :label="t('graph.pathTo')">
            <UiInput v-model:value="pathTo" />
          </FormField>
          <FormField path="hops" :label="t('graph.pathHops')">
            <UiInputNumber v-model:value="pathHops" :min="1" :max="6" />
          </FormField>
          <UiAlert v-if="pathError" type="warning">{{ pathError }}</UiAlert>
          <template v-if="pathResult">
            <UiAlert :type="pathResult.found ? 'success' : 'warning'">
              {{
                pathResult.found
                  ? t('graph.pathFound', { hops: pathResult.hops })
                  : t('graph.pathNotFound')
              }}
            </UiAlert>
            <ol v-if="pathResult.found" class="path-list">
              <li v-for="node in pathResult.nodes" :key="node">{{ node }}</li>
            </ol>
          </template>
        </FormContainer>
        <template #footer>
          <UiButton
            type="primary"
            attr-type="submit"
            form="graph-path-form"
            :loading="pathLoading"
            :disabled="!data || loading"
          >
            {{ t('graph.pathFind') }}
          </UiButton>
        </template>
      </UiDrawerContent>
    </UiDrawer>
    <UiDrawer v-model:show="showDiff" :width="520">
      <UiDrawerContent :title="t('graph.diffQuery')" closable>
        <FormContainer
          id="graph-diff-form"
          :model="diffModel"
          :rules="diffRules"
          class="panel-form"
          @submit="runDiff"
        >
          <FormField path="base" :label="t('graph.diffBase')">
            <UiInputNumber v-model:value="diffBase" :min="1" :precision="0" />
          </FormField>
          <FormField path="target" :label="t('graph.diffTarget')">
            <UiInputNumber v-model:value="diffTarget" :min="1" :precision="0" />
          </FormField>
          <UiAlert v-if="diffError" type="warning">{{ diffError }}</UiAlert>
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
            <UiAlert v-if="diffResult.truncated" type="warning">{{ t('graph.truncated') }}</UiAlert>
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
        </FormContainer>
        <template #footer>
          <UiButton type="primary" attr-type="submit" form="graph-diff-form" :loading="diffLoading">
            {{ t('graph.diffRun') }}
          </UiButton>
        </template>
      </UiDrawerContent>
    </UiDrawer>
    <UiDrawer v-model:show="showHistory" width="min(520px, 100vw)">
      <UiDrawerContent :title="t('graph.history')" closable>
        <UiAlert v-if="revisions.error.value || switchError" type="error">{{
          revisions.error.value || switchError
        }}</UiAlert>
        <UiButton :loading="revisions.loading.value" @click="revisions.reload">{{
          t('graph.refresh')
        }}</UiButton>
        <ul class="diff-list">
          <li v-for="item in revisions.data.value ?? []" :key="item.id">
            <span>{{ t('graph.historyItem', { id: item.id, run: item.run_id }) }}</span>
            <UiTag v-if="item.is_current" type="success">{{ t('graph.currentRevision') }}</UiTag>
            <UiButton size="small" @click="selectGraph(item.id)">{{ t('common.view') }}</UiButton>
            <UiPopconfirm
              v-if="canWrite && item.publishable && !item.is_current"
              @positive-click="switchCurrent(item.id)"
            >
              <template #trigger
                ><UiButton size="small" :disabled="switching">{{
                  t('graph.setCurrent')
                }}</UiButton></template
              >
              {{ t('graph.setCurrentHint') }}
            </UiPopconfirm>
          </li>
        </ul>
      </UiDrawerContent>
    </UiDrawer>
    <UiDrawer v-model:show="showMatrix" :width="560">
      <UiDrawerContent :title="t('graph.matrix')" closable>
        <UiAlert v-if="!typeMatrix" type="info">{{ t('graph.matrixEmpty') }}</UiAlert>
        <SearchTable
          v-else
          mode="none"
          :searchable="false"
          :columns="matrixColumns"
          :rows="typeMatrix.rows"
          :row-key="matrixRowKey"
          :max-height="560"
          :scroll-x="120 + typeMatrix.types.length * 70"
          size="small"
        />
      </UiDrawerContent>
    </UiDrawer>
    <UiDrawer v-model:show="showCentrality" :width="520">
      <UiDrawerContent :title="t('graph.centrality')" closable>
        <p class="centrality-hint">{{ t('graph.centralityHint') }}</p>
        <SearchTable
          mode="none"
          :searchable="false"
          :columns="centralityColumns"
          :rows="centralityRows"
          :row-key="centralityRowKey"
          :max-height="560"
          size="small"
        />
      </UiDrawerContent>
    </UiDrawer>
  </section>
</template>

<style scoped>
.graph-page {
  height: calc(100dvh - var(--header-height, 56px));
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.graph-heading {
  padding: var(--space-3) var(--space-5) var(--space-2);
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-default);
}
.graph-heading :deep(.page-header) {
  margin-bottom: 0;
}
.graph-heading :deep(h1) {
  font-size: var(--font-h2);
}
.workspace-context {
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.graph-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--surface-panel);
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
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--surface-background);
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
.canvas-empty :deep(.ui-empty) {
  pointer-events: auto;
  padding: 20px;
  background: var(--canvas);
}
.loading-indicator {
  position: absolute;
  z-index: var(--z-sticky);
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 20px;
  background: var(--surface-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
}
.graph-message {
  padding: 6px 16px;
}
.graph-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
  background: var(--surface-panel);
  border-top: 1px solid var(--border-default);
}
.graph-inspector {
  flex: 0 0 300px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-default);
  background: var(--surface-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-panel);
  overflow: hidden;
}
.observation-binding {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 7px 16px;
  align-items: center;
  background: var(--surface-muted);
  border-bottom: 1px solid var(--border-default);
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.observation-binding code,
.inspector-binding code {
  font-family: var(--font-mono, monospace);
  color: var(--foreground-primary);
}
.observation-binding .spacer {
  flex: 1;
}
.inspector-binding {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 10px;
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
  background: var(--surface-muted);
  border-left: 2px solid var(--action-primary);
}
.truncation-readout {
  color: var(--status-not-run);
}
.inspector-heading {
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
}
.inspector-body {
  padding: 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.inspector-body h2 {
  font-size: var(--font-h2);
  margin: 0;
  overflow-wrap: anywhere;
}
.object-iri,
.evidence-context {
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
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
  font-size: var(--font-caption);
  color: var(--foreground-secondary);
}
.attribute-list dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: var(--font-small);
}
.scope-hint {
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
  margin: 0;
}
p {
  margin-top: 0;
}
@media (max-width: 64rem) {
  .graph-inspector {
    position: absolute;
    z-index: var(--z-sticky);
    top: 0;
    bottom: 0;
    right: 0;
    width: min(340px, 90vw);
    box-shadow: var(--shadow-overlay);
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
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
  white-space: nowrap;
}
label :deep(.ui-select),
label :deep(.ui-input-wrap) {
  flex: 1;
  min-width: 0;
}
.recommendation-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.recommendation-row .reason {
  color: var(--foreground-secondary);
}
.replay {
  display: flex;
  gap: 8px;
  align-items: center;
}
.replay > span {
  flex: none;
  color: var(--foreground-secondary);
  font-size: var(--font-caption);
}
.replay :deep(.ui-slider) {
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
  color: var(--status-pass);
}
.diff-list .removed {
  color: var(--status-violation);
}
@media (max-width: 48rem) {
  .graph-heading {
    padding: 8px 12px;
  }
  .graph-workspace {
    padding: 6px;
  }
  .graph-toolbar {
    padding: var(--space-2) var(--space-3);
    gap: var(--space-2);
    flex-wrap: nowrap;
    overflow-x: auto;
    flex-shrink: 0;
  }
  .graph-toolbar > * {
    flex-shrink: 0;
  }
  .graph-search {
    min-width: 180px;
  }
  .graph-footer {
    padding: 6px 12px;
    font-size: var(--font-caption);
  }
}
</style>
