<script setup lang="ts">
import {
  NAlert,
  NButton,
  NEmpty,
  NFormItem,
  NInput,
  NRadioButton,
  NRadioGroup,
  NSpace,
} from 'naive-ui'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { EvidenceTrace } from '@/api/graph'
import { graphApi } from '@/api/graph'
import EvidenceTable from '@/components/EvidenceTable.vue'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const mode = ref('entity')
const iri = ref('')
const subject = ref('')
const predicate = ref('')
const object = ref('')
watch(
  () => route.query,
  (query) => {
    mode.value = query.subject ? 'fact' : 'entity'
    iri.value = String(query.iri ?? '')
    subject.value = String(query.subject ?? '')
    predicate.value = String(query.predicate ?? '')
    object.value = String(query.object ?? '')
  },
  { immediate: true },
)
const { data, error, loading, reload } = useAsyncData<EvidenceTrace>((signal) => {
  const query = route.query
  const graphId = query.graph ? Number(query.graph) : undefined
  if (query.iri) return graphApi.entityEvidence(String(query.iri), graphId, signal)
  if (query.subject && query.predicate && query.object) {
    return graphApi.factEvidence(
      {
        subject: String(query.subject),
        predicate: String(query.predicate),
        object: String(query.object),
      },
      graphId,
      signal,
    )
  }
  return Promise.resolve(null)
})
async function search() {
  await router.replace({
    name: 'graph-evidence',
    query: {
      graph: route.query.graph,
      ...(mode.value === 'entity'
        ? { iri: iri.value }
        : { subject: subject.value, predicate: predicate.value, object: object.value }),
    },
  })
  reload()
}
</script>

<template>
  <section class="graph-page">
    <NSpace justify="space-between" align="center">
      <h2>{{ t('page.graphEvidence') }}</h2>
      <RouterLink :to="{ name: 'graph-entities', query: { graph: route.query.graph } }">{{
        t('page.graphEntities')
      }}</RouterLink>
    </NSpace>
    <form @submit.prevent="search">
      <NRadioGroup v-model:value="mode" :aria-label="t('graph.traceMode')" class="modes">
        <NRadioButton value="entity">{{ t('graph.byEntity') }}</NRadioButton>
        <NRadioButton value="fact">{{ t('graph.byFact') }}</NRadioButton>
      </NRadioGroup>
      <NFormItem v-if="mode === 'entity'" :label="t('common.iri')">
        <NInput
          v-model:value="iri"
          :aria-label="t('common.iri')"
          :placeholder="t('graph.entityIri')"
        />
      </NFormItem>
      <template v-else>
        <NFormItem :label="t('graph.subject')"
          ><NInput
            v-model:value="subject"
            :aria-label="t('graph.subject')"
            :placeholder="t('graph.subject')"
        /></NFormItem>
        <NFormItem :label="t('graph.predicate')"
          ><NInput
            v-model:value="predicate"
            :aria-label="t('graph.predicate')"
            :placeholder="t('graph.predicate')"
        /></NFormItem>
        <NFormItem :label="t('graph.object')"
          ><NInput
            v-model:value="object"
            :aria-label="t('graph.object')"
            :placeholder="t('graph.object')"
        /></NFormItem>
      </template>
      <NButton
        attr-type="submit"
        type="primary"
        :loading="loading"
        :disabled="mode === 'entity' ? !iri : !subject || !predicate || !object"
        >{{ t('graph.trace') }}</NButton
      >
    </form>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <template v-if="data">
      <p>
        {{ t('graph.resultSet', { id: data.graph_revision_id }) }} ·
        {{ t('graph.totalEvidence', { n: data.total_count }) }}
      </p>
      <NAlert v-if="data.quarantined_count" type="warning">{{
        t('graph.quarantineWarning')
      }}</NAlert>
      <EvidenceTable v-if="data.total_count" :items="data.evidences" />
      <NEmpty v-else :description="t('graph.noEvidence')" />
    </template>
    <NEmpty v-else-if="!loading && !error" :description="t('graph.traceHint')" />
  </section>
</template>

<style scoped>
.graph-page {
  display: grid;
  gap: 16px;
}
h2,
p {
  margin: 0;
}
.modes {
  margin-bottom: 16px;
}
</style>
