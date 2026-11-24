<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  FrozenResource,
  FrozenResourceBrief,
  FrozenRule,
  RevisionContents,
} from '@/api/ontology-history'
import { ontologyHistoryApi } from '@/api/ontology-history'
import {
  UiAlert,
  UiButton,
  UiCard,
  UiDescriptions,
  UiDescriptionsItem,
  UiEmpty,
  UiSpace,
} from '@/components/ui'

import GovernanceIdentity from '../../components/GovernanceIdentity.vue'

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
  return labels?.[locale.value]?.trim() || `${fallback} (${t('enumDictionaries.untranslated')})`
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
function resourceVersion(item: FrozenResourceBrief) {
  return `${label(item.label_i18n, item.name)} · ${t('ontologyHistory.version', {
    revision: item.revision,
  })}`
}
watch(() => [props.ontologyId, props.revision], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => {
  listController?.abort()
  cancelDetail()
})
</script>

<template>
  <UiCard class="governance-page" :title="t('ontologyHistory.title', { revision })">
    <p>{{ t('ontologyHistory.hint') }}</p>
    <UiAlert v-if="error" type="error" role="alert">{{ error }}</UiAlert>
    <UiButton :loading="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
    <p v-if="loading || detailLoading" role="status">{{ t('common.loading') }}</p>
    <div class="history-workspace">
      <aside class="history-register">
        <template v-if="contents">
          <h3>{{ t('ontologyHistory.resources') }}</h3>
          <UiEmpty v-if="!contents.resources.length" :description="t('ontologyHistory.empty')" />
          <div class="history-rows">
            <UiButton
              v-for="item in contents.resources"
              :key="item.resource_id"
              :class="{ 'history-selected': resource?.resource_id === item.resource_id }"
              :aria-label="resourceVersion(item)"
              @click="open('resource', item.resource_id)"
            >
              {{ label(item.label_i18n, item.name) }}
              <span class="mono"> · {{ item.name }}</span> ·
              {{ t('ontologyHistory.version', { revision: item.revision }) }}
            </UiButton>
          </div>
          <h3>{{ t('ontologyHistory.rules') }}</h3>
          <UiEmpty v-if="!contents.rules.length" :description="t('ontologyHistory.empty')" />
          <div class="history-rows">
            <UiButton
              v-for="item in contents.rules"
              :key="item.rule_id"
              :class="{ 'history-selected': rule?.rule_id === item.rule_id }"
              :aria-label="`${item.identifier} · ${t('ontologyHistory.version', { revision: item.revision })}`"
              @click="open('rule', item.rule_id)"
            >
              {{ item.identifier }} ·
              {{ t('ontologyHistory.version', { revision: item.revision }) }}
            </UiButton>
          </div>
        </template>
      </aside>
      <section class="history-inspector">
        <UiEmpty
          v-if="!resource && !rule && !detailLoading"
          :description="t('ontologyHistory.hint')"
        />
        <section v-if="resource && snapshot" class="detail" aria-live="polite">
          <div class="exchange-identity">
            <GovernanceIdentity
              :name="snapshot.name"
              :iri="snapshot.iri"
              :revision="resource.revision"
              :context="t('ontologyHistory.hint')"
            />
          </div>
          <h3>{{ label(snapshot.label_i18n, snapshot.name) }}</h3>
          <UiDescriptions :column="1" bordered>
            <UiDescriptionsItem :label="t('ontologyHistory.versionLabel')">{{
              resource.revision
            }}</UiDescriptionsItem>
            <UiDescriptionsItem :label="t('ontologyHistory.iri')">{{
              snapshot.iri
            }}</UiDescriptionsItem>
            <UiDescriptionsItem :label="t('ontologyHistory.definition')">{{
              label(snapshot.definition_i18n)
            }}</UiDescriptionsItem>
            <UiDescriptionsItem :label="t('ontologyHistory.namespace')"
              >{{ snapshot.namespace.prefix }} · {{ snapshot.namespace.iri }}</UiDescriptionsItem
            >
            <UiDescriptionsItem :label="t('ontologyHistory.checksum')">{{
              resource.checksum
            }}</UiDescriptionsItem>
          </UiDescriptions>
          <h4>{{ t('ontologyHistory.references') }}</h4>
          <UiAlert v-if="missingDependencies" type="warning">{{
            t('ontologyHistory.missingPins')
          }}</UiAlert>
          <UiSpace>
            <UiButton
              v-for="id in snapshot.parent_ids"
              :key="`parent-${id}`"
              :disabled="!contents?.resources.some((item) => item.resource_id === id)"
              @click="open('resource', id)"
            >
              {{ t('ontologyHistory.parent') }} · {{ resourceLabel(id) }}
            </UiButton>
            <UiButton
              v-for="link in snapshot.resource_refs"
              :key="`${link.role}-${link.target_id}`"
              :disabled="!contents?.resources.some((item) => item.resource_id === link.target_id)"
              @click="open('resource', link.target_id)"
            >
              {{ t(`ontologyHistory.roles.${link.role}`) }} · {{ resourceLabel(link.target_id) }}
            </UiButton>
          </UiSpace>
          <UiAlert
            v-if="snapshot.kind === 'DATATYPE_PROP' && !snapshot.datatype_props?.length"
            type="warning"
            >{{ t('ontologyHistory.missingProperty') }}</UiAlert
          >
          <section v-for="prop in snapshot.datatype_props" :key="prop.iri" class="property">
            <h4>{{ label(prop.label_i18n, prop.name) }}</h4>
            <UiDescriptions :column="1" bordered>
              <UiDescriptionsItem :label="t('ontologyHistory.iri')">{{
                prop.iri
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.datatype')">{{
                prop.datatype
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.nullable')">{{
                t(prop.nullable ? 'ontologyHistory.yes' : 'ontologyHistory.no')
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.default')">{{
                prop.default_value ?? '—'
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.cardinality')"
                >{{ prop.min_cardinality ?? '—' }} /
                {{ prop.max_cardinality ?? '—' }}</UiDescriptionsItem
              >
              <UiDescriptionsItem :label="t('ontologyHistory.range')"
                >{{ prop.min_value ?? '—' }} / {{ prop.max_value ?? '—' }}</UiDescriptionsItem
              >
              <UiDescriptionsItem :label="t('ontologyHistory.source')">{{
                prop.source_clause_ref || '—'
              }}</UiDescriptionsItem>
              <UiDescriptionsItem v-if="prop.enum_dictionary" :label="t('ontologyHistory.enum')">
                {{ label(prop.enum_dictionary.label_i18n, prop.enum_dictionary.name) }} ·
                {{ t('ontologyHistory.version', { revision: prop.enum_dictionary.revision }) }}
                <ul>
                  <li v-for="entry in prop.enum_dictionary.entries" :key="entry.value">
                    {{ entry.value }} · {{ label(entry.label_i18n) }}
                  </li>
                </ul>
              </UiDescriptionsItem>
            </UiDescriptions>
          </section>
          <template v-if="snapshot.object_prop">
            <h4>{{ t('ontologyHistory.relationConstraints') }}</h4>
            <UiDescriptions :column="1" bordered>
              <UiDescriptionsItem :label="t('ontologyHistory.domain')"
                >{{ snapshot.object_prop.domain_cardinality.min }} /
                {{ snapshot.object_prop.domain_cardinality.max }}</UiDescriptionsItem
              >
              <UiDescriptionsItem :label="t('ontologyHistory.rangeSide')"
                >{{ snapshot.object_prop.range_cardinality.min }} /
                {{ snapshot.object_prop.range_cardinality.max }}</UiDescriptionsItem
              >
              <UiDescriptionsItem
                v-for="(enabled, feature) in snapshot.object_prop.owl"
                :key="feature"
                :label="t(`ontologyHistory.features.${feature}`)"
                >{{ t(enabled ? 'ontologyHistory.yes' : 'ontologyHistory.no') }}</UiDescriptionsItem
              >
            </UiDescriptions>
          </template>
        </section>
        <section v-if="rule" class="detail" aria-live="polite">
          <h3>
            {{ rule.identifier }} · {{ t('ontologyHistory.version', { revision: rule.revision }) }}
          </h3>
          <p>{{ rule.source_reference }}</p>
          <UiAlert v-if="rule.snapshot_state === 'UNAVAILABLE'" type="warning">{{
            t('ontologyHistory.unavailable')
          }}</UiAlert>
          <template v-else-if="rule.snapshot">
            <UiDescriptions :column="1" bordered>
              <UiDescriptionsItem :label="t('ontologyHistory.name')">{{
                label(rule.snapshot.name_i18n)
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.target')">{{
                rule.snapshot.target_iri
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.language')">{{
                rule.snapshot.language
              }}</UiDescriptionsItem>
              <UiDescriptionsItem :label="t('ontologyHistory.execution')">{{
                rule.snapshot.execution
              }}</UiDescriptionsItem>
            </UiDescriptions>
            <h4>{{ t('ontologyHistory.expression') }}</h4>
            <pre>{{ rule.snapshot.expression }}</pre>
            <h4>{{ t('ontologyHistory.positive') }}</h4>
            <pre>{{ rule.snapshot.positive_example || '—' }}</pre>
            <h4>{{ t('ontologyHistory.negative') }}</h4>
            <pre>{{ rule.snapshot.negative_example || '—' }}</pre>
          </template>
        </section>
      </section>
    </div>
  </UiCard>
</template>

<style scoped>
.detail {
  border-top: 1px solid var(--border);
  margin-top: 20px;
  padding-top: 12px;
}
.property {
  margin-top: 16px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  padding: 12px;
}
p,
.detail {
  overflow-wrap: anywhere;
}
</style>

<style scoped src="../../styles/observatory.css"></style>
