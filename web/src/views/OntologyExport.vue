<script setup lang="ts">
import { NAlert, NButton, NCard, NForm, NFormItem, NInputNumber, NSelect, NSpace } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Ontology = components['schemas']['OntologyBrief']
const { t, locale } = useI18n()
const ontologies = ref<Ontology[]>([])
const selectedId = ref<number | null>(null)
const revision = ref<number | null>(null)
const format = ref<'turtle' | 'json-ld'>('turtle')
const loading = ref(false)
const downloading = ref(false)
const error = ref('')
const success = ref(false)
const controller = new AbortController()
const options = computed(() =>
  ontologies.value.map((ontology) => ({
    value: ontology.id,
    label: `${ontology.label_i18n?.[locale.value] || ontology.name} · ${ontology.name}`,
    disabled: ontology.current_revision === 0,
  })),
)
const formats = computed(() => [
  { value: 'turtle', label: t('export.formats.turtle') },
  { value: 'json-ld', label: t('export.formats.jsonld') },
])
const selected = computed(() => ontologies.value.find((item) => item.id === selectedId.value))

function resetSelection() {
  revision.value = null
  success.value = false
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const items: Ontology[] = []
    for (let page = 1; ; page++) {
      const { data } = await http.get<Ontology[]>('/ontologies', {
        params: { page, page_size: 200 },
        signal: controller.signal,
      })
      items.push(...data)
      if (data.length < 200) break
    }
    ontologies.value = items
  } catch (err) {
    if (!controller.signal.aborted) error.value = t('rules.requestFailed', { code: errorCode(err) })
  } finally {
    loading.value = false
  }
}

function errorCode(err: unknown) {
  return err && typeof err === 'object' && 'code' in err ? String(err.code) : 'NETWORK_ERROR'
}

async function download() {
  if (!selected.value || downloading.value) return
  const ontology = selected.value
  const selectedFormat = format.value
  const selectedRevision = revision.value ?? ontology.current_revision
  downloading.value = true
  error.value = ''
  success.value = false
  try {
    const { data } = await http.get<Blob>(`/ontologies/${ontology.id}/export`, {
      params: { format: selectedFormat, revision: selectedRevision },
      responseType: 'blob',
      signal: controller.signal,
    })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = `${ontology.name.replace(/[^a-zA-Z0-9_-]/g, '_')}-r${selectedRevision}.${selectedFormat === 'turtle' ? 'ttl' : 'jsonld'}`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    success.value = true
  } catch (err) {
    if (controller.signal.aborted) return
    const body = (err as { response?: { data?: Blob } })?.response?.data
    let detail: { code?: string; params?: { reason?: string } } = {}
    if (body instanceof Blob) {
      try {
        detail = JSON.parse(await body.text())
      } catch {
        /* Non-JSON errors use the fallback below. */
      }
    }
    error.value = t('export.failed', {
      reason: detail.params?.reason || detail.code || errorCode(err),
    })
  } finally {
    downloading.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <section class="export-page">
    <h2>{{ t('export.title') }}</h2>
    <p>{{ t('export.intro') }}</p>
    <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
    <NAlert v-if="success" type="success" role="status">{{ t('export.downloaded') }}</NAlert>
    <NCard>
      <NForm label-placement="top" :disabled="downloading">
        <NFormItem :label="t('export.ontology')">
          <NSelect
            v-model:value="selectedId"
            :options="options"
            :loading="loading"
            filterable
            :placeholder="t('export.selectOntology')"
            @update:value="resetSelection"
          />
        </NFormItem>
        <NFormItem :label="t('export.revision')">
          <NInputNumber
            v-model:value="revision"
            :min="1"
            :max="selected?.current_revision || undefined"
            :precision="0"
            clearable
            :placeholder="t('export.latest')"
          />
        </NFormItem>
        <NFormItem :label="t('export.format')"
          ><NSelect v-model:value="format" :options="formats"
        /></NFormItem>
        <NAlert type="info">{{ t('export.snapshotHint') }}</NAlert>
        <NSpace class="actions">
          <NButton
            type="primary"
            :disabled="!selected || loading"
            :loading="downloading"
            @click="download"
            >{{ t('export.download') }}</NButton
          >
          <NButton :disabled="downloading" :loading="loading" @click="load">{{
            t('graph.refresh')
          }}</NButton>
        </NSpace>
      </NForm>
    </NCard>
  </section>
</template>

<style scoped>
.export-page {
  display: grid;
  gap: 16px;
  max-width: 880px;
}
h2,
p {
  margin: 0;
}
p {
  color: var(--text-secondary);
}
.actions {
  margin-top: 24px;
}
</style>
