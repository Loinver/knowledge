<script setup lang="ts">
import {
  NAlert,
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NPagination,
  NPopconfirm,
  NSpin,
  NTag,
} from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { knowledgeApi } from '@/api/knowledge'
import { useAuthStore } from '@/stores/auth'

import {
  activeTask,
  positivePage,
  useKnowledgeAction,
  useKnowledgeMessage,
  useKnowledgeRead,
} from '../composables/useKnowledge'
import DocumentStatus from './DocumentStatus.vue'

const props = defineProps<{ kbId: number; baseArchived: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const docId = computed(() => (typeof route.query.doc === 'string' ? route.query.doc : ''))
const taskPage = computed(() => positivePage(route.query.taskPage))
const { data, error, loading, paused, reload } = useKnowledgeRead(
  (signal) => {
    const id = props.kbId
    const doc = docId.value
    const page = taskPage.value
    return doc
      ? Promise.all([
          knowledgeApi.document(id, doc, signal),
          knowledgeApi.tasks(id, doc, page, signal),
        ]).then(([document, tasks]) => ({ document, tasks }))
      : Promise.resolve(null)
  },
  (value) => activeTask(value.document),
)
const { busy, error: actionError, run } = useKnowledgeAction(() => `${props.kbId}:${docId.value}`)
const { reason, message } = useKnowledgeMessage()
const canWrite = computed(
  () =>
    ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') &&
    !props.baseArchived &&
    !error.value &&
    !loading.value,
)
function close() {
  void router.push({ query: { ...route.query, doc: undefined, taskPage: undefined } })
}
async function act(action: 'archive' | 'restore' | 'reprocess') {
  const doc = data.value?.document
  if (!doc || !canWrite.value || (action === 'reprocess' && (doc.archived || activeTask(doc))))
    return
  const result = await run((signal) =>
    knowledgeApi.documentAction(props.kbId, doc.id, action, doc.revision, signal),
  )
  if (result) {
    reload()
    emit('changed')
  }
}
async function download() {
  const doc = data.value?.document
  if (!doc) return
  const blob = await run((signal) => knowledgeApi.original(props.kbId, doc.id, signal))
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = doc.name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const date = (value: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
</script>

<template>
  <NDrawer :show="!!docId" :width="620" @update:show="!$event && close()">
    <NDrawerContent :title="data?.document.name ?? t('kb.documentDetail')" closable>
      <div class="kb-stack">
        <NAlert v-if="error" type="error" role="alert"
          >{{ error }} <NButton @click="reload">{{ t('kb.retry') }}</NButton></NAlert
        >
        <NAlert v-if="actionError" type="error" role="alert"
          >{{ actionError }} <NButton @click="reload">{{ t('kb.refresh') }}</NButton></NAlert
        >
        <NAlert v-if="paused" type="warning"
          >{{ t('kb.pollPaused') }} <NButton @click="reload">{{ t('kb.refresh') }}</NButton></NAlert
        >
        <NSpin :show="loading">
          <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
          <div v-if="data" class="kb-stack">
            <NAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</NAlert>
            <NTag v-if="data.document.archived" type="warning">{{ t('kb.archived') }}</NTag>
            <DocumentStatus :document="data.document" />
            <p class="kb-muted">{{ t('kb.indexTaskExplanation') }}</p>
            <div class="kb-actions">
              <NButton :loading="busy" @click="download">{{ t('kb.original') }}</NButton>
              <NButton
                :disabled="!canWrite || busy || data.document.archived || activeTask(data.document)"
                @click="act('reprocess')"
                >{{ t('kb.reprocess') }}</NButton
              >
              <NPopconfirm @positive-click="act(data.document.archived ? 'restore' : 'archive')"
                ><template #trigger
                  ><NButton :disabled="!canWrite || busy">{{
                    t(data.document.archived ? 'kb.restore' : 'kb.archive')
                  }}</NButton></template
                >{{
                  t(data.document.archived ? 'kb.restoreConfirm' : 'kb.documentArchiveConfirm')
                }}</NPopconfirm
              >
            </div>
            <div v-if="data.document.active_index" class="kb-panel kb-stack">
              <strong>{{ t('kb.activeIndex') }}</strong>
              <span>{{ t('kb.chunks', { n: data.document.active_index.chunk_count }) }}</span>
              <span
                >{{ data.document.active_index.parser_version }} ·
                {{ data.document.active_index.chunker_version }}</span
              >
              <span
                >{{ t('kb.parseStatus') }} ·
                {{ t(`kb.taskStatus.${data.document.active_index.parse_status}`) }}</span
              >
              <span v-if="data.document.active_index.embedding_model"
                >{{ data.document.active_index.embedding_model }} ·
                {{ data.document.active_index.embedding_version }}</span
              >
              <NAlert v-if="data.document.active_index.error_reason" type="warning">{{
                reason(data.document.active_index.error_reason)
              }}</NAlert>
              <NAlert
                v-for="(warning, index) in data.document.active_index.warnings"
                :key="index"
                type="warning"
                >{{ reason(String(warning.reason ?? '')) }}</NAlert
              >
            </div>
            <h2>{{ t('kb.tasks') }}</h2>
            <NEmpty v-if="!data.tasks.items.length" :description="t('kb.emptyTasks')" />
            <article v-for="task in data.tasks.items" :key="task.id" class="kb-panel kb-stack">
              <div class="kb-meta">
                <strong>{{ t('kb.generation', { n: task.generation }) }}</strong
                ><span>{{ t(`kb.taskStatus.${task.status}`) }}</span
                ><span>{{ t(`kb.phase.${task.phase}`) }}</span>
              </div>
              <span>{{
                t('kb.taskProgress', { done: task.processed_chunks, total: task.total_chunks })
              }}</span>
              <span class="kb-muted">{{ date(task.created_at) }}</span>
              <NAlert v-if="task.error_code || task.error_reason" type="warning">{{
                task.error_code
                  ? message({ code: task.error_code, params: { reason: task.error_reason } })
                  : reason(task.error_reason)
              }}</NAlert>
            </article>
            <NPagination
              v-if="data.tasks.total > 10"
              :page="taskPage"
              :page-size="10"
              :item-count="data.tasks.total"
              @update:page="router.push({ query: { ...route.query, taskPage: $event } })"
            />
          </div>
        </NSpin>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
