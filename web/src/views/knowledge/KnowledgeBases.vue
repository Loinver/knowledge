<script setup lang="ts">
import './knowledge.css'

import {
  NAlert,
  NButton,
  NEmpty,
  NInput,
  NPagination,
  NSelect,
  NSpin,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import PageHeader from '@/components/PageHeader.vue'
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
const statuses = computed(() =>
  ['active', 'archived', 'all'].map((value) => ({ value, label: t(`kb.filter.${value}`) })),
)
const sorts = computed(() => [
  { value: '-updated_at', label: t('kb.updatedFirst') },
  { value: 'name', label: t('kb.nameSort') },
])
function filter(key: string, value: string | number) {
  void router.push({
    query: { ...route.query, [key]: value, ...(key === 'page' ? {} : { page: 1 }) },
  })
}
function created(base: KnowledgeBase) {
  void router.push({ name: 'knowledge-base-detail', params: { id: base.id } })
}
const date = (value: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' }).format(new Date(value))
</script>

<template>
  <section class="kb-page">
    <PageHeader :title="t('kb.title')" :description="t('kb.subtitle')">
      <template #actions
        ><NButton type="primary" :disabled="!canWrite" @click="showCreate = true">{{
          t('kb.create')
        }}</NButton></template
      >
    </PageHeader>
    <NAlert type="info"
      >{{ t('kb.globalAccess') }} <span v-if="!canWrite">{{ t('ui.readonly') }}</span></NAlert
    >
    <section class="kb-panel kb-stack">
      <form class="kb-toolbar" @submit.prevent="filter('q', q.trim())">
        <NInput
          v-model:value="q"
          clearable
          :placeholder="t('kb.filterPlaceholder')"
          :input-props="{ 'aria-label': t('kb.filterPlaceholder') }"
        />
        <NButton attr-type="submit">{{ t('kb.filterAction') }}</NButton>
        <NSelect
          :value="filters.status"
          :options="statuses"
          :aria-label="t('kb.status')"
          @update:value="filter('status', $event)"
        />
        <NSelect
          :value="filters.sort"
          :options="sorts"
          :aria-label="t('kb.sort')"
          @update:value="filter('sort', $event)"
        />
      </form>
      <NAlert v-if="error" type="error" role="alert"
        >{{ error }} <NButton @click="reload">{{ t('kb.retry') }}</NButton></NAlert
      >
      <NSpin :show="loading">
        <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
        <div v-else-if="data?.items.length" class="kb-table-scroll">
          <NTable :single-line="false">
            <thead>
              <tr>
                <th>{{ t('kb.name') }}</th>
                <th>{{ t('kb.documents') }}</th>
                <th>{{ t('kb.searchable') }}</th>
                <th>{{ t('kb.indexRevision') }}</th>
                <th>{{ t('kb.status') }}</th>
                <th>{{ t('kb.updatedAt') }}</th>
                <th>{{ t('kb.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in data.items" :key="item.id">
                <td class="kb-name">
                  <RouterLink
                    :to="{ name: 'knowledge-base-detail', params: { id: item.id } }"
                    :title="item.name"
                    >{{ item.name }}</RouterLink
                  >
                  <div class="kb-muted kb-wrap">{{ item.description }}</div>
                </td>
                <td>{{ item.document_count }}</td>
                <td>{{ item.searchable_count }}</td>
                <td>{{ item.index_revision }}</td>
                <td>
                  <NTag size="small" :bordered="false">{{
                    t(item.archived ? 'kb.archived' : 'kb.active')
                  }}</NTag>
                </td>
                <td>{{ date(item.updated_at) }}</td>
                <td>
                  <RouterLink :to="{ name: 'knowledge-base-search', params: { id: item.id } }">{{
                    t('kb.search')
                  }}</RouterLink>
                </td>
              </tr>
            </tbody>
          </NTable>
        </div>
        <NEmpty
          v-else-if="!error"
          class="kb-empty"
          :description="
            t(filters.q || filters.status !== 'active' ? 'kb.noMatch' : 'kb.emptyBases')
          "
        />
      </NSpin>
      <div v-if="data && data.total > 20" class="kb-pagination">
        <NPagination
          :page="filters.page"
          :page-size="20"
          :item-count="data.total"
          @update:page="filter('page', $event)"
        />
      </div>
    </section>
    <BaseEditor v-model:show="showCreate" @saved="created" />
  </section>
</template>
