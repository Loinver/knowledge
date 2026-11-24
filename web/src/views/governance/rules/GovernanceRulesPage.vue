<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { Rule, RuleInput, RuleTest } from '@/api/governance'
import { rulesApi } from '@/api/governance'
import { getSessionGeneration, subscribeTokens } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import {
  FormContainer,
  FormField,
  SearchPanel,
  SearchTable,
  UiAlert,
  UiButton,
  UiCard,
  UiDrawer,
  UiDrawerContent,
  UiInput,
  UiPopconfirm,
  UiSelect,
  UiSpace,
  UiTabPane,
  UiTabs,
  UiTag,
} from '@/components/ui'
import type { FormInst, FormRules } from '@/components/ui/formTypes'
import { useAssetAccess } from '@/composables/useAssetAccess'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

import GovernanceIdentity from '../components/GovernanceIdentity.vue'

const { t, te, locale } = useI18n()
const { canWrite } = useAssetAccess()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const items = ref<Rule[]>([])
const total = ref(0)
const page = ref(Math.max(1, Number(route.query.page) || 1))
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const search = ref(query.value)
const sourceKind = ref<string | null>(
  ['STANDARD', 'ENTERPRISE'].includes(String(route.query.source))
    ? String(route.query.source)
    : null,
)
const loading = ref(false)
const initialized = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const showEditor = ref(false)
const saved = ref<Rule | null>(null)
const testResult = ref<RuleTest | null>(null)
const tab = ref('metadata')
const form = ref<RuleInput>(emptyRule())
let readController: AbortController | undefined
let alive = true
let testGeneration = 0
let editorGeneration = 0
const listSession = ref(getSessionGeneration())
const stopListSession = subscribeTokens(() => {
  listSession.value = getSessionGeneration()
})
const listIdentity = computed(() =>
  JSON.stringify([listSession.value, auth.user?.id, auth.user?.role, auth.user?.status]),
)
const listQuery = computed(() => ({
  page: page.value,
  page_size: 20,
  q: search.value,
  source_kind: sourceKind.value || undefined,
}))
const listKey = computed(() => JSON.stringify([listIdentity.value, listQuery.value]))
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
const formRef = ref<FormInst | null>(null)
watch(
  [showEditor, canWrite],
  () => {
    editorGeneration++
    testGeneration++
    busy.value = false
    formRef.value?.restoreValidation()
  },
  { flush: 'sync' },
)

watch(
  form,
  () => {
    testGeneration++
    testResult.value = null
  },
  { deep: true, flush: 'sync' },
)

function emptyRule(): RuleInput {
  return {
    identifier: '',
    name_i18n: { 'zh-CN': '', 'en-US': '' },
    category: '',
    source_kind: 'ENTERPRISE',
    source_reference: '',
    target_iri: '',
    severity: 'VIOLATION',
    language: 'SHACL',
    expression: '',
    execution: 'AUTO',
    positive_example: '',
    negative_example: '',
  }
}

function payload(rule: Rule): RuleInput {
  return {
    identifier: rule.identifier,
    name_i18n: { ...rule.name_i18n },
    category: rule.category,
    source_kind: rule.source_kind,
    source_reference: rule.source_reference,
    target_iri: rule.target_iri,
    severity: rule.severity,
    language: rule.language,
    expression: rule.expression,
    execution: rule.execution,
    positive_example: rule.positive_example,
    negative_example: rule.negative_example,
  }
}

const dirty = computed(
  () => !saved.value || JSON.stringify(form.value) !== JSON.stringify(payload(saved.value)),
)
// Saving keeps the editor open for testing; compare with the accepted revision after each save.
const editorVisible = useDraftGuard(
  showEditor,
  () =>
    JSON.stringify(form.value) !== JSON.stringify(saved.value ? payload(saved.value) : emptyRule()),
  () => true,
)
const needsExamples = computed(() => form.value.language === 'SHACL')
const expressionValid = computed(() => {
  if (form.value.language !== 'DATA' && form.value.language !== 'DERIVATION') return true
  try {
    const config = JSON.parse(form.value.expression) as { op?: string }
    const ops =
      form.value.language === 'DATA'
        ? ['acyclic', 'sum_le', 'unique_attr', 'required_edge', 'date_format']
        : ['transitive', 'symmetric', 'co_occurrence', 'product_chain']
    return typeof config === 'object' && config !== null && !!config.op && ops.includes(config.op)
  } catch {
    return false
  }
})
const canSave = computed(
  () =>
    form.value.identifier.trim() &&
    form.value.name_i18n['zh-CN']?.trim() &&
    form.value.category.trim() &&
    form.value.source_reference.trim() &&
    form.value.target_iri.trim() &&
    form.value.expression.trim() &&
    expressionValid.value &&
    (!needsExamples.value ||
      (form.value.positive_example.trim() && form.value.negative_example.trim())),
)
const rules = computed<FormRules>(() => {
  const required = {
    required: true,
    message: t('common.required'),
    trigger: ['input', 'blur', 'change'],
  }
  const result: FormRules = Object.fromEntries(
    [
      'identifier',
      'name_i18n.zh-CN',
      'category',
      'source_reference',
      'target_iri',
      'source_kind',
      'severity',
      'language',
      'execution',
    ].map((path) => [path, required]),
  )
  result.expression = [
    required,
    {
      validator: () => expressionValid.value,
      message: t('rules.invalid', { reason: t('rules.expression') }),
      trigger: ['input', 'blur'],
    },
  ]
  if (needsExamples.value) {
    result.positive_example = required
    result.negative_example = required
  }
  return result
})
function showInvalidTab(errors: Record<string, string>) {
  const first = Object.keys(errors)[0]
  tab.value = ['expression', 'language', 'execution'].includes(first)
    ? 'expression'
    : ['positive_example', 'negative_example'].includes(first)
      ? 'examples'
      : 'metadata'
}
const sourceOptions = computed(() =>
  ['STANDARD', 'ENTERPRISE'].map((value) => ({ value, label: t(`rules.sources.${value}`) })),
)
const severityOptions = computed(() =>
  ['INFO', 'WARNING', 'VIOLATION'].map((value) => ({
    value,
    label: t(`rules.severities.${value}`),
  })),
)
const languageOptions = computed(() =>
  ['SHACL', 'OWL', 'DATA', 'DERIVATION'].map((value) => ({
    value,
    label: t(`rules.languages.${value}`),
  })),
)
const executionOptions = computed(() =>
  ['AUTO', 'MANUAL'].map((value) => ({ value, label: t(`rules.executions.${value}`) })),
)
const label = (rule: Rule) =>
  rule.name_i18n[locale.value]?.trim() ||
  `${rule.name_i18n['zh-CN'] || rule.identifier} (${t('rules.untranslated')})`
const stateType = (state: string) =>
  state === 'PASS'
    ? 'success'
    : state === 'VIOLATION'
      ? 'error'
      : state === 'NOT_RUN'
        ? 'warning'
        : 'default'

const columns = computed(() => [
  { title: t('rules.identifier'), key: 'identifier', width: 170 },
  { title: t('common.label'), key: 'name_i18n', render: label },
  {
    title: t('rules.source'),
    key: 'source_kind',
    render: (row: Rule) => t(`rules.sources.${row.source_kind}`),
  },
  { title: t('rules.reference'), key: 'source_reference', ellipsis: { tooltip: true } },
  { title: t('common.revision'), key: 'revision', width: 90 },
  {
    title: t('common.actions'),
    key: 'actions',
    fixed: 'right' as const,
    width: 100,
    render: (row: Rule) =>
      h(
        UiButton,
        {
          size: 'small',
          disabled: busy.value,
          onClick: () => editRule(row),
        },
        { default: () => t(canWrite.value ? 'common.edit' : 'governanceUi.details') },
      ),
  },
])

function errorText(err: unknown) {
  const body = err as { code?: string; params?: Record<string, string | number> }
  const code = body?.code || 'NETWORK_ERROR'
  if (code === 'KG.REVISION_CONFLICT') return t('rules.conflict')
  if (code === 'KG.RESOURCE_NOT_FOUND') return t('rules.notFound')
  if (body.params?.reason === 'rule_identifier_taken') return t('rules.identifierTaken')
  if (code === 'KG.VALIDATION_VIOLATION' || code === 'KG.INVALID_REQUEST') {
    return t('rules.invalid', { reason: body.params?.reason || code })
  }
  if (code === 'KG.INVALID_NAME' || code === 'KG.INVALID_IRI') {
    return t('rules.invalid', { reason: body.params?.field || code })
  }
  return te(`errors.${code}`)
    ? t(`errors.${code}`, body.params || {})
    : t('rules.requestFailed', { code })
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
    const result = await rulesApi.list(listQuery.value, controller.signal)
    if (!owns()) return
    if (!result.items.length && page.value > 1) {
      page.value--
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (owns()) error.value = errorText(err)
  } finally {
    if (owns()) {
      initialized.value = true
      loading.value = false
    }
  }
}

watch(page, load, { immediate: true })
watch(listIdentity, () => {
  if (auth.user) void load()
})
watch([search, sourceKind], () => {
  if (page.value === 1) void load()
  else page.value = 1
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
function resetSearch() {
  query.value = ''
  if (search.value === '' && sourceKind.value === null) {
    if (page.value === 1) void load()
    else page.value = 1
  } else {
    search.value = ''
    sourceKind.value = null
  }
}
watch([page, search, sourceKind], () => {
  void router.replace({
    query: {
      ...route.query,
      q: search.value || undefined,
      source: sourceKind.value || undefined,
      page: page.value > 1 ? page.value : undefined,
    },
  })
})
onBeforeUnmount(() => {
  alive = false
  stopListSession()
  readController?.abort()
})

function createRule() {
  if (!canWrite.value || busy.value) return
  saved.value = null
  form.value = emptyRule()
  testResult.value = null
  tab.value = 'metadata'
  error.value = ''
  notice.value = ''
  showEditor.value = true
}

async function editRule(rule: Rule) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  const owner = editorGeneration
  try {
    const latest = await rulesApi.get(rule.id)
    if (!alive || owner !== editorGeneration) return
    saved.value = latest
    form.value = payload(latest)
    testResult.value = null
    tab.value = 'metadata'
    showEditor.value = true
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = errorText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

async function save() {
  if (!canWrite.value || busy.value) return
  const owner = editorGeneration
  const draft = form.value
  const snapshot = JSON.stringify(draft)
  const previous = saved.value
  busy.value = true
  try {
    await formRef.value?.validate()
  } catch {
    if (owner === editorGeneration) busy.value = false
    return
  }
  if (
    !alive ||
    owner !== editorGeneration ||
    !canWrite.value ||
    !canSave.value ||
    form.value !== draft ||
    JSON.stringify(form.value) !== snapshot
  ) {
    if (owner === editorGeneration) busy.value = false
    return
  }
  error.value = ''
  notice.value = ''
  try {
    const input = {
      ...(JSON.parse(snapshot) as RuleInput),
      name_i18n: Object.fromEntries(
        Object.entries(form.value.name_i18n).filter(([, value]) => value.trim()),
      ),
    }
    const result = previous ? await rulesApi.update(previous, input) : await rulesApi.create(input)
    if (
      !alive ||
      owner !== editorGeneration ||
      form.value !== draft ||
      JSON.stringify(form.value) !== snapshot
    )
      return
    saved.value = result
    form.value = payload(result)
    testResult.value = null
    notice.value = t('rules.saved')
    await load()
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = errorText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

async function runTest() {
  if (!saved.value || busy.value || dirty.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  testResult.value = null
  const generation = ++testGeneration
  const rule = saved.value
  const owner = editorGeneration
  try {
    const result = await rulesApi.test(rule)
    if (alive && generation === testGeneration && saved.value?.id === rule.id && !dirty.value) {
      testResult.value = result
    }
  } catch (err) {
    if (alive && owner === editorGeneration && generation === testGeneration)
      error.value = errorText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}

async function remove() {
  if (!canWrite.value || !saved.value || busy.value) return
  busy.value = true
  error.value = ''
  const owner = editorGeneration
  try {
    await rulesApi.remove(saved.value)
    if (!alive || owner !== editorGeneration) return
    showEditor.value = false
    notice.value = t('rules.deleted')
    await load()
  } catch (err) {
    if (alive && owner === editorGeneration) error.value = errorText(err)
  } finally {
    if (alive && owner === editorGeneration) busy.value = false
  }
}
</script>

<template>
  <section class="rules-page governance-page">
    <PageHeader :title="t('page.governanceRules')" :description="t('rules.intro')">
      <template #actions>
        <UiButton type="primary" :disabled="busy || !canWrite" @click="createRule">{{
          t('rules.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.rulesReadOnly') }}</UiAlert>
    <UiAlert v-if="notice && !showEditor" type="success" role="status">{{ notice }}</UiAlert>
    <section class="governance-ledger">
      <header class="governance-caption">
        <h2>{{ t('page.governanceRules') }}</h2>
        <span>{{ t('governanceLedger.resultCount', { count: total }) }}</span>
      </header>
      <SearchPanel
        v-model:query="query"
        class="filters"
        :loading="loading"
        @submit="doSearch"
        @clear="clearSearch"
        @reset="resetSearch"
      >
        <template #filter>
          <FormField :label="t('rules.source')" :show-feedback="false">
            <UiSelect
              v-model:value="sourceKind"
              :options="sourceOptions"
              :placeholder="t('rules.allSources')"
              clearable
              class="source-filter"
            />
          </FormField>
          <UiButton :aria-busy="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
        </template>
      </SearchPanel>
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
        :row-key="(row: Rule) => row.id"
        size="small"
        :max-height="600"
        :scroll-x="800"
        :empty-text="t(search || sourceKind ? 'ui.emptyFiltered' : 'rules.empty')"
        @retry="load"
      >
        <template #toolbar><span /></template>
      </SearchTable>
    </section>
    <UiDrawer
      v-model:show="editorVisible"
      width="min(800px, 100vw)"
      :auto-focus="true"
      :mask-closable="false"
      :close-on-esc="!busy"
    >
      <UiDrawerContent
        class="governance-editor"
        :title="saved ? t('rules.edit') : t('rules.create')"
        :closable="!busy"
      >
        <div class="editor-identity">
          <GovernanceIdentity
            :name="form.identifier || t('rules.create')"
            name-key="rules.identifier"
            :iri="form.target_iri"
            :revision="saved?.revision"
          />
        </div>
        <UiSpace vertical size="large">
          <UiAlert v-if="!canWrite" type="info">{{ t('governanceUi.rulesReadOnly') }}</UiAlert>
          <UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert>
          <UiAlert v-if="notice" type="success" role="status">{{ notice }}</UiAlert>
          <UiAlert v-if="saved" type="info">{{
            t('rules.editingRevision', { revision: saved.revision })
          }}</UiAlert>
          <FormContainer
            id="governance-rule-form"
            ref="formRef"
            :model="form"
            :rules="rules"
            label-placement="top"
            :disabled="busy"
            :submitting="busy"
            @submit="save"
            @invalid="showInvalidTab"
          >
            <UiTabs v-model:value="tab" type="line" animated>
              <UiTabPane name="metadata" display-directive="show" :tab="t('rules.metadata')">
                <fieldset class="form-section">
                  <legend>{{ t('governanceUi.ruleDefinition') }}</legend>
                  <div class="form-grid">
                    <FormField
                      :readonly="!canWrite"
                      path="identifier"
                      :label="t('rules.identifier')"
                      required
                      ><UiInput
                        v-model:value="form.identifier"
                        :input-props="{ 'aria-label': t('rules.identifier') }"
                    /></FormField>
                    <FormField
                      :readonly="!canWrite"
                      path="category"
                      :label="t('rules.category')"
                      required
                      ><UiInput
                        v-model:value="form.category"
                        :input-props="{ 'aria-label': t('rules.category') }"
                    /></FormField>
                    <FormField
                      :readonly="!canWrite"
                      path="name_i18n.zh-CN"
                      :label="t('common.labelZh')"
                      required
                      ><UiInput
                        v-model:value="form.name_i18n['zh-CN']"
                        :input-props="{ 'aria-label': t('common.labelZh') }"
                    /></FormField>
                    <FormField
                      :readonly="!canWrite"
                      path="name_i18n.en-US"
                      :label="t('common.labelEn')"
                      ><UiInput
                        v-model:value="form.name_i18n['en-US']"
                        :input-props="{ 'aria-label': t('common.labelEn') }"
                    /></FormField>
                    <FormField
                      :readonly="!canWrite"
                      path="source_kind"
                      :label="t('rules.source')"
                      required
                      ><UiSelect v-model:value="form.source_kind" :options="sourceOptions"
                    /></FormField>
                    <FormField
                      :readonly="!canWrite"
                      path="severity"
                      :label="t('rules.severity')"
                      required
                      ><UiSelect v-model:value="form.severity" :options="severityOptions"
                    /></FormField>
                  </div>
                </fieldset>
                <fieldset class="form-section">
                  <legend>{{ t('governanceUi.ruleTarget') }}</legend>
                  <FormField
                    :readonly="!canWrite"
                    path="source_reference"
                    :label="t('rules.reference')"
                    :help="t('rules.sourceHint')"
                    required
                    ><UiInput
                      v-model:value="form.source_reference"
                      :input-props="{ 'aria-label': t('rules.reference') }"
                  /></FormField>
                  <FormField
                    :readonly="!canWrite"
                    path="target_iri"
                    :label="t('rules.target')"
                    required
                    ><UiInput
                      v-model:value="form.target_iri"
                      :input-props="{ 'aria-label': t('rules.target') }"
                  /></FormField></fieldset
              ></UiTabPane>
              <UiTabPane name="expression" display-directive="show" :tab="t('rules.expressionTab')">
                <fieldset class="form-section">
                  <legend>{{ t('governanceUi.ruleLogic') }}</legend>
                  <div class="form-grid">
                    <FormField :readonly="!canWrite" path="language" :label="t('rules.language')"
                      ><UiSelect v-model:value="form.language" :options="languageOptions"
                    /></FormField>
                    <FormField :readonly="!canWrite" path="execution" :label="t('rules.execution')"
                      ><UiSelect v-model:value="form.execution" :options="executionOptions"
                    /></FormField>
                  </div>
                  <UiAlert
                    v-if="form.language === 'OWL' || form.execution === 'MANUAL'"
                    type="warning"
                    class="source-hint"
                    >{{ t('rules.notRunHint') }}</UiAlert
                  >
                  <UiAlert
                    v-else-if="form.language === 'DATA' || form.language === 'DERIVATION'"
                    type="info"
                    class="source-hint"
                    >{{ t(`rules.${form.language.toLowerCase()}Hint`) }}</UiAlert
                  >
                  <UiAlert v-else type="info" class="source-hint">{{
                    t('rules.shaclHint')
                  }}</UiAlert>
                  <FormField
                    :readonly="!canWrite"
                    path="expression"
                    :label="t('rules.expression')"
                    required
                    ><UiInput
                      v-model:value="form.expression"
                      :input-props="{ 'aria-label': t('rules.expression') }"
                      type="textarea"
                      :autosize="{ minRows: 12, maxRows: 24 }"
                      class="code-input"
                  /></FormField></fieldset
              ></UiTabPane>
              <UiTabPane name="examples" display-directive="show" :tab="t('rules.examples')">
                <UiAlert v-if="needsExamples" type="info" class="source-hint">{{
                  t('rules.examplesHint')
                }}</UiAlert>
                <UiAlert v-else type="info" class="source-hint">{{
                  t('rules.examplesOptionalHint')
                }}</UiAlert>
                <div class="example-grid">
                  <FormField
                    :readonly="!canWrite"
                    path="positive_example"
                    :label="t('rules.positive')"
                    ><UiInput
                      v-model:value="form.positive_example"
                      :input-props="{ 'aria-label': t('rules.positive') }"
                      type="textarea"
                      :autosize="{ minRows: 6, maxRows: 15 }"
                      class="code-input"
                  /></FormField>
                  <FormField
                    :readonly="!canWrite"
                    path="negative_example"
                    :label="t('rules.negative')"
                    ><UiInput
                      v-model:value="form.negative_example"
                      :input-props="{ 'aria-label': t('rules.negative') }"
                      type="textarea"
                      :autosize="{ minRows: 6, maxRows: 15 }"
                      class="code-input"
                  /></FormField>
                </div>
                <UiButton :disabled="!saved || dirty || busy" :loading="busy" @click="runTest">{{
                  t('rules.runTest')
                }}</UiButton>
                <p v-if="dirty">{{ t('rules.saveBeforeTest') }}</p>
                <template v-if="testResult">
                  <UiSpace align="center" class="test-summary"
                    ><strong>{{
                      t('rules.testRevision', { revision: testResult.revision })
                    }}</strong
                    ><UiTag :type="stateType(testResult.state)">{{
                      t(`validation.${testResult.state}`)
                    }}</UiTag></UiSpace
                  >
                  <UiAlert v-if="dirty" type="warning">{{ t('rules.staleTest') }}</UiAlert>
                  <UiAlert v-if="testResult.state === 'NOT_RUN'" type="warning">{{
                    t('rules.notRunHint')
                  }}</UiAlert>
                  <UiAlert v-else-if="testResult.state === 'VIOLATION'" type="error">{{
                    t('rules.examplesFailed')
                  }}</UiAlert>
                  <UiCard
                    v-for="example in ['positive', 'negative'] as const"
                    v-show="testResult[example]"
                    :key="example"
                    :title="t(`rules.${example}`)"
                    size="small"
                    class="test-report"
                  >
                    <UiTag :type="stateType(testResult[example]?.state || 'NOT_RUN')">{{
                      t(`validation.${testResult[example]?.state || 'NOT_RUN'}`)
                    }}</UiTag>
                    <pre>{{ testResult[example]?.report_text }}</pre>
                  </UiCard>
                </template>
              </UiTabPane>
            </UiTabs>
          </FormContainer>
        </UiSpace>
        <template #footer>
          <UiSpace justify="space-between" class="editor-footer">
            <UiPopconfirm v-if="saved" :disabled="busy || !canWrite" @positive-click="remove">
              <template #trigger
                ><UiButton type="error" secondary :disabled="busy || !canWrite">{{
                  t('common.delete')
                }}</UiButton></template
              >
              {{ t('rules.confirmDelete', { identifier: saved.identifier }) }}
            </UiPopconfirm>
            <UiSpace
              ><UiButton :disabled="busy" @click="editorVisible = false">{{
                t('common.cancel')
              }}</UiButton
              ><UiButton
                type="primary"
                :loading="busy"
                :disabled="busy || !canWrite || !canSave || !dirty"
                attr-type="submit"
                form="governance-rule-form"
                >{{ t('common.save') }}</UiButton
              ></UiSpace
            >
          </UiSpace>
        </template>
      </UiDrawerContent>
    </UiDrawer>
  </section>
</template>

<style scoped>
.rules-page {
  display: grid;
  gap: 16px;
}
.rules-page :deep(.ui-card) {
  background: var(--bg-surface);
  border-color: var(--border);
  border-radius: var(--radius-medium);
}
.section-title {
  border-left: 3px solid var(--pri);
  padding-left: 12px;
  margin: 8px 0 20px;
  font-size: 15px;
}
h2 {
  margin: 0;
}
p {
  color: var(--text-secondary);
}
.filters {
  margin-bottom: 16px;
}
.source-filter {
  width: 210px;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.source-hint {
  margin-bottom: 16px;
}
.code-input,
pre {
  font-family: ui-monospace, monospace;
}
.test-summary,
.test-report {
  margin-top: 16px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 320px;
  overflow: auto;
}
.editor-footer {
  width: 100%;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style scoped src="../styles/observatory.css"></style>
