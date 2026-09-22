<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Rule, RuleInput, RuleTest } from '@/api/governance'
import { rulesApi } from '@/api/governance'

const { t, te, locale } = useI18n()
const items = ref<Rule[]>([])
const total = ref(0)
const page = ref(1)
const query = ref('')
const search = ref('')
const sourceKind = ref<string | null>(null)
const loading = ref(false)
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
const canSave = computed(
  () =>
    form.value.identifier.trim() &&
    form.value.name_i18n['zh-CN']?.trim() &&
    form.value.category.trim() &&
    form.value.source_reference.trim() &&
    form.value.target_iri.trim() &&
    form.value.expression.trim() &&
    form.value.positive_example.trim() &&
    form.value.negative_example.trim(),
)
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
  ['SHACL', 'OWL'].map((value) => ({ value, label: t(`rules.languages.${value}`) })),
)
const executionOptions = computed(() =>
  ['AUTO', 'MANUAL'].map((value) => ({ value, label: t(`rules.executions.${value}`) })),
)
const label = (rule: Rule) =>
  rule.name_i18n[locale.value] ||
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
    width: 100,
    render: (row: Rule) =>
      h(
        NButton,
        {
          size: 'small',
          disabled: busy.value,
          onClick: () => editRule(row),
        },
        { default: () => t('common.edit') },
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
  readController?.abort()
  const controller = new AbortController()
  readController = controller
  loading.value = true
  error.value = ''
  try {
    const result = await rulesApi.list(
      {
        page: page.value,
        page_size: 20,
        q: search.value,
        source_kind: sourceKind.value || undefined,
      },
      controller.signal,
    )
    if (controller.signal.aborted) return
    items.value = result.items
    total.value = result.total
    if (!items.value.length && page.value > 1) page.value--
  } catch (err) {
    if (!controller.signal.aborted) error.value = errorText(err)
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

watch([page, search, sourceKind], load, { immediate: true })
watch([search, sourceKind], () => {
  page.value = 1
})
onBeforeUnmount(() => {
  alive = false
  readController?.abort()
})

function createRule() {
  saved.value = null
  form.value = emptyRule()
  testResult.value = null
  tab.value = 'metadata'
  error.value = ''
  notice.value = ''
  showEditor.value = true
}

async function editRule(rule: Rule) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const latest = await rulesApi.get(rule.id)
    if (!alive) return
    saved.value = latest
    form.value = payload(latest)
    testResult.value = null
    tab.value = 'metadata'
    showEditor.value = true
  } catch (err) {
    if (alive) error.value = errorText(err)
  } finally {
    if (alive) busy.value = false
  }
}

async function save() {
  if (busy.value || !canSave.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const input = {
      ...form.value,
      name_i18n: Object.fromEntries(
        Object.entries(form.value.name_i18n).filter(([, value]) => value.trim()),
      ),
    }
    const result = saved.value
      ? await rulesApi.update(saved.value, input)
      : await rulesApi.create(input)
    if (!alive) return
    saved.value = result
    form.value = payload(result)
    testResult.value = null
    notice.value = t('rules.saved')
    await load()
  } catch (err) {
    if (alive) error.value = errorText(err)
  } finally {
    if (alive) busy.value = false
  }
}

async function runTest() {
  if (!saved.value || busy.value || dirty.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  testResult.value = null
  try {
    const result = await rulesApi.test(saved.value)
    if (alive) testResult.value = result
  } catch (err) {
    if (alive) error.value = errorText(err)
  } finally {
    if (alive) busy.value = false
  }
}

async function remove() {
  if (!saved.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await rulesApi.remove(saved.value)
    if (!alive) return
    showEditor.value = false
    notice.value = t('rules.deleted')
    await load()
  } catch (err) {
    if (alive) error.value = errorText(err)
  } finally {
    if (alive) busy.value = false
  }
}
</script>

<template>
  <section class="rules-page">
    <NSpace justify="space-between" align="center">
      <div>
        <h2>{{ t('page.governanceRules') }}</h2>
        <p>{{ t('rules.intro') }}</p>
      </div>
      <NButton type="primary" :disabled="busy" @click="createRule">{{ t('rules.create') }}</NButton>
    </NSpace>
    <NAlert v-if="error && !showEditor" type="error" role="alert">{{ error }}</NAlert>
    <NAlert v-if="notice && !showEditor" type="success" role="status">{{ notice }}</NAlert>
    <NCard size="small">
      <NSpace class="filters" align="end">
        <NFormItem :label="t('common.search')" :show-feedback="false"
          ><NInput v-model:value="query" clearable @keyup.enter="search = query.trim()"
        /></NFormItem>
        <NButton @click="search = query.trim()">{{ t('common.search') }}</NButton>
        <NFormItem :label="t('rules.source')" :show-feedback="false"
          ><NSelect
            v-model:value="sourceKind"
            :options="sourceOptions"
            :placeholder="t('rules.allSources')"
            clearable
            class="source-filter"
        /></NFormItem>
        <NButton :loading="loading" @click="load">{{ t('graph.refresh') }}</NButton>
      </NSpace>
      <NDataTable
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: Rule) => row.id"
        :scroll-x="800"
      >
        <template #empty><NEmpty :description="t('rules.empty')" /></template>
      </NDataTable>
      <NPagination
        v-if="total > 20"
        v-model:page="page"
        :page-size="20"
        :item-count="total"
        class="pagination"
      />
    </NCard>
    <NDrawer
      v-model:show="showEditor"
      width="min(800px, 100vw)"
      :auto-focus="true"
      :mask-closable="false"
      :close-on-esc="!busy"
    >
      <NDrawerContent :title="saved ? t('rules.edit') : t('rules.create')" :closable="!busy">
        <NSpace vertical size="large">
          <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
          <NAlert v-if="notice" type="success" role="status">{{ notice }}</NAlert>
          <NAlert v-if="saved" type="info">{{
            t('rules.editingRevision', { revision: saved.revision })
          }}</NAlert>
          <NForm label-placement="top" :disabled="busy">
            <NTabs v-model:value="tab" type="line" animated>
              <NTabPane name="metadata" :tab="t('rules.metadata')">
                <div class="form-grid">
                  <NFormItem :label="t('rules.identifier')" required
                    ><NInput v-model:value="form.identifier"
                  /></NFormItem>
                  <NFormItem :label="t('rules.category')" required
                    ><NInput v-model:value="form.category"
                  /></NFormItem>
                  <NFormItem :label="t('common.labelZh')" required
                    ><NInput v-model:value="form.name_i18n['zh-CN']"
                  /></NFormItem>
                  <NFormItem :label="t('common.labelEn')"
                    ><NInput v-model:value="form.name_i18n['en-US']"
                  /></NFormItem>
                  <NFormItem :label="t('rules.source')" required
                    ><NSelect v-model:value="form.source_kind" :options="sourceOptions"
                  /></NFormItem>
                  <NFormItem :label="t('rules.severity')" required
                    ><NSelect v-model:value="form.severity" :options="severityOptions"
                  /></NFormItem>
                </div>
                <NFormItem :label="t('rules.reference')" required
                  ><NInput v-model:value="form.source_reference"
                /></NFormItem>
                <NAlert type="info" class="source-hint">{{ t('rules.sourceHint') }}</NAlert>
                <NFormItem :label="t('rules.target')" required
                  ><NInput v-model:value="form.target_iri"
                /></NFormItem>
              </NTabPane>
              <NTabPane name="expression" :tab="t('rules.expressionTab')">
                <div class="form-grid">
                  <NFormItem :label="t('rules.language')"
                    ><NSelect v-model:value="form.language" :options="languageOptions"
                  /></NFormItem>
                  <NFormItem :label="t('rules.execution')"
                    ><NSelect v-model:value="form.execution" :options="executionOptions"
                  /></NFormItem>
                </div>
                <NAlert
                  v-if="form.language === 'OWL' || form.execution === 'MANUAL'"
                  type="warning"
                  class="source-hint"
                  >{{ t('rules.notRunHint') }}</NAlert
                >
                <NAlert v-else type="info" class="source-hint">{{ t('rules.shaclHint') }}</NAlert>
                <NFormItem :label="t('rules.expression')" required
                  ><NInput
                    v-model:value="form.expression"
                    type="textarea"
                    :autosize="{ minRows: 12, maxRows: 24 }"
                    class="code-input"
                /></NFormItem>
              </NTabPane>
              <NTabPane name="examples" :tab="t('rules.examples')">
                <NAlert type="info" class="source-hint">{{ t('rules.examplesHint') }}</NAlert>
                <NFormItem :label="t('rules.positive')"
                  ><NInput
                    v-model:value="form.positive_example"
                    type="textarea"
                    :autosize="{ minRows: 6, maxRows: 15 }"
                    class="code-input"
                /></NFormItem>
                <NFormItem :label="t('rules.negative')"
                  ><NInput
                    v-model:value="form.negative_example"
                    type="textarea"
                    :autosize="{ minRows: 6, maxRows: 15 }"
                    class="code-input"
                /></NFormItem>
                <NButton :disabled="!saved || dirty || busy" :loading="busy" @click="runTest">{{
                  t('rules.runTest')
                }}</NButton>
                <p v-if="dirty">{{ t('rules.saveBeforeTest') }}</p>
                <template v-if="testResult">
                  <NSpace align="center" class="test-summary"
                    ><strong>{{
                      t('rules.testRevision', { revision: testResult.revision })
                    }}</strong
                    ><NTag :type="stateType(testResult.state)">{{
                      t(`validation.${testResult.state}`)
                    }}</NTag></NSpace
                  >
                  <NAlert v-if="dirty" type="warning">{{ t('rules.staleTest') }}</NAlert>
                  <NAlert v-if="testResult.state === 'NOT_RUN'" type="warning">{{
                    t('rules.notRunHint')
                  }}</NAlert>
                  <NAlert v-else-if="testResult.state === 'VIOLATION'" type="error">{{
                    t('rules.examplesFailed')
                  }}</NAlert>
                  <NCard
                    v-for="example in ['positive', 'negative'] as const"
                    v-show="testResult[example]"
                    :key="example"
                    :title="t(`rules.${example}`)"
                    size="small"
                    class="test-report"
                  >
                    <NTag :type="stateType(testResult[example]?.state || 'NOT_RUN')">{{
                      t(`validation.${testResult[example]?.state || 'NOT_RUN'}`)
                    }}</NTag>
                    <pre>{{ testResult[example]?.report_text }}</pre>
                  </NCard>
                </template>
              </NTabPane>
            </NTabs>
          </NForm>
        </NSpace>
        <template #footer>
          <NSpace justify="space-between" class="editor-footer">
            <NPopconfirm v-if="saved" :disabled="busy" @positive-click="remove">
              <template #trigger
                ><NButton type="error" secondary :disabled="busy">{{
                  t('common.delete')
                }}</NButton></template
              >
              {{ t('rules.confirmDelete', { identifier: saved.identifier }) }}
            </NPopconfirm>
            <NSpace
              ><NButton :disabled="busy" @click="showEditor = false">{{
                t('common.cancel')
              }}</NButton
              ><NButton
                type="primary"
                :loading="busy"
                :disabled="!canSave || !dirty"
                @click="save"
                >{{ t('common.save') }}</NButton
              ></NSpace
            >
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.rules-page {
  display: grid;
  gap: 16px;
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
