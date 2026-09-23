<script setup lang="ts">
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpin,
} from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  DomainBrief,
  DomainMember,
  EntityTypeBrief,
  PublishCheckResult,
  ResourceStatus,
} from '@/api/client'
import { api } from '@/api/client'
import PageHeader from '@/components/PageHeader.vue'

const { t, locale } = useI18n()

const loading = ref(false)
const items = ref<DomainBrief[]>([])
const typeList = ref<EntityTypeBrief[]>([])
const selected = ref<DomainBrief | null>(null)
const members = ref<DomainMember[]>([])
const membersLoading = ref(false)
const addTypeId = ref<number | null>(null)
const checkResult = ref<PublishCheckResult | null>(null)
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const actionError = ref('')

const STATUS_VAR: Record<ResourceStatus, string> = {
  PUBLISHED: 'var(--s-pass)',
  DRAFT: 'var(--s-notrun)',
  ARCHIVED: 'var(--s-na)',
}

function pickLabel(labels: Record<string, string> | null | undefined, fallback: string): string {
  return labels?.[locale.value] ?? labels?.['zh-CN'] ?? fallback
}

const typeById = computed(() => {
  const map: Record<number, EntityTypeBrief> = {}
  for (const tp of typeList.value) map[tp.id] = tp
  return map
})

const typeOptions = computed(() =>
  typeList.value.map((tp) => ({ label: pickLabel(tp.label_i18n, tp.name), value: tp.id })),
)

/** 发布检查的四项子检查，逐项列出比只给一句「未通过」有用得多。 */
const checkItems = computed(() => {
  const r = checkResult.value
  if (!r) return []
  return [
    { key: 'memberExists', ok: r.member_exists },
    { key: 'versionsAvailable', ok: r.versions_available },
    { key: 'dependenciesComplete', ok: r.dependencies_complete },
    { key: 'noCircularRef', ok: r.no_circular_ref },
  ]
})

async function load() {
  loading.value = true
  try {
    items.value = await api.domains.list()
    // 列表刷新后保持选中项指向新对象，避免详情区显示过期状态
    if (selected.value) {
      selected.value = items.value.find((d) => d.id === selected.value?.id) ?? null
    }
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function select(domain: DomainBrief) {
  selected.value = domain
  checkResult.value = null
  actionError.value = ''
  addTypeId.value = null
  membersLoading.value = true
  try {
    members.value = await api.domains.members(domain.id)
  } catch {
    members.value = []
  } finally {
    membersLoading.value = false
  }
}

async function addMember() {
  actionError.value = ''
  if (!selected.value || !addTypeId.value) {
    actionError.value = t('domain.addMemberIncomplete')
    return
  }
  try {
    await api.domains.addMember(selected.value.id, addTypeId.value)
    addTypeId.value = null
    members.value = await api.domains.members(selected.value.id)
  } catch (err) {
    actionError.value = (err as { code?: string }).code || t('common.save')
  }
}

async function removeMember(memberId: number) {
  if (!selected.value) return
  actionError.value = ''
  try {
    await api.domains.removeMember(selected.value.id, memberId)
    members.value = await api.domains.members(selected.value.id)
  } catch (err) {
    actionError.value = (err as { code?: string }).code || t('common.delete')
  }
}

async function publishCheck() {
  if (!selected.value) return
  actionError.value = ''
  try {
    checkResult.value = await api.domains.publishCheck(selected.value.id)
  } catch (err) {
    actionError.value = (err as { code?: string }).code || t('domain.publishCheck')
  }
}

async function publish() {
  if (!selected.value) return
  actionError.value = ''
  try {
    await api.domains.publish(selected.value.id)
    await load()
    if (selected.value) await select(selected.value)
  } catch (err) {
    actionError.value = (err as { code?: string }).code || t('common.publish')
  }
}

const formData = ref({ name: '', iri: '', labelZh: '', labelEn: '' })

async function handleCreate() {
  createError.value = ''
  const f = formData.value
  if (!f.name || !f.iri || !f.labelZh) {
    createError.value = t('domain.createIncomplete')
    return
  }
  creating.value = true
  try {
    await api.domains.create({
      name: f.name,
      iri: f.iri,
      label_i18n: { 'zh-CN': f.labelZh, 'en-US': f.labelEn || f.name },
    })
    showCreate.value = false
    formData.value = { name: '', iri: '', labelZh: '', labelEn: '' }
    await load()
  } catch (err) {
    createError.value = (err as { code?: string }).code || t('common.save')
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    api.entityTypes
      .list()
      .then((r) => {
        typeList.value = r
      })
      .catch(() => undefined),
  ])
})
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.domains')" :description="t('domain.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('common.create') }}</NButton>
      </template>
    </PageHeader>

    <NSpin :show="loading">
      <div class="split">
        <!-- 左：域列表。业务域当前是平铺的（无父子），所以用列表而非树 -->
        <aside class="list-card">
          <header class="list-head">
            <span>{{ t('domain.list') }}</span>
            <span class="mono count">{{ items.length }}</span>
          </header>
          <div v-if="items.length" class="list-body">
            <button
              v-for="d in items"
              :key="d.id"
              type="button"
              class="domain-item"
              :class="{ on: selected?.id === d.id }"
              @click="select(d)"
            >
              <i class="dot" :style="{ background: STATUS_VAR[d.status] }" />
              <span class="item-name">{{ pickLabel(d.label_i18n, d.name) }}</span>
              <span class="mono rev">{{ `v${d.current_revision}` }}</span>
            </button>
          </div>
          <div v-else class="list-empty">
            <NEmpty :description="t('common.empty')" />
          </div>
        </aside>

        <!-- 右：详情 -->
        <section v-if="selected" class="detail">
          <header class="detail-head">
            <div class="detail-title">
              <h3>{{ pickLabel(selected.label_i18n, selected.name) }}</h3>
              <span class="mono sub">{{ selected.name }}</span>
              <span class="status-tag" :style="{ '--dot': STATUS_VAR[selected.status] }">
                <i class="status-dot" />
                {{ t(`resourceStatus.${selected.status}`) }}
              </span>
            </div>
            <span class="iri">{{ selected.iri }}</span>
            <div class="detail-actions">
              <NButton size="small" @click="publishCheck">{{ t('domain.publishCheck') }}</NButton>
              <NButton size="small" type="primary" @click="publish">
                {{ t('common.publish') }}
              </NButton>
            </div>
          </header>

          <!-- 发布检查结果：四项子检查逐项列出 -->
          <div v-if="checkResult" class="check-panel">
            <div class="check-head">
              <span class="check-verdict" :class="checkResult.can_publish ? 'ok' : 'bad'">
                {{ checkResult.can_publish ? t('domain.checkPassed') : t('domain.checkFailed') }}
              </span>
            </div>
            <ul class="check-list">
              <li v-for="c in checkItems" :key="c.key">
                <i
                  class="dot"
                  :style="{ background: c.ok ? 'var(--s-pass)' : 'var(--s-violation)' }"
                />
                {{ t(`domain.${c.key}`) }}
              </li>
            </ul>
            <ul v-if="checkResult.issues.length" class="issue-list">
              <li v-for="issue in checkResult.issues" :key="issue">{{ issue }}</li>
            </ul>
          </div>

          <div class="member-add">
            <NSelect
              v-model:value="addTypeId"
              :options="typeOptions"
              filterable
              clearable
              :placeholder="t('domain.addMember')"
              class="member-select"
            />
            <NButton @click="addMember">{{ t('domain.addMember') }}</NButton>
          </div>

          <p v-if="actionError" class="action-error">{{ actionError }}</p>

          <NSpin :show="membersLoading">
            <div class="member-card">
              <table v-if="members.length" class="member-table">
                <thead>
                  <tr>
                    <th>{{ t('domain.memberResource') }}</th>
                    <th style="width: 30%">{{ t('common.iri') }}</th>
                    <th style="width: 18%">{{ t('domain.role') }}</th>
                    <th style="width: 90px" />
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in members" :key="m.id">
                    <td class="member-name">
                      {{ pickLabel(typeById[m.resource_id]?.label_i18n, `#${m.resource_id}`) }}
                    </td>
                    <td>
                      <span
                        v-if="typeById[m.resource_id]"
                        class="iri"
                        :title="typeById[m.resource_id].iri"
                      >
                        {{ typeById[m.resource_id].iri }}
                      </span>
                      <span v-else class="muted">{{ t('common.noneValue') }}</span>
                    </td>
                    <td>
                      <span class="mini-tag">
                        {{ m.as_ref ? t('domain.refMember') : t('domain.coreMember') }}
                      </span>
                    </td>
                    <td>
                      <NButton size="tiny" quaternary type="error" @click="removeMember(m.id)">
                        {{ t('common.delete') }}
                      </NButton>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="member-empty">
                <NEmpty :description="t('domain.noMembers')" />
              </div>
            </div>
          </NSpin>
        </section>

        <section v-else class="detail detail-empty">
          <NEmpty :description="t('domain.selectHint')" />
        </section>
      </div>
    </NSpin>

    <NDrawer v-model:show="showCreate" :width="480">
      <NDrawerContent :title="t('domain.create')" closable>
        <NForm label-placement="top">
          <NFormItem :label="t('common.name')">
            <NInput v-model:value="formData.name" placeholder="HumanResources" />
          </NFormItem>
          <NFormItem :label="t('common.iri')">
            <NInput v-model:value="formData.iri" placeholder="urn:knowledge:domain:hr" />
          </NFormItem>
          <NFormItem :label="t('common.labelZh')">
            <NInput v-model:value="formData.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')">
            <NInput v-model:value="formData.labelEn" />
          </NFormItem>
        </NForm>
        <p v-if="createError" class="action-error">{{ createError }}</p>
        <template #footer>
          <div class="drawer-actions">
            <NButton type="primary" :loading="creating" @click="handleCreate">
              {{ t('common.save') }}
            </NButton>
            <NButton @click="showCreate = false">{{ t('common.cancel') }}</NButton>
          </div>
        </template>
      </NDrawerContent>
    </NDrawer>
  </section>
</template>

<style scoped>
.page {
  padding-bottom: var(--space-5);
}

.split {
  display: grid;
  grid-template-columns: 262px minmax(0, 1fr);
  gap: var(--space-3);
  align-items: start;
}

/* ── 左侧列表 ───────────────────────────────────────────── */
.list-card {
  overflow: hidden;
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.list-head {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  font-size: var(--font-caption);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.list-head .count {
  margin-left: auto;
  color: var(--text-tertiary);
  font-size: 10px;
}

.list-body {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.domain-item {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 8px 10px;
  font: inherit;
  font-size: var(--font-small);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: var(--r-md);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.domain-item:hover {
  background: var(--bg-hover);
}

.domain-item.on {
  color: #bfd4fb;
  font-weight: 500;
  background: var(--accent-soft);
}

.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.domain-item .rev {
  margin-left: auto;
  color: var(--text-disabled);
  font-size: 10px;
}

.list-empty {
  padding: var(--space-5);
}

/* ── 右侧详情 ───────────────────────────────────────────── */
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.detail-empty {
  align-items: center;
  justify-content: center;
  min-height: 260px;
}

.detail-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-title {
  display: flex;
  gap: 9px;
  align-items: center;
}

.detail-title h3 {
  margin: 0;
  font-size: var(--font-h2);
  font-weight: 500;
}

.detail-title .sub {
  color: var(--text-tertiary);
  font-size: var(--font-small);
}

.detail-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: 4px;
}

/* ── 发布检查 ───────────────────────────────────────────── */
.check-panel {
  padding: 12px 14px;
  background: var(--bg-inset);
  border-radius: var(--r-md);
  box-shadow: 0 0 0 1px var(--border-subtle);
}

.check-verdict {
  font-size: var(--font-small);
  font-weight: 500;
}

.check-verdict.ok {
  color: var(--s-pass);
}

.check-verdict.bad {
  color: var(--s-violation);
}

.check-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  padding: 0;
  margin: 10px 0 0;
  list-style: none;
  font-size: var(--font-caption);
  color: var(--text-secondary);
}

.check-list li {
  display: flex;
  gap: 6px;
  align-items: center;
}

.issue-list {
  margin: 10px 0 0;
  padding-left: 18px;
  font-size: var(--font-caption);
  color: var(--s-violation);
}

/* ── 成员 ───────────────────────────────────────────────── */
.member-add {
  display: flex;
  gap: var(--space-2);
}

.member-select {
  max-width: 320px;
}

.action-error {
  margin: 0;
  color: var(--danger);
  font-size: var(--font-small);
}

.member-card {
  overflow: hidden;
  border-radius: var(--r-md);
  box-shadow: 0 0 0 1px var(--border-subtle);
}

.member-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-caption);
}

.member-table th {
  padding: 8px 12px;
  font-weight: 400;
  color: var(--text-tertiary);
  text-align: left;
  background: var(--bg-inset);
  border-bottom: 1px solid var(--border-subtle);
}

.member-table td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.member-table tr:last-child td {
  border-bottom: 0;
}

.member-name {
  font-weight: 500;
}

.member-empty {
  padding: var(--space-5);
}

.muted {
  color: var(--text-disabled);
}

.mini-tag {
  padding: 1px 8px;
  font-size: 10px;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

.status-tag {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 2px 9px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-pill);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--dot);
  border-radius: 50%;
}

.drawer-actions {
  display: flex;
  gap: var(--space-2);
}

@media (max-width: 900px) {
  .split {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
