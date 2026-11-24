<script setup lang="ts">
import './knowledge.css'

import { computed, h, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns } from '@/components/ui'
import {
  RowActions,
  SearchPanel,
  SearchTable,
  TableToolbar,
  UiAlert,
  UiButton,
  UiEmpty,
  UiSelect,
  UiTag,
} from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

import BaseEditor from './components/BaseEditor.vue'
import { pageQuery, useKnowledgeRead } from './composables/useKnowledge'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const showCreate = ref(false)
const q = ref('')
watch(
  () => route.query.q,
  (value) => {
    q.value = typeof value === 'string' ? value : ''
  },
  { immediate: true },
)
const filters = computed<ReturnType<typeof pageQuery>>((previous) => {
  const next = pageQuery(route.query)
  return previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next
})
const { data, error, loading, reload } = useKnowledgeRead((signal) =>
  knowledgeApi.page(filters.value, signal),
)
const snapshot = shallowRef<{ query: string; value: NonNullable<typeof data.value> } | null>(null)
watch(data, (value) => {
  if (value) snapshot.value = { query: JSON.stringify(filters.value), value }
})
const current = computed(
  () =>
    data.value ??
    (snapshot.value?.query === JSON.stringify(filters.value) ? snapshot.value.value : null),
)
const statuses = computed(() =>
  ['active', 'archived', 'all'].map((value) => ({ value, label: t(`kb.filter.${value}`) })),
)
const sorts = computed(() => [
  { value: '-updated_at', label: t('kb.updatedFirst') },
  { value: 'name', label: t('kb.nameSort') },
])
function filter(key: string, value: unknown) {
  const next = typeof value === 'string' || typeof value === 'number' ? value : ''
  void router.push({
    query: { ...route.query, [key]: next, ...(key === 'page' ? {} : { page: 1 }) },
  })
}
function resetFilters() {
  q.value = ''
  void router.push({
    query: { ...route.query, q: undefined, status: undefined, sort: undefined, page: undefined },
  })
}
function created(base: KnowledgeBase) {
  void router.push({ name: 'knowledge-base-detail', params: { id: base.id } })
}
const date = (value: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' }).format(new Date(value))
const number = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const columns = computed<DataTableColumns<KnowledgeBase>>(() => [
  {
    key: 'name',
    title: t('kb.name'),
    minWidth: 260,
    render: (item) =>
      h('div', { class: 'kb-name' }, [
        h(
          RouterLink,
          { to: { name: 'knowledge-base-detail', params: { id: item.id } }, title: item.name },
          () => item.name,
        ),
        h('div', { class: 'kb-muted kb-wrap' }, item.description),
      ]),
  },
  {
    key: 'document_count',
    title: t('kb.documents'),
    width: 100,
    render: (item) => number(item.document_count),
  },
  {
    key: 'searchable_count',
    title: t('kb.searchable'),
    width: 100,
    render: (item) => number(item.searchable_count),
  },
  { key: 'index_revision', title: t('kb.indexRevision'), width: 100 },
  {
    key: 'archived',
    title: t('kb.status'),
    width: 100,
    render: (item) =>
      h(UiTag, { size: 'small' }, () => t(item.archived ? 'kb.archived' : 'kb.active')),
  },
  {
    key: 'updated_at',
    title: t('kb.updatedAt'),
    width: 140,
    render: (item) => date(item.updated_at),
  },
  {
    key: 'actions',
    title: t('kb.actions'),
    width: 130,
    fixed: 'right',
    render: (item) =>
      h(RowActions<KnowledgeBase>, { row: item }, () =>
        h(RouterLink, { to: { name: 'knowledge-base-search', params: { id: item.id } } }, () =>
          t('kb.search'),
        ),
      ),
  },
])
</script>
<template>
  <section class="kb-page kb-list-page">
    <PageHeader :title="t('kb.title')" :description="t('kb.subtitle')">
      <template #actions
        ><UiButton type="primary" :disabled="!canWrite" @click="showCreate = true">{{
          t('kb.create')
        }}</UiButton></template
      >
    </PageHeader>
    <UiAlert type="info"
      >{{ t('kb.globalAccess') }} <span v-if="!canWrite">{{ t('ui.readonly') }}</span></UiAlert
    >
    <section class="kb-panel kb-stack kb-base-ledger">
      <SearchPanel
        v-model:query="q"
        :placeholder="t('kb.filterPlaceholder')"
        :label="t('kb.filterPlaceholder')"
        :loading="loading"
        @submit="filter('q', $event)"
        @clear="filter('q', '')"
        @reset="resetFilters"
      >
        <template #filters>
          <UiSelect
            :value="filters.status"
            :options="statuses"
            :aria-label="t('kb.status')"
            @update:value="filter('status', $event)"
          />
          <UiSelect
            :value="filters.sort"
            :options="sorts"
            :aria-label="t('kb.sort')"
            @update:value="filter('sort', $event)"
          />
        </template>
      </SearchPanel>
      <SearchTable
        :rows="current?.items ?? []"
        :columns="columns"
        :total="current?.total"
        :page="filters.page"
        :page-size="20"
        mode="remote"
        :searchable="false"
        :loading="loading"
        :error="error"
        :initialized="!!current"
        :scroll-x="1030"
        :row-key="(row: KnowledgeBase) => row.id"
        @update:page="filter('page', $event)"
        @retry="reload"
      >
        <template #toolbar="{ total }"
          ><TableToolbar :label="t('kb.title')" :total="total" :loading="loading"
        /></template>
        <template #empty
          ><UiEmpty
            :description="
              t(filters.q || filters.status !== 'active' ? 'kb.noMatch' : 'kb.emptyBases')
            "
        /></template>
      </SearchTable>
    </section>
    <BaseEditor v-model:show="showCreate" @saved="created" />
  </section>
</template>
