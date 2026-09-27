<script setup lang="ts">
import {
  NAlert,
  NButton,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { entityTypesApi } from '@/api/entity-types'
import type { RelationTypeDetail, RelationTypeUsages, TypeRuleUsage } from '@/api/relations'
import { relationsApi } from '@/api/relations'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const route = useRoute()

const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const data = ref<RelationTypeDetail | null>(null)
/** 规则 / 引用与版本：一次请求取全，两个页签共用。 */
const usages = ref<RelationTypeUsages | null>(null)
const usagesLoading = ref(false)
/** 端点 type_id → 类型标签，把端点显示成名字而不是裸 id。 */
const typeLabels = ref<Record<number, string>>({})
let loadGeneration = 0
let alive = true

const isDraft = computed(() => data.value?.status === 'DRAFT')

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
      map[item.id] = item.label_i18n?.[locale.value] ?? item.label_i18n?.['zh-CN'] ?? item.name
    }
    typeLabels.value = map
  } catch {
    typeLabels.value = {}
  }
}

async function loadUsages(id: number, generation: number) {
  usagesLoading.value = true
  try {
    const result = await relationsApi.usages(id)
    if (alive && generation === loadGeneration) usages.value = result
  } catch {
    // 页签数据失败不影响基本信息；保持空态即可，不覆盖整页错误。
    if (alive && generation === loadGeneration) usages.value = null
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
  void loadUsages(id, generation)
}

async function handlePublish() {
  if (!data.value || !isDraft.value || busy.value) return
  const generation = loadGeneration
  busy.value = true
  notice.value = ''
  try {
    const result = await relationsApi.publish(data.value.id)
    if (!alive || generation !== loadGeneration) return
    notice.value = t('relationDetail.published', { revision: result.revision })
    await loadDetail()
  } catch (err) {
    if (alive && generation === loadGeneration) error.value = t('relationDetail.publishFailed')
  } finally {
    if (alive && generation === loadGeneration) busy.value = false
  }
}

const ruleColumns = computed(() => [
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
  <div>
    <PageHeader
      :title="data ? localized(data.label_i18n) : t('page.relationDetail')"
      :description="t('relationDetail.hint')"
    >
      <template #actions>
        <NButton
          v-if="data && isDraft"
          type="primary"
          :disabled="busy"
          :loading="busy"
          @click="handlePublish"
        >
          {{ t('common.publish') }}
        </NButton>
      </template>
    </PageHeader>

    <NAlert v-if="error" type="error" role="alert" class="alert">{{ error }}</NAlert>
    <NAlert v-if="notice" type="success" role="status" class="alert">{{ notice }}</NAlert>

    <NSpin :show="loading">
      <template v-if="data">
        <NTabs type="line" animated>
          <NTabPane name="basic" :tab="t('relationDetail.basic')">
            <NDescriptions :column="2" bordered label-placement="left">
              <NDescriptionsItem :label="t('common.name')">
                <span class="mono">{{ data.name }}</span>
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('common.iri')">
                <span class="mono">{{ data.iri }}</span>
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('common.status')">
                {{ t(`resourceStatus.${data.status}`) }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('common.revision')">
                <span class="mono">{{
                  t('relationDetail.revisionValue', { revision: data.current_revision })
                }}</span>
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('common.labelZh')">
                {{ data.label_i18n?.['zh-CN'] || t('common.noneValue') }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('common.labelEn')">
                {{ data.label_i18n?.['en-US'] || t('common.noneValue') }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('relation.assocEntity')">
                {{
                  data.enable_attributes
                    ? (data.assoc_resource_id ?? t('common.noneValue'))
                    : t('relationDetail.notEnabled')
                }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('relation.inverseOf')">
                {{ data.inverse_of ?? t('common.noneValue') }}
              </NDescriptionsItem>
            </NDescriptions>
          </NTabPane>

          <NTabPane name="endpoints" :tab="t('relationDetail.endpoints')">
            <p class="hint">{{ t('relationDetail.endpointsHint') }}</p>
            <NDescriptions :column="1" bordered label-placement="left">
              <NDescriptionsItem :label="t('relation.domain')">
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
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('relation.range')">
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
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('relation.owl')">
                <NSpace v-if="owlTags.length" :size="4">
                  <NTag v-for="tag in owlTags" :key="tag" size="small">{{ tag }}</NTag>
                </NSpace>
                <span v-else>{{ t('relationDetail.owlNone') }}</span>
              </NDescriptionsItem>
            </NDescriptions>
            <section class="section">
              <h3 class="section-title">{{ t('relationDetail.attributeDefs') }}</h3>
              <NSpace v-if="data.attribute_defs?.length" :size="4">
                <NTag v-for="def in data.attribute_defs" :key="def.name" size="small">
                  {{ def.name }} · {{ def.datatype }}
                </NTag>
              </NSpace>
              <NEmpty v-else :description="t('relationDetail.noAttributes')" />
            </section>
          </NTabPane>

          <NTabPane name="rules" :tab="t('relationDetail.rules')">
            <NDataTable
              :columns="ruleColumns"
              :data="usages?.rules ?? []"
              :row-key="(row: TypeRuleUsage) => row.id"
              :loading="usagesLoading"
              :scroll-x="560"
            >
              <template #empty><NEmpty :description="t('relationDetail.noRules')" /></template>
            </NDataTable>
          </NTabPane>

          <NTabPane name="references" :tab="t('relationDetail.references')">
            <NSpin :show="usagesLoading">
              <section class="section">
                <h3 class="section-title">{{ t('relationDetail.referencedBy') }}</h3>
                <div v-if="usages?.domains?.length" class="ref-group">
                  <span class="ref-label">{{ t('page.domains') }}</span>
                  <NSpace>
                    <NTag
                      v-for="domain in usages.domains"
                      :key="domain.id"
                      size="small"
                      :type="domain.as_ref ? 'warning' : 'default'"
                    >
                      {{ localized(domain.label_i18n) }}
                      <template v-if="domain.as_ref">{{ t('domain.refMember') }}</template>
                    </NTag>
                  </NSpace>
                </div>
                <div v-if="usages?.ontologies?.length" class="ref-group">
                  <span class="ref-label">{{ t('page.ontologies') }}</span>
                  <NSpace>
                    <NTag v-for="onto in usages.ontologies" :key="onto.id" size="small">
                      {{
                        t('relationDetail.ontologyRef', {
                          name: localized(onto.label_i18n),
                          revision: onto.current_revision,
                        })
                      }}
                    </NTag>
                  </NSpace>
                </div>
                <NEmpty
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
                <NEmpty v-else :description="t('relationDetail.noRevisions')" />
              </section>
            </NSpin>
          </NTabPane>
        </NTabs>
      </template>
      <NEmpty v-else-if="!loading" :description="t('relationDetail.notFound')" />
    </NSpin>
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
