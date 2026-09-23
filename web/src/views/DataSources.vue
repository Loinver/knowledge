<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DatasourceBrief, DatasourceCreate, TestConnectionResponse } from '@/api/datasources'
import { datasourcesApi } from '@/api/datasources'
import { useApiError } from '@/composables/useApiError'

interface SourceForm {
  name: string
  kind: 'sqlite' | 'mysql' | 'postgresql'
  database: string
  host: string
  port: number | null
  user: string
  credential: string
}

const { t } = useI18n()
const { toMessage } = useApiError()
const message = useMessage()
const items = ref<DatasourceBrief[]>([])
const query = ref('')
const kindFilter = ref<string | null>(null)
const statusFilter = ref<string | null>(null)
const loading = ref(true)
const error = ref('')
const showCreate = ref(false)
const saving = ref(false)
const testing = ref(false)
const formError = ref('')
const testResult = ref<TestConnectionResponse | null>(null)
const form = ref<SourceForm>(emptyForm())
let controller: AbortController | undefined
let alive = true

const kindOptions = computed(() => [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'MySQL', value: 'mysql' },
  { label: 'PostgreSQL', value: 'postgresql' },
])
const statusOptions = computed(() => [
  { label: t('dataAccess.sources.status.connected'), value: 'CONNECTED' },
  { label: t('dataAccess.sources.status.disconnected'), value: 'DISCONNECTED' },
])
const network = computed(() => form.value.kind !== 'sqlite')
const visible = computed(() =>
  items.value.filter((item) => {
    const matchesKind = !kindFilter.value || item.kind === kindFilter.value
    const matchesStatus = !statusFilter.value || item.status === statusFilter.value
    const needle = query.value.trim().toLowerCase()
    return matchesKind && matchesStatus && (!needle || item.name.toLowerCase().includes(needle))
  }),
)
const connectedCount = computed(
  () => items.value.filter((item) => item.status === 'CONNECTED').length,
)

function emptyForm(): SourceForm {
  return { name: '', kind: 'sqlite', database: '', host: '', port: null, user: '', credential: '' }
}

function displayKind(kind: string) {
  return kindOptions.value.find((item) => item.value === kind)?.label ?? kind
}

function connectionLabel(item: DatasourceBrief) {
  return item.kind === 'sqlite'
    ? t('dataAccess.sources.connection.sqlite')
    : t('dataAccess.sources.connection.network', { kind: displayKind(item.kind) })
}

function connectionParams() {
  if (form.value.kind === 'sqlite') return { database: form.value.database.trim() }
  return {
    host: form.value.host.trim(),
    port: form.value.port ?? (form.value.kind === 'mysql' ? 3306 : 5432),
    database: form.value.database.trim(),
    user: form.value.user.trim(),
  }
}

function connectionRequest() {
  return {
    kind: form.value.kind,
    params: connectionParams(),
    ...(form.value.credential ? { credential: form.value.credential } : {}),
  }
}

function resetForm() {
  form.value = emptyForm()
  formError.value = ''
  testResult.value = null
}

function openCreate() {
  resetForm()
  showCreate.value = true
}

function validateForm() {
  if (!form.value.name.trim()) {
    formError.value = t('dataAccess.sources.validation.name')
    return false
  }
  const missingNetwork =
    network.value &&
    (!form.value.host.trim() || !form.value.user.trim() || !form.value.database.trim())
  if (!form.value.database.trim() || missingNetwork) {
    formError.value = t('dataAccess.sources.validation.connection')
    return false
  }
  formError.value = ''
  return true
}

async function load() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  error.value = ''
  try {
    const next = await datasourcesApi.list({ q: query.value.trim() || undefined }, current.signal)
    if (alive && controller === current) items.value = next
  } catch (err) {
    if (alive && controller === current) error.value = toMessage(err)
  } finally {
    if (alive && controller === current) loading.value = false
  }
}

async function testConnection() {
  if (!validateForm()) return
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await datasourcesApi.testConnection(connectionRequest())
  } catch (err) {
    formError.value = toMessage(err)
  } finally {
    testing.value = false
  }
}

async function createSource() {
  if (!validateForm()) return
  saving.value = true
  try {
    const payload: DatasourceCreate = { name: form.value.name.trim(), ...connectionRequest() }
    await datasourcesApi.create(payload)
    showCreate.value = false
    message.success(t('dataAccess.sources.states.created'))
    await load()
  } catch (err) {
    formError.value = toMessage(err)
  } finally {
    saving.value = false
  }
}

async function removeSource(item: DatasourceBrief) {
  try {
    await datasourcesApi.remove(item.id)
    message.success(t('dataAccess.sources.states.deleted'))
    await load()
  } catch (err) {
    error.value = toMessage(err)
  }
}

onMounted(() => void load())
onBeforeUnmount(() => {
  alive = false
  controller?.abort()
})
</script>

<template>
  <section class="sources-page">
    <header class="page-heading">
      <div>
        <div class="breadcrumb">{{ t('dataAccess.sources.breadcrumb') }}</div>
        <h1>{{ t('dataAccess.sources.title') }}</h1>
        <p>{{ t('dataAccess.sources.description') }}</p>
      </div>
      <NButton type="primary" @click="openCreate">{{
        t('dataAccess.sources.actions.create')
      }}</NButton>
    </header>

    <div class="stats-grid">
      <NCard size="small"
        ><strong>{{ items.length }}</strong
        ><span>{{ t('dataAccess.sources.stats.total') }}</span></NCard
      >
      <NCard size="small"
        ><strong class="ok">{{ connectedCount }}</strong
        ><span>{{ t('dataAccess.sources.stats.connected') }}</span></NCard
      >
      <NCard size="small"
        ><strong class="bad">{{ items.length - connectedCount }}</strong
        ><span>{{ t('dataAccess.sources.stats.failed') }}</span></NCard
      >
    </div>

    <NAlert type="info" :show-icon="false">{{ t('dataAccess.sources.security') }}</NAlert>
    <NAlert v-if="error" type="error" closable @close="error = ''">{{ error }}</NAlert>

    <NCard class="list-card" :title="t('dataAccess.sources.listTitle')">
      <template #header-extra>
        <NSpace>
          <NInput
            v-model:value="query"
            clearable
            :placeholder="t('dataAccess.sources.search')"
            @keyup.enter="load"
            @clear="load"
          />
          <NSelect
            v-model:value="kindFilter"
            clearable
            :options="kindOptions"
            :placeholder="t('dataAccess.sources.filters.kind')"
          />
          <NSelect
            v-model:value="statusFilter"
            clearable
            :options="statusOptions"
            :placeholder="t('dataAccess.sources.filters.status')"
          />
        </NSpace>
      </template>
      <NSpin :show="loading">
        <NEmpty
          v-if="!loading && visible.length === 0"
          :description="
            query || kindFilter || statusFilter
              ? t('dataAccess.sources.states.noMatch')
              : t('dataAccess.sources.states.empty')
          "
        />
        <div v-else class="source-list">
          <article v-for="item in visible" :key="item.id" class="source-row">
            <div>
              <strong>{{ item.name }}</strong
              ><small>{{ item.id }}</small>
            </div>
            <NTag size="small">{{ displayKind(item.kind) }}</NTag>
            <code>{{ connectionLabel(item) }}</code>
            <NTag size="small" :type="item.status === 'CONNECTED' ? 'success' : 'warning'">
              {{
                item.status === 'CONNECTED'
                  ? t('dataAccess.sources.status.connected')
                  : t('dataAccess.sources.status.disconnected')
              }}
            </NTag>
            <NPopconfirm @positive-click="removeSource(item)">
              <template #trigger
                ><NButton quaternary type="error" size="small">{{
                  t('dataAccess.sources.actions.delete')
                }}</NButton></template
              >
              {{ t('dataAccess.sources.deleteConfirm', { name: item.name }) }}
            </NPopconfirm>
          </article>
        </div>
      </NSpin>
    </NCard>

    <NModal
      v-model:show="showCreate"
      preset="card"
      class="source-modal"
      :title="t('dataAccess.sources.createTitle')"
      @after-leave="resetForm"
    >
      <NForm label-placement="top">
        <NFormItem :label="t('dataAccess.sources.fields.name')" required
          ><NInput v-model:value="form.name"
        /></NFormItem>
        <NFormItem :label="t('dataAccess.sources.fields.kind')" required
          ><NSelect v-model:value="form.kind" :options="kindOptions"
        /></NFormItem>
        <div class="form-grid">
          <NFormItem v-if="network" :label="t('dataAccess.sources.fields.host')" required
            ><NInput v-model:value="form.host"
          /></NFormItem>
          <NFormItem v-if="network" :label="t('dataAccess.sources.fields.port')"
            ><NInputNumber v-model:value="form.port" class="full-width" :show-button="false"
          /></NFormItem>
          <NFormItem :label="t('dataAccess.sources.fields.database')" required
            ><NInput v-model:value="form.database"
          /></NFormItem>
          <NFormItem v-if="network" :label="t('dataAccess.sources.fields.user')" required
            ><NInput v-model:value="form.user"
          /></NFormItem>
        </div>
        <NFormItem :label="t('dataAccess.sources.fields.credential')">
          <NInput
            v-model:value="form.credential"
            type="password"
            show-password-on="click"
            :placeholder="t('dataAccess.sources.fields.credentialHint')"
          />
        </NFormItem>
        <NAlert v-if="formError" type="error">{{ formError }}</NAlert>
        <NAlert v-if="testResult" :type="testResult.ok ? 'success' : 'warning'">
          {{ testResult.message }}
          <span v-if="testResult.table_count != null">
            · {{ t('dataAccess.sources.testTables', { count: testResult.table_count }) }}
          </span>
        </NAlert>
        <NSpace justify="end">
          <NButton :loading="testing" :disabled="saving" @click="testConnection">{{
            t('dataAccess.sources.actions.test')
          }}</NButton>
          <NButton type="primary" :loading="saving" :disabled="testing" @click="createSource">{{
            t('dataAccess.sources.actions.save')
          }}</NButton>
        </NSpace>
      </NForm>
    </NModal>
  </section>
</template>

<style scoped>
.sources-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  padding: 24px;
  color: var(--text);
}
.page-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
.breadcrumb {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}
.page-heading h1 {
  margin: 4px 0 0;
  font-size: var(--font-h1);
}
.page-heading p,
.source-row small {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.stats-grid strong,
.stats-grid span {
  display: block;
}
.stats-grid strong {
  font-size: 24px;
}
.stats-grid span {
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.ok {
  color: var(--success, #34d399);
}
.bad {
  color: var(--danger, #f87171);
}
.source-list {
  display: grid;
}
.source-row {
  display: grid;
  grid-template-columns: minmax(160px, 1.2fr) 110px minmax(180px, 2fr) 130px auto;
  gap: 12px;
  align-items: center;
  padding: 14px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.source-row div {
  display: flex;
  min-width: 0;
  flex-direction: column;
}
.source-row code {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-modal {
  width: min(640px, calc(100vw - 32px));
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}
.full-width {
  width: 100%;
}
@media (max-width: 800px) {
  .sources-page {
    padding: 16px;
  }
  .page-heading,
  .stats-grid,
  .form-grid,
  .source-row {
    display: grid;
    grid-template-columns: 1fr;
  }
  .source-row code {
    grid-column: 1 / -1;
  }
}
</style>
