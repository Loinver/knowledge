<script setup lang="ts">
import { NAlert, NButton, NCard, NDescriptions, NDescriptionsItem, NEmpty, NSpace } from 'naive-ui'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FrozenResource, FrozenRule, RevisionContents } from '@/api/ontology-history'
import { ontologyHistoryApi } from '@/api/ontology-history'

const props = defineProps<{ ontologyId: number; revision: number }>()
const { t, locale } = useI18n()
const contents = ref<RevisionContents | null>(null)
const resource = ref<FrozenResource | null>(null)
const rule = ref<FrozenRule | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
let listController: AbortController | null = null
let detailController: AbortController | null = null
const snapshot = computed(() => resource.value?.snapshot)
const missingDependencies = computed(() => {
  const pinned = new Set(contents.value?.resources.map((item) => item.resource_id))
  return [
    ...(snapshot.value?.parent_ids ?? []),
    ...(snapshot.value?.resource_refs.map((item) => item.target_id) ?? []),
  ].some((id) => !pinned.has(id))
})

function label(labels: Record<string, string> | null | undefined, fallback = '—') {
  return labels?.[locale.value] || labels?.['zh-CN'] || labels?.['en-US'] || fallback
}
function fail(err: unknown) {
  const code = err && typeof err === 'object' && 'code' in err ? String(err.code) : 'NETWORK_ERROR'
  return t('rules.requestFailed', { code })
}
function cancelDetail() {
  detailController?.abort()
  resource.value = null
  rule.value = null
  detailLoading.value = false
}
async function load() {
  listController?.abort()
  cancelDetail()
  contents.value = null
  error.value = ''
  const request = new AbortController()
  listController = request
  loading.value = true
  try {
    const result = await ontologyHistoryApi.contents(
      props.ontologyId,
      props.revision,
      request.signal,
    )
    if (!request.signal.aborted) contents.value = result
  } catch (err) {
    if (!request.signal.aborted) error.value = fail(err)
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
async function open(kind: 'resource' | 'rule', id: number) {
  cancelDetail()
  error.value = ''
  const request = new AbortController()
  detailController = request
  detailLoading.value = true
  try {
    if (kind === 'resource') {
      const result = await ontologyHistoryApi.resource(
        props.ontologyId,
        props.revision,
        id,
        request.signal,
      )
      if (!request.signal.aborted) resource.value = result
    } else {
      const result = await ontologyHistoryApi.rule(
        props.ontologyId,
        props.revision,
        id,
        request.signal,
      )
      if (!request.signal.aborted) rule.value = result
    }
  } catch (err) {
    if (!request.signal.aborted) error.value = fail(err)
  } finally {
    if (!request.signal.aborted) detailLoading.value = false
  }
}
function resourceLabel(id: number) {
  const entry = contents.value?.resources.find((item) => item.resource_id === id)
  return entry ? label(entry.label_i18n, entry.name) : String(id)
}
watch(() => [props.ontologyId, props.revision], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => {
  listController?.abort()
  cancelDetail()
})
</script>

<template>
  <NCard :title="t('ontologyHistory.title', { revision })">
    <p>{{ t('ontologyHistory.hint') }}</p>
    <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
    <NButton :loading="loading" @click="load">{{ t('graph.refresh') }}</NButton>
    <p v-if="loading || detailLoading" role="status">{{ t('common.loading') }}</p>
    <template v-if="contents">
      <h3>{{ t('ontologyHistory.resources') }}</h3>
      <NEmpty v-if="!contents.resources.length" :description="t('ontologyHistory.empty')" />
      <NSpace>
        <NButton
          v-for="item in contents.resources"
          :key="item.resource_id"
          @click="open('resource', item.resource_id)"
        >
          {{ label(item.label_i18n, item.name) }}
          <span v-if="item.kind === 'DATATYPE_PROP'"> · {{ item.name }}</span> ·
          {{ t('ontologyHistory.version', { revision: item.revision }) }}
        </NButton>
      </NSpace>
      <h3>{{ t('ontologyHistory.rules') }}</h3>
      <NEmpty v-if="!contents.rules.length" :description="t('ontologyHistory.empty')" />
      <NSpace>
        <NButton
          v-for="item in contents.rules"
          :key="item.rule_id"
          @click="open('rule', item.rule_id)"
        >
          {{ item.identifier }} · {{ t('ontologyHistory.version', { revision: item.revision }) }}
        </NButton>
      </NSpace>
    </template>
    <section v-if="resource && snapshot" class="detail" aria-live="polite">
      <h3>{{ label(snapshot.label_i18n, snapshot.name) }}</h3>
      <NDescriptions :column="1" bordered>
        <NDescriptionsItem :label="t('ontologyHistory.versionLabel')">{{
          resource.revision
        }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('ontologyHistory.iri')">{{ snapshot.iri }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('ontologyHistory.definition')">{{
          label(snapshot.definition_i18n)
        }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('ontologyHistory.namespace')"
          >{{ snapshot.namespace.prefix }} · {{ snapshot.namespace.iri }}</NDescriptionsItem
        >
        <NDescriptionsItem :label="t('ontologyHistory.checksum')">{{
          resource.checksum
        }}</NDescriptionsItem>
      </NDescriptions>
      <h4>{{ t('ontologyHistory.references') }}</h4>
      <NAlert v-if="missingDependencies" type="warning">{{
        t('ontologyHistory.missingPins')
      }}</NAlert>
      <NSpace>
        <NButton
          v-for="id in snapshot.parent_ids"
          :key="`parent-${id}`"
          :disabled="!contents?.resources.some((item) => item.resource_id === id)"
          @click="open('resource', id)"
        >
          {{ t('ontologyHistory.parent') }} · {{ resourceLabel(id) }}
        </NButton>
        <NButton
          v-for="link in snapshot.resource_refs"
          :key="`${link.role}-${link.target_id}`"
          :disabled="!contents?.resources.some((item) => item.resource_id === link.target_id)"
          @click="open('resource', link.target_id)"
        >
          {{ t(`ontologyHistory.roles.${link.role}`) }} · {{ resourceLabel(link.target_id) }}
        </NButton>
      </NSpace>
      <NAlert
        v-if="snapshot.kind === 'DATATYPE_PROP' && !snapshot.datatype_props?.length"
        type="warning"
        >{{ t('ontologyHistory.missingProperty') }}</NAlert
      >
      <section v-for="prop in snapshot.datatype_props" :key="prop.iri" class="property">
        <h4>{{ label(prop.label_i18n, prop.name) }}</h4>
        <NDescriptions :column="1" bordered>
          <NDescriptionsItem :label="t('ontologyHistory.iri')">{{ prop.iri }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.datatype')">{{
            prop.datatype
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.nullable')">{{
            t(prop.nullable ? 'ontologyHistory.yes' : 'ontologyHistory.no')
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.default')">{{
            prop.default_value ?? '—'
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.cardinality')"
            >{{ prop.min_cardinality ?? '—' }} /
            {{ prop.max_cardinality ?? '—' }}</NDescriptionsItem
          >
          <NDescriptionsItem :label="t('ontologyHistory.range')"
            >{{ prop.min_value ?? '—' }} / {{ prop.max_value ?? '—' }}</NDescriptionsItem
          >
          <NDescriptionsItem :label="t('ontologyHistory.source')">{{
            prop.source_clause_ref || '—'
          }}</NDescriptionsItem>
          <NDescriptionsItem v-if="prop.enum_dictionary" :label="t('ontologyHistory.enum')">
            {{ label(prop.enum_dictionary.label_i18n, prop.enum_dictionary.name) }} ·
            {{ t('ontologyHistory.version', { revision: prop.enum_dictionary.revision }) }}
            <ul>
              <li v-for="entry in prop.enum_dictionary.entries" :key="entry.value">
                {{ entry.value }} · {{ label(entry.label_i18n) }}
              </li>
            </ul>
          </NDescriptionsItem>
        </NDescriptions>
      </section>
      <template v-if="snapshot.object_prop">
        <h4>{{ t('ontologyHistory.relationConstraints') }}</h4>
        <NDescriptions :column="1" bordered>
          <NDescriptionsItem :label="t('ontologyHistory.domain')"
            >{{ snapshot.object_prop.domain_cardinality.min }} /
            {{ snapshot.object_prop.domain_cardinality.max }}</NDescriptionsItem
          >
          <NDescriptionsItem :label="t('ontologyHistory.rangeSide')"
            >{{ snapshot.object_prop.range_cardinality.min }} /
            {{ snapshot.object_prop.range_cardinality.max }}</NDescriptionsItem
          >
          <NDescriptionsItem
            v-for="(enabled, feature) in snapshot.object_prop.owl"
            :key="feature"
            :label="t(`ontologyHistory.features.${feature}`)"
            >{{ t(enabled ? 'ontologyHistory.yes' : 'ontologyHistory.no') }}</NDescriptionsItem
          >
        </NDescriptions>
      </template>
    </section>
    <section v-if="rule" class="detail" aria-live="polite">
      <h3>
        {{ rule.identifier }} · {{ t('ontologyHistory.version', { revision: rule.revision }) }}
      </h3>
      <p>{{ rule.source_reference }}</p>
      <NAlert v-if="rule.snapshot_state === 'UNAVAILABLE'" type="warning">{{
        t('ontologyHistory.unavailable')
      }}</NAlert>
      <template v-else-if="rule.snapshot">
        <NDescriptions :column="1" bordered>
          <NDescriptionsItem :label="t('ontologyHistory.name')">{{
            label(rule.snapshot.name_i18n)
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.target')">{{
            rule.snapshot.target_iri
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.language')">{{
            rule.snapshot.language
          }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('ontologyHistory.execution')">{{
            rule.snapshot.execution
          }}</NDescriptionsItem>
        </NDescriptions>
        <h4>{{ t('ontologyHistory.expression') }}</h4>
        <pre>{{ rule.snapshot.expression }}</pre>
        <h4>{{ t('ontologyHistory.positive') }}</h4>
        <pre>{{ rule.snapshot.positive_example || '—' }}</pre>
        <h4>{{ t('ontologyHistory.negative') }}</h4>
        <pre>{{ rule.snapshot.negative_example || '—' }}</pre>
      </template>
    </section>
  </NCard>
</template>

<style scoped>
.detail {
  border-top: 1px solid var(--border-color);
  margin-top: 20px;
  padding-top: 12px;
}
.property {
  margin-top: 16px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--bg-secondary);
  padding: 12px;
}
p,
.detail {
  overflow-wrap: anywhere;
}
</style>
