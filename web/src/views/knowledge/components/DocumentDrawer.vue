<script setup lang="ts">
import { computed, h, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { knowledgeApi, type KnowledgeTask } from '@/api/knowledge'
import type { DataTableColumns } from '@/components/ui'
import { SearchTable, TableToolbar } from '@/components/ui'
import {
  UiAlert,
  UiButton,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiPopconfirm,
  UiSpin,
  UiTag,
} from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

import {
  activeTask,
  positivePage,
  useKnowledgeAction,
  useKnowledgeActor,
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
const actor = useKnowledgeActor()
const {
  busy,
  error: actionError,
  run,
} = useKnowledgeAction(() =>
  JSON.stringify([props.kbId, docId.value, actor.value, props.baseArchived]),
)
const readKey = computed(() => JSON.stringify([props.kbId, docId.value, taskPage.value]))
const snapshot = shallowRef<{ key: string; value: NonNullable<typeof data.value> } | null>(null)
watch(data, (value) => {
  if (value) snapshot.value = { key: readKey.value, value }
})
const current = computed(
  () => data.value ?? (snapshot.value?.key === readKey.value ? snapshot.value.value : null),
)
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
  if (
    !doc ||
    busy.value ||
    !canWrite.value ||
    (action === 'reprocess' && (doc.archived || activeTask(doc)))
  )
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
  if (!doc || busy.value || loading.value || error.value) return
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
const columns = computed<DataTableColumns<KnowledgeTask>>(() => [
  { key: 'generation', title: t('kb.generation', { n: '' }), width: 90 },
  {
    key: 'status',
    title: t('kb.status'),
    minWidth: 110,
    render: (task) => t(`kb.taskStatus.${task.status}`),
  },
  {
    key: 'phase',
    title: t('kb.indexAndTask'),
    minWidth: 160,
    render: (task) =>
      h('div', { class: 'kb-stack' }, [
        h('span', t(`kb.phase.${task.phase}`)),
        h('span', t('kb.taskProgress', { done: task.processed_chunks, total: task.total_chunks })),
        task.error_code || task.error_reason
          ? h(UiAlert, { type: 'warning' }, () =>
              task.error_code
                ? message({ code: task.error_code, params: { reason: task.error_reason } })
                : reason(task.error_reason),
            )
          : null,
      ]),
  },
  {
    key: 'created_at',
    title: t('kb.updatedAt'),
    width: 150,
    render: (task) => date(task.created_at),
  },
])
</script>

<template>
  <UiDrawer :show="!!docId" :width="'min(620px, 100vw)'" @update:show="!$event && close()">
    <UiDrawerContent :title="current?.document.name ?? t('kb.documentDetail')" closable>
      <div class="kb-stack kb-inspector-content">
        <UiAlert v-if="error" type="error" role="alert"
          >{{ error }} <UiButton @click="reload">{{ t('kb.retry') }}</UiButton></UiAlert
        >
        <UiAlert v-if="actionError" type="error" role="alert"
          >{{ actionError }} <UiButton @click="reload">{{ t('kb.refresh') }}</UiButton></UiAlert
        >
        <UiAlert v-if="paused" type="warning"
          >{{ t('kb.pollPaused') }}
          <UiButton @click="reload">{{ t('kb.refresh') }}</UiButton></UiAlert
        >
        <UiSpin :show="loading">
          <p v-if="loading" role="status">{{ t('kb.loading') }}</p>
          <div v-if="current" class="kb-stack">
            <UiAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</UiAlert>
            <UiTag v-if="current.document.archived" type="warning">{{ t('kb.archived') }}</UiTag>
            <DocumentStatus :document="current.document" />
            <p class="kb-muted">{{ t('kb.indexTaskExplanation') }}</p>
            <div class="kb-actions">
              <UiButton :loading="busy" @click="download">{{ t('kb.original') }}</UiButton>
              <UiButton
                :disabled="
                  !canWrite || busy || current.document.archived || activeTask(current.document)
                "
                @click="act('reprocess')"
                >{{ t('kb.reprocess') }}</UiButton
              >
              <UiPopconfirm @positive-click="act(current.document.archived ? 'restore' : 'archive')"
                ><template #trigger
                  ><UiButton :disabled="!canWrite || busy">{{
                    t(current.document.archived ? 'kb.restore' : 'kb.archive')
                  }}</UiButton></template
                >{{
                  t(current.document.archived ? 'kb.restoreConfirm' : 'kb.documentArchiveConfirm')
                }}</UiPopconfirm
              >
            </div>
            <div v-if="current.document.active_index" class="kb-panel kb-stack">
              <strong>{{ t('kb.activeIndex') }}</strong>
              <span>{{ t('kb.chunks', { n: current.document.active_index.chunk_count }) }}</span>
              <span
                >{{ current.document.active_index.parser_version }} ·
                {{ current.document.active_index.chunker_version }}</span
              >
              <span
                >{{ t('kb.parseStatus') }} ·
                {{ t(`kb.taskStatus.${current.document.active_index.parse_status}`) }}</span
              >
              <span v-if="current.document.active_index.embedding_model"
                >{{ current.document.active_index.embedding_model }} ·
                {{ current.document.active_index.embedding_version }}</span
              >
              <UiAlert v-if="current.document.active_index.error_reason" type="warning">{{
                reason(current.document.active_index.error_reason)
              }}</UiAlert>
              <UiAlert
                v-for="(warning, index) in current.document.active_index.warnings"
                :key="index"
                type="warning"
                >{{ reason(String(warning.reason ?? '')) }}</UiAlert
              >
            </div>
            <SearchTable
              :rows="current.tasks.items"
              :columns="columns"
              :total="current.tasks.total"
              :page="taskPage"
              :page-size="10"
              :row-key="(task: KnowledgeTask) => task.id"
              mode="remote"
              :searchable="false"
              :initialized="!!current"
              :loading="loading"
              :error="error"
              :scroll-x="510"
              @retry="reload"
              @update:page="router.push({ query: { ...route.query, taskPage: $event } })"
            >
              <template #toolbar="{ total }"
                ><TableToolbar :label="t('kb.tasks')" :total="total" :loading="loading"
              /></template>
              <template #empty><UiEmpty :description="t('kb.emptyTasks')" /></template>
            </SearchTable>
          </div>
        </UiSpin>
      </div>
    </UiDrawerContent>
  </UiDrawer>
</template>
