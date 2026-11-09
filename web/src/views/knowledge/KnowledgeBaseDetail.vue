<script setup lang="ts">
import './knowledge.css'

import {
  NAlert,
  NButton,
  NEmpty,
  NInput,
  NPagination,
  NPopconfirm,
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
import DocumentDrawer from './components/DocumentDrawer.vue'
import DocumentStatus from './components/DocumentStatus.vue'
import {
  activeTask,
  pageQuery,
  useKnowledgeAction,
  useKnowledgeRead,
} from './composables/useKnowledge'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const id = computed(() => Number(route.params.id))
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const filters = computed<ReturnType<typeof pageQuery>>((previous) => {
  const next = pageQuery(route.query)
  return previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next
})
const q = ref('')
watch(
  () => route.query.q,
  (value) => {
    q.value = typeof value === 'string' ? value : ''
  },
  { immediate: true },
)
const { data, error, loading, paused, reload } = useKnowledgeRead(
  (signal) => {
    const current = id.value
    const params = filters.value
    return Promise.all([
      knowledgeApi.get(current, signal),
      knowledgeApi.documents(current, params, signal),
    ]).then(([base, documents]) => ({ base, documents }))
  },
  (value) => value.base.processing_count > 0 || value.documents.items.some(activeTask),
)
const capabilities = useKnowledgeRead(knowledgeApi.capabilities)
const { busy, error: actionError, run } = useKnowledgeAction(() => id.value)
const notice = ref('')
watch(id, () => {
  notice.value = ''
  showEdit.value = false
})
const showEdit = ref(false)
const editBase = ref<KnowledgeBase | null>(null)
const canEdit = computed(
  () =>
    canWrite.value && !!data.value && !data.value.base.archived && !error.value && !loading.value,
)
const statuses = computed(() =>
  ['active', 'archived', 'all'].map((value) => ({ value, label: t(`kb.filter.${value}`) })),
)
const sorts = computed(() => [
  { value: '-updated_at', label: t('kb.updatedFirst') },
  { value: 'name', label: t('kb.nameSort') },
])
const uploadHint = computed(() =>
  capabilities.data.value
    ? t('kb.uploadHint', {
        formats: capabilities.data.value.supported_formats.map((format) => `.${format}`).join(', '),
        size: capabilities.data.value.max_file_bytes / 1024 / 1024,
        documents: capabilities.data.value.max_documents_per_base,
        chunks: capabilities.data.value.max_chunks_per_document,
        baseChunks: capabilities.data.value.max_chunks_per_base,
      })
    : '',
)
function filter(key: string, value: string | number) {
  void router.push({
    query: { ...route.query, [key]: value, ...(key === 'page' ? {} : { page: 1 }) },
  })
}
function openEdit() {
  editBase.value = data.value?.base ?? null
  showEdit.value = true
}
async function archive() {
  const base = data.value?.base
  if (!base || !canWrite.value || error.value || loading.value) return
  const result = await run((signal) =>
    knowledgeApi[base.archived ? 'restore' : 'archive'](base.id, base.revision, signal),
  )
  if (result) {
    notice.value = t(result.archived ? 'kb.archiveDone' : 'kb.restoreDone')
    reload()
  }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const cap = capabilities.data.value
  const current = id.value
  if (!file || !cap || !canEdit.value || busy.value) return
  notice.value = ''
  if (file.size > cap.max_file_bytes || file.size === 0) {
    actionError.value = t(file.size ? 'kb.fileTooLarge' : 'kb.fileEmpty')
    input.value = ''
    return
  }
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!cap.supported_formats.includes(extension)) {
    actionError.value = t('kb.unsupportedFile')
    input.value = ''
    return
  }
  const result = await run((signal) => knowledgeApi.upload(current, file, signal))
  input.value = ''
  if (result) {
    notice.value = t(result.duplicate ? 'kb.duplicateUpload' : 'kb.uploaded')
    reload()
    await router.push({ query: { ...route.query, doc: result.id, taskPage: undefined } })
  }
}
</script>

<template>
  <section class="kb-page">
    <PageHeader :title="data?.base.name ?? t('kb.detail')" :description="data?.base.description">
      <template #context
        ><div class="kb-meta">
          <span>{{ t('kb.globalAccess') }}</span
          ><span v-if="data">{{ t('kb.indexRevision') }} · {{ data.base.index_revision }}</span
          ><NTag v-if="data?.base.archived" size="small">{{ t('kb.archived') }}</NTag>
        </div></template
      >
      <template #actions>
        <RouterLink :to="{ name: 'knowledge-bases' }">{{ t('kb.backToBases') }}</RouterLink>
        <NButton :disabled="!canEdit || busy" @click="openEdit">{{ t('common.edit') }}</NButton>
        <NPopconfirm @positive-click="archive"
          ><template #trigger
            ><NButton :loading="busy" :disabled="!canWrite || !data || !!error || loading">{{
              t(data?.base.archived ? 'kb.restore' : 'kb.archive')
            }}</NButton></template
          >{{ t(data?.base.archived ? 'kb.restoreConfirm' : 'kb.archiveConfirm') }}</NPopconfirm
        >
        <NButton
          type="primary"
          @click="router.push({ name: 'knowledge-base-search', params: { id } })"
          >{{ t('kb.search') }}</NButton
        >
      </template>
    </PageHeader>
    <NAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</NAlert>
    <NAlert v-if="data?.base.archived" type="warning">{{ t('kb.archivedNotice') }}</NAlert>
    <NAlert v-if="error" type="error" role="alert"
      >{{ error }} <NButton @click="reload">{{ t('kb.retry') }}</NButton></NAlert
    >
    <NAlert v-if="actionError" type="error" role="alert"
      >{{ actionError }} <NButton @click="reload">{{ t('kb.refresh') }}</NButton></NAlert
    >
    <NAlert v-if="notice" type="success" role="status">{{ notice }}</NAlert>
    <NAlert v-if="paused" type="warning"
      >{{ t('kb.pollPaused') }} <NButton @click="reload">{{ t('kb.refresh') }}</NButton></NAlert
    >
    <NSpin :show="loading">
      <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
      <div v-if="data" class="kb-stack">
        <section class="kb-panel kb-metrics" :aria-label="t('kb.coverage')">
          <div class="kb-metric">
            <span>{{ t('kb.documents') }}</span
            ><strong>{{ data.base.document_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.searchable') }}</span
            ><strong>{{ data.base.searchable_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.processing') }}</span
            ><strong>{{ data.base.processing_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.failedPartial') }}</span
            ><strong>{{ data.base.failed_count }} / {{ data.base.partial_count }}</strong>
          </div>
        </section>
        <section class="kb-panel kb-stack">
          <h2>{{ t('kb.documents') }}</h2>
          <div class="kb-stack">
            <NAlert v-if="capabilities.error.value" type="error"
              >{{ capabilities.error.value }}
              <NButton @click="capabilities.reload">{{ t('kb.retry') }}</NButton></NAlert
            >
            <label for="kb-upload">{{ t('kb.upload') }}</label>
            <input
              id="kb-upload"
              class="kb-file"
              type="file"
              :accept="
                capabilities.data.value?.supported_formats.map((value) => `.${value}`).join(',')
              "
              :disabled="
                !canEdit ||
                busy ||
                !capabilities.data.value ||
                data.base.document_count >= (capabilities.data.value?.max_documents_per_base ?? 0)
              "
              aria-describedby="kb-upload-hint"
              @change="upload"
            />
            <p id="kb-upload-hint" class="kb-muted">{{ uploadHint || t('kb.loading') }}</p>
            <p v-if="busy" role="status">{{ t('kb.working') }}</p>
            <p
              v-if="capabilities.data.value && !capabilities.data.value.embedding_configured"
              class="kb-muted"
            >
              {{ t('kb.semanticUnavailable') }}
            </p>
          </div>
          <form class="kb-toolbar" @submit.prevent="filter('q', q.trim())">
            <NInput
              v-model:value="q"
              clearable
              :placeholder="t('kb.documentFilter')"
              :input-props="{ 'aria-label': t('kb.documentFilter') }"
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
          <div v-if="data.documents.items.length" class="kb-table-scroll">
            <NTable :single-line="false">
              <thead>
                <tr>
                  <th>{{ t('kb.filename') }}</th>
                  <th>{{ t('kb.indexAndTask') }}</th>
                  <th>{{ t('kb.size') }}</th>
                  <th>{{ t('kb.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in data.documents.items" :key="doc.id">
                  <td class="kb-name">
                    <RouterLink
                      :title="doc.name"
                      :to="{ query: { ...route.query, doc: doc.id, taskPage: undefined } }"
                      >{{ doc.name }}</RouterLink
                    >
                    <div v-if="doc.archived">
                      <NTag size="small">{{ t('kb.archived') }}</NTag>
                    </div>
                  </td>
                  <td><DocumentStatus :document="doc" /></td>
                  <td>{{ t('kb.byteSize', { n: doc.size_bytes }) }}</td>
                  <td>
                    <NButton
                      size="small"
                      @click="
                        router.push({ query: { ...route.query, doc: doc.id, taskPage: undefined } })
                      "
                      >{{ t('kb.viewTasks') }}</NButton
                    >
                  </td>
                </tr>
              </tbody>
            </NTable>
          </div>
          <NEmpty
            v-else
            class="kb-empty"
            :description="
              t(filters.q || filters.status !== 'active' ? 'kb.noMatch' : 'kb.emptyDocuments')
            "
          />
          <div v-if="data.documents.total > 20" class="kb-pagination">
            <NPagination
              :page="filters.page"
              :page-size="20"
              :item-count="data.documents.total"
              @update:page="filter('page', $event)"
            />
          </div>
        </section>
      </div>
    </NSpin>
    <BaseEditor v-model:show="showEdit" :base="editBase" @saved="reload" />
    <DocumentDrawer :kb-id="id" :base-archived="data?.base.archived ?? true" @changed="reload" />
  </section>
</template>
