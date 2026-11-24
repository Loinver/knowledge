<script setup lang="ts">
import { computed, h, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  AssetAuditAction,
  AssetAuditLog,
  AssetAuditQuery,
  AssetAuditVersion,
  AssetType,
} from '@/api/asset-audit'
import { assetAuditApi } from '@/api/asset-audit'
import type { DataTableColumns } from '@/components/ui'
import {
  FormField,
  SearchPanel,
  SearchTable,
  UiButton,
  UiCard,
  UiDatePicker,
  UiEmpty,
  UiSelect,
  UiTag,
} from '@/components/ui'
import { useAsyncData } from '@/composables/useAsyncData'

const { t, locale } = useI18n()
const page = ref(1)
const pageSize = 20
const query = ref('')
const action = ref<AssetAuditAction | null>(null)
const objectType = ref<AssetType | null>(null)
const result = ref<AssetAuditLog['result'] | null>(null)
const timeRange = ref<[number, number] | null>(null)
const applied = reactive<AssetAuditQuery>({})
const { data, error, loading, reload } = useAsyncData((signal) =>
  assetAuditApi.page({ ...applied, page: page.value, page_size: pageSize }, signal),
)

const actions: AssetAuditAction[] = [
  'CREATE',
  'EDIT',
  'RENAME',
  'ASSEMBLE',
  'PUBLISH',
  'UNPUBLISH',
  'DELETE',
  'SWITCH_CURRENT',
  'IMPORT',
]
const objectTypes: AssetType[] = [
  'NAMESPACE',
  'ENTITY_TYPE',
  'RELATION_TYPE',
  'BUSINESS_DOMAIN',
  'ONTOLOGY',
  'MAPPING',
  'DATASOURCE',
  'RULE',
  'ASSEMBLY_TEMPLATE',
  'ENUM_DICTIONARY',
  'STANDARD_CLAUSE',
  'GRAPH_REVISION',
]
const actionOptions = computed(() =>
  actions.map((value) => ({
    value,
    label: t(`assetAudit.actions.${value}`),
  })),
)
const objectOptions = computed(() =>
  objectTypes.map((value) => ({
    value,
    label: t(`assetAudit.objects.${value}`),
  })),
)
const resultOptions = computed(() =>
  ['OK', 'FAILED'].map((value) => ({
    value,
    label: t(`system.results.${value}`),
  })),
)

function versionText(version: AssetAuditVersion | null) {
  if (!version) return t('assetAudit.unavailable')
  const parts = Object.entries(version)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${t(`assetAudit.versions.${key}`)}: ${value}`)
  return parts.length ? parts.join(' · ') : t('assetAudit.unversioned')
}

const columns = computed<DataTableColumns<AssetAuditLog>>(() => [
  {
    title: t('system.time'),
    key: 'created_at',
    width: 180,
    render: (row) =>
      new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'short',
        timeStyle: 'medium',
      }).format(new Date(row.created_at)),
  },
  {
    title: t('assetAudit.actorId'),
    key: 'actor_id',
    width: 275,
    render: (row) => h('code', row.actor_id),
  },
  {
    title: t('system.action'),
    key: 'action',
    width: 130,
    render: (row) => t(`assetAudit.actions.${row.action}`),
  },
  {
    title: t('assetAudit.object'),
    key: 'object_type',
    width: 150,
    render: (row) =>
      `${t(`assetAudit.objects.${row.object_type}`)} · ${row.object_id ?? t('assetAudit.unassigned')}`,
  },
  {
    title: t('assetAudit.before'),
    key: 'version_before',
    width: 210,
    render: (row) => versionText(row.version_before),
  },
  {
    title: t('assetAudit.after'),
    key: 'version_after',
    width: 210,
    render: (row) => versionText(row.version_after),
  },
  {
    title: t('system.result'),
    key: 'result',
    width: 100,
    render: (row) =>
      h(
        UiTag,
        { size: 'small', type: row.result === 'OK' ? 'success' : 'error' },
        {
          default: () => t(`system.results.${row.result}`),
        },
      ),
  },
  {
    title: t('assetAudit.errorCode'),
    key: 'error_code',
    width: 220,
    render: (row) => row.error_code ?? '-',
  },
  {
    title: t('assetAudit.correlationId'),
    key: 'correlation_id',
    width: 275,
    render: (row) => h('code', row.correlation_id),
  },
])

function search() {
  Object.assign(applied, {
    q: query.value.trim() || undefined,
    action: action.value ?? undefined,
    object_type: objectType.value ?? undefined,
    result: result.value ?? undefined,
    since: timeRange.value ? new Date(timeRange.value[0]).toISOString() : undefined,
    until: timeRange.value ? new Date(timeRange.value[1]).toISOString() : undefined,
  })
  page.value = 1
  reload()
}

function clearSearch() {
  query.value = ''
  search()
}

function reset() {
  query.value = ''
  action.value = null
  objectType.value = null
  result.value = null
  timeRange.value = null
  search()
}
</script>

<template>
  <UiCard size="small" class="asset-audit ledger-panel"
    ><header class="ledger-heading">
      <h2>{{ t('assetAudit.title') }}</h2>
      <span v-if="data && !loading">{{ t('assetAudit.total', { count: data.total }) }}</span>
    </header>
    <p class="audit-hint">{{ t('assetAudit.hint') }}</p>

    <SearchTable
      v-model:page="page"
      :searchable="false"
      mode="remote"
      :total="data?.total ?? 0"
      :page-size="pageSize"
      :pagination="true"
      :error="error"
      size="small"
      :columns="columns"
      :rows="data?.items ?? []"
      :loading="loading"
      :row-key="(row: AssetAuditLog) => row.id"
      :scroll-x="1750"
      @retry="reload"
    >
      <template #search
        ><SearchPanel
          v-model:query="query"
          :loading="loading"
          :placeholder="t('assetAudit.searchHint')"
          @submit="search"
          @clear="clearSearch"
          @reset="reset"
          ><template #filter
            ><div class="flex flex-wrap items-end gap-3">
              <FormField :label="t('system.action')" :show-feedback="false">
                <UiSelect
                  v-model:value="action"
                  :aria-label="t('system.action')"
                  :options="actionOptions"
                  clearable
                />
              </FormField>
              <FormField :label="t('assetAudit.objectType')" :show-feedback="false">
                <UiSelect
                  v-model:value="objectType"
                  :aria-label="t('assetAudit.objectType')"
                  :options="objectOptions"
                  clearable
                />
              </FormField>
              <FormField :label="t('system.result')" :show-feedback="false">
                <UiSelect
                  v-model:value="result"
                  :aria-label="t('system.result')"
                  :options="resultOptions"
                  clearable
                />
              </FormField>
              <FormField
                :label="t('assetAudit.timeRange')"
                :show-feedback="false"
                class="time-filter"
              >
                <UiDatePicker
                  v-model:value="timeRange"
                  type="datetimerange"
                  :aria-label="t('assetAudit.timeRange')"
                  clearable
                />
              </FormField>
              <div class="filter-actions">
                <UiButton :loading="loading" @click="reload">{{ t('graph.refresh') }}</UiButton>
              </div>
            </div></template
          ></SearchPanel
        ></template
      >
      <template #empty
        ><UiEmpty :description="error ? t('assetAudit.loadFailed') : t('assetAudit.empty')"
      /></template>
    </SearchTable>
  </UiCard>
</template>

<style scoped src="../../SystemWorkspace.css"></style>

<style scoped>
.asset-audit {
  margin-bottom: var(--space-4);
}
.audit-hint {
  margin-top: 0;
  color: var(--text-secondary);
}
.audit-filters {
  display: grid;
  grid-template-columns: minmax(210px, 2fr) repeat(3, minmax(140px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.time-filter {
  grid-column: span 2;
}
.time-filter :deep(.ui-date-picker) {
  width: 100%;
}
.filter-actions {
  display: flex;
  align-items: end;
  gap: var(--space-2);
  grid-column: span 2;
}
.audit-error {
  margin-bottom: var(--space-3);
}
.audit-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
@media (max-width: 900px) {
  .audit-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
  .audit-filters {
    grid-template-columns: minmax(0, 1fr);
  }
  .time-filter,
  .filter-actions {
    grid-column: auto;
  }
  .filter-actions {
    flex-wrap: wrap;
  }
}
</style>
