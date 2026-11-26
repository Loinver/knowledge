<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AuditAction, AuditLog } from '@/api/auth'
import { authApi } from '@/api/auth'
import { getSessionGeneration, subscribeTokens } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns } from '@/components/ui'
import {
  FormField,
  SearchTable,
  UiButton,
  UiCard,
  UiEmpty,
  UiSelect,
  UiTabPane,
  UiTabs,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'
import AssetAuditLogs from '@/views/system/audit-logs/components/AssetAuditLogs.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const auth = useAuthStore()

const ACTIONS: AuditAction[] = [
  'LOGIN',
  'LOGOUT',
  'REGISTER',
  'PASSWORD_CHANGED',
  'RESET_REQUESTED',
  'PASSWORD_RESET',
  'PROFILE_UPDATED',
  'ROLE_CHANGED',
  'STATUS_CHANGED',
]

const items = ref<AuditLog[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const error = ref('')
let generation = 0
let alive = true

const query = ref('')
const keyword = ref('')
const actionFilter = ref<AuditAction | null>(null)
const listSession = ref(getSessionGeneration())
const stopListSession = subscribeTokens(() => {
  listSession.value = getSessionGeneration()
})
const listIdentity = computed(() =>
  JSON.stringify([listSession.value, auth.user?.id, auth.user?.role, auth.user?.status]),
)
const listQuery = computed(() => ({
  q: keyword.value || undefined,
  action: actionFilter.value ?? undefined,
  page: page.value,
  page_size: pageSize,
}))
const listKey = computed(() => JSON.stringify([listIdentity.value, listQuery.value]))
watch(
  listKey,
  () => {
    generation++
    items.value = []
    total.value = 0
    error.value = ''
    loading.value = false
  },
  { flush: 'sync' },
)
watch(listIdentity, () => {
  if (auth.user) void load()
})
onBeforeUnmount(() => {
  alive = false
  generation++
  stopListSession()
})
const actionOptions = computed(() =>
  ACTIONS.map((value) => ({ value, label: t(`system.actions.${value}`) })),
)

const columns = computed<DataTableColumns<AuditLog>>(() => [
  { title: t('system.actor'), key: 'actor' },
  {
    title: t('system.action'),
    key: 'action',
    render: (row) => t(`system.actions.${row.action}`),
  },
  {
    title: t('system.target'),
    key: 'target',
    render: (row) => row.target ?? '-',
  },
  {
    title: t('system.result'),
    key: 'result',
    render: (row) =>
      h(
        UiTag,
        { size: 'small', type: row.result === 'OK' ? 'success' : 'error' },
        { default: () => t(`system.results.${row.result}`) },
      ),
  },
  { title: t('system.ip'), key: 'ip', render: (row) => h('code', row.ip ?? '-') },
  {
    title: t('system.time'),
    key: 'created_at',
    render: (row) =>
      new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'medium' }).format(
        new Date(row.created_at),
      ),
  },
])

async function load() {
  if (!alive) return
  const request = ++generation
  const session = getSessionGeneration()
  const key = listKey.value
  const owns = () =>
    alive && request === generation && session === getSessionGeneration() && key === listKey.value
  loading.value = true
  error.value = ''
  try {
    const result = await authApi.auditLogs(listQuery.value)
    if (!owns()) return
    if (page.value > Math.max(1, Math.ceil(result.total / pageSize))) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize))
      void load()
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (owns()) error.value = toMessage(err)
  } finally {
    if (owns()) loading.value = false
  }
}

function search() {
  keyword.value = query.value.trim()
  page.value = 1
  void load()
}
function clearSearch() {
  query.value = ''
  search()
}
function resetSearch() {
  query.value = ''
  actionFilter.value = null
  search()
}

onMounted(load)
</script>

<template>
  <section class="system-page audit-page">
    <PageHeader :title="t('page.systemAuditLogs')" :description="t('system.auditHint')" />
    <UiTabs class="audit-tabs" type="line" default-value="assets"
      ><UiTabPane name="assets" :tab="t('assetAudit.title')"><AssetAuditLogs /></UiTabPane
      ><UiTabPane name="account" :tab="t('assetAudit.accountTitle')">
        <UiCard size="small" class="ledger-panel"
          ><header class="ledger-heading">
            <div>
              <h2>{{ t('operationsUi.auditLedger') }}</h2>
              <p class="ledger-description">{{ t('assetAudit.accountTitle') }}</p>
            </div>
            <span v-if="!error && !loading">{{ t('assetAudit.total', { count: total }) }}</span>
          </header>

          <SearchTable
            v-model:page="page"
            v-model:query="query"
            mode="remote"
            :total="total"
            :page-size="pageSize"
            :pagination="true"
            :search-placeholder="t('system.searchAuditLogs')"
            :error="error"
            size="small"
            :columns="columns"
            :rows="items"
            :loading="loading"
            :row-key="(row: AuditLog) => row.id"
            :scroll-x="820"
            @submit="search"
            @clear="clearSearch"
            @reset="resetSearch"
            @retry="load"
            @update:page="load"
          >
            <template #filter
              ><div class="flex flex-wrap items-end gap-3">
                <FormField
                  :label="t('system.action')"
                  label-placement="top"
                  :label-width="72"
                  :show-feedback="false"
                >
                  <UiSelect
                    v-model:value="actionFilter"
                    :options="actionOptions"
                    clearable
                    class="filter-select"
                    @update:value="search"
                  />
                </FormField>
                <UiButton :loading="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
              </div></template
            >
            <template #empty><UiEmpty :description="t('common.empty')" /></template>
          </SearchTable>
        </UiCard> </UiTabPane
    ></UiTabs>
  </section>
</template>

<style scoped src="../SystemWorkspace.css"></style>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) auto minmax(150px, 1fr) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.audit-tabs {
  padding: 0;
  min-width: 0;
}
@media (max-width: 900px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
.filter-select {
  width: 100%;
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
</style>
