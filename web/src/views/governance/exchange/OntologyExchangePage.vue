<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type { Ontology, OntologyExportFormat } from '@/api/ontology'
import { ontologyApi } from '@/api/ontology'
import type { RestoreResult } from '@/api/ontology-restore'
import PageHeader from '@/components/PageHeader.vue'
import {
  FormContainer,
  FormField,
  UiAlert,
  UiButton,
  UiEmpty,
  UiInputNumber,
  UiSelect,
  UiSpace,
  UiTabPane,
  UiTabs,
} from '@/components/ui'
import OntologyHistory from '@/views/governance/exchange/components/OntologyHistory.vue'
import OntologyRestore from '@/views/governance/exchange/components/OntologyRestore.vue'

import GovernanceIdentity from '../components/GovernanceIdentity.vue'

const { t, locale } = useI18n()
const route = useRoute()
const activeTab = ref('export')
const ontologies = ref<Ontology[]>([])
const selectedId = ref<number | null>(null)
const revision = ref<number | null>(null)
watch(
  () => [route.query.ontology, route.query.revision],
  ([ontology, version]) => {
    const id = Number(ontology)
    const rev = Number(version)
    selectedId.value = Number.isSafeInteger(id) && id > 0 ? id : null
    revision.value = Number.isSafeInteger(rev) && rev > 0 ? rev : null
  },
  { immediate: true },
)
const format = ref<OntologyExportFormat>('turtle')
const loading = ref(false)
const downloading = ref(false)
const error = ref('')
const success = ref(false)
const controller = new AbortController()
const options = computed(() =>
  ontologies.value.map((ontology) => ({
    value: ontology.id,
    label: `${ontology.label_i18n?.[locale.value]?.trim() || t('enumDictionaries.untranslated')} · ${ontology.name}`,
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
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const items: Ontology[] = []
    for (let page = 1; ; page++) {
      const data = await ontologyApi.list({ page, page_size: 200 }, controller.signal)
      items.push(...data)
      if (data.length < 200) break
    }
    if (!controller.signal.aborted) ontologies.value = items
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
  if (
    !selected.value ||
    selected.value.current_revision < 1 ||
    downloading.value ||
    loading.value ||
    error.value
  )
    return
  const ontology = selected.value
  const selectedFormat = format.value
  const selectedRevision = revision.value ?? ontology.current_revision
  if (
    !Number.isSafeInteger(selectedRevision) ||
    selectedRevision < 1 ||
    selectedRevision > ontology.current_revision
  )
    return
  downloading.value = true
  error.value = ''
  success.value = false
  try {
    const data = await ontologyApi.export(
      ontology.id,
      { format: selectedFormat, revision: selectedRevision },
      controller.signal,
    )
    if (controller.signal.aborted) return
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = `${ontology.name.replace(/[^a-zA-Z0-9_-]/g, '_')}-r${selectedRevision}.${selectedFormat === 'turtle' ? 'ttl' : 'jsonld'}`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    success.value = true
  } catch (err) {
    if (controller.signal.aborted) return
    const detail = err as { params?: { reason?: string } } | null
    error.value = t('export.failed', {
      reason: detail?.params?.reason || errorCode(err),
    })
  } finally {
    downloading.value = false
  }
}

onMounted(load)
async function restored(result: RestoreResult) {
  await load()
  if (controller.signal.aborted) return
  selectedId.value = result.ontology_id
  revision.value = result.current_revision
}
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <section class="export-page governance-page">
    <PageHeader :title="t('ui.exchange')" :description="t('governanceUi.exchangeIntro')" />
    <UiTabs v-model:value="activeTab" type="line" class="exchange-tabs">
      <UiTabPane name="export" :tab="t('governanceUi.exportTab')" display-directive="show">
        <UiAlert v-if="error" type="error" role="alert"
          >{{ error }}
          <UiButton @click="load">{{ t('governanceUi.retry') }}</UiButton>
        </UiAlert>
        <UiAlert v-if="success" type="success" role="status">{{ t('export.downloaded') }}</UiAlert>
        <p v-if="loading" role="status">{{ t('common.loading') }}</p>
        <UiEmpty
          v-else-if="!error && !ontologies.length"
          :description="t('governanceUi.noOntologies')"
        />
        <div class="exchange-workspace">
          <section class="exchange-controls">
            <header class="exchange-step-heading">
              <span class="exchange-step-number">{{ t('export.ontology') }}</span>
              <h2>{{ t('governanceUi.exportTab') }}</h2>
              <p>{{ t('export.snapshotHint') }}</p>
            </header>
            <FormContainer label-placement="top" :disabled="downloading || loading">
              <FormField :label="t('export.ontology')">
                <UiSelect
                  v-model:value="selectedId"
                  :options="options"
                  :loading="loading"
                  filterable
                  :placeholder="t('export.selectOntology')"
                  @update:value="resetSelection"
                />
              </FormField>
              <FormField :label="t('export.revision')">
                <UiInputNumber
                  v-model:value="revision"
                  :min="1"
                  :max="selected?.current_revision || undefined"
                  :precision="0"
                  clearable
                  :placeholder="t('export.latest')"
                />
              </FormField>
              <FormField :label="t('export.format')"
                ><UiSelect v-model:value="format" :options="formats"
              /></FormField>
              <UiSpace class="actions">
                <UiButton
                  type="primary"
                  :disabled="!selected || !selected.current_revision || loading || !!error"
                  :loading="downloading"
                  @click="download"
                  >{{ t('export.download') }}</UiButton
                >
                <UiButton :disabled="downloading" :loading="loading" @click="load">{{
                  t('graph.refresh')
                }}</UiButton>
              </UiSpace>
            </FormContainer>
          </section>
          <section class="exchange-inspector">
            <header class="exchange-preview-heading">
              <h2>{{ t('common.revision') }}</h2>
              <span>{{ t('export.snapshotHint') }}</span>
            </header>
            <div v-if="selected" class="exchange-identity">
              <GovernanceIdentity
                :name="selected.name"
                :iri="selected.iri"
                :revision="revision ?? selected.current_revision"
                :context="t('export.snapshotHint')"
              />
            </div>
            <OntologyHistory
              v-if="!loading && !error && selected && (revision ?? selected.current_revision) > 0"
              :ontology-id="selected.id"
              :revision="revision ?? selected.current_revision"
            />
            <UiEmpty v-else :description="t('export.selectOntology')" />
          </section>
        </div>
      </UiTabPane>
      <UiTabPane name="import" :tab="t('governanceUi.importTab')" display-directive="show">
        <OntologyRestore @restored="restored" />
      </UiTabPane>
    </UiTabs>
  </section>
</template>

<style scoped>
.export-page {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.exchange-tabs {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  padding: 12px 20px 20px;
}
.exchange-tabs :deep(.ui-tab-pane) {
  display: grid;
  gap: 16px;
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

<style scoped src="../styles/observatory.css"></style>
