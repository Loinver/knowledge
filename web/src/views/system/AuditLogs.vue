<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NFormItem,
  NInput,
  NPagination,
  NSelect,
  NSpace,
  NTag,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AuditAction, AuditLog } from '@/api/auth'
import { authApi } from '@/api/auth'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t } = useI18n()
const { toMessage } = useApiError()

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

const query = ref('')
const keyword = ref('')
const actionFilter = ref<AuditAction | null>(null)
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
        NTag,
        { size: 'small', type: row.result === 'OK' ? 'success' : 'error' },
        { default: () => t(`system.results.${row.result}`) },
      ),
  },
  { title: t('system.ip'), key: 'ip', render: (row) => h('code', row.ip ?? '-') },
  {
    title: t('system.time'),
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await authApi.auditLogs({
      q: keyword.value || undefined,
      action: actionFilter.value ?? undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items
    total.value = result.total
    if (!items.value.length && page.value > 1) page.value--
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
}

function search() {
  keyword.value = query.value.trim()
  page.value = 1
  void load()
}

onMounted(load)
</script>

<template>
  <section>
    <PageHeader :title="t('page.systemAuditLogs')" :description="t('system.auditHint')" />
    <NCard size="small">
      <NSpace class="filters" align="end">
        <NFormItem :label="t('common.search')" :show-feedback="false">
          <NInput
            v-model:value="query"
            clearable
            :placeholder="t('system.searchAuditLogs')"
            @keyup.enter="search"
          />
        </NFormItem>
        <NButton @click="search">{{ t('common.search') }}</NButton>
        <NFormItem :label="t('system.action')" :show-feedback="false">
          <NSelect
            v-model:value="actionFilter"
            :options="actionOptions"
            clearable
            class="filter-select"
            @update:value="search"
          />
        </NFormItem>
        <NButton :loading="loading" @click="load">{{ t('graph.refresh') }}</NButton>
      </NSpace>
      <NDataTable
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: AuditLog) => row.id"
        :scroll-x="820"
      >
        <template #empty><NEmpty :description="error || t('common.empty')" /></template>
      </NDataTable>
      <NPagination
        v-if="total > pageSize"
        v-model:page="page"
        :page-size="pageSize"
        :item-count="total"
        class="pagination"
        @update:page="load"
      />
    </NCard>
  </section>
</template>

<style scoped>
.filters {
  margin-bottom: var(--space-4);
}
.filter-select {
  width: 180px;
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
</style>
