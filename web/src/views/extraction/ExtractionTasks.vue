<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCheckbox,
  NDatePicker,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  NTable,
  NTag,
} from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { DatasourceBrief } from '@/api/datasources'
import { datasourcesApi } from '@/api/datasources'
import type { ExtractionTask } from '@/api/extraction'
import { extractionApi } from '@/api/extraction'
import type { Mapping } from '@/api/mappings'
import { mappingsApi } from '@/api/mappings'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

const { t, locale } = useI18n()
const router = useRouter()
const { toMessage } = useApiError()

const auth = useAuthStore()
const canWrite = computed(() => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR')
const showCreate = ref(false)
const cancellationRequested = ref<number[]>([])
const tasks = ref<ExtractionTask[]>([])
const mappings = ref<Mapping[]>([])
const datasources = ref<DatasourceBrief[]>([])
const loading = ref(false)
const optionLoading = ref(false)
const revisionLoading = ref(false)
const taskError = ref('')
const createError = ref('')
const notice = ref('')
const page = ref(1)

const selectedMappingId = ref<number | null>(null)
const selectedDatasourceId = ref<number | null>(null)
const publishedRevisionId = ref<number | null>(null)
const namespace = ref('https://example.org/kg/')
const incremental = ref(false)
const runAfter = ref<number | null>(null)
const creating = ref(false)
const cancellingId = ref<number | null>(null)
const formRef = ref<FormInst | null>(null)

let taskController: AbortController | undefined
let optionController: AbortController | undefined
let pollTimer: number | undefined
let disposed = false
let mappingGeneration = 0

const mappingOptions = computed(() =>
  mappings.value
    .filter((item) => item.status === 'PUBLISHED')
    .map((item) => ({ label: item.name, value: item.id })),
)
const datasourceOptions = computed(() =>
  datasources.value.map((item) => ({ label: `${item.name} · ${item.kind}`, value: item.id })),
)
const canCreate = computed(
  () =>
    canWrite.value &&
    Boolean(
      namespace.value.trim() &&
      selectedMappingId.value &&
      selectedDatasourceId.value &&
      publishedRevisionId.value,
    ) &&
    !creating.value &&
    !revisionLoading.value &&
    !optionLoading.value,
)
const rules = computed<FormRules>(() => ({
  mapping: {
    required: true,
    type: 'number',
    message: t('tasks.mappingRequired'),
    trigger: ['blur', 'change'],
  },
  datasource: {
    required: true,
    type: 'number',
    message: t('tasks.datasourceRequired'),
    trigger: ['blur', 'change'],
  },
  namespace: [
    {
      required: true,
      message: t('tasks.namespaceRequired'),
      trigger: ['blur', 'input'],
    },
  ],
}))

const dateFormat = computed(
  () => new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }),
)

function formatTime(value: string | null | undefined): string {
  if (!value) return '-'
  const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`
  return dateFormat.value.format(new Date(timestamp))
}

function progressText(task: ExtractionTask): string {
  const progress = task.progress ?? {}
  const phase = typeof progress.phase === 'string' ? progress.phase : '-'
  const entityCount = typeof progress.entity_count === 'number' ? progress.entity_count : null
  const tripleCount = typeof progress.triple_count === 'number' ? progress.triple_count : null
  const quarantineCount =
    typeof progress.quarantine_count === 'number' ? progress.quarantine_count : null
  const counts = [
    entityCount === null ? null : t('tasks.entityCount', { count: entityCount }),
    tripleCount === null ? null : t('tasks.tripleCount', { count: tripleCount }),
    quarantineCount === null ? null : t('tasks.quarantineCount', { count: quarantineCount }),
  ].filter(Boolean)
  return [t(`tasks.phases.${phase}`, phase), ...counts].join(' · ')
}

function canCancel(task: ExtractionTask): boolean {
  return (
    canWrite.value &&
    !cancellationRequested.value.includes(task.id) &&
    (task.status === 'PENDING' || task.status === 'RUNNING')
  )
}

async function loadTasks(): Promise<void> {
  taskController?.abort()
  const controller = new AbortController()
  taskController = controller
  loading.value = true
  taskError.value = ''
  try {
    const items = await extractionApi.tasks(page.value, controller.signal)
    if (controller.signal.aborted) return
    tasks.value = items
    cancellationRequested.value = cancellationRequested.value.filter(
      (id) =>
        !items.some((item) => item.id === id && !['PENDING', 'RUNNING'].includes(item.status)),
    )
  } catch (err) {
    if (!controller.signal.aborted) taskError.value = toMessage(err)
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

async function loadOptions(): Promise<void> {
  optionController?.abort()
  const controller = new AbortController()
  optionController = controller
  optionLoading.value = true
  createError.value = ''
  try {
    const [mappingItems, datasourceItems] = await Promise.all([
      mappingsApi.list(controller.signal),
      datasourcesApi.list({}, controller.signal),
    ])
    if (controller.signal.aborted) return
    mappings.value = mappingItems
    datasources.value = datasourceItems
  } catch (err) {
    if (!controller.signal.aborted) createError.value = toMessage(err)
  } finally {
    if (!controller.signal.aborted) optionLoading.value = false
  }
}

async function chooseMapping(value: number | null): Promise<void> {
  const generation = ++mappingGeneration
  selectedMappingId.value = value
  publishedRevisionId.value = null
  createError.value = ''
  revisionLoading.value = value !== null
  if (value === null) return
  try {
    const revision = await mappingsApi.published(value)
    if (disposed || generation !== mappingGeneration) return
    if (!revision) throw { code: 'KG.REVISION_NOT_FOUND' }
    publishedRevisionId.value = revision.id
  } catch (err) {
    if (!disposed && generation === mappingGeneration) createError.value = toMessage(err)
  } finally {
    if (!disposed && generation === mappingGeneration) revisionLoading.value = false
  }
}

async function createTask(): Promise<void> {
  if (!canCreate.value) return
  const generation = mappingGeneration
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (disposed || generation !== mappingGeneration || !canCreate.value) return
  creating.value = true
  createError.value = ''
  notice.value = ''
  try {
    const task = await extractionApi.createTask({
      mapping_revision_id: publishedRevisionId.value as number,
      datasource_id: selectedDatasourceId.value as number,
      namespace: namespace.value.trim(),
      incremental: incremental.value,
      run_after: runAfter.value === null ? null : new Date(runAfter.value).toISOString(),
    })
    if (disposed) return
    showCreate.value = false
    notice.value = t('tasks.createdNotice', { id: task.id })
    page.value = 1
    await loadTasks()
  } catch (err) {
    if (!disposed) createError.value = toMessage(err)
  } finally {
    if (!disposed) creating.value = false
  }
}

async function cancelTask(task: ExtractionTask): Promise<void> {
  if (!canCancel(task) || cancellingId.value !== null) return
  cancellingId.value = task.id
  notice.value = ''
  try {
    const cancelled = await extractionApi.cancelTask(task.id)
    if (disposed) return
    const complete = cancelled.status === 'CANCELLED'
    if (!complete && ['PENDING', 'RUNNING'].includes(cancelled.status))
      cancellationRequested.value = [...cancellationRequested.value, cancelled.id]
    notice.value = t(complete ? 'tasks.cancelled' : 'extractionUi.cancelRequested', {
      id: cancelled.id,
    })
    await loadTasks()
  } catch (err) {
    if (!disposed) taskError.value = toMessage(err)
  } finally {
    if (!disposed) cancellingId.value = null
  }
}

function gotoRuns(runId: number): void {
  void router.push({ name: 'extraction-runs', query: { run: runId } })
}

watch(page, () => void loadTasks())

onMounted(async () => {
  await Promise.all([loadOptions(), loadTasks()])
  if (disposed) return
  pollTimer = window.setInterval(() => {
    if (!document.hidden && !loading.value) void loadTasks()
  }, 2000)
})

onBeforeUnmount(() => {
  disposed = true
  mappingGeneration += 1
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
  taskController?.abort()
  optionController?.abort()
})
</script>

<template>
  <section class="tasks-page">
    <PageHeader :title="t('page.extractionTasks')" :description="t('tasks.description')">
      <template #actions>
        <NButton type="primary" :disabled="!canWrite" @click="showCreate = true">{{
          t('tasks.createTitle')
        }}</NButton>
        <NButton :disabled="loading" :loading="loading" @click="loadTasks">
          {{ t('graph.refresh') }}
        </NButton>
      </template>
    </PageHeader>

    <NAlert v-if="notice" type="info" role="status">{{ notice }}</NAlert>
    <NAlert v-if="!canWrite" type="info">{{ t('extractionUi.viewer') }}</NAlert>
    <NAlert v-if="taskError" type="error" role="alert"
      >{{ taskError
      }}<NButton :disabled="loading" @click="loadTasks">{{
        t('extractionUi.retry')
      }}</NButton></NAlert
    >

    <NSpin :show="loading">
      <div v-if="tasks.length" class="table-scroll">
        <NTable :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ t('tasks.id') }}</th>
              <th>{{ t('tasks.mappingRevision') }}</th>
              <th>{{ t('tasks.datasource') }}</th>
              <th>{{ t('common.status') }}</th>
              <th>{{ t('tasks.progress') }}</th>
              <th>{{ t('tasks.created') }}</th>
              <th>{{ t('tasks.finished') }}</th>
              <th>{{ t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in tasks" :key="task.id">
              <td>{{ task.id }}</td>
              <td>{{ task.mapping_revision_id }}</td>
              <td>{{ task.datasource_id }}</td>
              <td>
                <NTag
                  :type="
                    task.status === 'FAILED'
                      ? 'error'
                      : task.status === 'SUCCESS'
                        ? 'success'
                        : 'default'
                  "
                  >{{
                    cancellationRequested.includes(task.id)
                      ? t('extractionUi.cancelling')
                      : t(`tasks.statuses.${task.status}`, task.status)
                  }}</NTag
                >
                <p v-if="task.error" class="task-error">
                  {{ t(`errors.${task.error}`, task.error) }}
                </p>
              </td>
              <td>{{ progressText(task) }}</td>
              <td>{{ formatTime(task.created_at) }}</td>
              <td>{{ formatTime(task.finished_at) }}</td>
              <td>
                <NSpace size="small" :wrap="false">
                  <NButton
                    v-if="task.run_id"
                    size="small"
                    quaternary
                    @click="gotoRuns(task.run_id!)"
                  >
                    {{ t('tasks.viewRun') }}
                  </NButton>
                  <NButton
                    v-if="canCancel(task)"
                    size="small"
                    type="error"
                    quaternary
                    :loading="cancellingId === task.id"
                    :disabled="cancellingId !== null && cancellingId !== task.id"
                    @click="cancelTask(task)"
                  >
                    {{ t('tasks.cancel') }}
                  </NButton>
                </NSpace>
              </td>
            </tr>
          </tbody>
        </NTable>
      </div>
      <NEmpty v-else-if="!loading && !taskError" :description="t('tasks.empty')" />
    </NSpin>

    <NSpace align="center">
      <NButton :disabled="loading || page === 1" @click="page--">
        {{ t('runs.previous') }}
      </NButton>
      <span aria-live="polite">{{ t('runs.page', { page }) }}</span>
      <NButton :disabled="loading || tasks.length < 20" @click="page++">
        {{ t('runs.next') }}
      </NButton>
    </NSpace>
    <NDrawer
      v-model:show="showCreate"
      :width="'min(520px, 100vw)'"
      :mask-closable="!creating"
      :close-on-esc="!creating"
    >
      <NDrawerContent :title="t('tasks.createTitle')" :closable="!creating">
        <NAlert v-if="createError" type="error" role="alert"
          >{{ createError
          }}<NButton
            :disabled="!canWrite || optionLoading || creating"
            @click="selectedMappingId ? chooseMapping(selectedMappingId) : loadOptions()"
            >{{ t('extractionUi.retry') }}</NButton
          ></NAlert
        >
        <NAlert v-if="publishedRevisionId" type="info">{{
          t('extractionUi.taskFrozen', { revision: publishedRevisionId })
        }}</NAlert>
        <NEmpty
          v-if="!optionLoading && !createError && !mappingOptions.length"
          :description="t('extractionUi.noPublishedMappings')"
        />
        <NSpin :show="optionLoading">
          <NForm
            ref="formRef"
            :model="{
              mapping: selectedMappingId,
              datasource: selectedDatasourceId,
              namespace,
            }"
            :rules="rules"
            label-placement="top"
            class="task-form"
          >
            <NFormItem :label="t('tasks.mapping')" path="mapping">
              <NSelect
                :value="selectedMappingId"
                :options="mappingOptions"
                :loading="revisionLoading"
                :placeholder="t('tasks.chooseMapping')"
                filterable
                :disabled="!canWrite || optionLoading || creating"
                @update:value="chooseMapping"
              />
            </NFormItem>
            <NFormItem :label="t('tasks.datasource')" path="datasource">
              <NSelect
                v-model:value="selectedDatasourceId"
                :options="datasourceOptions"
                :placeholder="t('tasks.chooseDatasource')"
                filterable
                :disabled="!canWrite || optionLoading || creating"
              />
            </NFormItem>
            <NFormItem :label="t('tasks.namespace')" path="namespace">
              <NInput
                v-model:value="namespace"
                :disabled="!canWrite || optionLoading || creating"
              />
            </NFormItem>
            <NFormItem :label="t('tasks.runAfter')" path="runAfter">
              <NDatePicker
                v-model:value="runAfter"
                :disabled="!canWrite || optionLoading || creating"
                type="datetime"
                clearable
                class="date-input"
                :placeholder="t('tasks.runNow')"
              />
            </NFormItem>
            <NFormItem :label="t('tasks.mode')" path="incremental">
              <NCheckbox
                v-model:checked="incremental"
                :disabled="!canWrite || optionLoading || creating"
              >
                {{ t('tasks.incremental') }}
              </NCheckbox>
            </NFormItem>
            <div class="form-actions">
              <NButton :disabled="creating" @click="showCreate = false">{{
                t('common.cancel')
              }}</NButton>
              <NButton
                type="primary"
                :disabled="!canCreate"
                :loading="creating"
                @click="createTask"
              >
                {{ t('tasks.create') }}
              </NButton>
            </div>
          </NForm>
        </NSpin>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.tasks-page {
  display: grid;
  gap: var(--space-4);
}
.task-form {
  display: grid;
  gap: var(--space-2);
  grid-template-columns: minmax(0, 1fr);
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  grid-column: 1 / -1;
}
.date-input {
  width: 100%;
}
.table-scroll {
  overflow-x: auto;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
@media (max-width: 767px) {
  .task-form {
    grid-template-columns: 1fr;
  }
}
.task-error {
  max-width: 240px;
  overflow-wrap: anywhere;
  color: var(--s-violation);
}
</style>
