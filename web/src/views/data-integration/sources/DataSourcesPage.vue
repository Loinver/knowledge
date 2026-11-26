<script setup lang="ts">
import '../integration.css'

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { DatasourceBrief, TestConnectionResponse } from '@/api/datasources'
import { datasourcesApi } from '@/api/datasources'
import SearchPanel from '@/components/business/SearchPanel.vue'
import SearchTable from '@/components/business/SearchTable.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  RowActions,
  UiAlert,
  UiButton,
  UiInput,
  UiInputNumber,
  UiModal,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiTag,
  useMessage,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

import { connectionInput, createInput, editInput, emptySourceForm, sourceRules } from './sourceForm'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const message = useMessage()
const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const items = ref<DatasourceBrief[]>([])
const query = ref('')
const appliedQuery = ref('')
const kindFilter = ref<string | null>(null)
const statusFilter = ref<string | null>(null)
const page = ref(1)
const loading = ref(true)
const listError = ref('')
let controller: AbortController | undefined
let testController: AbortController | undefined
let alive = true

const showCreate = ref(false)
const createSession = ref(0)
const createVersion = ref(0)
const saving = ref(false)
const testing = ref(false)
const testError = ref('')
const testResult = ref<TestConnectionResponse | null>(null)
const form = ref(emptySourceForm())
const formRef = ref<FormInst | null>(null)
const createOwner = () => [
  showCreate.value,
  createSession.value,
  createVersion.value,
  canWrite.value,
]
const createMutation = useOwnedMutation(createOwner, toMessage)
const createBusy = createMutation.busy
const formError = computed(() => createMutation.error.value || testError.value)
watch(form, () => createVersion.value++, { deep: true, flush: 'sync' })
watch(createOwner, () => (saving.value = false), { flush: 'sync' })

const showEdit = ref(false)
const editSession = ref(0)
const editVersion = ref(0)
const savingEdit = ref(false)
const editingId = ref<number | null>(null)
const editForm = ref({ name: '', credential: '' })
const editFormRef = ref<FormInst | null>(null)
const editOwner = () => [
  showEdit.value,
  editSession.value,
  editingId.value,
  editVersion.value,
  canWrite.value,
]
const editMutation = useOwnedMutation(editOwner, toMessage)
const editBusy = editMutation.busy
const editError = editMutation.error
watch(editForm, () => editVersion.value++, { deep: true, flush: 'sync' })
watch(editOwner, () => (savingEdit.value = false), { flush: 'sync' })

const rowAction = ref<{ id: number; kind: 'test' | 'delete' } | null>(null)
const rowMutation = useOwnedMutation(
  () => [
    rowAction.value,
    appliedQuery.value,
    kindFilter.value,
    statusFilter.value,
    page.value,
    canWrite.value,
  ],
  toMessage,
)
// The API may still finish after its UI owner is gone. Keep the physical same-ID lock
// until it settles, so an old stored test cannot race a credential update in this page.
const pendingRows = reactive(new Set<number>())
const rowBusy = rowMutation.busy
const testingId = computed(() =>
  rowBusy.value && rowAction.value?.kind === 'test' ? rowAction.value.id : null,
)
const deletingId = computed(() =>
  rowBusy.value && rowAction.value?.kind === 'delete' ? rowAction.value.id : null,
)
const error = computed(() => listError.value || rowMutation.error.value)

const kindOptions = [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'MySQL', value: 'mysql' },
  { label: 'PostgreSQL', value: 'postgresql' },
]
const statusOptions = computed(() => [
  { label: t('dataAccess.sources.status.connected'), value: 'CONNECTED' },
  { label: t('dataAccess.sources.status.disconnected'), value: 'DISCONNECTED' },
])
const network = computed(() => form.value.kind !== 'sqlite')
const rules = computed(() =>
  sourceRules(network.value, {
    name: t('dataAccess.sources.validation.name'),
    connection: t('dataAccess.sources.validation.connection'),
    required: t('common.required'),
  }),
)
const editRules = computed<FormRules>(() => ({
  name: {
    required: true,
    message: t('dataAccess.sources.validation.name'),
    trigger: ['input', 'blur'],
  },
}))
const visible = computed(() =>
  items.value.filter(
    (item) =>
      (!kindFilter.value || item.kind === kindFilter.value) &&
      (!statusFilter.value || item.status === statusFilter.value),
  ),
)
watch([kindFilter, statusFilter], () => (page.value = 1), { flush: 'sync' })
const connectedCount = computed(
  () => items.value.filter((item) => item.status === 'CONNECTED').length,
)
const numbers = computed(() => new Intl.NumberFormat(locale.value))
const columns = computed<DataTableColumns<DatasourceBrief>>(() => [
  { key: 'name', title: t('dataAccess.sources.fields.name'), minWidth: 160 },
  { key: 'kind', title: t('dataAccess.sources.fields.kind'), minWidth: 100 },
  { key: 'connection', title: t('graph.source'), minWidth: 140 },
  { key: 'status', title: t('common.status'), minWidth: 120 },
  { key: 'actions', title: t('common.actions'), minWidth: 300, fixed: 'right' },
])
const testFeedback = computed(() => {
  if (!testResult.value) return ''
  if (!testResult.value.ok) return t('dataAccess.sources.connection.failed')
  const count = testResult.value.table_count
  return count == null
    ? `${t('dataAccess.sources.states.testOk')} · ${t('common.noneValue')}`
    : t('dataAccess.sources.testTables', { count: numbers.value.format(count) })
})

function displayKind(kind: string) {
  return kindOptions.find((item) => item.value === kind)?.label ?? kind
}
function connectionLabel(item: DatasourceBrief) {
  return item.kind === 'sqlite'
    ? t('dataAccess.sources.connection.sqlite')
    : t('dataAccess.sources.connection.network', { kind: displayKind(item.kind) })
}
function connectionRequest() {
  return connectionInput(form.value)
}
function invalidateConnectionTest() {
  testController?.abort()
  testController = undefined
  testing.value = false
  testResult.value = null
  testError.value = ''
}
// Invalidate synchronously, including A → B → A edits in the same update.
watch(connectionRequest, invalidateConnectionTest, { flush: 'sync' })
watch(showCreate, invalidateConnectionTest, { flush: 'sync' })

function openCreate() {
  if (!canWrite.value) return
  createSession.value++
  form.value = emptySourceForm()
  invalidateConnectionTest()
  showCreate.value = true
}
function rowLocked(id: number) {
  return pendingRows.has(id) || (editBusy.value && editingId.value === id)
}
function openEdit(item: DatasourceBrief) {
  if (!canWrite.value || rowLocked(item.id)) return
  editSession.value++
  editingId.value = item.id
  editForm.value = { name: item.name, credential: '' }
  showEdit.value = true
}

async function load() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  listError.value = ''
  rowMutation.invalidate()
  try {
    const next = await datasourcesApi.list({ q: appliedQuery.value || undefined }, current.signal)
    if (alive && controller === current) items.value = next
  } catch (err) {
    if (alive && controller === current) listError.value = toMessage(err)
  } finally {
    if (alive && controller === current) loading.value = false
  }
}
function search(value = query.value) {
  const next = value.trim()
  if (next !== appliedQuery.value) items.value = []
  appliedQuery.value = next
  page.value = 1
  return load()
}
function resetSearch() {
  query.value = ''
  kindFilter.value = null
  statusFilter.value = null
  return search('')
}

async function testConnection() {
  if (!showCreate.value || testing.value || createBusy.value || !formRef.value) return
  createMutation.invalidate()
  const validator = formRef.value
  const payload = connectionRequest()
  const version = createVersion.value
  const current = new AbortController()
  testController = current
  const isCurrent = () => alive && showCreate.value && testController === current
  testing.value = true
  testResult.value = null
  testError.value = ''
  try {
    try {
      await validator.validate()
    } catch {
      return
    }
    if (!isCurrent() || version !== createVersion.value) return
    const result = await datasourcesApi.testConnection(payload, current.signal)
    if (isCurrent()) testResult.value = result
  } catch (err) {
    if (isCurrent()) testError.value = toMessage(err)
  } finally {
    if (isCurrent()) {
      testController = undefined
      testing.value = false
    }
  }
}

async function createSource() {
  if (!canWrite.value || !showCreate.value || createBusy.value || testing.value || !formRef.value)
    return
  testError.value = ''
  const validator = formRef.value
  const payload = createInput(form.value)
  const result = await createMutation.run(async (signal) => {
    try {
      await validator.validate()
    } catch {
      return
    }
    if (signal.aborted || !alive || !canWrite.value) return
    saving.value = true
    try {
      await datasourcesApi.create(payload)
      return signal
    } finally {
      if (!signal.aborted) saving.value = false
    }
  })
  if (!result || result.aborted || !alive) return
  showCreate.value = false
  message.success(t('dataAccess.sources.states.created'))
  await load()
}

async function saveEdit() {
  if (
    !canWrite.value ||
    !showEdit.value ||
    editBusy.value ||
    editingId.value === null ||
    !editFormRef.value
  )
    return
  const id = editingId.value
  if (pendingRows.has(id)) return
  const validator = editFormRef.value
  const payload = editInput(editForm.value)
  const result = await editMutation.run(async (signal) => {
    try {
      await validator.validate()
    } catch {
      return
    }
    if (signal.aborted || !alive || !canWrite.value || pendingRows.has(id)) return
    savingEdit.value = true
    pendingRows.add(id)
    try {
      await datasourcesApi.update(id, payload)
      return signal
    } finally {
      pendingRows.delete(id)
      if (!signal.aborted) savingEdit.value = false
    }
  })
  if (!result || result.aborted || !alive) return
  showEdit.value = false
  message.success(t('dataAccess.sources.states.updated'))
  await load()
}

async function removeSource(item: DatasourceBrief) {
  if (!canWrite.value || rowBusy.value || rowLocked(item.id)) return false
  const id = item.id
  rowAction.value = { id, kind: 'delete' }
  const result = await rowMutation.run(async (signal) => {
    pendingRows.add(id)
    try {
      await datasourcesApi.remove(id)
      return signal
    } finally {
      pendingRows.delete(id)
    }
  })
  if (!result || result.aborted || !alive) return false
  message.success(t('dataAccess.sources.states.deleted'))
  await load()
  return true
}

/** Stored tests persist status, unlike the temporary read-only connection test. */
async function testStored(item: DatasourceBrief) {
  if (!canWrite.value || rowBusy.value || rowLocked(item.id)) return
  const id = item.id
  rowAction.value = { id, kind: 'test' }
  const result = await rowMutation.run(async (signal) => {
    pendingRows.add(id)
    try {
      return { value: await datasourcesApi.testStored(id), signal }
    } finally {
      pendingRows.delete(id)
    }
  })
  if (!result || result.signal.aborted || !alive) return
  if (result.value.ok) message.success(t('dataAccess.sources.states.testOk'))
  else message.warning(t('dataAccess.sources.states.testFailed'))
  await load()
}

onMounted(() => void load())
onBeforeUnmount(() => {
  alive = false
  controller?.abort()
  invalidateConnectionTest()
})
const createVisible = useDraftGuard(
  showCreate,
  () => form.value,
  () => true,
  () => createSession.value,
)
const editVisible = useDraftGuard(
  showEdit,
  () => editForm.value,
  () => true,
  () => editSession.value,
)
</script>

<template>
  <section class="integration-page sources-page">
    <PageHeader
      :title="t('dataAccess.sources.title')"
      :description="t('dataAccess.sources.description')"
    >
      <template #actions>
        <UiButton type="primary" :disabled="!canWrite" @click="openCreate">{{
          t('dataAccess.sources.actions.create')
        }}</UiButton>
      </template>
    </PageHeader>

    <section class="source-management integration-run-ledger">
      <dl class="integration-readings" :aria-label="t('dataAccess.sources.listTitle')">
        <div>
          <dt>{{ t('dataAccess.sources.stats.total') }}</dt>
          <dd>{{ loading || error ? t('common.noneValue') : numbers.format(items.length) }}</dd>
        </div>
        <div>
          <dt>{{ t('dataAccess.sources.stats.connected') }}</dt>
          <dd class="ok">
            {{ loading || error ? t('common.noneValue') : numbers.format(connectedCount) }}
          </dd>
        </div>
        <div>
          <dt>{{ t('dataAccess.sources.stats.failed') }}</dt>
          <dd class="bad">
            {{
              loading || error
                ? t('common.noneValue')
                : numbers.format(items.length - connectedCount)
            }}
          </dd>
        </div>
      </dl>

      <UiAlert v-if="!canWrite" type="info">{{ t('ui.readonly') }}</UiAlert>
      <SearchPanel
        v-model:query="query"
        :loading="loading"
        :label="t('dataAccess.sources.search')"
        :placeholder="t('dataAccess.sources.search')"
        @submit="search"
        @clear="resetSearch"
        @reset="resetSearch"
      >
        <template #filters>
          <UiSelect
            v-model:value="kindFilter"
            clearable
            :options="kindOptions"
            :placeholder="t('dataAccess.sources.filters.kind')"
            :aria-label="t('dataAccess.sources.filters.kind')"
          />
          <UiSelect
            v-model:value="statusFilter"
            clearable
            :options="statusOptions"
            :placeholder="t('dataAccess.sources.filters.status')"
            :aria-label="t('dataAccess.sources.filters.status')"
          />
        </template>
      </SearchPanel>
      <SearchTable
        v-model:page="page"
        :rows="visible"
        :columns="columns"
        row-key="id"
        mode="local"
        :page-size="20"
        :searchable="false"
        :loading="loading"
        :error="error"
        :label="t('dataAccess.sources.listTitle')"
        :empty-text="
          appliedQuery || kindFilter || statusFilter
            ? t('dataAccess.sources.states.noMatch')
            : t('dataAccess.sources.states.empty')
        "
        @retry="load"
      >
        <template #cell-name="{ row }">
          <div class="source-name">
            <RouterLink :to="{ name: 'data-catalog', query: { datasourceId: row.id } }">
              <strong>{{ row.name }}</strong>
            </RouterLink>
            <small>{{ row.id }}</small>
          </div>
        </template>
        <template #cell-kind="{ row }"
          ><UiTag size="small">{{ displayKind(row.kind) }}</UiTag></template
        >
        <template #cell-connection="{ row }"
          ><span>{{ connectionLabel(row) }}</span></template
        >
        <template #cell-status="{ row }">
          <UiTag size="small" :type="row.status === 'CONNECTED' ? 'success' : 'warning'">
            {{
              row.status === 'CONNECTED'
                ? t('dataAccess.sources.status.connected')
                : t('dataAccess.sources.status.disconnected')
            }}
          </UiTag>
        </template>
        <template #cell-actions="{ row }">
          <RowActions :row="row">
            <RouterLink :to="{ name: 'data-catalog', query: { datasourceId: row.id } }">
              <UiButton size="small" type="primary" secondary>{{ t('page.dataCatalog') }}</UiButton>
            </RouterLink>
            <UiPopconfirm v-if="canWrite" @positive-click="removeSource(row)">
              <template #trigger>
                <UiButton
                  quaternary
                  type="error"
                  size="small"
                  :loading="deletingId === row.id"
                  :disabled="rowBusy || rowLocked(row.id)"
                >
                  {{ t('dataAccess.sources.actions.delete') }}
                </UiButton>
              </template>
              {{ t('dataAccess.sources.deleteConfirm', { name: row.name }) }}
            </UiPopconfirm>
            <UiButton
              size="small"
              :loading="testingId === row.id"
              :disabled="!canWrite || rowBusy || rowLocked(row.id)"
              @click="testStored(row)"
            >
              {{ t('dataAccess.sources.actions.testStored') }}
            </UiButton>
            <UiButton
              size="small"
              :disabled="!canWrite || rowLocked(row.id)"
              @click="openEdit(row)"
            >
              {{ t('dataAccess.sources.actions.edit') }}
            </UiButton>
          </RowActions>
        </template>
      </SearchTable>
      <p class="integration-caption ledger-note">{{ t('dataAccess.sources.security') }}</p>
    </section>

    <UiModal
      v-model:show="editVisible"
      preset="card"
      class="source-modal"
      style="width: min(640px, calc(100vw - 32px))"
      :title="t('dataAccess.sources.editTitle')"
      :closable="!savingEdit"
      :mask-closable="!savingEdit"
      :close-on-esc="!savingEdit"
    >
      <FormContainer
        id="datasource-edit-form"
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        :disabled="savingEdit"
        :readonly="!canWrite"
        :submitting="savingEdit"
        label-placement="top"
        class="integration-grouped-form"
        @submit="saveEdit"
      >
        <FormField path="name" :label="t('dataAccess.sources.fields.name')" required
          ><UiInput
            v-model:value="editForm.name"
            :input-props="{ 'aria-label': t('dataAccess.sources.fields.name') }"
        /></FormField>
        <FormField path="credential" :label="t('dataAccess.sources.fields.credential')"
          ><UiInput
            v-model:value="editForm.credential"
            type="password"
            show-password-on="click"
            :placeholder="t('dataAccess.sources.fields.credentialKeep')"
            :input-props="{ 'aria-label': t('dataAccess.sources.fields.credential') }"
        /></FormField>
      </FormContainer>
      <UiAlert :show-icon="false">{{ t('dataAccess.sources.securityHint') }}</UiAlert>
      <UiAlert v-if="editError" type="error">{{ editError }}</UiAlert>
      <template #footer>
        <UiSpace>
          <UiButton
            type="primary"
            attr-type="submit"
            form="datasource-edit-form"
            :loading="editBusy"
            :disabled="!canWrite || (editingId !== null && pendingRows.has(editingId))"
            @click.prevent="saveEdit"
            >{{ t('common.save') }}</UiButton
          >
          <UiButton :disabled="savingEdit" @click="editVisible = false">{{
            t('common.cancel')
          }}</UiButton>
        </UiSpace>
      </template>
    </UiModal>

    <UiModal
      v-model:show="createVisible"
      preset="card"
      class="source-modal"
      style="width: min(640px, calc(100vw - 32px))"
      :title="t('dataAccess.sources.createTitle')"
      :closable="!saving"
      :mask-closable="!saving"
      :close-on-esc="!saving"
    >
      <FormContainer
        ref="formRef"
        :model="form"
        :rules="rules"
        :disabled="saving"
        :readonly="!canWrite"
        :submitting="saving"
        label-placement="top"
        class="integration-grouped-form"
        @submit="createSource"
      >
        <fieldset class="integration-form-group">
          <legend>{{ t('dataAccess.sources.fields.name') }}</legend>
          <FormField path="name" :label="t('dataAccess.sources.fields.name')" required
            ><UiInput
              v-model:value="form.name"
              :input-props="{ 'aria-label': t('dataAccess.sources.fields.name') }"
          /></FormField>
          <FormField path="kind" :label="t('dataAccess.sources.fields.kind')" required
            ><UiSelect
              v-model:value="form.kind"
              :aria-label="t('dataAccess.sources.fields.kind')"
              :options="kindOptions"
          /></FormField>
        </fieldset>
        <fieldset class="integration-form-group">
          <legend>{{ t('graph.source') }}</legend>
          <div class="form-grid">
            <FormField
              v-if="network"
              path="host"
              :label="t('dataAccess.sources.fields.host')"
              required
              ><UiInput
                v-model:value="form.host"
                :input-props="{ 'aria-label': t('dataAccess.sources.fields.host') }"
            /></FormField>
            <FormField v-if="network" path="port" :label="t('dataAccess.sources.fields.port')"
              ><UiInputNumber
                v-model:value="form.port"
                :input-props="{ 'aria-label': t('dataAccess.sources.fields.port') }"
                class="full-width"
                :show-button="false"
            /></FormField>
            <FormField path="database" :label="t('dataAccess.sources.fields.database')" required
              ><UiInput
                v-model:value="form.database"
                :input-props="{ 'aria-label': t('dataAccess.sources.fields.database') }"
            /></FormField>
            <FormField
              v-if="network"
              path="user"
              :label="t('dataAccess.sources.fields.user')"
              required
              ><UiInput
                v-model:value="form.user"
                :input-props="{ 'aria-label': t('dataAccess.sources.fields.user') }"
            /></FormField>
          </div>
          <FormField path="credential" :label="t('dataAccess.sources.fields.credential')">
            <UiInput
              v-model:value="form.credential"
              :input-props="{ 'aria-label': t('dataAccess.sources.fields.credential') }"
              type="password"
              show-password-on="click"
              :placeholder="t('dataAccess.sources.fields.credentialHint')"
            />
          </FormField>
        </fieldset>
        <UiAlert v-if="formError" type="error">{{ formError }}</UiAlert>
        <UiAlert v-if="testResult" :type="testResult.ok ? 'success' : 'warning'">
          {{ testFeedback }}
        </UiAlert>
        <UiSpace justify="end">
          <UiButton :loading="testing" :disabled="createBusy" @click="testConnection">{{
            t('dataAccess.sources.actions.test')
          }}</UiButton>
          <UiButton
            type="primary"
            attr-type="submit"
            :loading="createBusy"
            :disabled="testing || !canWrite"
            @click.prevent="createSource"
            >{{ t('dataAccess.sources.actions.save') }}</UiButton
          >
        </UiSpace>
      </FormContainer>
    </UiModal>
  </section>
</template>

<style scoped>
.sources-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  color: var(--text);
}
.source-name {
  display: flex;
  flex-direction: column;
  overflow-wrap: anywhere;
}
.source-name small {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}
.full-width {
  width: 100%;
}
@media (max-width: 48rem) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
