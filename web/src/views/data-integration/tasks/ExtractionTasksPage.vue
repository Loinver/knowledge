<script setup lang="ts">
import '../integration.css'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { DatasourceBrief } from '@/api/datasources'
import { datasourcesApi } from '@/api/datasources'
import type { ExtractionTask, TaskCreateInput } from '@/api/extraction'
import { extractionApi } from '@/api/extraction'
import type { Mapping } from '@/api/mappings'
import { mappingsApi } from '@/api/mappings'
import SearchTable from '@/components/business/SearchTable.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiCheckbox,
  UiDatePicker,
  UiDrawer,
  UiDrawerContent,
  UiEmpty,
  UiInput,
  UiSelect,
  UiSpace,
  UiSpin,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

const { t, te, locale } = useI18n()
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
const initialized = ref(false)
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
const validating = ref(false)
const createSession = ref(0)
const cancellingId = ref<number | null>(null)
const formRef = ref<FormInst | null>(null)

let taskController: AbortController | undefined
let optionController: AbortController | undefined
let pollTimer: number | undefined
let disposed = false
let mappingGeneration = 0
let createInputGeneration = 0
let createPermissionGeneration = 0

const formModel = {
  get mapping() {
    return selectedMappingId.value
  },
  get datasource() {
    return selectedDatasourceId.value
  },
  get namespace() {
    return namespace.value
  },
  get runAfter() {
    return runAfter.value
  },
  get incremental() {
    return incremental.value
  },
}
const createVisible = useDraftGuard(
  showCreate,
  () => formModel,
  () => canWrite.value && !optionLoading.value,
  () => createSession.value,
)

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
    !creating.value &&
    !validating.value &&
    !revisionLoading.value &&
    !optionLoading.value,
)
const rules = computed<FormRules>(() => {
  const revision = publishedRevisionId.value
  return {
    mapping: {
      required: true,
      type: 'integer',
      min: 1,
      message: t('tasks.mappingRequired'),
      trigger: ['blur', 'input', 'change'],
      validator: () => Number.isSafeInteger(revision) && (revision ?? 0) > 0,
    },
    datasource: {
      required: true,
      type: 'integer',
      min: 1,
      message: t('tasks.datasourceRequired'),
      trigger: ['blur', 'input', 'change'],
    },
    namespace: {
      required: true,
      type: 'string',
      message: t('tasks.namespaceRequired'),
      trigger: ['blur', 'input'],
    },
    runAfter: {
      message: t('tasks.invalidRunAfter'),
      trigger: ['blur', 'input'],
      validator: (_rule, value) =>
        value === null ||
        (typeof value === 'number' &&
          Number.isSafeInteger(value) &&
          new Date(value).getUTCFullYear() >= 1 &&
          new Date(value).getUTCFullYear() <= 9999),
    },
    incremental: {
      required: true,
      type: 'boolean',
      message: t('tasks.invalidMode'),
      trigger: ['blur', 'input'],
    },
  }
})

const columns = computed<DataTableColumns<ExtractionTask>>(() => [
  { key: 'id', title: t('tasks.id'), format: 'raw' },
  { key: 'mapping_revision_id', title: t('tasks.mappingRevision'), format: 'raw' },
  { key: 'datasource_id', title: t('tasks.datasource'), format: 'raw' },
  { key: 'status', title: t('common.status') },
  { key: 'progress', title: t('tasks.progress'), render: progressText },
  { key: 'created_at', title: t('tasks.created'), render: (task) => formatTime(task.created_at) },
  {
    key: 'finished_at',
    title: t('tasks.finished'),
    render: (task) => formatTime(task.finished_at),
  },
  { key: 'actions', title: t('common.actions'), fixed: 'right' },
])
const canPrevious = computed(() => !loading.value && page.value > 1)
const canNext = computed(() => !loading.value && !taskError.value && tasks.value.length === 20)
function previousPage() {
  if (!disposed && canPrevious.value) page.value--
}
function nextPage() {
  if (!disposed && canNext.value) page.value++
}

function openCreate() {
  if (disposed || !canWrite.value || showCreate.value) return
  selectedMappingId.value = null
  selectedDatasourceId.value = null
  publishedRevisionId.value = null
  namespace.value = 'https://example.org/kg/'
  incremental.value = false
  runAfter.value = null
  const retryOptions = Boolean(createError.value && !mappings.value.length)
  createError.value = ''
  showCreate.value = true
  if (retryOptions) void loadOptions()
}

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
  if (disposed) return
  taskController?.abort()
  const controller = new AbortController()
  taskController = controller
  loading.value = true
  taskError.value = ''
  try {
    const items = await extractionApi.tasks(page.value, controller.signal)
    if (controller.signal.aborted || disposed) return
    tasks.value = items
    cancellationRequested.value = cancellationRequested.value.filter(
      (id) =>
        !items.some((item) => item.id === id && !['PENDING', 'RUNNING'].includes(item.status)),
    )
  } catch (err) {
    if (!controller.signal.aborted && !disposed) taskError.value = toMessage(err)
  } finally {
    if (!controller.signal.aborted && !disposed) {
      loading.value = false
      initialized.value = true
    }
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
  if (disposed || !canWrite.value || creating.value) return
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
  if (disposed || !showCreate.value || !canCreate.value || !formRef.value) return
  const session = createSession.value
  const generation = mappingGeneration
  const inputGeneration = createInputGeneration
  const permissionGeneration = createPermissionGeneration
  const instance = formRef.value
  const snapshot = { ...formModel, revision: publishedRevisionId.value }
  const isCurrent = () =>
    !disposed &&
    showCreate.value &&
    session === createSession.value &&
    permissionGeneration === createPermissionGeneration &&
    canWrite.value
  validating.value = true
  try {
    try {
      await instance.validate()
    } catch {
      return
    }
    if (
      !isCurrent() ||
      generation !== mappingGeneration ||
      inputGeneration !== createInputGeneration ||
      instance !== formRef.value ||
      !canWrite.value ||
      optionLoading.value ||
      revisionLoading.value
    )
      return
    const payload: TaskCreateInput = {
      mapping_revision_id: snapshot.revision!,
      datasource_id: snapshot.datasource!,
      namespace: snapshot.namespace.trim(),
      incremental: snapshot.incremental,
      run_after: snapshot.runAfter === null ? null : new Date(snapshot.runAfter).toISOString(),
    }
    creating.value = true
    validating.value = false
    createError.value = ''
    notice.value = ''
    const task = await extractionApi.createTask(payload)
    if (!isCurrent()) return
    showCreate.value = false
    notice.value = t('tasks.createdNotice', { id: task.id })
    if (page.value === 1) await loadTasks()
    else page.value = 1
  } catch (err) {
    if (isCurrent()) createError.value = toMessage(err)
  } finally {
    if (isCurrent()) {
      creating.value = false
      validating.value = false
    }
  }
}

async function cancelTask(task: ExtractionTask): Promise<void> {
  if (disposed || !canCancel(task) || cancellingId.value !== null) return
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
watch(
  canWrite,
  () => {
    createPermissionGeneration++
    creating.value = false
    validating.value = false
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)
watch(
  [selectedMappingId, selectedDatasourceId, namespace, incremental, runAfter],
  () => createInputGeneration++,
  { flush: 'sync' },
)
watch(
  showCreate,
  () => {
    createSession.value++
    mappingGeneration++
    creating.value = false
    validating.value = false
    revisionLoading.value = false
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)

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
  <section class="integration-page tasks-page">
    <PageHeader :title="t('page.extractionTasks')" :description="t('tasks.description')">
      <template #actions>
        <UiButton type="primary" :disabled="!canWrite" @click="openCreate">{{
          t('tasks.createTitle')
        }}</UiButton>
        <UiButton :disabled="loading" :loading="loading" @click="loadTasks">
          {{ t('graph.refresh') }}
        </UiButton>
      </template>
    </PageHeader>

    <UiAlert v-if="notice" type="info" role="status">{{ notice }}</UiAlert>
    <UiAlert v-if="!canWrite" type="info">{{ t('extractionUi.viewer') }}</UiAlert>
    <dl class="integration-readings" :aria-label="t('page.extractionTasks')">
      <div v-for="status in ['PENDING', 'RUNNING', 'FAILED', 'SUCCESS']" :key="status">
        <dt>{{ t(`tasks.statuses.${status}`) }}</dt>
        <dd>
          {{
            loading || taskError || !initialized
              ? t('common.noneValue')
              : tasks.filter((task) => task.status === status).length
          }}
        </dd>
      </div>
    </dl>
    <section class="integration-ledger integration-run-ledger">
      <header class="integration-panel-heading">
        <h2>{{ t('tasks.progress') }}</h2>
        <span>{{ t('runs.page', { page }) }}</span>
      </header>
      <SearchTable
        :rows="tasks"
        :columns="columns"
        :loading="loading"
        :error="taskError"
        :initialized="initialized"
        :searchable="false"
        :empty-text="t('tasks.empty')"
        :label="t('page.extractionTasks')"
        mode="none"
        @retry="loadTasks"
      >
        <template #toolbar />
        <template #cell-status="{ row: task }">
          <UiTag
            :type="
              task.status === 'FAILED' ? 'error' : task.status === 'SUCCESS' ? 'success' : 'default'
            "
            >{{
              cancellationRequested.includes(task.id)
                ? t('extractionUi.cancelling')
                : t(`tasks.statuses.${task.status}`, task.status)
            }}</UiTag
          >
          <p v-if="task.error" class="task-error">
            {{
              te(`tasks.reasons.${task.error}`)
                ? t(`tasks.reasons.${task.error}`)
                : toMessage({ code: task.error })
            }}
          </p>
        </template>
        <template #actions="{ row: task }">
          <UiSpace size="small" :wrap="false">
            <UiButton
              v-if="task.run_id !== null"
              size="small"
              quaternary
              @click="gotoRuns(task.run_id!)"
              >{{ t('tasks.viewRun') }}</UiButton
            >
            <UiButton
              v-if="canCancel(task)"
              size="small"
              type="error"
              quaternary
              :loading="cancellingId === task.id"
              :disabled="cancellingId !== null && cancellingId !== task.id"
              @click="cancelTask(task)"
              >{{ t('tasks.cancel') }}</UiButton
            >
          </UiSpace>
        </template>
      </SearchTable>
      <nav class="integration-pager" :aria-label="t('page.extractionTasks')">
        <UiSpace align="center">
          <UiButton :disabled="!canPrevious" @click="previousPage">
            {{ t('runs.previous') }}
          </UiButton>
          <span aria-live="polite">{{ t('runs.page', { page }) }}</span>
          <UiButton :disabled="!canNext" @click="nextPage">
            {{ t('runs.next') }}
          </UiButton>
        </UiSpace>
      </nav>
    </section>
    <UiDrawer
      v-model:show="createVisible"
      :width="'min(520px, 100vw)'"
      :mask-closable="!creating"
      :close-on-esc="!creating"
    >
      <UiDrawerContent :title="t('tasks.createTitle')" :closable="!creating">
        <UiAlert v-if="createError" type="error" role="alert"
          >{{ createError
          }}<UiButton
            :disabled="!canWrite || optionLoading || creating"
            @click="selectedMappingId ? chooseMapping(selectedMappingId) : loadOptions()"
            >{{ t('extractionUi.retry') }}</UiButton
          ></UiAlert
        >
        <UiAlert v-if="publishedRevisionId" type="info">{{
          t('extractionUi.taskFrozen', { revision: publishedRevisionId })
        }}</UiAlert>
        <UiEmpty
          v-if="!optionLoading && !createError && !mappingOptions.length"
          :description="t('extractionUi.noPublishedMappings')"
        />
        <UiSpin :show="optionLoading">
          <FormContainer
            ref="formRef"
            :model="formModel"
            :disabled="!canWrite || optionLoading || creating"
            :submitting="creating"
            :rules="rules"
            label-placement="top"
            class="task-form"
            @submit="createTask"
          >
            <fieldset class="integration-form-group">
              <legend>{{ t('extractionUi.versionChain') }}</legend>
              <FormField :label="t('tasks.mapping')" path="mapping">
                <UiSelect
                  :value="selectedMappingId"
                  :options="mappingOptions"
                  :loading="revisionLoading"
                  :placeholder="t('tasks.chooseMapping')"
                  filterable
                  :disabled="!canWrite || optionLoading || creating"
                  @update:value="chooseMapping"
                />
              </FormField>
              <FormField :label="t('tasks.datasource')" path="datasource">
                <UiSelect
                  v-model:value="selectedDatasourceId"
                  :options="datasourceOptions"
                  :placeholder="t('tasks.chooseDatasource')"
                  filterable
                  :disabled="!canWrite || optionLoading || creating"
                />
              </FormField>
            </fieldset>
            <fieldset class="integration-form-group">
              <legend>{{ t('tasks.mode') }}</legend>
              <FormField :label="t('tasks.namespace')" path="namespace">
                <UiInput
                  v-model:value="namespace"
                  :disabled="!canWrite || optionLoading || creating"
                />
              </FormField>
              <FormField :label="t('tasks.runAfter')" path="runAfter" :help="t('tasks.runNow')">
                <UiDatePicker
                  v-model:value="runAfter"
                  :disabled="!canWrite || optionLoading || creating"
                  type="datetime"
                  clearable
                  class="date-input"
                  :placeholder="t('tasks.runNow')"
                />
              </FormField>
              <FormField :label="t('tasks.mode')" path="incremental">
                <UiCheckbox
                  v-model:checked="incremental"
                  :disabled="!canWrite || optionLoading || creating"
                >
                  {{ t('tasks.incremental') }}
                </UiCheckbox>
              </FormField>
            </fieldset>
          </FormContainer>
        </UiSpin>
        <template #footer>
          <div class="form-actions">
            <UiButton :disabled="creating" @click="createVisible = false">{{
              t('common.cancel')
            }}</UiButton>
            <UiButton
              type="primary"
              :disabled="!canCreate"
              :loading="creating || validating"
              @click="createTask"
            >
              {{ t('tasks.create') }}
            </UiButton>
          </div>
        </template>
      </UiDrawerContent>
    </UiDrawer>
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
  gap: var(--space-2);
}
.date-input {
  width: 100%;
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
