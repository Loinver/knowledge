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
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import {
  graphApi,
  type GraphDiff,
  type GraphPath,
  type GraphRecommendations,
  type ViewTemplate,
  viewTemplateApi,
} from '@/api/graph'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAsyncData } from '@/composables/useAsyncData'
import GraphCanvas from '@/views/graph/components/GraphCanvas.vue'
import { exportCsv, exportPng, exportSvg } from '@/views/graph/components/graphExport'
import GraphFactTable from '@/views/graph/components/GraphFactTable.vue'
import { LAYOUTS } from '@/views/graph/components/graphLayout'

const { t } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()
const center = computed(() => (typeof route.query.center === 'string' ? route.query.center : ''))
const graphId = computed(() => (route.query.graph ? Number(route.query.graph) : undefined))
const layoutId = computed(() =>
  typeof route.query.layout === 'string' ? route.query.layout : null,
)
const depth = ref(1)
const excludedTypes = ref<string[]>([])
const includeDerived = ref(true)
const searchText = ref('')
const { data, loading, error, reload } = useAsyncData((signal) =>
  graphApi.view(
    {
      graph_revision_id: graphId.value,
      center: center.value,
      depth: depth.value,
      excluded_types: excludedTypes.value,
      include_derived: includeDerived.value,
    },
    signal,
  ),
)
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
      label: `${node.attrs.name ?? node.row_key} · ${node.iri}`,
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
  const query: Record<string, string | number | undefined> = {}
  for (const [key, value] of Object.entries(patch)) {
    if (value !== null && value !== undefined) query[key] = value as string | number
  }
  void router.replace({ query: { ...route.query, ...query } })
}

function explore(iri: string | null) {
  updateQuery({
    graph: graphId.value ?? data.value?.graph_revision_id,
    center: iri || undefined,
  })
}

function selectGraph(id: number | null) {
  excludedTypes.value = []
  updateQuery({ graph: id || undefined, layout: undefined })
}

function selectLayout(id: string | null) {
  updateQuery({ layout: id || undefined })
}

// ===== 形态推荐（语义信号 → 形态 + 理由） =====
const recommendations = ref<GraphRecommendations | null>(null)
watch(
  () => [data.value?.graph_revision_id] as const,
  ([revision], previous) => {
    if (!revision || revision === previous?.[0]) return
    void graphApi
      .recommendations(revision, new AbortController().signal)
      .then((result) => {
        recommendations.value = result
      })
      .catch(() => {
        recommendations.value = null
      })
  },
  { immediate: true },
)
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
const templates = ref<ViewTemplate[]>([])
const templateError = ref('')
const templateName = ref('')
watch(
  () => data.value?.ontology_id,
  () => {
    const signal = new AbortController().signal
    if (!data.value?.ontology_id) {
      templates.value = []
      return
    }
    void viewTemplateApi
      .list(data.value.ontology_id, signal)
      .then((page) => {
        templates.value = page.items
      })
      .catch(() => {
        templates.value = []
      })
  },
  { immediate: true },
)
const templateOptions = computed(() =>
  templates.value.map((template) => ({
    value: template.id,
    label: `${template.name_i18n['zh-CN'] || template.layout_id}${template.stale ? ` · ${t('graph.templateStale')}` : ''}`,
  })),
)
async function saveTemplate() {
  const name = templateName.value.trim()
  if (!name || !data.value?.ontology_id || !data.value?.ontology_revision) return
  try {
    await viewTemplateApi.create({
      name_i18n: { 'zh-CN': name, 'en-US': name },
      layout_id: layoutId.value ?? (center.value ? 'ring' : 'type_grid'),
      config: {
        center: center.value || undefined,
        depth: depth.value,
        excluded_types: excludedTypes.value,
      },
      ontology_id: data.value.ontology_id,
      ontology_revision: data.value.ontology_revision,
    })
    templateName.value = ''
    const page = await viewTemplateApi.list(data.value.ontology_id, new AbortController().signal)
    templates.value = page.items
  } catch (cause) {
    templateError.value = toMessage(cause)
  }
}
function applyTemplate(id: number) {
  selectedTemplateId.value = id
  const template = templates.value.find((item) => item.id === id)
  if (!template) return
  const config = template.config as {
    center?: string
    depth?: number
    excluded_types?: string[]
  }
  depth.value = config.depth ?? 1
  excludedTypes.value = config.excluded_types ?? []
  updateQuery({
    layout: template.layout_id,
    center: config.center || undefined,
  })
}

// 模板此前只能创建和应用，已保存的视图无法删除；应用后出现删除入口。
const selectedTemplateId = ref<number | null>(null)
const removingTemplate = ref(false)
const selectedTemplateName = computed(
  () =>
    templates.value.find((item) => item.id === selectedTemplateId.value)?.name_i18n['zh-CN'] ?? '',
)
async function removeTemplate() {
  if (selectedTemplateId.value === null || removingTemplate.value) return
  removingTemplate.value = true
  templateError.value = ''
  try {
    await viewTemplateApi.remove(selectedTemplateId.value)
    if (data.value?.ontology_id) {
      const page = await viewTemplateApi.list(data.value.ontology_id, new AbortController().signal)
      templates.value = page.items
    }
    selectedTemplateId.value = null
  } catch (cause) {
    templateError.value = toMessage(cause)
  } finally {
    removingTemplate.value = false
  }
}

// ===== 质量叠加（G-28）：隔离命中节点标记 =====
const qualityOverlay = ref(false)
const flaggedIris = ref<Set<string>>(new Set())
watch(
  [qualityOverlay, () => data.value?.run_id] as const,
  ([enabled, runId]) => {
    if (!enabled || !runId) {
      flaggedIris.value = new Set()
      return
    }
    // 拉取失败只影响叠加标记，静默清空即可，但不能留下未处理的 rejection
    void graphApi
      .runQuarantine(runId, new AbortController().signal)
      .then((rows) => {
        const rowKeys = new Set(rows.map((row) => row.row_key))
        flaggedIris.value = new Set(
          (data.value?.nodes ?? [])
            .filter((node) => rowKeys.has(node.row_key))
            .map((node) => node.iri),
        )
      })
      .catch(() => {
        flaggedIris.value = new Set()
      })
  },
  { immediate: true },
)

// ===== 关系路径（G-12）与版本差异（G-24）抽屉 =====
const showPath = ref(false)
const showDiff = ref(false)
const showMatrix = ref(false)
const showCentrality = ref(false)
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
async function findPath() {
  const graph = graphId.value ?? data.value?.graph_revision_id
  if (!graph || !pathFrom.value || !pathTo.value) return
  pathError.value = ''
  try {
    pathResult.value = await graphApi.path(
      graph,
      { from: pathFrom.value, to: pathTo.value, max_hops: pathHops.value, include_derived: true },
      new AbortController().signal,
    )
  } catch (cause) {
    pathError.value = toMessage(cause)
  }
}

const revisions = ref<{ id: number }[]>([])
const diffBase = ref<number | null>(null)
const diffTarget = ref<number | null>(null)
// 打开抽屉时预填最近两个结果集，便于直接计算差异
watch(showDiff, (open) => {
  if (!open) return
  const target = data.value?.graph_revision_id
  if (target) diffTarget.value = target
  if (!diffBase.value && target) diffBase.value = Math.max(1, target - 1)
})
const diffResult = ref<GraphDiff | null>(null)
const diffError = ref('')
watch(showDiff, async (open) => {
  if (!open || revisions.value.length) return
  try {
    const page = await graphApi.revisions(new AbortController().signal)
    revisions.value = page.items
  } catch {
    revisions.value = []
  }
})
async function runDiff() {
  if (!diffBase.value || !diffTarget.value) return
  diffError.value = ''
  try {
    diffResult.value = await graphApi.diff(
      diffBase.value,
      diffTarget.value,
      new AbortController().signal,
    )
  } catch (cause) {
    diffError.value = toMessage(cause)
  }
}

// ===== 导出（PNG/SVG/CSV） =====
const exportError = ref('')
function svgElement(): SVGSVGElement | null {
  return document.querySelector('.canvas-scroll svg')
}
async function doExport(kind: 'png' | 'svg' | 'csv') {
  exportError.value = ''
  const graph = data.value
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
  const graph = data.value
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
  const graph = data.value
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
      name: String(graph.nodes.find((node) => node.iri === iri)?.attrs.name ?? iri).slice(0, 30),
      in: value.in,
      out: value.out,
      total: value.in + value.out,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 30)
})

// ===== 时间切片回放（G-23）：timeline 形态下按日期窗口过滤画布数据 =====
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}/
const replayRange = ref<[number, number] | null>(null)
const replayBounds = computed<[number, number] | null>(() => {
  const graph = data.value
  if (!graph) return null
  const times: number[] = []
  for (const node of graph.nodes) {
    for (const value of Object.values(node.attrs)) {
      if (typeof value === 'string' && ISO_DATE_RE.test(value)) {
        times.push(new Date(value.slice(0, 10)).getTime())
        break
      }
    }
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
        for (const value of Object.values(node.attrs)) {
          if (typeof value === 'string' && ISO_DATE_RE.test(value)) {
            const time = new Date(value.slice(0, 10)).getTime()
            return time >= range[0] && time <= range[1]
          }
        }
        return false
      })
      .map((node) => node.iri),
  )
  return {
    ...graph,
    nodes: graph.nodes.filter((node) => keep.has(node.iri)),
    edges: graph.edges.filter((edge) => keep.has(edge.subject) && keep.has(edge.object_)),
  }
})
function onExport(kind: string) {
  void doExport(kind as 'png' | 'svg' | 'csv')
}
</script>

<template>
  <section class="graph-page">
    <PageHeader :title="t('page.graphBrowse')" :description="t('graph.canvasHint')">
      <template #actions>
        <RouterLink :to="{ name: 'graph-entities', query: { graph: data?.graph_revision_id } }">{{
          t('page.graphEntities')
        }}</RouterLink>
      </template>
    </PageHeader>
    <div class="controls">
      <label>
        <span>{{ t('graph.searchHint') }}</span>
        <NSelect
          :value="center || null"
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
      </label>
      <label>
        <span>{{ t('graph.depth') }}</span>
        <NSelect
          v-model:value="depth"
          :disabled="!center"
          :options="[
            { label: t('graph.oneDegree'), value: 1 },
            { label: t('graph.twoDegrees'), value: 2 },
          ]"
          :aria-label="t('graph.depth')"
        />
      </label>
      <label>
        <span>{{ t('graph.revisionInput') }}</span>
        <NInputNumber
          :value="graphId ?? null"
          :min="1"
          :precision="0"
          clearable
          :placeholder="t('graph.currentResult')"
          :aria-label="t('graph.revisionInput')"
          @update:value="selectGraph"
        />
      </label>
      <label>
        <span>{{ t('graph.layoutLabel') }}</span>
        <NSelect
          :value="layoutId ?? (center ? 'ring' : 'type_grid')"
          :options="layoutOptions"
          :aria-label="t('graph.layoutLabel')"
          @update:value="selectLayout"
        />
      </label>
    </div>
    <NAlert v-if="search.error.value" type="warning">{{ search.error.value }}</NAlert>
    <NSpace align="center">
      <NButton :disabled="!center" @click="explore(null)">{{ t('graph.overview') }}</NButton>
      <NCheckbox v-model:checked="includeDerived">{{ t('graph.showDerived') }}</NCheckbox>
      <NCheckbox v-model:checked="qualityOverlay">{{ t('graph.qualityOverlay') }}</NCheckbox>
      <NButton @click="showPath = true">{{ t('graph.pathQuery') }}</NButton>
      <NButton @click="showDiff = true">{{ t('graph.diffQuery') }}</NButton>
      <NButton @click="showMatrix = true">{{ t('graph.matrix') }}</NButton>
      <NButton @click="showCentrality = true">{{ t('graph.centrality') }}</NButton>
      <NPopselect :options="exportOptions" trigger="click" @update:value="onExport">
        <NButton>{{ t('graph.export.title') }}</NButton>
      </NPopselect>
      <NButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</NButton>
      <RouterLink
        v-if="center && data"
        :to="{
          name: 'graph-entity-detail',
          params: { id: center },
          query: { graph: data.graph_revision_id },
        }"
        >{{ t('page.graphEntityDetail') }}</RouterLink
      >
      <NPopselect
        v-if="templateOptions.length"
        :options="templateOptions"
        trigger="click"
        @update:value="applyTemplate"
      >
        <NButton>{{ t('graph.templates') }}</NButton>
      </NPopselect>
      <NPopconfirm v-if="selectedTemplateId !== null" @positive-click="removeTemplate">
        <template #trigger>
          <NButton size="small" tertiary type="error" :loading="removingTemplate">{{
            t('graph.templateDelete')
          }}</NButton>
        </template>
        {{ t('graph.templateDeleteConfirm', { name: selectedTemplateName }) }}
      </NPopconfirm>
      <span v-if="data" class="inline-save">
        <NInput
          v-model:value="templateName"
          size="small"
          :placeholder="t('graph.templateName')"
          @keydown.enter.prevent="saveTemplate"
        />
        <NButton size="small" :disabled="!templateName.trim()" @click="saveTemplate">{{
          t('graph.templateSave')
        }}</NButton>
      </span>
    </NSpace>
    <label>
      <span>{{ t('graph.hiddenTypes') }}</span>
      <NSelect
        v-model:value="excludedTypes"
        :options="typeOptions"
        multiple
        clearable
        :aria-label="t('graph.hiddenTypes')"
        :placeholder="t('graph.hiddenTypes')"
      />
    </label>
    <NAlert v-if="recommendations?.recommendations.length" type="info" class="recommendations">
      <div class="recommendation-row">
        <span>{{ t('graph.recommended') }}</span>
        <NButton
          v-for="item in recommendations.recommendations.filter(
            (rec) => rec.reason_key !== 'graph.reason.generic',
          )"
          :key="item.layout_id"
          size="tiny"
          :type="layoutId === item.layout_id ? 'primary' : 'default'"
          @click="selectLayout(item.layout_id)"
        >
          {{ t(`graph.layout.${item.layout_id}`) }}
        </NButton>
        <span class="reason">
          {{
            reasonText(
              recommendations.recommendations.find(
                (rec) => rec.reason_key !== 'graph.reason.generic',
              )?.reason_key ?? 'graph.reason.generic',
              recommendations.signals,
            )
          }}
        </span>
        <NTag
          v-for="item in recommendations.recommendations.filter(
            (rec) => rec.reason_key !== 'graph.reason.generic',
          )"
          :key="item.layout_id + '-tag'"
          size="small"
          :type="layoutId === item.layout_id ? 'primary' : 'default'"
          round
        >
          {{ item.layout_id }}
        </NTag>
      </div>
    </NAlert>
    <label v-if="layoutId === 'timeline' && replayBounds && replayRange" class="replay">
      <span>{{ t('graph.replay') }}</span>
      <NSlider
        v-model:value="replayRange"
        range
        :min="replayBounds[0]"
        :max="replayBounds[1]"
        :step="24 * 3600 * 1000"
        :format-tooltip="(value: number) => new Date(value).toISOString().slice(0, 10)"
        :aria-label="t('graph.replay')"
      />
    </label>
    <NAlert v-if="error" type="warning">{{ error }}</NAlert>
    <NAlert v-if="exportError" type="warning">{{ exportError }}</NAlert>
    <NAlert v-if="templateError" type="warning">{{ templateError }}</NAlert>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <template v-if="data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{
          t('graph.visibleCounts', {
            nodes: data.nodes.length,
            edges: data.edges.length,
            total: data.entity_total,
          })
        }}
      </p>
      <NAlert v-if="data.truncated" type="warning">{{ t('graph.truncated') }}</NAlert>
      <NAlert v-if="data.quarantine_count" type="warning">{{
        t('graph.graphQuarantine', { count: data.quarantine_count, run: data.run_id })
      }}</NAlert>
      <NEmpty v-if="!data.nodes.length" :description="t('graph.noVisibleNodes')" />
      <template v-else>
        <GraphCanvas
          :graph="replayedGraph ?? data"
          :neighborhood="!!center"
          :layout-id="layoutId"
          :flagged-iris="qualityOverlay ? flaggedIris : undefined"
          :highlight-iris="highlightIris"
          @select="explore"
        />
        <NTabs type="line" animated>
          <NTabPane name="direct" :tab="t('graph.directRelation')">
            <GraphFactTable
              :items="data.edges.filter((edge) => edge.kind === 'DIRECT')"
              :graph-revision-id="data.graph_revision_id"
            />
          </NTabPane>
          <NTabPane name="derived" :tab="t('graph.derived')">
            <p>{{ t('graph.derivedHint') }}</p>
            <GraphFactTable
              :items="data.edges.filter((edge) => edge.kind === 'DERIVED')"
              :graph-revision-id="data.graph_revision_id"
              derived
            />
          </NTabPane>
        </NTabs>
      </template>
    </template>
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
          <NButton type="primary" :disabled="!pathFrom || !pathTo" @click="findPath">{{
            t('graph.pathFind')
          }}</NButton>
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
          <NButton type="primary" :disabled="!diffBase || !diffTarget" @click="runDiff">{{
            t('graph.diffRun')
          }}</NButton>
          <NAlert v-if="diffError" type="warning">{{ diffError }}</NAlert>
          <template v-if="diffResult">
            <p>
              {{
                t('graph.diffSummary', {
                  added: diffResult.triple_added_count,
                  removed: diffResult.triple_removed_count,
                  entityAdded: diffResult.entity_added_count,
                  entityRemoved: diffResult.entity_removed_count,
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
            </ul>
          </template>
        </div>
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
  display: grid;
  gap: 16px;
  min-width: 0;
}
h2,
p {
  margin: 0;
}
.controls {
  display: grid;
  /* 标签在控件左侧，各列要预留标签宽度 */
  grid-template-columns: minmax(220px, 2fr) minmax(150px, 1fr) minmax(190px, 1fr) minmax(
      180px,
      1fr
    );
  gap: 16px;
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
