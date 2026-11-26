<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { Clause, ClauseBrief, ClauseInput } from '@/api/clauses'
import { clausesApi } from '@/api/clauses'
import { getSessionGeneration, subscribeTokens } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  SearchPanel,
  SearchTable,
  UiAlert,
  UiButton,
  UiDrawer,
  UiDrawerContent,
  UiInput,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAssetAccess } from '@/composables/useAssetAccess'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

import GovernanceIdentity from '../components/GovernanceIdentity.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const { canWrite } = useAssetAccess()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const items = ref<ClauseBrief[]>([])
const total = ref(0)
const page = ref(Math.max(1, Number(route.query.page) || 1))
const search = ref(typeof route.query.q === 'string' ? route.query.q : '')
const query = ref(search.value)
const initialized = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const showEditor = ref(false)
const saved = ref<Clause | null>(null)
const form = ref<ClauseInput>(emptyClause())
let readController: AbortController | undefined
let alive = true
let editorGeneration = 0
const editorController = new AbortController()
const listSession = ref(getSessionGeneration())
const stopListSession = subscribeTokens(() => {
  listSession.value = getSessionGeneration()
})
const listIdentity = computed(() =>
  JSON.stringify([listSession.value, auth.user?.id, auth.user?.role, auth.user?.status]),
)
const listQuery = computed(() => ({ page: page.value, page_size: 20, q: search.value }))
const listKey = computed(() => JSON.stringify([listIdentity.value, listQuery.value]))
// A snapshot belongs to the submitted query and actor, not the search input draft.
watch(
  listKey,
  () => {
    readController?.abort()
    items.value = []
    total.value = 0
    error.value = ''
    loading.value = false
  },
  { flush: 'sync' },
)
const editorVisible = useDraftGuard(
  showEditor,
  () =>
    JSON.stringify(form.value) !==
    JSON.stringify(saved.value ? payload(saved.value) : emptyClause()),
  () => true,
)

/** 附录性质是枚举码，标签走 i18n，不直出英文。 */
const natureOptions = computed(() => [
  { label: t('clauses.nature.NORMATIVE'), value: 'NORMATIVE' },
  { label: t('clauses.nature.INFORMATIVE'), value: 'INFORMATIVE' },
])

function emptyClause(): ClauseInput {
  return {
    standard: '',
    clause_number: '',
    title_i18n: { 'zh-CN': '', 'en-US': '' },
    self_authored_description: { 'zh-CN': '', 'en-US': '' },
    product_fallback: '',
    appendix_nature: 'NORMATIVE',
    date_lexicon: '',
    clause_disambiguation: '',
    example_domain: '',
  }
}

function payload(c: Clause): ClauseInput {
  return {
    standard: c.standard,
    clause_number: c.clause_number,
    title_i18n: { ...c.title_i18n },
    self_authored_description: { ...c.self_authored_description },
    product_fallback: c.product_fallback ?? '',
    appendix_nature: c.appendix_nature as ClauseInput['appendix_nature'],
    date_lexicon: c.date_lexicon ?? '',
    clause_disambiguation: c.clause_disambiguation ?? '',
    example_domain: c.example_domain ?? '',
  }
}

function failText(err: unknown): string {
  const e = err as { message?: string; code?: string }
  if (!e) return t('clauses.failed', { reason: '' })
  if (e.code === 'KG.ALREADY_EXISTS') return t('clauses.duplicate')
  if (e.code === 'KG.REVISION_CONFLICT') return t('clauses.conflict')
  // 其余错误按 code 走统一 i18n 码表，不直出后端英文 message
  return toMessage(err)
}

async function load() {
  if (!alive) return
  readController?.abort()
  const controller = new AbortController()
  readController = controller
  const key = listKey.value
  const session = getSessionGeneration()
  const owns = () =>
    alive &&
    !controller.signal.aborted &&
    key === listKey.value &&
    session === getSessionGeneration()
  loading.value = true
  error.value = ''
  try {
    const data = await clausesApi.list(listQuery.value, controller.signal)
    if (!owns()) return
    items.value = data.items
    total.value = data.total
  } catch (err) {
    if (!owns()) return
    error.value = failText(err)
  } finally {
    if (owns()) {
      initialized.value = true
      loading.value = false
    }
  }
}

function openCreate() {
  if (!canWrite.value || busy.value) return
  saved.value = null
  form.value = emptyClause()
  error.value = ''
  notice.value = ''
  showEditor.value = true
}

async function openEdit(c: ClauseBrief) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  const owner = editorGeneration
  try {
    const detail = await clausesApi.get(c.id, editorController.signal)
    if (!alive || owner !== editorGeneration) return
    saved.value = detail
    form.value = payload(detail)
    showEditor.value = true
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = failText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

async function submit() {
  if (!canWrite.value || busy.value) return
  const owner = editorGeneration
  const draft = form.value
  const snapshot = JSON.stringify(draft)
  const previous = saved.value
  busy.value = true
  // 必填约束在界面上先拦一层，避免只收到通用请求错误。
  // 不再空表单直发、靠后端 422 兜底
  try {
    await formRef.value?.validate()
  } catch {
    if (owner === editorGeneration) busy.value = false
    return
  }
  if (
    !canWrite.value ||
    !alive ||
    owner !== editorGeneration ||
    form.value !== draft ||
    JSON.stringify(form.value) !== snapshot ||
    !canSave.value
  ) {
    if (owner === editorGeneration) busy.value = false
    return
  }
  error.value = ''
  notice.value = ''
  try {
    if (previous) {
      const rest = JSON.parse(snapshot) as ClauseInput
      delete (rest as Partial<ClauseInput>).standard
      delete (rest as Partial<ClauseInput>).clause_number
      const updated = await clausesApi.update(previous, rest)
      if (
        !alive ||
        owner !== editorGeneration ||
        form.value !== draft ||
        JSON.stringify(form.value) !== snapshot
      )
        return
      saved.value = updated
      form.value = payload(updated)
      notice.value = t('clauses.saved')
      await load()
    } else {
      const created = await clausesApi.create(JSON.parse(snapshot) as ClauseInput)
      if (
        !alive ||
        owner !== editorGeneration ||
        form.value !== draft ||
        JSON.stringify(form.value) !== snapshot
      )
        return
      saved.value = created
      form.value = payload(created)
      notice.value = t('clauses.saved')
      await load()
    }
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = failText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

const formRef = ref<FormInst | null>(null)
// 必填约束与后端一致：标准号、条款号、中文标题和自撰说明为空直接提示，
// 字段路径与共享 Field 的点路径读取契约一致。
const rules = computed<FormRules>(() => ({
  'self_authored_description.zh-CN': {
    required: true,
    message: t('common.required'),
    trigger: ['blur', 'input'],
  },
  standard: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  clause_number: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  'title_i18n.zh-CN': {
    required: true,
    message: t('common.required'),
    trigger: ['blur', 'input'],
  },
}))
const canSave = computed(() =>
  Boolean(
    form.value.standard.trim() &&
    form.value.clause_number.trim() &&
    form.value.title_i18n['zh-CN']?.trim() &&
    form.value.self_authored_description['zh-CN']?.trim(),
  ),
)
watch(
  [showEditor, canWrite],
  () => {
    editorGeneration++
    busy.value = false
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)

async function remove(c: ClauseBrief) {
  if (!canWrite.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  const owner = editorGeneration
  try {
    await clausesApi.remove(c)
    if (!alive || owner !== editorGeneration) return
    notice.value = t('clauses.deleted')
    await load()
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = failText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

watch(page, load, { immediate: true })
watch(listIdentity, () => {
  if (auth.user) void load()
})
watch(search, () => {
  if (page.value === 1) void load()
  else page.value = 1
})
watch([page, search], () => {
  void router.replace({
    query: {
      ...route.query,
      q: search.value || undefined,
      page: page.value > 1 ? page.value : undefined,
    },
  })
})

function doSearch(value = query.value) {
  query.value = value
  const next = value.trim()
  if (search.value === next) {
    if (page.value === 1) void load()
    else page.value = 1
  } else search.value = next
}
function clearSearch() {
  doSearch('')
}

onBeforeUnmount(() => {
  alive = false
  stopListSession()
  readController?.abort()
  editorController.abort()
})

const columns = computed(() => [
  {
    title: t('clauses.standard'),
    key: 'standard',
    minWidth: 220,
    render: (row: ClauseBrief) =>
      h('div', { class: 'governance-object' }, [
        h('strong', row.standard),
        h('code', row.clause_number),
      ]),
  },
  {
    title: t('clauses.title'),
    key: 'title',
    minWidth: 240,
    render: (row: ClauseBrief) =>
      row.title_i18n[locale.value]?.trim() || t('enumDictionaries.untranslated'),
  },
  {
    title: t('clauses.natureLabel'),
    key: 'appendix_nature',
    width: 120,
    render: (row: ClauseBrief) =>
      row.appendix_nature === 'NORMATIVE' ? t('clauses.normative') : t('clauses.informative'),
  },
  {
    title: t('clauses.productFallback'),
    key: 'product_fallback',
    width: 200,
    render: (row: ClauseBrief) => row.product_fallback ?? '',
  },
  {
    title: t('common.actions'),
    key: 'actions',
    fixed: 'right' as const,
    width: 160,
    render: (row: ClauseBrief) =>
      h('div', { style: 'display:flex;gap:8px' }, [
        h(UiButton, { size: 'small', disabled: busy.value, onClick: () => openEdit(row) }, () =>
          t(canWrite.value ? 'common.edit' : 'governanceUi.details'),
        ),
        h(
          UiPopconfirm,
          { disabled: busy.value || !canWrite.value, onPositiveClick: () => remove(row) },
          {
            trigger: () =>
              h(
                UiButton,
                { size: 'small', type: 'error', disabled: busy.value || !canWrite.value },
                () => t('common.delete'),
              ),
            default: () => t('clauses.deleteConfirm'),
          },
        ),
      ]),
  },
])
</script>

<template>
  <div class="clauses-page governance-page">
    <PageHeader :title="t('page.governanceClauses')" :description="t('clauses.intro')">
      <template #actions>
        <UiButton type="primary" :disabled="busy || !canWrite" @click="openCreate">{{
          t('clauses.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert>
    <UiAlert v-if="notice && !showEditor" type="success" role="status">{{ notice }}</UiAlert>
    <section class="governance-ledger">
      <header class="governance-caption">
        <h2>{{ t('governanceUi.clauseIdentity') }}</h2>
        <span v-if="loading">{{ t('common.loading') }}</span>
        <span v-else-if="!error">{{ t('governanceLedger.resultCount', { count: total }) }}</span>
      </header>
      <SearchPanel
        v-model:query="query"
        class="toolbar"
        :loading="loading"
        :placeholder="t('clauses.searchPlaceholder')"
        @submit="doSearch"
        @clear="clearSearch"
        @reset="clearSearch"
      />
      <SearchTable
        v-model:page="page"
        :columns="columns"
        :rows="items"
        :loading="loading"
        :initialized="initialized"
        :error="!showEditor ? error : ''"
        :searchable="false"
        mode="remote"
        :total="total"
        :page-size="20"
        :pagination="true"
        :row-key="(row: ClauseBrief) => row.id"
        :scroll-x="1000"
        size="small"
        :empty-text="t(search ? 'ui.emptyFiltered' : 'clauses.empty')"
        @retry="load"
      >
        <template #toolbar><span /></template>
      </SearchTable>
    </section>

    <UiDrawer
      v-model:show="editorVisible"
      width="min(760px, 100vw)"
      :mask-closable="!busy"
      :close-on-esc="!busy"
    >
      <UiDrawerContent
        class="governance-editor"
        :title="saved ? t('clauses.edit') : t('clauses.create')"
        :closable="!busy"
      >
        <div class="editor-identity">
          <GovernanceIdentity
            :name="`${form.standard} · ${form.clause_number}`"
            name-key="common.displayName"
            :revision="saved?.revision"
          />
        </div>
        <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.readOnly') }}</UiAlert>
        <FormContainer
          id="governance-clause-form"
          ref="formRef"
          :model="form"
          :rules="rules"
          :submitting="busy"
          :disabled="busy || !canWrite"
          label-placement="top"
          @submit="submit"
        >
          <fieldset class="form-section">
            <legend>{{ t('governanceUi.clauseIdentity') }}</legend>
            <div class="form-grid">
              <FormField :label="t('clauses.standard')" path="standard">
                <UiInput
                  v-model:value="form.standard"
                  :disabled="!!saved || busy || !canWrite"
                  :placeholder="t('clauses.standardPlaceholder')"
                />
              </FormField>
              <FormField :label="t('clauses.clauseNumber')" path="clause_number">
                <UiInput
                  v-model:value="form.clause_number"
                  :disabled="!!saved || busy || !canWrite"
                  :placeholder="t('clauses.clauseNumberPlaceholder')"
                />
              </FormField>
            </div>
            <FormField :label="t('clauses.natureLabel')">
              <UiSelect v-model:value="form.appendix_nature" :options="natureOptions" />
            </FormField>
          </fieldset>
          <fieldset class="form-section">
            <legend>{{ t('governanceUi.clauseMeaning') }}</legend>
            <FormField :label="t('clauses.title') + ' (zh-CN)'" path="title_i18n.zh-CN">
              <UiInput v-model:value="form.title_i18n['zh-CN']" />
            </FormField>
            <FormField :label="t('clauses.title') + ' (en-US)'">
              <UiInput v-model:value="form.title_i18n['en-US']" />
            </FormField>
            <FormField
              :label="t('clauses.description') + ' (zh-CN)'"
              path="self_authored_description.zh-CN"
            >
              <UiInput
                v-model:value="form.self_authored_description['zh-CN']"
                type="textarea"
                :rows="3"
              />
            </FormField>
            <FormField :label="t('clauses.description') + ' (en-US)'">
              <UiInput
                v-model:value="form.self_authored_description['en-US']"
                type="textarea"
                :rows="3"
              />
            </FormField>
          </fieldset>
          <details class="terminology">
            <summary>{{ t('governanceUi.clauseTerminology') }}</summary>
            <p>{{ t('governanceUi.clauseTerminologyHint') }}</p>
            <FormField :label="t('clauses.productFallback')">
              <UiInput v-model:value="form.product_fallback" />
            </FormField>
            <FormField :label="t('clauses.dateLexicon')">
              <UiInput v-model:value="form.date_lexicon" />
            </FormField>
            <FormField :label="t('clauses.disambiguation')">
              <UiInput v-model:value="form.clause_disambiguation" type="textarea" :rows="2" />
            </FormField>
            <FormField :label="t('clauses.exampleDomain')">
              <UiInput v-model:value="form.example_domain" />
            </FormField>
          </details>
        </FormContainer>
        <UiSpace v-if="notice" role="status" align="center">
          <UiTag type="success">{{ notice }}</UiTag>
        </UiSpace>
        <UiSpace v-if="error" role="alert" align="center">
          <UiTag type="error">{{ error }}</UiTag>
        </UiSpace>
        <template #footer>
          <UiSpace>
            <UiButton
              :loading="busy"
              :disabled="busy || !canWrite"
              type="primary"
              attr-type="submit"
              form="governance-clause-form"
              >{{ t('common.save') }}</UiButton
            >
            <UiButton :disabled="busy" @click="editorVisible = false">{{
              t('common.cancel')
            }}</UiButton>
          </UiSpace>
        </template>
      </UiDrawerContent>
    </UiDrawer>
  </div>
</template>

<style scoped>
.clauses-page {
  display: grid;
  gap: var(--space-4);
}
.clauses-page .toolbar {
  margin-bottom: 16px;
}
.clauses-page :deep(.ui-card),
.terminology {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
}
.section-title {
  font-size: 15px;
  border-left: 3px solid var(--pri);
  padding-left: 12px;
  margin: 20px 0 16px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.terminology {
  padding: 16px;
}
.terminology summary {
  cursor: pointer;
  font-weight: 600;
}
.terminology p {
  color: var(--text-secondary);
}
.terminology summary:focus-visible {
  outline: 2px solid var(--pri);
  outline-offset: 4px;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style scoped src="../styles/observatory.css"></style>
