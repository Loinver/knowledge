<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { namespacesApi } from '@/api/namespaces'
import type { ModelingApplication, ModelingCandidate } from '@/api/ontology-modeling'
import { ontologyModelingApi } from '@/api/ontology-modeling'
import { getSessionGeneration } from '@/api/tokens'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiCard,
  UiCheckbox,
  UiDivider,
  UiEmpty,
  UiInput,
  UiSelect,
  UiSpace,
  UiTag,
} from '@/components/ui'
import type { FormInst, FormRules } from '@/components/ui/formTypes'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

import { parseCandidateEditor, pretty, useAiModeling } from './useAiModeling'

const props = defineProps<{ ontologyId: number; draftId: string; baseEditRevision: number }>()
const emit = defineEmits<{ applied: [application: ModelingApplication] }>()
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const auth = useAuthStore()
const generationForm = ref<FormInst | null>(null)
const candidateForm = ref<FormInst | null>(null)
let storage: Storage | null = null
try {
  storage = typeof sessionStorage === 'undefined' ? null : sessionStorage
} catch {
  /* Browser storage is optional. */
}
const {
  capabilities,
  namespaces,
  namespaceIds,
  text,
  authorizeTransfer,
  excerpts,
  proposals,
  total,
  page,
  selected,
  candidateJson,
  editNote,
  validation,
  confirmedDigest,
  error,
  notice,
  initialError,
  initializing,
  busy,
  pendingApplication,
  application,
  dirty,
  editable,
  validationCurrent,
  generationAvailable,
  validatingForm,
  canApply,
  canRetry,
  initialize,
  refreshList,
  selectProposal,
  generate,
  saveCandidate,
  validate,
  acceptPlan,
  apply,
  queryApplication,
  retryApplication,
  discard,
  addExcerpt,
  dispose,
} = useAiModeling(() => props, {
  api: ontologyModelingApi,
  namespacesApi,
  t,
  toMessage,
  storage,
  identity: () => `${getSessionGeneration()}:${auth.user?.id ?? ''}`,
  canWrite: () => auth.user?.role === 'ADMIN' || auth.user?.role === 'EDITOR',
  confirmChange: () => typeof window !== 'undefined' && window.confirm(t('modeling.discardEdits')),
  validateGenerate: async () => {
    await generationForm.value?.validate()
  },
  validateCandidate: async () => {
    await candidateForm.value?.validate()
  },
  onApplied: (receipt) => emit('applied', receipt),
})
onBeforeUnmount(dispose)
const namespaceOptions = computed(() =>
  namespaces.value
    .filter((ns) => !ns.protected)
    .map((ns) => ({ value: ns.id, label: `${ns.prefix} · ${ns.iri}` })),
)
const rows = computed(() =>
  selected.value
    ? [
        ...selected.value.candidate.resources,
        ...selected.value.candidate.axioms,
        ...selected.value.candidate.constraints,
      ]
    : [],
)
type Row =
  | ModelingCandidate['resources'][number]
  | ModelingCandidate['axioms'][number]
  | ModelingCandidate['constraints'][number]
function translated(value: unknown, language = locale.value): string {
  return value &&
    typeof value === 'object' &&
    language in value &&
    typeof value[language as keyof typeof value] === 'string'
    ? String(value[language as keyof typeof value]).trim() || t('enumDictionaries.untranslated')
    : t('enumDictionaries.untranslated')
}
function metadata(row: Row) {
  return 'metadata' in row.spec ? row.spec.metadata : null
}
function rowTitle(row: Row) {
  return `${row.candidate_id} · ${'local_name' in row.spec ? row.spec.local_name : row.spec.kind}`
}
function sourceText(sourceHandle: string, spanHandle: string): string {
  const source = selected.value?.sources[sourceHandle]
  if (!source || typeof source !== 'object' || !('spans' in source) || !Array.isArray(source.spans))
    return t('modeling.sourceMissing')
  const span = source.spans.find(
    (item: unknown) =>
      item && typeof item === 'object' && 'handle' in item && item.handle === spanHandle,
  )
  return span && typeof span.text === 'string' ? span.text : t('modeling.sourceMissing')
}
const sourceEntries = computed(() => Object.entries(selected.value?.sources ?? {}))
const validationIssues = computed(() => {
  const issues = validation.value?.plan.issues
  if (!Array.isArray(issues)) return []
  return issues.map((issue: unknown) => {
    if (!issue || typeof issue !== 'object' || !('code' in issue) || typeof issue.code !== 'string')
      return t('modeling.issueUnknown')
    return toMessage({ code: issue.code, params: 'params' in issue ? issue.params : {} })
  })
})
const authorizedExcerpts = computed(() => excerpts.value.filter((excerpt) => excerpt.authorized))
// Form models only read the composable's existing refs; no second editable candidate.
const generationModel = computed(() => ({
  namespaceIds: namespaceIds.value,
  text: text.value,
  excerpts: excerpts.value,
  authorizeTransfer: authorizeTransfer.value,
}))
const generationRules = computed<FormRules>(() => {
  const required = { required: true, message: t('common.required') }
  const rules: FormRules = {
    namespaceIds: {
      ...required,
      type: 'array',
      max: 20,
      validator: () =>
        namespaceIds.value.every((id) =>
          namespaces.value.some((ns) => ns.id === id && !ns.protected),
        ),
    },
    text: [{ ...required }, { max: 16000, message: t('ds.form.maxLength', { max: 16000 }) }],
    authorizeTransfer: {
      validator: (_, value) => value === true,
      message: t('modeling.authorizeTransfer'),
    },
  }
  excerpts.value.forEach((excerpt, index) => {
    if (!excerpt.authorized) return
    rules[`excerpts.${index}.title`] = [
      required,
      { max: 200, message: t('ds.form.maxLength', { max: 200 }) },
    ]
    rules[`excerpts.${index}.text`] = [
      required,
      { max: 16000, message: t('ds.form.maxLength', { max: 16000 }) },
    ]
  })
  return rules
})
const candidateModel = computed(() => ({
  candidateJson: candidateJson.value,
  editNote: editNote.value,
}))
const candidateRules = computed<FormRules>(() => ({
  candidateJson: {
    required: true,
    validator: (_, value) => {
      try {
        parseCandidateEditor(String(value))
        return true
      } catch {
        return false
      }
    },
    message: t('modeling.invalidJson'),
  },
  editNote: [
    { required: true, message: t('common.required') },
    { max: 1000, message: t('ds.form.maxLength', { max: 1000 }) },
  ],
}))
</script>

<template>
  <section class="modeling-panel">
    <UiAlert type="info">{{ t('modeling.draftOnly') }}</UiAlert>
    <p class="target">
      {{ t('modeling.target', { id: ontologyId, draft: draftId, revision: baseEditRevision }) }}
    </p>
    <UiAlert v-if="initialError" type="error"
      >{{ initialError }} <UiButton @click="initialize">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="capabilities && !capabilities.chat_configured" type="info">{{
      t('modeling.noModel')
    }}</UiAlert>
    <UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert>
    <UiAlert v-if="notice" type="info" role="status">{{ notice }}</UiAlert>

    <UiCard v-if="pendingApplication" :title="t('modeling.pendingApplication')" size="small">
      <p>{{ t('modeling.outcomePending') }}</p>
      <dl>
        <dt>{{ t('modeling.requestKey') }}</dt>
        <dd class="mono">{{ pendingApplication.key }}</dd>
        <dt>{{ t('modeling.planDigest') }}</dt>
        <dd class="mono">{{ pendingApplication.payload.compiled_plan_digest }}</dd>
      </dl>
      <UiSpace>
        <UiButton :loading="busy === 'query'" :disabled="!!busy" @click="queryApplication">{{
          t('modeling.queryApplication')
        }}</UiButton>
        <UiButton :loading="busy === 'apply'" :disabled="!canRetry" @click="retryApplication">{{
          t('modeling.retrySameKey')
        }}</UiButton>
      </UiSpace>
      <p class="hint">{{ t('modeling.recoveryHint') }}</p>
    </UiCard>
    <details v-if="application">
      <summary>{{ t('modeling.applicationReceipt') }}</summary>
      <pre>{{ pretty(application) }}</pre>
    </details>

    <FormContainer
      ref="generationForm"
      :model="generationModel"
      :rules="generationRules"
      :disabled="!!busy || !!pendingApplication"
      @submit="generate"
    >
      <FormField path="namespaceIds" :label="t('common.namespace')">
        <UiSelect
          v-model:value="namespaceIds"
          :options="namespaceOptions"
          :loading="initializing"
          multiple
          filterable
        />
      </FormField>
      <FormField path="text" :label="t('modeling.requirements')">
        <UiInput
          v-model:value="text"
          type="textarea"
          :maxlength="16000"
          :autosize="{ minRows: 4, maxRows: 10 }"
        />
      </FormField>
      <FormField :label="t('modeling.excerpts')">
        <UiSpace vertical class="full-width">
          <UiCard v-for="(excerpt, index) in excerpts" :key="excerpt.id" size="small">
            <FormField :path="`excerpts.${index}.title`" :label="t('modeling.excerptTitle')"
              ><UiInput v-model:value="excerpt.title" :maxlength="200"
            /></FormField>
            <FormField :path="`excerpts.${index}.text`" :label="t('modeling.excerptText')"
              ><UiInput
                v-model:value="excerpt.text"
                type="textarea"
                :maxlength="16000"
                :autosize="{ minRows: 2, maxRows: 6 }"
            /></FormField>
            <UiSpace justify="space-between">
              <FormField :path="`excerpts.${index}.authorized`" :show-feedback="false"
                ><UiCheckbox
                  v-model:checked="excerpt.authorized"
                  :aria-label="t('modeling.authorizeExcerpt')"
                  >{{ t('modeling.authorizeExcerpt') }}</UiCheckbox
                ></FormField
              >
              <UiButton
                size="small"
                @click="excerpts = excerpts.filter((item) => item.id !== excerpt.id)"
                >{{ t('modeling.removeExcerpt') }}</UiButton
              >
            </UiSpace>
          </UiCard>
          <UiButton :disabled="excerpts.length >= 5" @click="addExcerpt">{{
            t('modeling.addExcerpt')
          }}</UiButton>
        </UiSpace>
      </FormField>
      <UiCard :title="t('modeling.transferSources')" size="small">
        <ul>
          <li>{{ t('modeling.requirements') }}</li>
          <li v-for="excerpt in authorizedExcerpts" :key="excerpt.id">
            {{ excerpt.title || t('modeling.excerptTitle') }}
          </li>
        </ul>
        <p>{{ t('modeling.automaticSources') }}</p>
        <p v-if="excerpts.some((excerpt) => !excerpt.authorized)" class="hint">
          {{ t('modeling.skippedExcerpts') }}
        </p>
        <FormField path="authorizeTransfer" :show-feedback="false"
          ><UiCheckbox
            v-model:checked="authorizeTransfer"
            :aria-label="t('modeling.authorizeTransfer')"
            >{{ t('modeling.authorizeTransfer') }}</UiCheckbox
          ></FormField
        >
      </UiCard>
    </FormContainer>
    <UiButton
      type="primary"
      :loading="busy === 'generate'"
      :disabled="!generationAvailable"
      @click="generate"
      >{{ t('modeling.generate') }}</UiButton
    >
    <details v-if="capabilities">
      <summary>{{ t('modeling.capabilities') }}</summary>
      <pre>{{ pretty(capabilities) }}</pre>
    </details>

    <UiDivider />
    <h3>{{ t('modeling.proposals') }}</h3>
    <UiSpace
      ><UiButton :disabled="!!busy || initializing" @click="refreshList()">{{
        t('graph.refresh')
      }}</UiButton>
      <UiButton :disabled="page <= 1 || !!busy" @click="refreshList(page - 1)">{{
        t('modeling.previous')
      }}</UiButton>
      <span>{{ t('modeling.page', { page, total }) }}</span>
      <UiButton :disabled="page * 20 >= total || !!busy" @click="refreshList(page + 1)">{{
        t('modeling.next')
      }}</UiButton></UiSpace
    >
    <UiEmpty v-if="!proposals.length" :description="t('modeling.noProposals')" />
    <UiSpace vertical>
      <UiButton
        v-for="proposal in proposals"
        :key="proposal.id"
        :type="selected?.id === proposal.id ? 'primary' : 'default'"
        :disabled="!!busy && busy !== 'select'"
        @click="selectProposal(proposal.id)"
      >
        {{ t('modeling.proposal', { id: proposal.id, revision: proposal.revision }) }} ·
        {{ t(`modeling.states.${proposal.state}`) }}
      </UiButton>
    </UiSpace>

    <template v-if="selected">
      <UiAlert
        v-if="selected.stale || selected.base_edit_revision !== baseEditRevision"
        type="warning"
        >{{ t('modeling.stale') }}</UiAlert
      >
      <dl class="metadata">
        <dt>{{ t('modeling.candidateDigest') }}</dt>
        <dd class="mono">{{ selected.candidate_digest }}</dd>
      </dl>
      <details>
        <summary>{{ t('modeling.provenance') }}</summary>
        <pre>{{ pretty(selected.provenance) }}</pre>
      </details>
      <details>
        <summary>{{ t('modeling.sources') }}</summary>
        <UiCard
          v-for="[handle, source] in sourceEntries"
          :key="handle"
          :title="handle"
          size="small"
        >
          <pre>{{ pretty(source) }}</pre>
        </UiCard>
      </details>
      <UiCard :title="t('modeling.scope')" size="small"
        ><p>{{ translated(selected.candidate.scope.goal_i18n) }}</p>
        <ul>
          <li v-for="(assumption, index) in selected.candidate.scope.assumptions_i18n" :key="index">
            {{ translated(assumption) }}
          </li>
        </ul>
      </UiCard>
      <UiCard
        v-if="selected.candidate.ontology_metadata"
        :title="t('modeling.ontologyMetadata')"
        size="small"
      >
        <pre>{{ pretty(selected.candidate.ontology_metadata) }}</pre>
      </UiCard>
      <UiCard v-for="row in rows" :key="row.candidate_id" :title="rowTitle(row)" size="small">
        <UiTag size="small">{{ t(`modeling.kinds.${row.spec.kind}`) }}</UiTag>
        <template v-if="metadata(row)">
          <dl>
            <dt>{{ t('common.labelZh') }}</dt>
            <dd>{{ translated(metadata(row)?.labels, 'zh-CN') }}</dd>
            <dt>{{ t('common.labelEn') }}</dt>
            <dd>{{ translated(metadata(row)?.labels, 'en-US') }}</dd>
            <dt>{{ t('common.definitionZh') }}</dt>
            <dd>{{ translated(metadata(row)?.definitions, 'zh-CN') }}</dd>
            <dt>{{ t('common.definitionEn') }}</dt>
            <dd>{{ translated(metadata(row)?.definitions, 'en-US') }}</dd>
          </dl>
          <ul>
            <li v-for="(synonym, index) in metadata(row)?.synonyms" :key="index">
              {{ synonym.language }} · {{ synonym.text }}
            </li>
          </ul>
        </template>
        <p>
          {{ t(`modeling.basis.${row.evidence.basis}`) }} ·
          {{ translated(row.evidence.rationale_i18n) }}
        </p>
        <ul>
          <li v-for="(reference, index) in row.evidence.source_refs" :key="index">
            <span class="mono">{{ reference.source_handle }} / {{ reference.span_handle }}</span>
            <blockquote>
              {{ sourceText(reference.source_handle, reference.span_handle) }}
            </blockquote>
          </li>
        </ul>
        <details>
          <summary>{{ t('modeling.details') }}</summary>
          <pre>{{ pretty(row.spec) }}</pre>
          <pre>{{ pretty(row.evidence) }}</pre>
        </details>
      </UiCard>
      <UiCard :title="t('modeling.questions')" size="small">
        <UiEmpty
          v-if="!selected.candidate.questions.length"
          :description="t('modeling.noQuestions')"
        />
        <p v-for="question in selected.candidate.questions" :key="question.id">
          <UiTag :type="question.blocking ? 'warning' : 'default'" size="small">{{
            question.id
          }}</UiTag>
          {{ translated(question.question_i18n) }}
        </p>
      </UiCard>
      <FormContainer
        ref="candidateForm"
        :model="candidateModel"
        :rules="candidateRules"
        :disabled="!editable && !validatingForm"
        @submit="saveCandidate"
      >
        <FormField path="candidateJson" :label="t('modeling.jsonEditor')"
          ><UiInput
            v-model:value="candidateJson"
            type="textarea"
            class="json-editor"
            :autosize="{ minRows: 12, maxRows: 30 }"
        /></FormField>
        <FormField path="editNote" :label="t('modeling.editNote')"
          ><UiInput v-model:value="editNote" :maxlength="1000"
        /></FormField>
      </FormContainer>
      <details v-if="dirty" open>
        <summary>{{ t('modeling.diff') }}</summary>
        <div class="diff">
          <div>
            <h4>{{ t('modeling.savedCandidate') }}</h4>
            <pre>{{ pretty(selected.candidate) }}</pre>
          </div>
          <div>
            <h4>{{ t('modeling.editedCandidate') }}</h4>
            <pre>{{ candidateJson }}</pre>
          </div>
        </div>
      </details>
      <UiSpace
        ><UiButton
          :disabled="!editable || !dirty"
          :loading="busy === 'save'"
          @click="saveCandidate"
          >{{ t('modeling.saveCandidate') }}</UiButton
        >
        <UiButton :disabled="!editable || dirty" :loading="busy === 'validate'" @click="validate">{{
          t('modeling.validate')
        }}</UiButton>
        <UiButton :disabled="!editable" :loading="busy === 'discard'" @click="discard">{{
          t('modeling.discardProposal')
        }}</UiButton></UiSpace
      >
      <UiAlert v-if="dirty" type="warning">{{ t('modeling.saveBeforeValidation') }}</UiAlert>
      <UiCard v-if="validation" :title="t('modeling.validation')" size="small">
        <UiAlert v-if="!validationCurrent" type="warning">{{
          t('modeling.notApplicable')
        }}</UiAlert>
        <ul>
          <li v-for="check in validation.checks" :key="check.check_code">
            <UiTag
              :type="
                check.state === 'PASS' ? 'success' : check.state === 'NA' ? 'default' : 'warning'
              "
              size="small"
              >{{ t(`report.states.${check.state}`) }}</UiTag
            >
            {{ t(`modeling.checks.${check.check_code}`) }}
          </li>
        </ul>
        <ul>
          <li v-for="(issue, index) in validationIssues" :key="index">{{ issue }}</li>
        </ul>
        <details open>
          <summary>{{ t('modeling.planChanges') }}</summary>
          <pre>{{ pretty(validation.plan) }}</pre>
        </details>
        <dl>
          <dt>{{ t('modeling.planDigest') }}</dt>
          <dd class="mono">{{ validation.compiled_plan_digest }}</dd>
        </dl>
        <UiCheckbox
          :checked="validationCurrent && confirmedDigest === validation.compiled_plan_digest"
          :disabled="!validationCurrent || !!busy || !!pendingApplication"
          @update:checked="acceptPlan"
          >{{ t('modeling.confirmPlan') }}</UiCheckbox
        >
        <UiButton type="primary" :disabled="!canApply" :loading="busy === 'apply'" @click="apply">{{
          t('modeling.apply')
        }}</UiButton>
      </UiCard>
    </template>
  </section>
</template>

<style scoped>
.modeling-panel {
  display: grid;
  gap: var(--space-3);
}
.target,
.hint {
  color: var(--foreground-secondary);
}
.full-width {
  width: 100%;
}
.mono,
pre {
  font-family: var(--font-mono);
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 480px;
  overflow: auto;
  font-size: var(--font-caption);
}
dl {
  display: grid;
  grid-template-columns: minmax(90px, 1fr) minmax(0, 3fr);
  gap: var(--space-2);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
blockquote {
  margin: 6px 0;
  white-space: pre-wrap;
}
.diff {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}
:deep(.json-editor textarea) {
  font-family: var(--font-mono);
}
@media (max-width: 700px) {
  .diff {
    grid-template-columns: 1fr;
  }
}
</style>
