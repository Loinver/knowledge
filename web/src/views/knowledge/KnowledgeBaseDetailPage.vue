<script setup lang="ts">
import './knowledge.css'

import { computed, h, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeBase, type KnowledgeDocument } from '@/api/knowledge'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormActions,
  FormContainer,
  FormField,
  SearchPanel,
  SearchTable,
  TableToolbar,
} from '@/components/ui'
import { UiAlert, UiButton, UiEmpty, UiPopconfirm, UiSelect, UiSpin, UiTag } from '@/components/ui'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
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
const readKey = computed(() => JSON.stringify([id.value, filters.value]))
const snapshot = shallowRef<{ key: string; value: NonNullable<typeof data.value> } | null>(null)
watch(data, (value) => {
  if (value) snapshot.value = { key: readKey.value, value }
})
const current = computed(
  () => data.value ?? (snapshot.value?.key === readKey.value ? snapshot.value.value : null),
)
usePageIdentity(() => (data.value?.base.id === id.value ? data.value.base.name : ''))
const { busy, error: actionError, run } = useKnowledgeAction(() => `${id.value}:${auth.user?.role}`)
const notice = ref('')
const uploadForm = ref<{ file: File | null }>({ file: null })
const uploadFormRef = ref<FormInst | null>(null)
const uploadInput = ref<HTMLInputElement | null>(null)
watch(id, () => {
  notice.value = ''
  showEdit.value = false
  uploadForm.value = { file: null }
  if (uploadInput.value) uploadInput.value.value = ''
})
const showEdit = ref(false)
const editBase = ref<KnowledgeBase | null>(null)
const canEdit = computed(
  () =>
    canWrite.value &&
    data.value?.base.id === id.value &&
    !data.value.base.archived &&
    !error.value &&
    !loading.value,
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
function openEdit() {
  editBase.value = data.value?.base ?? null
  showEdit.value = true
}
async function archive() {
  const base = data.value?.base
  if (
    !base ||
    base.id !== id.value ||
    !canWrite.value ||
    error.value ||
    loading.value ||
    busy.value
  )
    return
  const result = await run((signal) =>
    knowledgeApi[base.archived ? 'restore' : 'archive'](base.id, base.revision, signal),
  )
  if (result) {
    notice.value = t(result.archived ? 'kb.archiveDone' : 'kb.restoreDone')
    reload()
  }
}
function fileError(file: File | null) {
  const cap = capabilities.data.value
  if (!file) return t('common.required')
  if (!cap) return t('kb.loading')
  if (file.size > cap.max_file_bytes || file.size === 0)
    return t(file.size ? 'kb.fileTooLarge' : 'kb.fileEmpty')
  if (!cap.supported_formats.includes(file.name.split('.').pop()?.toLowerCase() ?? ''))
    return t('kb.unsupportedFile')
  return ''
}
const uploadRules = computed<FormRules>(() => ({
  file: { required: true, validator: (_rule, value) => fileError(value as File | null) || true },
}))
function selectFile(event: Event) {
  if (busy.value) return
  uploadForm.value.file = (event.target as HTMLInputElement).files?.[0] ?? null
  actionError.value = ''
}
async function upload(event?: Event) {
  if (event) selectFile(event)
  const file = uploadForm.value.file
  const cap = capabilities.data.value
  const current = id.value
  if (
    !file ||
    !cap ||
    !canEdit.value ||
    busy.value ||
    (data.value?.base.document_count ?? 0) >= cap.max_documents_per_base
  )
    return
  notice.value = ''
  const invalid = fileError(file)
  if (invalid) {
    actionError.value = invalid
    return
  }
  const result = await run((signal) => knowledgeApi.upload(current, file, signal))
  if (result) {
    uploadForm.value.file = null
    if (uploadInput.value) uploadInput.value.value = ''
    notice.value = t(result.duplicate ? 'kb.duplicateUpload' : 'kb.uploaded')
    reload()
    await router.push({ query: { ...route.query, doc: result.id, taskPage: undefined } })
  }
}
const columns = computed<DataTableColumns<KnowledgeDocument>>(() => [
  {
    key: 'name',
    title: t('kb.filename'),
    minWidth: 230,
    render: (doc) =>
      h('div', { class: 'kb-name' }, [
        h(
          RouterLink,
          { title: doc.name, to: { query: { ...route.query, doc: doc.id, taskPage: undefined } } },
          () => doc.name,
        ),
        doc.archived ? h(UiTag, { size: 'small' }, () => t('kb.archived')) : null,
      ]),
  },
  {
    key: 'status',
    title: t('kb.indexAndTask'),
    minWidth: 260,
    render: (doc) => h(DocumentStatus, { document: doc }),
  },
  {
    key: 'size_bytes',
    title: t('kb.size'),
    width: 100,
    render: (doc) => t('kb.byteSize', { n: doc.size_bytes }),
  },
  {
    key: 'actions',
    title: t('kb.actions'),
    width: 130,
    fixed: 'right',
    render: (doc) =>
      h(
        UiButton,
        {
          size: 'small',
          onClick: () =>
            router.push({ query: { ...route.query, doc: doc.id, taskPage: undefined } }),
        },
        () => t('kb.viewTasks'),
      ),
  },
])
</script>

<template>
  <section class="kb-page kb-detail-page">
    <PageHeader
      :title="current?.base.name ?? t('kb.detail')"
      :description="current?.base.description"
      :eyebrow="t('kb.detail')"
      :identity="current ? `${current.base.id} · r${current.base.revision}` : undefined"
    >
      <template #context
        ><div class="kb-meta">
          <span>{{ t('kb.globalAccess') }}</span
          ><span v-if="current"
            >{{ t('kb.indexRevision') }} · {{ current.base.index_revision }}</span
          ><UiTag v-if="current?.base.archived" size="small">{{ t('kb.archived') }}</UiTag>
        </div></template
      >
      <template #actions>
        <RouterLink :to="{ name: 'knowledge-bases' }">{{ t('kb.backToBases') }}</RouterLink>
        <UiButton :disabled="!canEdit || busy" @click="openEdit">{{ t('common.edit') }}</UiButton>
        <UiPopconfirm @positive-click="archive"
          ><template #trigger
            ><UiButton :loading="busy" :disabled="!canWrite || !current || !!error || loading">{{
              t(current?.base.archived ? 'kb.restore' : 'kb.archive')
            }}</UiButton></template
          >{{ t(current?.base.archived ? 'kb.restoreConfirm' : 'kb.archiveConfirm') }}</UiPopconfirm
        >
        <UiButton
          type="primary"
          @click="router.push({ name: 'knowledge-base-search', params: { id } })"
          >{{ t('kb.search') }}</UiButton
        >
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</UiAlert>
    <UiAlert v-if="current?.base.archived" type="warning">{{ t('kb.archivedNotice') }}</UiAlert>
    <UiAlert v-if="error" type="error" role="alert"
      >{{ error }} <UiButton @click="reload">{{ t('kb.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="actionError" type="error" role="alert"
      >{{ actionError }} <UiButton @click="reload">{{ t('kb.refresh') }}</UiButton></UiAlert
    >
    <UiAlert v-if="notice" type="success" role="status">{{ notice }}</UiAlert>
    <UiAlert v-if="paused" type="warning"
      >{{ t('kb.pollPaused') }} <UiButton @click="reload">{{ t('kb.refresh') }}</UiButton></UiAlert
    >
    <UiSpin :show="loading">
      <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
      <div v-if="current" class="kb-stack">
        <section class="kb-panel kb-metrics" :aria-label="t('kb.coverage')">
          <div class="kb-metric">
            <span>{{ t('kb.documents') }}</span
            ><strong>{{ current.base.document_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.searchable') }}</span
            ><strong>{{ current.base.searchable_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.processing') }}</span
            ><strong>{{ current.base.processing_count }}</strong>
          </div>
          <div class="kb-metric">
            <span>{{ t('kb.failedPartial') }}</span
            ><strong>{{ current.base.failed_count }} / {{ current.base.partial_count }}</strong>
          </div>
        </section>
        <div class="kb-detail-workspace">
          <section class="kb-panel kb-stack kb-document-ledger">
            <header class="kb-panel-heading">
              <h2>{{ t('kb.documents') }}</h2>
              <span class="kb-muted">{{ t('kb.indexAndTask') }}</span>
            </header>
            <SearchPanel
              v-model:query="q"
              :placeholder="t('kb.documentFilter')"
              :label="t('kb.documentFilter')"
              :loading="loading"
              @submit="filter('q', $event)"
              @clear="filter('q', '')"
              @reset="resetFilters"
            >
              <template #filters>
                <UiSelect
                  class="w-full sm:w-36"
                  :value="filters.status"
                  :options="statuses"
                  :aria-label="t('kb.status')"
                  @update:value="filter('status', $event)"
                />
                <UiSelect
                  class="w-full sm:w-40"
                  :value="filters.sort"
                  :options="sorts"
                  :aria-label="t('kb.sort')"
                  @update:value="filter('sort', $event)"
                />
              </template>
            </SearchPanel>
            <SearchTable
              :rows="current.documents.items"
              :columns="columns"
              :total="current.documents.total"
              :page="filters.page"
              :page-size="20"
              :row-key="(doc: KnowledgeDocument) => doc.id"
              mode="remote"
              :searchable="false"
              :initialized="!!current"
              :loading="loading"
              :error="error"
              :scroll-x="720"
              @update:page="filter('page', $event)"
              @retry="reload"
            >
              <template #toolbar="{ total }"
                ><TableToolbar :label="t('kb.documents')" :total="total" :loading="loading"
              /></template>
              <template #empty
                ><UiEmpty
                  :description="
                    t(filters.q || filters.status !== 'active' ? 'kb.noMatch' : 'kb.emptyDocuments')
                  "
              /></template>
            </SearchTable>
          </section>
          <aside class="kb-panel kb-stack kb-ingest-inspector" :aria-label="t('kb.detail')">
            <header class="kb-panel-heading">
              <h2>{{ t('kb.upload') }}</h2>
              <UiTag size="small">{{
                t(current.base.archived ? 'kb.archived' : 'kb.active')
              }}</UiTag>
            </header>
            <div class="kb-stack">
              <UiAlert v-if="capabilities.error.value" type="error"
                >{{ capabilities.error.value }}
                <UiButton @click="capabilities.reload">{{ t('kb.retry') }}</UiButton></UiAlert
              >
              <FormContainer
                ref="uploadFormRef"
                :model="uploadForm"
                :rules="uploadRules"
                :disabled="
                  !canEdit ||
                  busy ||
                  !capabilities.data.value ||
                  current.base.document_count >=
                    (capabilities.data.value?.max_documents_per_base ?? 0)
                "
                :submitting="busy"
                @submit="upload()"
              >
                <FormField
                  path="file"
                  :label="t('kb.upload')"
                  :help="uploadHint || t('kb.loading')"
                  required
                >
                  <template #default="field">
                    <input
                      :id="field.id"
                      ref="uploadInput"
                      class="kb-file w-full rounded-md border border-input bg-background p-2 focus-visible:outline-ring"
                      type="file"
                      :accept="
                        capabilities.data.value?.supported_formats
                          .map((value) => `.${value}`)
                          .join(',')
                      "
                      :disabled="field.disabled"
                      :aria-labelledby="field.ariaLabelledby"
                      :aria-describedby="field.ariaDescribedby"
                      :aria-invalid="field.ariaInvalid"
                      @change="selectFile"
                    />
                  </template>
                </FormField>
                <FormActions :submitting="busy">
                  <UiButton
                    type="primary"
                    attr-type="submit"
                    :loading="busy"
                    :disabled="!canEdit || !uploadForm.file"
                    >{{ t('kb.upload') }}</UiButton
                  >
                </FormActions>
              </FormContainer>
              <p v-if="busy" role="status">{{ t('kb.working') }}</p>
              <p
                v-if="capabilities.data.value && !capabilities.data.value.embedding_configured"
                class="kb-muted"
              >
                {{ t('kb.semanticUnavailable') }}
              </p>
            </div>

            <dl class="kb-facts">
              <dt>{{ t('kb.indexRevision') }}</dt>
              <dd>{{ current.base.index_revision }}</dd>
              <dt>{{ t('common.status') }}</dt>
              <dd>{{ t(current.base.archived ? 'kb.archived' : 'kb.active') }}</dd>
            </dl>
          </aside>
        </div>
      </div>
    </UiSpin>
    <BaseEditor v-model:show="showEdit" :base="editBase" @saved="reload" />
    <DocumentDrawer :kb-id="id" :base-archived="current?.base.archived ?? true" @changed="reload" />
  </section>
</template>
