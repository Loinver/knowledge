<script setup lang="ts">
import { NAlert, NButton, NCard, NFormItem, NInput, NSelect, NSpace } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { RestoreInput, RestorePreview, RestoreResult } from '@/api/ontology-restore'
import { ontologyRestoreApi } from '@/api/ontology-restore'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useGovernanceAccess } from '@/views/governance/composables/useGovernanceAccess'

const { t } = useI18n()
const { canWrite } = useGovernanceAccess()
const emit = defineEmits<{ restored: [result: RestoreResult] }>()
const format = ref<RestoreInput['format']>('turtle')
const content = ref('')
const preview = ref<RestorePreview | null>(null)
const loading = ref(false)
const error = ref('')
const applying = ref(false)
const restored = ref<RestoreResult | null>(null)
// This inline form survives tab changes; protect route/unload until its content is imported.
const draftOpen = ref(true)
useDraftGuard(
  draftOpen,
  () => !restored.value && (!!content.value || format.value !== 'turtle'),
  () => canWrite.value,
)
let controller: AbortController | null = null
let generation = 0
const formats = computed(() => [
  { value: 'turtle', label: t('export.formats.turtle') },
  { value: 'json-ld', label: t('export.formats.jsonld') },
])

function invalidate() {
  generation++
  controller?.abort()
  preview.value = null
  error.value = ''
  loading.value = false
  restored.value = null
}
watch([content, format], invalidate, { flush: 'sync' })

async function loadFile(event: Event) {
  if (!canWrite.value || applying.value) return
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  invalidate()
  const owner = generation
  if (file.size > 65536) {
    error.value = t('ontologyRestore.tooLarge')
    input.value = ''
    return
  }
  try {
    const text = await file.text()
    if (owner !== generation) return
    format.value =
      file.name.endsWith('.jsonld') || file.name.endsWith('.json') ? 'json-ld' : 'turtle'
    content.value = text
  } catch {
    if (owner === generation) error.value = t('ontologyRestore.readFailed')
  } finally {
    input.value = ''
  }
}

async function inspect() {
  if (!canWrite.value || !content.value.trim() || loading.value || applying.value) return
  invalidate()
  const owner = generation
  const request = new AbortController()
  controller = request
  loading.value = true
  try {
    const result = await ontologyRestoreApi.preview(
      { format: format.value, content: content.value },
      request.signal,
    )
    if (owner === generation) preview.value = result
  } catch (err) {
    if (owner === generation) {
      const code =
        err && typeof err === 'object' && 'code' in err ? String(err.code) : 'NETWORK_ERROR'
      error.value = t('rules.requestFailed', { code })
    }
  } finally {
    if (owner === generation) loading.value = false
  }
}

async function apply() {
  if (!canWrite.value || !preview.value?.can_apply || applying.value) return
  const payload = {
    format: format.value,
    content: content.value,
    preview_digest: preview.value.preview_digest,
  }
  const owner = generation
  const request = new AbortController()
  controller = request
  applying.value = true
  error.value = ''
  try {
    const result = await ontologyRestoreApi.apply(payload, request.signal)
    if (owner !== generation) return
    restored.value = result
    emit('restored', result)
  } catch (err) {
    if (owner === generation) {
      const code =
        err && typeof err === 'object' && 'code' in err ? String(err.code) : 'NETWORK_ERROR'
      error.value = t('ontologyRestore.applyFailed', { code })
    }
  } finally {
    if (owner === generation) preview.value = null
    applying.value = false
  }
}
onBeforeUnmount(invalidate)
</script>

<template>
  <NCard :title="t('ontologyRestore.title')">
    <NAlert v-if="!canWrite" type="info">{{ t('governanceUi.importReadOnly') }}</NAlert>
    <p>{{ t('ontologyRestore.intro') }}</p>
    <NFormItem :label="t('ontologyRestore.file')" label-for="ontology-restore-file">
      <input
        id="ontology-restore-file"
        type="file"
        accept=".ttl,.jsonld,.json"
        :disabled="applying || !canWrite"
        @change="loadFile"
      />
    </NFormItem>
    <NFormItem :label="t('export.format')">
      <NSelect
        v-model:value="format"
        :options="formats"
        :disabled="applying || !canWrite"
        :aria-label="t('export.format')"
      />
    </NFormItem>
    <NFormItem :label="t('ontologyRestore.content')" label-for="ontology-restore-content">
      <NInput
        v-model:value="content"
        type="textarea"
        :rows="6"
        :disabled="applying || !canWrite"
        :input-props="{ id: 'ontology-restore-content' }"
      />
    </NFormItem>
    <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
    <NAlert v-if="restored" type="success" role="status">
      {{
        t('ontologyRestore.restored', {
          id: restored.ontology_id,
          revision: restored.current_revision,
          source: restored.source_revision ?? '—',
        })
      }}
    </NAlert>
    <NSpace>
      <NButton
        :disabled="!canWrite || !content.trim() || applying"
        :loading="loading"
        @click="inspect"
      >
        {{ t('ontologyRestore.preview') }}
      </NButton>
      <NButton
        type="primary"
        :disabled="!canWrite || !preview?.can_apply || applying"
        :loading="applying"
        @click="apply"
      >
        {{ t('ontologyRestore.apply') }}
      </NButton>
    </NSpace>
    <section v-if="preview" class="preview" aria-live="polite">
      <NAlert :type="preview.can_apply ? 'success' : 'warning'">
        {{ t(preview.can_apply ? 'ontologyRestore.ready' : 'ontologyRestore.blocked') }}
      </NAlert>
      <p>
        {{
          t('ontologyRestore.summary', {
            name: preview.name || preview.root_iri || '—',
            resources: preview.resources.length,
            dictionaries: preview.enum_names.length,
            revision: preview.source_revision ?? '—',
          })
        }}
      </p>
      <ul v-if="preview.conflicts.length" class="issues">
        <li v-for="(issue, index) in preview.conflicts" :key="index">
          {{ issue.code }} · {{ issue.iri }}
        </li>
      </ul>
      <details v-if="preview.unsupported_triples.length">
        <summary>
          {{ t('ontologyRestore.unsupported', { count: preview.unsupported_triples.length }) }}
        </summary>
        <pre>{{ preview.unsupported_triples.join('\n') }}</pre>
      </details>
      <details>
        <summary>{{ t('ontologyRestore.resources') }}</summary>
        <ul>
          <li v-for="resource in preview.resources" :key="resource.iri">
            <strong>{{ resource.name }}</strong> · {{ t(`coreCheck.kinds.${resource.kind}`) }}
            <p>{{ resource.iri }}</p>
            <p v-if="resource.dependencies.length">
              {{ t('ontologyRestore.dependencies') }}: {{ resource.dependencies.join(', ') }}
            </p>
          </li>
        </ul>
      </details>
    </section>
  </NCard>
</template>

<style scoped>
.preview {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}
p,
li {
  overflow-wrap: anywhere;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
summary {
  cursor: pointer;
}
li + li {
  margin-top: 8px;
}
</style>
