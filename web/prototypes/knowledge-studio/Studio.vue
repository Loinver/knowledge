<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Asset } from './data'
import { denseAssets, fields, graphEdges, graphNodes, referenceAssets, sampleRuns } from './data'
import Icon from './StudioIcon.vue'

const { t } = useI18n()
const previewRecord = { employeeId: 'E-0012', fullName: '员工 A', email: 'example@example.org' }
const sourceTableName = 'hr_database / employees'
const params = new URLSearchParams(location.search)
const direction = ref(params.get('direction') === 'b' ? 'b' : 'a')
const page = ref(params.get('page') || 'dashboard')
const dataset = ref(
  params.get('data') === 'reference' && ['dashboard', 'assets', 'designer'].includes(page.value)
    ? 'reference'
    : 'dense',
)
const displayState = ref(params.get('state') || 'normal')
const nav = [
  'dashboard',
  'assets',
  'designer',
  'mapping',
  'graph',
  'governance',
  'knowledge',
  'system',
]
const query = ref('')
const filter = ref('all')
const domain = ref('allDomains')
const assetTab = ref('overview')
const selectedId = ref<number | null>(null)
const checked = ref<number[]>([])
const localAssets = ref<Asset[]>([])
const allAssets = computed(() => [
  ...(dataset.value === 'reference' ? referenceAssets : denseAssets),
  ...localAssets.value,
])
const filteredAssets = computed(() =>
  allAssets.value.filter(
    (a) =>
      (filter.value === 'all' ||
        (filter.value === 'published'
          ? a.status === 'PUBLISHED'
          : filter.value === 'draft'
            ? a.status === 'DRAFT'
            : a.violation)) &&
      (domain.value === 'allDomains' || a.domain === domain.value) &&
      [a.label, a.name, a.iri].some((s) => s.toLowerCase().includes(query.value.toLowerCase())),
  ),
)
const selected = computed(() => allAssets.value.find((a) => a.id === selectedId.value))
const selectedFields = computed(() => {
  if (dataset.value === 'reference')
    return [{ name: 'name', label: '名称', type: 'string', required: true }]
  const names: Record<string, Array<[string, string, string]>> = {
    Department: [
      ['departmentCode', '部门编码', 'string'],
      ['departmentName', '部门名称', 'string'],
      ['level', '组织层级', 'integer'],
      ['validFrom', '生效日期', 'date'],
    ],
    Project: [
      ['projectCode', '项目编号', 'string'],
      ['projectName', '项目名称', 'string'],
      ['startDate', '开始日期', 'date'],
      ['budget', '预算金额', 'decimal'],
    ],
    Position: [
      ['positionCode', '岗位编码', 'string'],
      ['positionName', '岗位名称', 'string'],
      ['grade', '岗位职级', 'enum'],
    ],
    Organization: [
      ['organizationCode', '机构编码', 'string'],
      ['fullName', '机构全称', 'string'],
      ['registrationDate', '登记日期', 'date'],
    ],
    ProjectParticipation: [
      ['participationId', '参与记录编号', 'string'],
      ['role', '参与角色', 'enum'],
      ['startDate', '开始日期', 'date'],
      ['effortDays', '投入人日', 'decimal'],
    ],
    SupplierQualificationReview: [
      ['reviewId', '复核编号', 'string'],
      ['reviewDate', '复核日期', 'date'],
      ['conclusion', '复核结论', 'enum'],
      ['expiresAt', '有效期至', 'date'],
    ],
    Skill: [
      ['skillCode', '技能编码', 'string'],
      ['skillName', '技能名称', 'string'],
      ['category', '技能类别', 'enum'],
    ],
  }
  if (selected.value?.name === 'Employee') return fields
  return (
    names[selected.value?.name || ''] || [
      ['code', '业务编码', 'string'],
      ['name', '名称', 'string'],
    ]
  ).map(([name, label, type]) => ({ name, label, type, required: true }))
})
const stats = computed(() =>
  dataset.value === 'reference'
    ? {
        types: 2 + localAssets.value.length,
        relations: 1,
        domains: 1,
        ontologies: 1,
        sources: 1,
        mappings: 1,
        runs: 1,
        results: 1,
        drafts: 1 + localAssets.value.length,
        quarantine: 0,
      }
    : {
        types: 14 + localAssets.value.length,
        relations: 18,
        domains: 4,
        ontologies: 3,
        sources: 4,
        mappings: 6,
        runs: 12,
        results: 8,
        drafts: 4 + localAssets.value.length,
        quarantine: 7,
      },
)
const stageItems = computed(() => [
  { key: 'model', icon: 'designer', count: stats.value.ontologies, page: 'designer' },
  { key: 'source', icon: 'mapping', count: stats.value.sources, page: 'mapping' },
  { key: 'map', icon: 'link', count: stats.value.mappings, page: 'mapping' },
  { key: 'run', icon: 'clock', count: stats.value.runs, page: 'runs' },
  { key: 'explore', icon: 'graph', count: stats.value.results, page: 'graph' },
  { key: 'govern', icon: 'governance', count: null, page: 'governance' },
])
const counters = computed(() => [
  { key: 'entityTypes', count: stats.value.types },
  { key: 'relationTypes', count: stats.value.relations },
  { key: 'domains', count: stats.value.domains },
  { key: 'ontology', count: stats.value.ontologies },
])
const filterCount = (key: string) =>
  allAssets.value.filter(
    (a) =>
      key === 'all' ||
      (key === 'published'
        ? a.status === 'PUBLISHED'
        : key === 'draft'
          ? a.status === 'DRAFT'
          : a.violation),
  ).length
const navigate = (target: string) => {
  page.value = target
  if (!['dashboard', 'assets', 'designer'].includes(target)) dataset.value = 'dense'
  selectedId.value = null
  query.value = ''
  filter.value = 'all'
  domain.value = 'allDomains'
  checked.value = []
  focusMode.value = false
  displayState.value = 'normal'
  if (target === 'designer' || target === 'graph')
    selectedId.value = dataset.value === 'dense' ? 1 : null
}
const select = (a: Asset) => {
  selectedId.value = a.id
  assetTab.value = 'overview'
}
const reset = () => {
  query.value = ''
  filter.value = 'all'
  domain.value = 'allDomains'
  displayState.value = 'normal'
}
watch([direction, page, dataset, displayState], () =>
  history.replaceState(
    null,
    '',
    `?direction=${direction.value}&page=${page.value}&data=${dataset.value}&state=${displayState.value}`,
  ),
)
watch(dataset, () => {
  selectedId.value = null
  checked.value = []
  localAssets.value = []
  reset()
})
watch(filteredAssets, (items) => {
  if (
    page.value === 'assets' &&
    selectedId.value !== null &&
    !items.some((a) => a.id === selectedId.value)
  )
    selectedId.value = null
})

const focusMode = ref(false),
  resourcesVisible = ref(true),
  graphQuery = ref(''),
  zoom = ref(1),
  pan = ref({ x: 0, y: 0 }),
  layoutDirty = ref(false)
const nodes = computed(() =>
  dataset.value === 'reference'
    ? [{ ...referenceAssets[1], x: 390, y: 240 }]
    : graphNodes.map((n) => ({ ...denseAssets.find((a) => a.id === n.id)!, ...n })),
)
const edges = computed(() =>
  dataset.value === 'reference' ? [{ from: 3, to: 3, label: 'UI 验收关系' }] : graphEdges,
)
const findNode = (id: number) => nodes.value.find((n) => n.id === id)!
const edgePath = (from: number, to: number) => {
  const a = findNode(from),
    b = findNode(to)
  if (from === to)
    return `M ${a.x + 50} ${a.y} C ${a.x - 10} ${a.y - 130}, ${a.x + 230} ${a.y - 130}, ${a.x + 160} ${a.y - 2}`
  const dx = b.x - a.x,
    dy = b.y - a.y,
    horizontal = Math.abs(dx) > Math.abs(dy)
  const x1 = a.x + 105 + (horizontal ? Math.sign(dx) * 106 : 0),
    y1 = a.y + 57 + (horizontal ? 0 : Math.sign(dy) * 58)
  const x2 = b.x + 105 - (horizontal ? Math.sign(dx) * 108 : 0),
    y2 = b.y + 57 - (horizontal ? 0 : Math.sign(dy) * 60)
  return horizontal
    ? `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`
    : `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`
}
const edgeLabel = (from: number, to: number) => {
  const a = findNode(from),
    b = findNode(to)
  return from === to
    ? `translate(${a.x + 105},${a.y - 85})`
    : `translate(${(a.x + b.x) / 2 + 105},${(a.y + b.y) / 2 + 40})`
}
const drag = ref<{ x: number; y: number; px: number; py: number } | null>(null)
const startPan = (e: PointerEvent) => {
  if ((e.target as Element).closest('.graph-node')) return
  drag.value = { x: e.clientX, y: e.clientY, px: pan.value.x, py: pan.value.y }
  ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
}
const movePan = (e: PointerEvent) => {
  if (drag.value)
    pan.value = {
      x: drag.value.px + (e.clientX - drag.value.x),
      y: drag.value.py + (e.clientY - drag.value.y),
    }
}
const wheel = (e: WheelEvent) => {
  if (e.ctrlKey || e.metaKey)
    zoom.value = Math.max(0.5, Math.min(1.8, zoom.value - e.deltaY * 0.002))
  else pan.value = { x: pan.value.x - e.deltaX, y: pan.value.y - e.deltaY }
}
const fit = () => {
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
}
const graphStyle = computed(() => ({
  transform: `translate(${pan.value.x}px,${pan.value.y}px) scale(${zoom.value})`,
  transformOrigin: '50% 50%',
}))

const modal = ref(''),
  modalTitle = ref(''),
  dialog = ref<HTMLDialogElement | null>(null),
  dialogInput = ref<HTMLInputElement | null>(null),
  command = ref('')
const editLabel = ref(''),
  editName = ref(''),
  editDefinition = ref(''),
  formError = ref(false)
let returnFocus: HTMLElement | null = null
const openModal = async (kind: string, title = kind) => {
  returnFocus = document.activeElement as HTMLElement
  modal.value = kind
  modalTitle.value = title
  await nextTick()
  dialog.value?.showModal()
  dialogInput.value?.focus()
}
const closeModal = () => {
  dialog.value?.close()
  modal.value = ''
  nextTick(() => returnFocus?.focus())
}
const startEdit = (isNew = false) => {
  formError.value = false
  editLabel.value = isNew ? '' : selected.value?.label || ''
  editName.value = isNew ? '' : selected.value?.name || ''
  editDefinition.value = isNew ? '' : selected.value?.definition || ''
  openModal(isNew ? 'new' : 'edit', isNew ? 'newTitle' : 'editing')
}
const save = () => {
  if (!editLabel.value.trim()) {
    formError.value = true
    return
  }
  const base = selected.value
  const value: Asset = {
    id: modal.value === 'new' ? 100 + localAssets.value.length : base!.id,
    name: editName.value || 'NewEntity',
    label: editLabel.value,
    definition: editDefinition.value,
    domain: 'org',
    status: 'DRAFT',
    props: 0,
    relations: 0,
    revision: 0,
    updated: '2026-11-26',
    violation: false,
    iri: `https://example.org/prototype/${editName.value || 'NewEntity'}`,
  }
  if (modal.value === 'new') localAssets.value.push(value)
  else {
    const old = allAssets.value.find((a) => a.id === value.id)
    if (old) {
      old.label = value.label
      old.definition = value.definition
    }
  }
  closeModal()
  notify('localSaved')
}
const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
const notify = (key: string) => {
  toast.value = t(key)
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 3200)
}
const copyIri = async () => {
  if (selected.value) {
    try {
      await navigator.clipboard.writeText(selected.value.iri)
      notify('copied')
    } catch {
      openModal('copy', 'identity')
    }
  }
}
const showDrafts = () => {
  navigate('assets')
  filter.value = 'draft'
}
const autoLayout = () => {
  fit()
}
const saveLayout = () => {
  openModal('layoutInfo', 'saveLayout')
}
const showStructure = (title: string) => {
  auxTab.value = title
  openModal('structure', 'reader')
}
const commandNavigate = (target: string) => {
  closeModal()
  navigate(target)
}
const commands = computed(() =>
  [...nav, 'runs'].filter((k) => t(k === 'runs' ? 'operations' : k).includes(command.value)),
)
const keyboard = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    openModal('command', 'commandTitle')
  }
  if (e.key === 'Escape') {
    if (modal.value) closeModal()
    else selectedId.value = null
  }
}
onMounted(() => document.addEventListener('keydown', keyboard))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', keyboard)
  clearTimeout(toastTimer)
})
const mappingStep = ref(2),
  runFilter = ref('all'),
  auxTab = ref('')
const visibleRuns = computed(() =>
  sampleRuns.filter((r) => runFilter.value === 'all' || r.status === runFilter.value),
)
const mapRows = ref([
  { source: 'employee_id', target: '员工编号 · employeeId', transform: '原值', policy: '隔离记录' },
  { source: 'full_name', target: '姓名 · fullName', transform: '去除首尾空格', policy: '隔离记录' },
  { source: 'email', target: '工作邮箱 · email', transform: '小写', policy: '保留空值' },
  { source: 'join_date', target: '入职日期 · joinDate', transform: '日期解析', policy: '隔离记录' },
])
const auxItems = computed(() =>
  page.value === 'knowledge'
    ? [
        {
          title: '企业制度与流程',
          sub: 'TXT / MD / CSV',
          count: '24',
          status: '18 可检索 · 4 处理中 · 2 失败',
        },
        { title: '组织与岗位知识', sub: 'TXT / MD / CSV', count: '16', status: '16 可检索' },
        { title: '采购业务术语', sub: 'TXT / MD / CSV', count: '8', status: '8 可检索' },
      ]
    : page.value === 'governance'
      ? [
          { title: t('clauses'), sub: '业务规则的标准依据', count: '32', status: '12 条关联规则' },
          { title: t('rules'), sub: '约束定义与业务含义', count: '18', status: '规则状态独立呈现' },
          {
            title: t('reports'),
            sub: '通过 / 违反 / 不适用 / 未执行',
            count: '—',
            status: '本原型未执行校验',
          },
          {
            title: t('exchange'),
            sub: '导入、导出与冻结版本恢复',
            count: '—',
            status: '需校验兼容性',
          },
        ]
      : [
          { title: t('users'), sub: '账号与角色分配', count: '12', status: '管理员专用' },
          {
            title: t('roles'),
            sub: '沿用 ADMIN / EDITOR / VIEWER',
            count: '3',
            status: '系统预设角色',
          },
          { title: t('audit'), sub: '操作与对象变更追溯', count: '—', status: '管理员专用' },
          { title: t('ai'), sub: '模型能力与可用状态', count: '2', status: '不展示密钥' },
        ],
)
</script>

<template>
  <div class="proposal-app" :class="['direction-' + direction, { 'focus-mode': focusMode }]">
    <div class="proposal-bar">
      <span class="proposal-label"><span class="proposal-dot"></span>{{ t('proposal') }}</span>
      <div class="direction-switch" role="group" :aria-label="t('proposal')">
        <button
          :class="{ active: direction === 'a' }"
          :aria-pressed="direction === 'a'"
          @click="direction = 'a'"
        >
          {{ t('a') }}<span>{{ t('recommended') }}</span>
        </button>
        <button
          :class="{ active: direction === 'b' }"
          :aria-pressed="direction === 'b'"
          @click="direction = 'b'"
        >
          {{ t('b') }}
        </button>
      </div>
      <span class="proposal-disclaimer">{{ t('simulation') }}</span>
      <label class="demo-control"
        ><span class="sr-only">{{ t('dataset') }}</span
        ><select v-model="dataset">
          <option value="dense">{{ t('dense') }}</option>
          <option value="reference" :disabled="!['dashboard', 'assets', 'designer'].includes(page)">
            {{ t('reference') }}
          </option>
        </select></label
      >
      <label class="demo-control"
        ><span class="sr-only">{{ t('state') }}</span
        ><select v-model="displayState">
          <option v-for="s in ['normal', 'loading', 'empty', 'error']" :key="s" :value="s">
            {{ t(s) }}
          </option>
        </select></label
      >
      <a href="./review.html" class="review-link"
        >{{ t('compare') }}<Icon name="arrow" :size="14"
      /></a>
    </div>

    <div class="app-frame">
      <aside class="global-rail" :aria-label="t('workspace')">
        <button class="brand-mark" :aria-label="t('brand')" @click="navigate('dashboard')">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M6 7h8v8H6z M18 17h8v8h-8z M18 7h8v4h-8z M6 21h8v4H6z" fill="currentColor" />
            <path d="m14 11 6 6M10 15v6" stroke="currentColor" stroke-width="2" />
          </svg>
        </button>
        <nav>
          <button
            v-for="item in nav.filter((n) => n !== 'system')"
            :key="item"
            :class="{ active: page === item || (page === 'runs' && item === 'mapping') }"
            :aria-current="page === item ? 'page' : undefined"
            @click="navigate(item)"
          >
            <Icon :name="item" :size="21" /><span>{{ t(item) }}</span>
          </button>
        </nav>
        <div class="rail-bottom">
          <button :class="{ active: page === 'system' }" @click="navigate('system')">
            <Icon name="system" /><span>{{ t('system') }}</span>
          </button>
          <div class="avatar" :title="t('prototype')">{{ t('brand').slice(0, 1) }}</div>
        </div>
      </aside>

      <div class="workspace-main">
        <header class="workspace-header">
          <div class="workspace-identity">
            <span class="brand-word">{{ t('brand') }}</span
            ><span class="slash">/</span><span>{{ t(page === 'runs' ? 'operations' : page) }}</span
            ><span class="context-tag">{{ t('workspace') }}</span>
          </div>
          <div class="header-right">
            <button class="command-trigger" @click="openModal('command', 'commandTitle')">
              <Icon name="search" :size="15" /><span>{{ t('pageSearch') }}</span
              ><kbd>{{ t('shortcut') }}</kbd></button
            ><span class="header-status"><span></span>{{ t('prototype') }}</span>
          </div>
        </header>
        <nav v-if="direction === 'b'" class="horizontal-nav">
          <button
            v-for="item in nav"
            :key="item"
            :class="{ active: page === item }"
            @click="navigate(item)"
          >
            {{ t(item) }}
          </button>
        </nav>

        <main
          v-if="displayState !== 'normal'"
          class="state-page"
          :aria-busy="displayState === 'loading'"
        >
          <div v-if="displayState === 'loading'" class="loading-layout">
            <div class="skeleton title-skeleton"></div>
            <div class="skeleton banner-skeleton"></div>
            <div v-for="n in 6" :key="n" class="skeleton row-skeleton"></div>
            <div role="status">
              {{ t('loadingTitle') }}
              <p>{{ t('loadingNote') }}</p>
            </div>
          </div>
          <div v-else class="empty-state" :role="displayState === 'error' ? 'alert' : 'status'">
            <div class="state-icon">
              <Icon :name="displayState === 'error' ? 'warning' : 'search'" :size="32" />
            </div>
            <h2>{{ t(displayState === 'error' ? 'errorTitle' : 'emptyTitle') }}</h2>
            <p>{{ t(displayState === 'error' ? 'errorNote' : 'emptyNote') }}</p>
            <button class="primary-button" @click="reset">
              {{ t(displayState === 'error' ? 'retry' : 'reset') }}<Icon name="arrow" />
            </button>
          </div>
        </main>

        <main v-else-if="page === 'dashboard'" class="dashboard-page page-scroll">
          <div class="page-heading">
            <div>
              <div class="eyebrow">{{ t('workspace') }}</div>
              <h1>{{ t(direction === 'b' ? 'editorial' : 'workspaceTitle') }}</h1>
              <p>{{ t(direction === 'b' ? 'editorialSub' : 'workspaceSub') }}</p>
            </div>
            <span class="date-label">{{
              new Intl.DateTimeFormat('zh-CN', {
                month: 'long',
                day: 'numeric',
                weekday: 'long',
              }).format(new Date('2026-11-26T12:00:00+08:00'))
            }}</span>
          </div>
          <div class="home-top">
            <section class="current-work">
              <div class="work-copy">
                <div class="eyebrow"><span class="live-dot"></span>{{ t('scope') }}</div>
                <h2>{{ dataset === 'reference' ? t('referenceOntology') : t('project') }}</h2>
                <p class="work-meta">
                  {{ t('result') }} <strong>{{ t('resultId') }}</strong
                  ><span>·</span>{{ t('published') }}
                </p>
                <p class="work-scope-label">{{ t('globalStats') }}</p>
                <div class="work-facts">
                  <div>
                    <strong>{{ stats.results }}</strong
                    ><span>{{ t('resultVersion') }}</span>
                  </div>
                  <div>
                    <strong>{{ stats.types }}</strong
                    ><span>{{ t('entityTypes') }}</span>
                  </div>
                  <div>
                    <strong>{{ stats.relations }}</strong
                    ><span>{{ t('relationTypes') }}</span>
                  </div>
                </div>
                <div class="button-row">
                  <button class="primary-button" @click="navigate('graph')">
                    {{ t('openGraph') }}<Icon name="arrow" /></button
                  ><button class="text-button" @click="navigate('designer')">
                    {{ t('modelEntry') }}
                  </button>
                </div>
              </div>
              <div class="mini-graph" aria-hidden="true">
                <svg viewBox="0 0 360 280">
                  <defs>
                    <pattern id="mini-dot" width="18" height="18" patternUnits="userSpaceOnUse">
                      <circle cx="1" cy="1" r=".7" fill="#b9ccc8" />
                    </pattern>
                  </defs>
                  <rect width="360" height="280" fill="url(#mini-dot)" />
                  <g stroke="#9db9b2" fill="none">
                    <path
                      d="M180 138 80 60M180 138 285 65M180 138 70 205M180 138 280 220M80 60 70 205M285 65 280 220"
                    />
                  </g>
                  <g
                    v-for="(n, i) in [
                      { x: 180, y: 138, r: 29 },
                      { x: 80, y: 60, r: 20 },
                      { x: 285, y: 65, r: 19 },
                      { x: 70, y: 205, r: 17 },
                      { x: 280, y: 220, r: 22 },
                    ]"
                    :key="i"
                  >
                    <circle :cx="n.x" :cy="n.y" :r="n.r + 7" fill="#e1ece8" />
                    <circle
                      :cx="n.x"
                      :cy="n.y"
                      :r="n.r"
                      :fill="i === 0 ? '#176d61' : 'white'"
                      stroke="#8daf9e"
                    />
                    <path
                      :d="`M${n.x - 6} ${n.y - 6}h12v12h-12z`"
                      fill="none"
                      :stroke="i === 0 ? 'white' : '#397569'"
                      stroke-width="1.5"
                    />
                  </g></svg
                ><span>{{ t('structure') }}</span>
              </div>
            </section>
            <section class="attention-panel">
              <div class="section-title">
                <h2>{{ t('needsAttention') }}</h2>
              </div>
              <button class="attention-item" @click="showDrafts">
                <span class="attention-icon amber"><Icon name="file" /></span>
                <div>
                  <strong>{{ t('draftTitle') }}</strong>
                  <p>{{ t('draftExplain') }}</p>
                </div>
                <b>{{ stats.drafts }}</b
                ><Icon name="arrow" :size="16" /></button
              ><button class="attention-item" @click="navigate('runs')">
                <span class="attention-icon" :class="stats.quarantine ? 'amber' : 'green'"
                  ><Icon :name="stats.quarantine ? 'warning' : 'check'"
                /></span>
                <div>
                  <strong>{{ t(stats.quarantine ? 'quarantineTitle' : 'noQuarantine') }}</strong>
                  <p>{{ t(stats.quarantine ? 'quarantineExplain' : 'notValidation') }}</p>
                </div>
                <b>{{ stats.quarantine }}</b
                ><Icon name="arrow" :size="16" />
              </button>
              <p class="quiet-note">{{ t('attentionNote') }}</p>
            </section>
          </div>
          <section class="workflow-section">
            <div class="section-title">
              <h2>{{ t('stages') }}</h2>
              <span>{{ t('stageNote') }}</span>
            </div>
            <div class="workflow-track">
              <button
                v-for="(stage, i) in stageItems"
                :key="stage.key"
                @click="navigate(stage.page)"
              >
                <span class="step-number">{{ String(i + 1).padStart(2, '0') }}</span
                ><Icon :name="stage.icon" :size="23" />
                <div>
                  <strong>{{ t(stage.key) }}</strong>
                  <p>{{ t(stage.key + 'Desc') }}</p>
                </div>
                <span class="step-count">{{ stage.count ?? '→' }}</span>
              </button>
            </div>
          </section>
          <section class="asset-overview">
            <div class="section-title">
              <h2>{{ t('assetsOverview') }}</h2>
              <button class="text-button" @click="navigate('assets')">
                {{ t('allAssets') }}<Icon name="arrow" :size="15" />
              </button>
            </div>
            <div class="asset-counters">
              <button
                v-for="item in counters"
                :key="item.key"
                @click="navigate(item.key === 'ontology' ? 'designer' : 'assets')"
              >
                <div class="counter-icon">
                  <Icon
                    :name="
                      item.key === 'relationTypes'
                        ? 'link'
                        : item.key === 'ontology'
                          ? 'designer'
                          : 'box'
                    "
                    :size="23"
                  />
                </div>
                <div>
                  <span>{{ t(item.key) }}</span
                  ><strong>{{ item.count }}</strong>
                </div>
                <Icon name="arrow" :size="17" />
              </button>
            </div>
          </section>
          <p class="dataset-note">{{ t(dataset === 'dense' ? 'denseNote' : 'referenceNote') }}</p>
        </main>

        <main v-else-if="page === 'assets'" class="assets-page">
          <aside class="asset-sidebar">
            <div class="sidebar-title">{{ t('assets') }}</div>
            <button class="section-current">
              <Icon name="box" />{{ t('entityTypes') }}<span>{{ allAssets.length }}</span></button
            ><button @click="openModal('structure', 'relationTypes')">
              <Icon name="link" />{{ t('relationTypes') }}</button
            ><button @click="openModal('structure', 'namespaces')">
              <Icon name="assets" />{{ t('namespaces') }}
            </button>
            <div class="sidebar-label">{{ t('status') }}</div>
            <button
              v-for="f in ['all', 'published', 'draft', 'violation']"
              :key="f"
              :class="{ selected: filter === f }"
              @click="filter = f"
            >
              <span class="filter-dot" :class="f"></span>{{ t(f) }}<span>{{ filterCount(f) }}</span>
            </button>
            <div class="sidebar-label">{{ t('businessDomains') }}</div>
            <button
              v-for="d in ['allDomains', 'hr', 'org', 'projectDomain', 'procurement']"
              :key="d"
              :class="{ selected: domain === d }"
              @click="domain = d"
            >
              <Icon name="assets" :size="14" />{{ t(d) }}
            </button>
            <div class="sidebar-bottom">
              <button @click="openModal('structure', 'dictionaries')">
                {{ t('dictionaries') }}<Icon name="arrow" :size="14" /></button
              ><button @click="openModal('structure', 'templates')">
                {{ t('templates') }}<Icon name="arrow" :size="14" />
              </button>
            </div>
          </aside>
          <section class="asset-main" :class="{ 'has-selection': selected }">
            <div class="page-heading compact">
              <div>
                <div v-if="direction === 'b'" class="eyebrow">{{ t('listTitle') }}</div>
                <h1>
                  {{ t('typeLibrary') }}<span>{{ allAssets.length }}</span>
                </h1>
                <p>{{ t('typeSub') }}</p>
              </div>
              <button class="primary-button" @click="startEdit(true)">
                <Icon name="plus" :size="16" />{{ t('newType') }}
              </button>
            </div>
            <div class="list-toolbar">
              <label class="search-field"
                ><Icon name="search" /><input
                  v-model="query"
                  :aria-label="t('searchTypes')"
                  :placeholder="t('searchTypes')" /><button
                  v-if="query"
                  :aria-label="t('clear')"
                  @click="query = ''"
                >
                  <Icon name="close" :size="15" /></button></label
              ><select v-model="filter" :aria-label="t('status')">
                <option v-for="f in ['all', 'published', 'draft', 'violation']" :key="f" :value="f">
                  {{ t(f) }}
                </option></select
              ><button class="icon-button" :aria-label="t('clear')" @click="reset">
                <Icon name="filter" />
              </button>
            </div>
            <div v-if="checked.length" class="selection-bar">
              <span>{{ t('selectedCount', { n: checked.length }) }}</span
              ><button @click="openModal('selected', 'selectedExport')">
                {{ t('selectedExport') }}</button
              ><button @click="checked = []">{{ t('clearSelection') }}</button>
            </div>
            <div v-if="!filteredAssets.length" class="empty-state inline">
              <Icon name="search" :size="30" />
              <h2>{{ t('emptyTitle') }}</h2>
              <p>{{ t('emptyNote') }}</p>
              <button class="secondary-button" @click="reset">{{ t('reset') }}</button>
            </div>
            <div v-else-if="direction === 'b'" class="catalog-grid">
              <button
                v-for="a in filteredAssets"
                :key="a.id"
                class="catalog-item"
                :class="{ selected: selectedId === a.id }"
                @click="select(a)"
              >
                <span class="catalog-number">{{ String(a.id).padStart(2, '0') }}</span>
                <div class="catalog-icon"><Icon name="box" :size="26" /></div>
                <h2>{{ a.label }}</h2>
                <code>{{ a.name }}</code>
                <p>{{ a.definition }}</p>
                <div class="catalog-foot">
                  <span class="badge" :class="a.status.toLowerCase()">{{
                    t(a.status === 'DRAFT' ? 'draft' : 'published')
                  }}</span
                  ><span>{{ a.props }} {{ t('props') }}<Icon name="arrow" :size="14" /></span>
                </div>
              </button>
            </div>
            <div v-else class="table-scroll">
              <table class="asset-table">
                <thead>
                  <tr>
                    <th class="checkbox-cell">
                      <span class="sr-only">{{ t('selectedCount', { n: checked.length }) }}</span>
                    </th>
                    <th>{{ t('name') }}</th>
                    <th class="count-column">{{ t('props') }}</th>
                    <th class="count-column">{{ t('relations') }}</th>
                    <th>{{ t('status') }}</th>
                    <th class="optional-column">{{ t('revision') }}</th>
                    <th class="optional-column">{{ t('updated') }}</th>
                    <th class="end-column"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="a in filteredAssets"
                    :key="a.id"
                    :class="{ selected: selectedId === a.id }"
                  >
                    <td class="checkbox-cell">
                      <input
                        v-model="checked"
                        type="checkbox"
                        :value="a.id"
                        :aria-label="t('rowSelect', { name: a.label })"
                      />
                    </td>
                    <td>
                      <button
                        class="object-cell"
                        :aria-label="t('entityPreview', { name: a.label })"
                        @click="select(a)"
                      >
                        <span class="type-symbol"><Icon name="box" :size="18" /></span
                        ><span class="object-name"
                          ><strong :title="a.label">{{ a.label }}</strong
                          ><code>{{ a.name }}</code></span
                        >
                      </button>
                    </td>
                    <td class="count-column">{{ a.props }}</td>
                    <td class="count-column">{{ a.relations }}</td>
                    <td>
                      <span class="badge" :class="a.status.toLowerCase()">{{
                        t(a.status === 'DRAFT' ? 'draft' : 'published')
                      }}</span
                      ><span v-if="a.violation" class="violation-mark" :title="t('violation')"
                        ><Icon name="warning" :size="14"
                      /></span>
                    </td>
                    <td class="optional-column mono">
                      {{ a.revision ? 'r' + a.revision : t('unavailable') }}
                    </td>
                    <td class="optional-column muted">{{ a.updated.slice(5) }}</td>
                    <td class="end-column">
                      <button
                        class="icon-button"
                        :aria-label="t('entityPreview', { name: a.label })"
                        @click="select(a)"
                      >
                        <Icon name="arrow" :size="16" />
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <footer class="list-footer">
              <span>{{
                t('countShown', { n: filteredAssets.length, total: allAssets.length })
              }}</span
              ><span>{{ t(dataset === 'dense' ? 'dense' : 'reference') }}</span>
            </footer>
          </section>
          <aside v-if="selected" class="inspector asset-inspector">
            <div class="inspector-heading">
              <span>{{ t('objectContext') }}</span
              ><button
                class="icon-button"
                :aria-label="t('closeDetails')"
                @click="selectedId = null"
              >
                <Icon name="close" />
              </button>
            </div>
            <div class="object-hero">
              <div class="hero-icon"><Icon name="box" :size="28" /></div>
              <span class="badge" :class="selected.status.toLowerCase()">{{
                t(selected.status === 'DRAFT' ? 'draft' : 'published')
              }}</span>
              <h2>{{ selected.label }}</h2>
              <code>{{ selected.name }}</code>
              <p>{{ selected.definition }}</p>
            </div>
            <div class="inspector-tabs" role="tablist">
              <button
                v-for="tab in ['overview', 'properties', 'validation']"
                :key="tab"
                role="tab"
                :aria-selected="assetTab === tab"
                :class="{ active: assetTab === tab }"
                @click="assetTab = tab"
              >
                {{ t(tab) }}
              </button>
            </div>
            <div class="inspector-body">
              <template v-if="assetTab === 'overview'"
                ><dl class="property-list">
                  <div>
                    <dt>{{ t('businessDomains') }}</dt>
                    <dd>{{ t(selected.domain) }}</dd>
                  </div>
                  <div>
                    <dt>{{ t('revision') }}</dt>
                    <dd>{{ selected.revision ? 'r' + selected.revision : t('unavailable') }}</dd>
                  </div>
                  <div>
                    <dt>{{ t('props') }}</dt>
                    <dd>{{ selected.props }}</dd>
                  </div>
                  <div>
                    <dt>{{ t('relations') }}</dt>
                    <dd>{{ selected.relations }}</dd>
                  </div>
                </dl>
                <div class="field-label">
                  {{ t('identity')
                  }}<button class="icon-button" :aria-label="t('copy')" @click="copyIri">
                    <Icon name="copy" :size="15" />
                  </button>
                </div>
                <code class="iri-block">{{ selected.iri }}</code>
                <div v-if="selected.revision" class="semantic-note">
                  <Icon name="governance" />
                  <div>
                    <strong>{{ t('frozen', { n: selected.revision }) }}</strong>
                    <p>{{ t('frozenDesc') }}</p>
                  </div>
                </div></template
              ><template v-else-if="assetTab === 'properties'"
                ><div
                  v-for="f in selectedFields.slice(
                    0,
                    Math.min(selected.props, selectedFields.length),
                  )"
                  :key="f.name"
                  class="property-row"
                >
                  <div>
                    <strong>{{ f.label }}</strong
                    ><code>{{ f.name }}</code>
                  </div>
                  <span>{{ f.type }}</span>
                </div>
                <p class="quiet-note">
                  {{ t('preview') }} · {{ Math.min(selected.props, selectedFields.length) }} /
                  {{ selected.props }}
                </p></template
              ><template v-else
                ><div class="validation-state">
                  <div v-if="selected.violation" class="history-validation">
                    <span class="badge failed">{{ t('failed') }}</span>
                    <p>{{ t('historyViolation') }}</p>
                  </div>
                  <span class="badge notrun">{{ t('notRun') }}</span>
                  <p>{{ t('validationNote') }}</p>
                </div></template
              >
            </div>
            <div class="inspector-footer">
              <button
                class="primary-button"
                @click="
                  selected.status === 'DRAFT' ? startEdit() : openModal('revision', 'startRevision')
                "
              >
                {{ t(selected.status === 'DRAFT' ? 'edit' : 'startRevision')
                }}<Icon name="arrow" :size="16" /></button
              ><button class="text-button" @click="openModal('detail', 'detail')">
                {{ t('openFull') }}
              </button>
            </div>
          </aside>
        </main>

        <main v-else-if="page === 'designer' || page === 'graph'" class="model-page">
          <div class="model-titlebar">
            <button
              class="icon-button"
              :aria-label="t('toggleResources')"
              @click="resourcesVisible = !resourcesVisible"
            >
              <Icon name="panel" />
            </button>
            <div class="model-title">
              <h1>{{ dataset === 'reference' ? t('referenceOntology') : t('project') }}</h1>
              <span>{{
                t(
                  page === 'graph'
                    ? 'exploreSub'
                    : dataset === 'reference'
                      ? 'referenceModelingSub'
                      : 'modelingSub',
                )
              }}</span>
            </div>
            <span class="badge" :class="page === 'graph' ? 'published' : 'draft'">{{
              t(page === 'graph' ? 'published' : 'workingRevision')
            }}</span>
            <div class="model-actions">
              <button class="secondary-button" @click="openModal('validate', 'verifyDemo')">
                <Icon name="governance" :size="16" />{{ t('validate') }}</button
              ><button
                v-if="page === 'designer'"
                class="primary-button"
                @click="openModal('publish', 'publishDemo')"
              >
                {{ t('publish') }}<Icon name="arrow" :size="16" /></button
              ><button
                class="icon-button"
                :aria-label="t(focusMode ? 'exitFocus' : 'focus')"
                @click="focusMode = !focusMode"
              >
                <Icon name="expand" />
              </button>
            </div>
          </div>
          <div class="model-workspace">
            <aside v-if="resourcesVisible && !focusMode" class="resource-panel">
              <div class="section-title">
                <h2>{{ t('resources') }}</h2>
                <span>{{ nodes.length }}</span>
              </div>
              <label class="search-field"
                ><Icon name="search" :size="15" /><input
                  v-model="graphQuery"
                  :placeholder="t('resourceSearch')"
                  :aria-label="t('resourceSearch')"
              /></label>
              <div class="sidebar-label">{{ t('onCanvas') }}</div>
              <button
                v-for="n in nodes.filter(
                  (n) =>
                    n.label.includes(graphQuery) ||
                    n.name.toLowerCase().includes(graphQuery.toLowerCase()),
                )"
                :key="n.id"
                class="resource-row"
                :class="{ active: selectedId === n.id }"
                @click="select(n)"
              >
                <Icon name="box" :size="16" /><span>{{ n.label }}</span
                ><small>{{ n.revision ? 'r' + n.revision : t('unavailable') }}</small>
              </button>
              <div class="sidebar-label">{{ t('relationTypes') }}</div>
              <div v-for="e in edges" :key="e.label" class="relation-resource">
                <Icon name="link" :size="14" />{{ e.label }}
              </div>
              <div class="resource-bottom">
                <button class="secondary-button" @click="openModal('add', 'addDemo')">
                  <Icon name="plus" :size="16" />{{ t('addResource') }}
                </button>
                <p>{{ t('layoutOnly') }}</p>
              </div>
            </aside>
            <section class="canvas-area" :aria-label="t('canvas')">
              <div class="canvas-toolbar">
                <span class="canvas-mode"
                  ><span class="live-dot"></span
                  >{{ t(page === 'graph' ? 'graph' : 'modeling') }}</span
                ><button v-if="page === 'designer'" @click="autoLayout">
                  <Icon name="assets" :size="15" />{{ t('layout') }}</button
                ><button
                  v-if="page === 'designer'"
                  :class="{ dirty: layoutDirty }"
                  @click="saveLayout"
                >
                  <Icon name="save" :size="15" />{{ t('saveLayout') }}
                </button>
              </div>
              <svg
                class="graph-svg"
                viewBox="0 0 1000 740"
                role="group"
                :aria-label="t('canvas')"
                @pointerdown="startPan"
                @pointermove="movePan"
                @pointerup="drag = null"
                @pointercancel="drag = null"
                @wheel.prevent="wheel"
              >
                <defs>
                  <marker
                    id="arrowhead"
                    markerWidth="9"
                    markerHeight="9"
                    refX="8"
                    refY="4"
                    orient="auto-start-reverse"
                  >
                    <path d="M0 0 8 4 0 8" fill="none" stroke="#82938d" stroke-width="1.3" />
                  </marker>
                </defs>
                <g :style="graphStyle">
                  <g v-if="dataset === 'reference'" class="domain-envelope">
                    <rect x="335" y="195" width="320" height="210" rx="18" />
                    <text x="355" y="221">{{ t('referenceDomain') }}</text>
                  </g>
                  <g v-for="edge in edges" :key="edge.label" class="graph-edge">
                    <path :d="edgePath(edge.from, edge.to)" marker-end="url(#arrowhead)" />
                    <g :transform="edgeLabel(edge.from, edge.to)">
                      <rect x="-53" y="-15" width="106" height="26" rx="4" />
                      <text text-anchor="middle" y="3">{{ edge.label }}</text>
                    </g>
                  </g>
                  <g
                    v-for="n in nodes"
                    :key="n.id"
                    class="graph-node"
                    :class="{ selected: selectedId === n.id }"
                    :transform="`translate(${n.x},${n.y})`"
                    role="button"
                    tabindex="0"
                    :aria-label="t('entityPreview', { name: n.label })"
                    :aria-pressed="selectedId === n.id"
                    @click.stop="select(n)"
                    @keydown.enter="select(n)"
                    @keydown.space.prevent="select(n)"
                  >
                    <rect class="node-shadow" x="0" y="4" width="210" height="114" rx="9" />
                    <rect class="node-body" width="210" height="114" rx="9" />
                    <path d="M0 42h210" stroke="#e8eeeb" />
                    <rect x="15" y="12" width="19" height="19" rx="4" fill="#e5f2ed" />
                    <path
                      d="m20 17 5-3 5 3v6l-5 3-5-3v-6z m0 0 5 3 5-3 m-5 3v6"
                      stroke="#227e69"
                      fill="none"
                    />
                    <text x="44" y="27" class="node-title">
                      {{ n.label.length > 11 ? n.label.slice(0, 10) + '…' : n.label }}
                    </text>
                    <text x="16" y="65" class="node-name">
                      {{ n.name.length > 23 ? n.name.slice(0, 21) + '…' : n.name }}
                    </text>
                    <text x="16" y="94" class="node-meta">
                      {{ n.props }} {{ t('props') }} · {{ n.relations }} {{ t('relations') }}
                    </text>
                    <text x="194" y="94" text-anchor="end" class="node-revision">
                      {{ n.revision ? 'r' + n.revision : t('draft') }}
                    </text>
                    <circle v-if="selectedId === n.id" cx="0" cy="57" r="4" />
                    <circle v-if="selectedId === n.id" cx="210" cy="57" r="4" />
                  </g>
                </g>
              </svg>
              <div class="canvas-controls">
                <button :aria-label="t('zoomOut')" @click="zoom = Math.max(0.5, zoom - 0.1)">
                  <Icon name="minus" :size="16" /></button
                ><span>{{ t('zoomPercent', { n: Math.round(zoom * 100) }) }}</span
                ><button :aria-label="t('zoomIn')" @click="zoom = Math.min(1.8, zoom + 0.1)">
                  <Icon name="plus" :size="16" /></button
                ><i></i
                ><button @click="fit"><Icon name="expand" :size="15" />{{ t('fit') }}</button>
              </div>
              <div class="canvas-legend">
                <span><i></i>{{ t('entityTypes') }}</span
                ><span><i class="line"></i>{{ t('relationTypes') }}</span>
              </div>
            </section>
            <aside v-if="selected && !focusMode" class="inspector graph-inspector">
              <div class="inspector-heading">
                <span>{{ t(page === 'graph' ? 'typeDescription' : 'modelInspector') }}</span
                ><button
                  class="icon-button"
                  :aria-label="t('closeDetails')"
                  @click="selectedId = null"
                >
                  <Icon name="close" />
                </button>
              </div>
              <div class="object-hero">
                <span class="badge type-badge">{{ t('typeResource') }}</span>
                <h2>{{ selected.label }}</h2>
                <code>{{ selected.name }}</code>
                <p>{{ selected.definition }}</p>
              </div>
              <div class="inspector-body">
                <div class="section-title">
                  <h3>{{ t('properties') }}</h3>
                  <span>{{ selected.props }}</span>
                </div>
                <div
                  v-for="f in selectedFields.slice(
                    0,
                    Math.min(selected.props, selectedFields.length),
                  )"
                  :key="f.name"
                  class="property-row"
                >
                  <div>
                    <strong
                      >{{ f.label }}<sup v-if="f.required">{{ t('asterisk') }}</sup></strong
                    ><code>{{ f.name }}</code>
                  </div>
                  <span>{{ f.type }}</span>
                </div>
                <p class="quiet-note">
                  {{ t('preview') }} · {{ Math.min(selected.props, selectedFields.length) }} /
                  {{ selected.props }}
                </p>
                <div class="semantic-note">
                  <Icon name="governance" :size="18" />
                  <div>
                    <strong
                      >{{ t('pinned') }}
                      {{ selected.revision ? 'r' + selected.revision : t('unavailable') }}</strong
                    >
                    <p>{{ t(page === 'graph' ? 'typeOverviewNote' : 'modelVersionNote') }}</p>
                  </div>
                </div>
              </div>
              <div class="inspector-footer">
                <button class="secondary-button" @click="openModal('detail', 'detail')">
                  {{ t('openFull') }}<Icon name="arrow" :size="16" />
                </button>
              </div>
            </aside>
          </div>
          <footer class="model-footer">
            <span
              >{{ nodes.length }} {{ t('entityTypes') }} · {{ edges.length }}
              {{ t('relationTypes') }}</span
            ><span>{{ t('dragHint') }}</span
            ><span>{{ t(layoutDirty ? 'notSaved' : 'localOnly') }}</span>
          </footer>
        </main>

        <main v-else-if="page === 'mapping'" class="mapping-page page-scroll">
          <div class="page-heading">
            <div>
              <div class="eyebrow">{{ t('mapping') }}</div>
              <h1>{{ t('mapTitle') }}</h1>
              <p>{{ t('mapSub') }}</p>
            </div>
            <button class="secondary-button" @click="navigate('runs')">
              <Icon name="clock" />{{ t('operations') }}
            </button>
          </div>
          <div class="mapping-steps">
            <button
              v-for="(s, i) in ['mapTarget', 'connection', 'mapDesign', 'preview', 'release']"
              :key="s"
              :class="{ active: mappingStep === i, done: mappingStep > i }"
              @click="mappingStep = i"
            >
              <span>{{ String(i + 1).padStart(2, '0') }}</span
              >{{ t(s) }}<Icon v-if="i < 4" name="arrow" :size="15" />
            </button>
          </div>
          <div class="mapping-context">
            <div>
              <span>{{ t('sourceTable') }}</span
              ><strong>{{ sourceTableName }}</strong>
            </div>
            <Icon name="arrow" :size="24" />
            <div>
              <span>{{ t('targetType') }}</span
              ><strong>{{ denseAssets[0].label }} · {{ denseAssets[0].name }}</strong>
            </div>
            <span class="badge draft">{{ t('draft') }}</span>
          </div>
          <section v-if="mappingStep === 2" class="mapping-content">
            <div class="section-title">
              <h2>
                {{ t(['mapTarget', 'connection', 'mapDesign', 'preview', 'release'][mappingStep]) }}
              </h2>
              <span>{{ t('localOnly') }}</span>
            </div>
            <p>{{ t('mapTip') }}</p>
            <table class="mapping-table">
              <thead>
                <tr>
                  <th>{{ t('sourceField') }}</th>
                  <th></th>
                  <th>{{ t('targetField') }}</th>
                  <th>{{ t('transform') }}</th>
                  <th>{{ t('nullPolicy') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in mapRows" :key="r.source">
                  <td>
                    <code>{{ r.source }}</code>
                  </td>
                  <td><Icon name="arrow" :size="16" /></td>
                  <td>{{ r.target }}</td>
                  <td>
                    <select v-model="r.transform" :aria-label="t('transform') + ' ' + r.source">
                      <option v-for="v in ['原值', '去除首尾空格', '小写', '日期解析']" :key="v">
                        {{ v }}
                      </option>
                    </select>
                  </td>
                  <td>
                    <span>{{ r.policy }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="semantic-note">
              <Icon name="governance" /><span>{{ t('structureNote') }}</span>
            </div>
          </section>
          <section v-else class="mapping-content mapping-outline">
            <Icon name="mapping" :size="30" />
            <h2>
              {{ t(['mapTarget', 'connection', 'mapDesign', 'preview', 'release'][mappingStep]) }}
            </h2>
            <p>{{ t('structureNote') }}</p>
            <button
              v-if="mappingStep === 3"
              class="secondary-button"
              @click="openModal('mapPreview', 'mappingPreview')"
            >
              {{ t('previewMap') }}
            </button>
          </section>
          <div class="mapping-footer">
            <button class="secondary-button" :disabled="mappingStep === 0" @click="mappingStep--">
              {{ t('previous') }}
            </button>
            <div>
              <button class="secondary-button" @click="openModal('mapPreview', 'mappingPreview')">
                {{ t('previewMap') }}</button
              ><button
                class="primary-button"
                @click="mappingStep < 4 ? mappingStep++ : openModal('publish', 'publishDemo')"
              >
                {{ t(mappingStep < 4 ? 'nextStep' : 'release') }}<Icon name="arrow" />
              </button>
            </div>
          </div>
        </main>

        <main v-else-if="page === 'runs'" class="page-scroll auxiliary-page">
          <div class="page-heading">
            <div>
              <div class="eyebrow">{{ t('mapping') }}</div>
              <h1>{{ t('operations') }}</h1>
              <p>{{ t('runSub') }}</p>
            </div>
            <button class="secondary-button" @click="navigate('mapping')">
              {{ t('mapTitle') }}
            </button>
          </div>
          <div class="filter-tabs">
            <button
              v-for="s in ['all', 'success', 'partial', 'failure']"
              :key="s"
              :class="{ active: runFilter === s }"
              @click="runFilter = s"
            >
              {{ t(s) }}
            </button>
          </div>
          <table class="run-table">
            <thead>
              <tr>
                <th>{{ t('runName') }}</th>
                <th>{{ t('status') }}</th>
                <th>{{ t('started') }}</th>
                <th>{{ t('output') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in visibleRuns" :key="r.id">
                <td>
                  <strong>{{ r.label }}</strong
                  ><code>{{ r.id }}</code>
                </td>
                <td>
                  <span class="badge" :class="r.status">{{ t(r.status) }}</span>
                </td>
                <td>{{ r.time }}</td>
                <td class="mono">{{ r.rows }}</td>
                <td>
                  <button class="text-button" @click="openModal('runDetail', 'viewRun')">
                    {{ t('inspect') }}<Icon name="arrow" :size="15" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="dataset-note">{{ t('denseNote') }}</p>
        </main>

        <main v-else class="page-scroll auxiliary-page">
          <div class="page-heading">
            <div>
              <div class="eyebrow">{{ t('structure') }}</div>
              <h1>{{ t(page + 'Title') }}</h1>
              <p>{{ t(page + 'Sub') }}</p>
            </div>
            <span class="badge type-badge">{{ t('localOnly') }}</span>
          </div>
          <div class="extension-grid">
            <button v-for="item in auxItems" :key="item.title" @click="showStructure(item.title)">
              <Icon :name="page" :size="28" /><span class="extension-count">{{ item.count }}</span>
              <h2>{{ item.title }}</h2>
              <p>{{ item.sub }}</p>
              <div>
                <span>{{ item.status }}</span
                ><Icon name="arrow" :size="17" />
              </div>
            </button>
          </div>
          <div class="extension-info">
            <Icon name="panel" :size="25" />
            <div>
              <h3>{{ t('structure') }}</h3>
              <p>{{ t('structureNote') }}</p>
            </div>
          </div>
        </main>
      </div>
    </div>

    <dialog
      ref="dialog"
      class="studio-dialog"
      :class="{ 'command-dialog': modal === 'command', 'detail-dialog': modal === 'detail' }"
      aria-labelledby="dialog-title"
      @cancel.prevent="closeModal"
      @click="$event.target === dialog && closeModal()"
    >
      <div class="dialog-heading">
        <h2 id="dialog-title">{{ t(modalTitle || 'detail') }}</h2>
        <button class="icon-button" :aria-label="t('close')" @click="closeModal">
          <Icon name="close" />
        </button>
      </div>
      <div class="dialog-body">
        <template v-if="modal === 'command'"
          ><label class="search-field"
            ><Icon name="search" /><input
              ref="dialogInput"
              v-model="command"
              :placeholder="t('commandPlaceholder')"
              :aria-label="t('commandPlaceholder')"
          /></label>
          <p class="quiet-note">{{ t('searchHint') }}</p>
          <button v-for="n in commands" :key="n" class="command-option" @click="commandNavigate(n)">
            <Icon :name="n" />{{ t(n === 'runs' ? 'operations' : n)
            }}<Icon name="arrow" :size="15" />
          </button>
          <p v-if="!commands.length">{{ t('noCommand') }}</p></template
        >
        <form v-else-if="modal === 'new' || modal === 'edit'" @submit.prevent="save">
          <label class="form-field"
            ><span>{{ t('label') }} {{ t('asterisk') }}</span
            ><input ref="dialogInput" v-model="editLabel" :aria-invalid="formError" /><small
              v-if="formError"
              class="form-error"
              role="alert"
              >{{ t('requiredName') }}</small
            ></label
          ><label class="form-field"
            ><span>{{ t('machineName') }}</span
            ><input v-model="editName" :disabled="modal === 'edit'" placeholder="Employee" /></label
          ><label class="form-field"
            ><span>{{ t('definition') }}</span
            ><textarea v-model="editDefinition" rows="3"></textarea>
          </label>
          <p class="quiet-note">{{ t('actionMock') }}</p>
          <div class="dialog-actions">
            <button type="button" class="secondary-button" @click="closeModal">
              {{ t('cancel') }}</button
            ><button class="primary-button" type="submit">{{ t('saveDraft') }}</button>
          </div>
        </form>
        <template v-else-if="modal === 'detail' && selected"
          ><div class="detail-heading">
            <div class="hero-icon"><Icon name="box" :size="27" /></div>
            <div>
              <h2>{{ selected.label }}</h2>
              <code>{{ selected.name }}</code>
            </div>
            <span class="badge" :class="selected.status.toLowerCase()">{{
              t(selected.status === 'DRAFT' ? 'draft' : 'published')
            }}</span>
          </div>
          <p>{{ selected.definition }}</p>
          <code class="iri-block">{{ selected.iri }}</code>
          <table class="detail-table">
            <thead>
              <tr>
                <th>{{ t('field') }}</th>
                <th>{{ t('datatype') }}</th>
                <th>{{ t('required') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="f in selectedFields.slice(
                  0,
                  Math.min(selected.props, selectedFields.length),
                )"
                :key="f.name"
              >
                <td>
                  {{ f.label }}<code>{{ f.name }}</code>
                </td>
                <td>{{ f.type }}</td>
                <td>{{ t(f.required ? 'yes' : 'no') }}</td>
              </tr>
            </tbody>
          </table>
          <p class="quiet-note">
            {{ t('preview') }} · {{ Math.min(selected.props, selectedFields.length) }} /
            {{ selected.props }} ·
            {{ t('validationNote') }}
          </p></template
        >
        <template v-else-if="modal === 'validate'"
          ><p>{{ t('verifyNote') }}</p>
          <div class="validation-examples">
            <span
              v-for="s in ['pass', 'failed', 'na', 'notRun']"
              :key="s"
              class="badge"
              :class="s.toLowerCase()"
              >{{ t(s) }}</span
            >
          </div>
          <div class="semantic-note">
            <Icon name="governance" /><span>{{ t('notRun') }}</span>
          </div></template
        >
        <template v-else-if="modal === 'publish' || modal === 'revision'"
          ><div class="modal-symbol"><Icon name="governance" :size="32" /></div>
          <p>{{ t(modal === 'revision' ? 'revisionNote' : 'publishNote') }}</p>
          <div class="semantic-note">
            <Icon name="clock" /><span>{{ t('validationNote') }}</span>
          </div></template
        >
        <template v-else-if="modal === 'selected'"
          ><div
            v-for="a in allAssets.filter((a) => checked.includes(a.id))"
            :key="a.id"
            class="property-row"
          >
            <strong>{{ a.label }}</strong
            ><code>{{ a.name }}</code>
          </div></template
        >
        <template v-else-if="modal === 'add'"
          ><div
            v-for="a in denseAssets.filter(
              (a) => !nodes.some((n) => n.id === a.id) && a.status === 'PUBLISHED',
            )"
            :key="a.id"
            class="property-row"
          >
            <span>{{ a.label }}</span
            ><span class="badge published">{{ t('published') }}</span>
          </div>
          <p class="quiet-note">{{ t('structureNote') }}</p></template
        >
        <template v-else-if="modal === 'mapPreview'"
          ><table class="detail-table">
            <tbody>
              <tr>
                <th v-for="key in Object.keys(previewRecord)" :key="key">{{ key }}</th>
              </tr>
              <tr>
                <td v-for="value in Object.values(previewRecord)" :key="value">{{ value }}</td>
              </tr>
            </tbody>
          </table>
          <p class="quiet-note">{{ t('actionMock') }}</p></template
        >
        <template v-else-if="modal === 'layoutInfo'"
          ><p>{{ t('layoutDemoNote') }}</p></template
        >
        <template v-else-if="modal === 'copy'"
          ><code class="iri-block">{{ selected?.iri }}</code></template
        >
        <template v-else
          ><div class="modal-symbol"><Icon :name="page" :size="32" /></div>
          <h3 v-if="auxTab">{{ auxTab }}</h3>
          <p>{{ t('structureNote') }}</p>
          <p class="quiet-note">{{ t('actionMock') }}</p></template
        >
      </div>
    </dialog>
    <div v-if="toast" class="toast" role="status"><Icon name="check" :size="17" />{{ toast }}</div>
  </div>
</template>
