<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { entityTypesApi } from '@/api/entity-types'
import type { RelationTypeDetail, RelationTypeUsages, TypeRuleUsage } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns } from '@/components/ui'
import {
  UiAlert,
  UiButton,
  UiDataTable,
  UiDescriptions,
  UiDescriptionsItem,
  UiEmpty,
  UiPopconfirm,
  UiSpace,
  UiSpin,
  UiTabPane,
  UiTabs,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { usePageIdentity } from '@/layout/navigation/usePageIdentity'
import { useAuthStore } from '@/stores/auth'

import AssetIdentity from '../components/AssetIdentity.vue'

const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const mutation = useOwnedMutation(() => route.params.id, toMessage)
const busy = mutation.busy
const error = ref('')
const notice = ref('')
const data = ref<RelationTypeDetail | null>(null)
/** 规则 / 引用与版本：一次请求取全，两个页签共用。 */
const usages = ref<RelationTypeUsages | null>(null)
const usagesLoading = ref(false)
const usagesError = ref('')
/** 端点 type_id → 类型标签，把端点显示成名字而不是裸 id。 */
const typeLabels = ref<Record<number, string>>({})
let loadGeneration = 0
let alive = true

usePageIdentity(() => data.value?.name)

const isDraft = computed(() => data.value?.status === 'DRAFT' && canWrite.value)

function localized(labels: Record<string, string> | null | undefined) {
  return labels?.[locale.value]?.trim() || t('enumDictionaries.untranslated')
}

/** 端点显示：优先类型标签，其次裸 id，避免空字符串看起来像没配。 */
function endpointName(typeId: number) {
  if (!typeId) return t('relationDetail.endpointMissing')
  return typeLabels.value[typeId] ?? `#${typeId}`
}

/** 基数 max = -1 表示无上限，不能直接显示成 "-1"。 */
function bound(value: number | undefined) {
  return value === undefined || value === -1 ? t('relationDetail.unbounded') : String(value)
}

const owlTags = computed(() => {
  const owl = data.value?.owl
  if (!owl) return []
  const pairs: [keyof typeof owl, string][] = [
    ['functional', 'functional'],
    ['inverse_functional', 'inverseFunctional'],
    ['symmetric', 'symmetric'],
    ['transitive', 'transitive'],
  ]
  return pairs.filter(([key]) => owl[key]).map(([, label]) => t(`relation.${label}`))
})

function failure(err: unknown) {
  return toMessage(err)
}

async function loadTypeLabels() {
  try {
    const list = await entityTypesApi.list({ page_size: 200 })
    const map: Record<number, string> = {}
    for (const item of list) {
      map[item.id] = localized(item.label_i18n)
    }
    typeLabels.value = map
  } catch {
    typeLabels.value = {}
  }
}

async function loadUsages(id: number, generation: number) {
  usagesLoading.value = true
  usagesError.value = ''
  try {
    const result = await relationsApi.usages(id)
    if (alive && generation === loadGeneration) usages.value = result
  } catch (cause) {
    if (alive && generation === loadGeneration) {
      usages.value = null
      usagesError.value = toMessage(cause)
    }
  } finally {
    if (alive && generation === loadGeneration) usagesLoading.value = false
  }
}

async function loadDetail() {
  const generation = ++loadGeneration
  data.value = null
  usages.value = null
  error.value = ''
  notice.value = ''
  const id = Number(route.params.id)
  if (!Number.isSafeInteger(id) || id <= 0) {
    error.value = t('relationDetail.notFound')
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await relationsApi.get(id)
    if (alive && generation === loadGeneration) data.value = result
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = failure(err)
  } finally {
    if (alive && generation === loadGeneration) loading.value = false
  }
  if (alive && generation === loadGeneration) void loadUsages(id, generation)
}

async function handlePublish() {
  if (!data.value || !isDraft.value || busy.value) return
  const id = data.value.id
  const generation = loadGeneration
  notice.value = ''
  const result = await mutation.run(() => relationsApi.publish(id))
  if (!alive || generation !== loadGeneration) return
  if (result) {
    await loadDetail()
    if (alive && Number(route.params.id) === id)
      notice.value = t('relationDetail.published', { revision: result.revision })
  } else if (mutation.error.value) {
    error.value = t('relationDetail.publishFailed')
  }
}

async function startRevision() {
  if (!canWrite.value || data.value?.status !== 'PUBLISHED' || busy.value) return
  const id = data.value.id
  const generation = loadGeneration
  error.value = ''
  const result = await mutation.run(async () => {
    await relationsApi.unpublish(id)
    return true
  })
  if (!alive || generation !== loadGeneration) return
  if (result) await loadDetail()
  else if (mutation.error.value) error.value = mutation.error.value
}

const ruleColumns = computed<DataTableColumns<TypeRuleUsage>>(() => [
  {
    title: t('rules.identifier'),
    key: 'identifier',
    minWidth: 160,
    render: (row: TypeRuleUsage) => h('span', { class: 'mono' }, row.identifier),
  },
  {
    title: t('common.label'),
    key: 'name_i18n',
    minWidth: 160,
    render: (row: TypeRuleUsage) => localized(row.name_i18n),
  },
  {
    title: t('rules.severity'),
    key: 'severity',
    width: 110,
    render: (row: TypeRuleUsage) => t(`rules.severities.${row.severity}`),
  },
])

watch(
  () => route.params.id,
  () => {
    void loadDetail()
    void loadTypeLabels()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  alive = false
  loadGeneration++
})
</script>

<template>
  <div class="asset-page asset-detail-page">
    <PageHeader
      :title="t('page.relationDetail')"
      :eyebrow="t('page.relationTypes')"
      :identity="data?.name"
    >
      <template #context>
        <strong v-if="data" class="detail-object-label">{{
          data.label_i18n?.[locale] || t('enumDictionaries.untranslated')
        }}</strong>
        <AssetIdentity
          v-if="data"
          :name="data.name"
          :iri="data.iri"
          :revision="data.current_revision"
          :status="data.status"
      /></template>
      <template #actions>
        <RouterLink :to="{ name: 'relation-types', query: route.query }">{{
          t('ui.backList')
        }}</RouterLink>
        <UiPopconfirm v-if="data?.status === 'PUBLISHED'" @positive-click="startRevision">
          <template #trigger
            ><UiButton :disabled="busy || !canWrite">{{
              t('common.startRevision')
            }}</UiButton></template
          >
          {{ t('common.startRevisionHint') }}
        </UiPopconfirm>
        <UiButton
          v-if="data && isDraft"
          :disabled="busy"
          @click="router.push({ name: 'relation-types', query: { ...route.query, edit: data.id } })"
          >{{ t('common.edit') }}</UiButton
        >
        <UiButton
          v-if="data && isDraft"
          type="primary"
          :disabled="busy"
          :loading="busy"
          @click="handlePublish"
        >
          {{ t('common.publish') }}
        </UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info" class="alert">{{ t('ui.readonly') }}</UiAlert>

    <UiAlert v-if="error" type="error" role="alert" class="alert"
      >{{ error }} <UiButton @click="loadDetail">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="notice" type="success" role="status" class="alert">{{ notice }}</UiAlert>

    <UiAlert v-if="data?.status === 'PUBLISHED'" type="info" class="alert">{{
      t('ui.frozen')
    }}</UiAlert>
    <UiSpin :show="loading">
      <template v-if="data">
        <div class="inspection-workspace">
          <aside class="inspection-rail">
            <h2>{{ t('relationDetail.endpoints') }}</h2>
            <div class="endpoint-path">
              <div>
                <small>{{ t('relation.domain') }}</small
                >{{ endpointName(data.domain_spec.type_id) }}
                <p class="mono">
                  {{ bound(data.domain_spec.cardinality?.min) }} /
                  {{ bound(data.domain_spec.cardinality?.max) }}
                </p>
              </div>
              <div class="path-link">{{ data.name }}</div>
              <div>
                <small>{{ t('relation.range') }}</small
                >{{ endpointName(data.range_spec.type_id) }}
                <p class="mono">
                  {{ bound(data.range_spec.cardinality?.min) }} /
                  {{ bound(data.range_spec.cardinality?.max) }}
                </p>
              </div>
            </div>
            <p>{{ t(data.status === 'PUBLISHED' ? 'ui.frozen' : 'ui.working') }}</p>
          </aside>
          <div class="inspection-main">
            <UiTabs type="line" animated>
              <UiTabPane name="basic" :tab="t('relationDetail.basic')">
                <UiDescriptions
                  :column="2"
                  bordered
                  label-placement="left"
                  content-style="overflow-wrap: anywhere"
                >
                  <UiDescriptionsItem :label="t('common.name')">
                    <span class="mono">{{ data.name }}</span>
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.iri')">
                    <span class="mono" :title="data.iri">{{ data.iri }}</span>
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.status')">
                    {{ t(`resourceStatus.${data.status}`) }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.revision')">
                    <span class="mono">{{
                      t('relationDetail.revisionValue', { revision: data.current_revision })
                    }}</span>
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.labelZh')">
                    {{ data.label_i18n?.['zh-CN'] || t('common.noneValue') }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.labelEn')">
                    {{ data.label_i18n?.['en-US']?.trim() || t('enumDictionaries.untranslated') }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.definitionZh')">
                    {{
                      data.definition_i18n?.['zh-CN']?.trim() || t('enumDictionaries.untranslated')
                    }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('common.definitionEn')">
                    {{
                      data.definition_i18n?.['en-US']?.trim() || t('enumDictionaries.untranslated')
                    }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('relation.assocEntity')">
                    {{
                      data.enable_attributes
                        ? (data.assoc_resource_id ?? t('common.noneValue'))
                        : t('relationDetail.notEnabled')
                    }}
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('relation.inverseOf')">
                    {{ data.inverse_of ?? t('common.noneValue') }}
                  </UiDescriptionsItem>
                </UiDescriptions>
              </UiTabPane>

              <UiTabPane name="endpoints" :tab="t('relationDetail.endpoints')">
                <p class="hint">{{ t('relationDetail.endpointsHint') }}</p>
                <UiDescriptions
                  :column="1"
                  bordered
                  label-placement="left"
                  content-style="overflow-wrap: anywhere"
                >
                  <UiDescriptionsItem :label="t('relation.domain')">
                    {{ endpointName(data.domain_spec.type_id) }}
                    ·
                    {{ t('relation.minCard') }}
                    {{ bound(data.domain_spec.cardinality?.min) }}
                    /
                    {{ t('relation.maxCard') }}
                    {{ bound(data.domain_spec.cardinality?.max) }}
                    <template v-if="data.domain_spec.role_i18n">
                      · {{ localized(data.domain_spec.role_i18n) }}
                    </template>
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('relation.range')">
                    {{ endpointName(data.range_spec.type_id) }}
                    ·
                    {{ t('relation.minCard') }}
                    {{ bound(data.range_spec.cardinality?.min) }}
                    /
                    {{ t('relation.maxCard') }}
                    {{ bound(data.range_spec.cardinality?.max) }}
                    <template v-if="data.range_spec.role_i18n">
                      · {{ localized(data.range_spec.role_i18n) }}
                    </template>
                  </UiDescriptionsItem>
                  <UiDescriptionsItem :label="t('relation.owl')">
                    <UiSpace v-if="owlTags.length" :size="4">
                      <UiTag v-for="tag in owlTags" :key="tag" size="small">{{ tag }}</UiTag>
                    </UiSpace>
                    <span v-else>{{ t('relationDetail.owlNone') }}</span>
                  </UiDescriptionsItem>
                </UiDescriptions>
                <section class="section">
                  <h3 class="section-title">{{ t('relationDetail.attributeDefs') }}</h3>
                  <UiSpace v-if="data.attribute_defs?.length" :size="4">
                    <UiTag v-for="def in data.attribute_defs" :key="def.name" size="small">
                      {{ def.name }} · {{ def.datatype }}
                    </UiTag>
                  </UiSpace>
                  <UiEmpty v-else :description="t('relationDetail.noAttributes')" />
                </section>
              </UiTabPane>

              <UiTabPane name="rules" :tab="t('relationDetail.rules')">
                <UiAlert v-if="usagesError" type="warning">
                  {{ usagesError }}
                  <UiButton @click="loadUsages(data.id, loadGeneration)">{{
                    t('ui.retry')
                  }}</UiButton>
                </UiAlert>
                <UiDataTable
                  v-else
                  :columns="ruleColumns"
                  :rows="usages?.rules ?? []"
                  mode="none"
                  :row-key="(row: TypeRuleUsage) => row.id"
                  :loading="usagesLoading"
                  :scroll-x="560"
                >
                  <template #empty><UiEmpty :description="t('relationDetail.noRules')" /></template>
                </UiDataTable>
              </UiTabPane>

              <UiTabPane name="references" :tab="t('relationDetail.references')">
                <UiAlert v-if="usagesError" type="warning"
                  >{{ usagesError }}
                  <UiButton @click="loadUsages(data.id, loadGeneration)">{{
                    t('ui.retry')
                  }}</UiButton></UiAlert
                >
                <UiSpin v-else :show="usagesLoading">
                  <section class="section">
                    <h3 class="section-title">{{ t('relationDetail.referencedBy') }}</h3>
                    <div v-if="usages?.domains?.length" class="ref-group">
                      <span class="ref-label">{{ t('page.domains') }}</span>
                      <UiSpace>
                        <UiTag
                          v-for="domain in usages.domains"
                          :key="domain.id"
                          size="small"
                          :type="domain.as_ref ? 'warning' : 'default'"
                        >
                          {{ localized(domain.label_i18n) }}
                          <template v-if="domain.as_ref">{{ t('domain.refMember') }}</template>
                        </UiTag>
                      </UiSpace>
                    </div>
                    <div v-if="usages?.ontologies?.length" class="ref-group">
                      <span class="ref-label">{{ t('page.ontologies') }}</span>
                      <UiSpace>
                        <UiTag v-for="onto in usages.ontologies" :key="onto.id" size="small">
                          {{
                            t('relationDetail.ontologyRef', {
                              name: localized(onto.label_i18n),
                              revision: onto.current_revision,
                            })
                          }}
                        </UiTag>
                      </UiSpace>
                    </div>
                    <UiEmpty
                      v-if="!usages?.domains?.length && !usages?.ontologies?.length"
                      :description="t('relationDetail.notReferenced')"
                    />
                  </section>

                  <section class="section">
                    <h3 class="section-title">{{ t('relationDetail.revisionHistory') }}</h3>
                    <ul v-if="usages?.revisions?.length" class="revision-list">
                      <li v-for="item in usages.revisions" :key="item.revision">
                        <span class="mono">{{
                          t('relationDetail.revisionValue', { revision: item.revision })
                        }}</span>
                        <span class="time">{{ item.published_at }}</span>
                      </li>
                    </ul>
                    <UiEmpty v-else :description="t('relationDetail.noRevisions')" />
                  </section>
                </UiSpin>
              </UiTabPane>
            </UiTabs>
          </div>
        </div>
      </template>
      <UiEmpty v-else-if="!loading && !error" :description="t('relationDetail.notFound')" />
    </UiSpin>
  </div>
</template>

<style scoped>
.alert {
  margin-bottom: 12px;
}
.hint {
  color: var(--text-secondary);
  font-size: var(--font-caption);
  margin: 0 0 12px;
}
.section {
  margin-top: 20px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
}
.ref-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}
.ref-label {
  color: var(--text-secondary);
  font-size: var(--font-caption);
  min-width: 72px;
}
.revision-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.revision-list li {
  display: flex;
  gap: 12px;
  padding: 4px 0;
}
.time {
  color: var(--text-secondary);
  font-size: var(--font-caption);
}
.mono {
  font-family: var(--font-mono);
}
</style>

<style scoped src="../styles/observatory.css"></style>
