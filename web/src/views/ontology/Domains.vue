<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCheckbox,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSpin,
} from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DomainBrief, DomainDetail, DomainMember, PublishCheckResult } from '@/api/domains'
import { domainsApi } from '@/api/domains'
import type { EntityTypeBrief, ResourceStatus } from '@/api/entity-types'
import { entityTypesApi } from '@/api/entity-types'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()

const loading = ref(true)
const items = ref<DomainBrief[]>([])
const typeList = ref<EntityTypeBrief[]>([])
const selected = ref<DomainBrief | null>(null)
/**
 * 选中域的详情。列表接口只返回 brief（没有 definition_i18n），
 * 编辑标签与定义需要详情，所以与成员一起按需拉取，保持同代次更新。
 */
const detail = ref<DomainDetail | null>(null)
const members = ref<DomainMember[]>([])
const membersLoading = ref(false)
const checking = ref(false)
const working = ref(false)
const addTypeId = ref<number | null>(null)
/** 新成员是否作为「跨域引用」加入。核心类型归属本域，跨域引用只被引用。 */
const addAsRef = ref(false)
const checkResult = ref<PublishCheckResult | null>(null)
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const notice = ref('')
const showBasicEditor = ref(false)
const basicError = ref('')
const basicFormRef = ref<FormInst | null>(null)
const basicForm = ref({ labelZh: '', labelEn: '', definitionZh: '', definitionEn: '' })
const actionError = ref('')
const listError = ref('')
const membersError = ref('')
const needsRefresh = ref(false)

type DomainSelection = { id: number; controller: AbortController }
let selection: DomainSelection | undefined
let listController: AbortController | undefined
let alive = true
const pendingWrites = new Map<number, Promise<unknown>>()
const canEdit = computed(
  () =>
    !!selected.value &&
    !loading.value &&
    !listError.value &&
    !membersLoading.value &&
    !membersError.value &&
    !working.value &&
    !checking.value &&
    !needsRefresh.value,
)

function isCurrentSelection(context: DomainSelection) {
  return (
    alive &&
    selection === context &&
    selected.value?.id === context.id &&
    !context.controller.signal.aborted
  )
}

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

const basicRules = computed<FormRules>(() => ({
  labelZh: {
    required: true,
    message: t('domain.basicIncomplete'),
    trigger: ['blur', 'input'],
  },
}))

async function load() {
  if (!alive) return null
  listController?.abort()
  const controller = new AbortController()
  listController = controller
  loading.value = true
  listError.value = ''
  try {
    const [next, types] = await Promise.all([
      domainsApi.list({}, controller.signal),
      entityTypesApi.list({}, controller.signal),
    ])
    if (!alive || controller.signal.aborted) return null
    items.value = next
    typeList.value = types
    // 选中对象的编辑版本只与随后重新读取的成员一起更新。
    return next
  } catch (err) {
    if (alive && !controller.signal.aborted) listError.value = toMessage(err)
    return null
  } finally {
    if (alive && !controller.signal.aborted) loading.value = false
  }
}

async function select(domain: DomainBrief | null) {
  if (!alive) return false
  selection?.controller.abort()
  selection = domain ? { id: domain.id, controller: new AbortController() } : undefined
  selected.value = domain
  members.value = []
  detail.value = null
  membersLoading.value = false
  checking.value = false
  working.value = false
  checkResult.value = null
  actionError.value = ''
  membersError.value = ''
  needsRefresh.value = false
  notice.value = ''
  addTypeId.value = null
  addAsRef.value = false
  return selection ? loadMembers(selection) : false
}

async function loadMembers(context: DomainSelection) {
  if (!isCurrentSelection(context)) return false
  membersLoading.value = true
  membersError.value = ''
  members.value = []
  checkResult.value = null
  try {
    const pending = pendingWrites.get(context.id)
    if (pending) {
      await pending.catch(() => undefined)
      if (!isCurrentSelection(context)) return false
      const next = await load()
      if (!next || !isCurrentSelection(context)) return false
      const fresh = next.find((domain) => domain.id === context.id)
      if (!fresh) {
        await select(null)
        return false
      }
      selected.value = fresh
    }
    if (!isCurrentSelection(context)) return false
    const [next, info] = await Promise.all([
      domainsApi.members(context.id, context.controller.signal),
      domainsApi.get(context.id, context.controller.signal),
    ])
    if (!isCurrentSelection(context)) return false
    members.value = next
    detail.value = info
    return true
  } catch (err) {
    if (isCurrentSelection(context)) membersError.value = toMessage(err)
    return false
  } finally {
    if (isCurrentSelection(context)) membersLoading.value = false
  }
}

async function refreshSelection() {
  const context = selection
  const next = await load()
  if (next && context && isCurrentSelection(context)) {
    await select(next.find((domain) => domain.id === context.id) ?? null)
  }
}

async function updateDomain(write: (id: number, revision: number) => Promise<unknown>) {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value || !selected.value) return false
  const revision = selected.value.edit_revision
  working.value = true
  actionError.value = ''
  checkResult.value = null
  try {
    const pending = write(context.id, revision)
    pendingWrites.set(context.id, pending)
    try {
      await pending
    } finally {
      if (pendingWrites.get(context.id) === pending) pendingWrites.delete(context.id)
    }
    if (!isCurrentSelection(context)) return false
    const next = await load()
    if (!isCurrentSelection(context)) return false
    if (!next) {
      needsRefresh.value = true
      return false
    }
    const fresh = next.find((domain) => domain.id === context.id)
    if (!fresh) {
      await select(null)
      return false
    }
    selected.value = fresh
    return await loadMembers(context)
  } catch (err) {
    if (isCurrentSelection(context)) {
      actionError.value = toMessage(err)
      needsRefresh.value = (err as { code?: string })?.code === 'KG.REVISION_CONFLICT'
    }
    return false
  } finally {
    if (isCurrentSelection(context)) working.value = false
  }
}

async function addMember() {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value) return
  const resourceId = addTypeId.value
  if (!resourceId) {
    actionError.value = t('domain.addMemberIncomplete')
    return
  }
  const updated = await updateDomain((id, revision) =>
    domainsApi.addMember(id, resourceId, addAsRef.value, revision),
  )
  if (updated && isCurrentSelection(context)) {
    addTypeId.value = null
    addAsRef.value = false
  }
}

async function removeMember(memberId: number) {
  if (!members.value.some((member) => member.id === memberId)) return
  await updateDomain((id, revision) => domainsApi.removeMember(id, memberId, revision))
}

async function publishCheck() {
  const context = selection
  if (!context || !isCurrentSelection(context) || !canEdit.value) return
  checking.value = true
  actionError.value = ''
  checkResult.value = null
  try {
    const result = await domainsApi.publishCheck(context.id, context.controller.signal)
    if (isCurrentSelection(context)) checkResult.value = result
  } catch (err) {
    if (isCurrentSelection(context)) actionError.value = toMessage(err)
  } finally {
    if (isCurrentSelection(context)) checking.value = false
  }
}

async function publish() {
  await updateDomain((id, revision) => domainsApi.publish(id, revision))
}

const formData = ref({ name: '', iri: '', labelZh: '', labelEn: '' })
const createFormRef = ref<FormInst | null>(null)

/** 业务域的机读名同样走 PascalCase；IRI 必填，格式由后端校验。 */
const createRules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
    {
      pattern: /^[A-Z][A-Za-z0-9]*$/,
      message: t('domain.namePattern'),
      trigger: ['blur', 'input'],
    },
  ],
  iri: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  labelZh: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
}))

/** 打开抽屉即重置表单与校验态。 */
watch(showCreate, (open) => {
  if (!open) return
  formData.value = { name: '', iri: '', labelZh: '', labelEn: '' }
  createError.value = ''
  createFormRef.value?.restoreValidation()
})

async function handleCreate() {
  if (!alive || creating.value) return
  createError.value = ''
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  const f = formData.value
  creating.value = true
  try {
    await domainsApi.create({
      name: f.name,
      iri: f.iri,
      label_i18n: { 'zh-CN': f.labelZh, 'en-US': f.labelEn || f.name },
    })
    if (!alive) return
    showCreate.value = false
    formData.value = { name: '', iri: '', labelZh: '', labelEn: '' }
    await load()
  } catch (err) {
    if (alive) createError.value = toMessage(err)
  } finally {
    if (alive) creating.value = false
  }
}

/** 打开基本信息编辑抽屉。机读名与 IRI 是业务域的身份，不在这里改。 */
function openBasicEditor() {
  const info = detail.value
  if (!info || !canEdit.value) return
  basicForm.value = {
    labelZh: info.label_i18n?.['zh-CN'] ?? '',
    labelEn: info.label_i18n?.['en-US'] ?? '',
    definitionZh: info.definition_i18n?.['zh-CN'] ?? '',
    definitionEn: info.definition_i18n?.['en-US'] ?? '',
  }
  basicError.value = ''
  showBasicEditor.value = true
}

async function saveBasic() {
  const context = selection
  const info = detail.value
  if (!context || !info || !isCurrentSelection(context) || !canEdit.value) return
  try {
    await basicFormRef.value?.validate()
  } catch {
    return
  }
  const labelZh = basicForm.value.labelZh.trim()
  const label: Record<string, string> = {
    'zh-CN': labelZh,
    'en-US': basicForm.value.labelEn.trim() || labelZh,
  }
  const definition: Record<string, string> = {}
  if (basicForm.value.definitionZh.trim()) definition['zh-CN'] = basicForm.value.definitionZh.trim()
  if (basicForm.value.definitionEn.trim()) definition['en-US'] = basicForm.value.definitionEn.trim()

  // 走统一的写入口，沿用它的选中代次校验与冲突处理
  const updated = await updateDomain((id, revision) =>
    domainsApi.update(id, {
      label_i18n: label,
      definition_i18n: definition,
      if_match: info.current_revision,
      if_edit_match: revision,
    }),
  )
  if (updated) {
    showBasicEditor.value = false
    notice.value = t('domain.basicSaved')
  }
}

onMounted(() => void load())
onBeforeUnmount(() => {
  alive = false
  listController?.abort()
  selection?.controller.abort()
})
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.domains')" :description="t('domain.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('common.create') }}</NButton>
      </template>
    </PageHeader>

    <NAlert v-if="listError" type="error" role="alert">
      {{ listError }}
      <NButton :loading="loading" @click="refreshSelection">{{ t('graph.refresh') }}</NButton>
    </NAlert>
    <NAlert v-if="notice" type="success" role="status">{{ notice }}</NAlert>
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
          <div v-else-if="!loading && !listError" class="list-empty">
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
              <NButton size="small" :disabled="!canEdit" @click="openBasicEditor">
                {{ t('common.edit') }}
              </NButton>
              <NButton size="small" :disabled="!canEdit" :loading="checking" @click="publishCheck">
                {{ t('domain.publishCheck') }}
              </NButton>
              <NButton size="small" type="primary" :disabled="!canEdit" @click="publish">
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
            <ul v-if="checkResult.issues?.length" class="issue-list">
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
              :disabled="!canEdit"
              class="member-select"
            />
            <NCheckbox v-model:checked="addAsRef" :disabled="!canEdit">
              {{ t('domain.asRef') }}
            </NCheckbox>
            <NButton :disabled="!canEdit" @click="addMember">{{ t('domain.addMember') }}</NButton>
          </div>

          <NAlert v-if="actionError || membersError" type="error" role="alert">
            {{ actionError || membersError }}
            <NButton :loading="loading || membersLoading" @click="refreshSelection">
              {{ t('graph.refresh') }}
            </NButton>
          </NAlert>

          <NSpin :show="membersLoading || working">
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
                      <NButton
                        size="tiny"
                        quaternary
                        type="error"
                        :disabled="!canEdit"
                        @click="removeMember(m.id)"
                      >
                        {{ t('common.delete') }}
                      </NButton>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div v-else-if="!membersLoading && !membersError" class="member-empty">
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

    <!-- 基本信息编辑。机读名与 IRI 是业务域的身份，只读展示。 -->
    <NDrawer
      v-model:show="showBasicEditor"
      :width="480"
      :mask-closable="!working"
      :close-on-esc="!working"
    >
      <NDrawerContent :title="t('domain.edit')" :closable="!working">
        <NAlert v-if="basicError" type="error" role="alert">{{ basicError }}</NAlert>
        <NForm
          ref="basicFormRef"
          :model="basicForm"
          :rules="basicRules"
          :disabled="working"
          label-placement="top"
        >
          <NFormItem :label="t('common.name')">
            <NInput :value="detail?.name ?? ''" disabled />
            <template #feedback>{{ t('domain.nameImmutable') }}</template>
          </NFormItem>
          <NFormItem :label="t('common.iri')">
            <NInput :value="detail?.iri ?? ''" disabled />
          </NFormItem>
          <NFormItem :label="t('common.labelZh')" path="labelZh">
            <NInput v-model:value="basicForm.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')" path="labelEn">
            <NInput v-model:value="basicForm.labelEn" />
          </NFormItem>
          <NFormItem :label="t('common.definitionZh')" path="definitionZh">
            <NInput
              v-model:value="basicForm.definitionZh"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </NFormItem>
          <NFormItem :label="t('common.definitionEn')" path="definitionEn">
            <NInput
              v-model:value="basicForm.definitionEn"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </NFormItem>
        </NForm>
        <template #footer>
          <NSpace justify="end">
            <NButton :disabled="working" @click="showBasicEditor = false">
              {{ t('common.cancel') }}
            </NButton>
            <NButton type="primary" :loading="working" @click="saveBasic">
              {{ t('common.save') }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NDrawer
      v-model:show="showCreate"
      :width="480"
      :mask-closable="!creating"
      :close-on-esc="!creating"
    >
      <NDrawerContent :title="t('domain.create')" :closable="!creating">
        <NForm
          ref="createFormRef"
          :model="formData"
          :rules="createRules"
          label-placement="top"
          :disabled="creating"
        >
          <NFormItem :label="t('common.name')" path="name">
            <NInput v-model:value="formData.name" placeholder="HumanResources" />
            <template #feedback>{{ t('domain.nameHint') }}</template>
          </NFormItem>
          <NFormItem :label="t('common.iri')" path="iri">
            <NInput v-model:value="formData.iri" placeholder="urn:knowledge:domain:hr" />
          </NFormItem>
          <NFormItem :label="t('common.labelZh')" path="labelZh">
            <NInput v-model:value="formData.labelZh" />
          </NFormItem>
          <NFormItem :label="t('common.labelEn')" path="labelEn">
            <NInput v-model:value="formData.labelEn" />
          </NFormItem>
        </NForm>
        <NAlert v-if="createError" type="error" class="action-error">{{ createError }}</NAlert>
        <template #footer>
          <div class="drawer-actions">
            <NButton :disabled="creating" @click="showCreate = false">
              {{ t('common.cancel') }}
            </NButton>
            <NButton type="primary" :loading="creating" @click="handleCreate">
              {{ t('common.save') }}
            </NButton>
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
  color: var(--text);
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
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.member-select {
  max-width: 320px;
}

.action-error {
  margin-bottom: var(--space-3);
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
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .split {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
