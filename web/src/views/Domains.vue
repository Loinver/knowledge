<script setup lang="ts">
import { useMessage } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NList,
  NListItem,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NThing,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DomainBrief, DomainMember } from '@/api/client'
import { api, type EntityTypeBrief } from '@/api/client'

const { t } = useI18n()
const message = useMessage()
const loading = ref(false)
const items = ref<DomainBrief[]>([])
const showCreate = ref(false)
const selectedDomain = ref<DomainBrief | null>(null)
const detailVisible = ref(false)
const members = ref<DomainMember[]>([])
const typeList = ref<EntityTypeBrief[]>([])
const addMemberTypeId = ref(0)
const publishCheckResult = ref<null | { can_publish: boolean; issues: string[] }>(null)

const columns = computed(() => [
  { title: t('common.name'), key: 'name' },
  { title: t('common.iri'), key: 'iri' },
  {
    title: t('common.status'),
    key: 'status',
    render(row: DomainBrief) {
      return h(
        NTag,
        { type: row.status === 'PUBLISHED' ? 'success' : 'default', size: 'small' },
        { default: () => t(`resourceStatus.${row.status}`) },
      )
    },
  },
  {
    title: t('common.actions'),
    key: 'actions',
    render(row: DomainBrief) {
      return h(
        NButton,
        { size: 'small', text: true, onClick: () => openDetail(row) },
        { default: () => t('common.edit') },
      )
    },
  },
])

const formData = ref({ name: '', iri: '', labelZh: '', labelEn: '', memberIds: [] as number[] })
const typeOptions = computed(() => typeList.value.map((tp) => ({ label: tp.name, value: tp.id })))

async function load() {
  loading.value = true
  try {
    items.value = await api.domains.list()
  } finally {
    loading.value = false
  }
}
async function openDetail(domain: DomainBrief) {
  selectedDomain.value = domain
  detailVisible.value = true
  members.value = await api.domains.members(domain.id)
}
async function handleAddMember() {
  if (!selectedDomain.value || !addMemberTypeId.value) return
  try {
    await api.domains.addMember(selectedDomain.value.id, addMemberTypeId.value)
    members.value = await api.domains.members(selectedDomain.value.id)
    message.success(t('domain.addMember'))
    addMemberTypeId.value = 0
  } catch (err) {
    const e = err as { code?: string }
    message.error(e.code || t('common.save'))
  }
}
async function handleRemoveMember(memberId: number) {
  if (!selectedDomain.value) return
  await api.domains.removeMember(selectedDomain.value.id, memberId)
  members.value = await api.domains.members(selectedDomain.value.id)
}
async function handlePublishCheck() {
  if (!selectedDomain.value) return
  publishCheckResult.value = await api.domains.publishCheck(selectedDomain.value.id)
}
async function handlePublish() {
  if (!selectedDomain.value) return
  try {
    await api.domains.publish(selectedDomain.value.id)
    message.success(t('common.publish'))
    await load()
  } catch {
    message.error(t('common.publish'))
  }
}
async function handleCreate() {
  if (!formData.value.name || !formData.value.iri || !formData.value.labelZh) {
    message.warning(t('domain.create'))
    return
  }
  try {
    await api.domains.create({
      name: formData.value.name,
      iri: formData.value.iri,
      label_i18n: {
        'zh-CN': formData.value.labelZh,
        'en-US': formData.value.labelEn || formData.value.name,
      },
      member_ids: formData.value.memberIds,
    })
    message.success(t('common.save'))
    showCreate.value = false
    await load()
  } catch (err) {
    const e = err as { code?: string }
    message.error(e.code || t('common.save'))
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    api.entityTypes.list().then((r) => {
      typeList.value = r
    }),
  ])
})
</script>

<template>
  <div class="page-container">
    <n-space align="center" justify="space-between" class="page-header">
      <h2>{{ t('page.domains') }}</h2>
      <n-button type="primary" @click="showCreate = true">{{ t('common.create') }}</n-button>
    </n-space>
    <n-spin :show="loading">
      <n-data-table
        :columns="columns"
        :data="items"
        :bordered="false"
        :pagination="{ pageSize: 20 }"
      >
        <template #empty><n-empty :description="t('common.empty')" /></template>
      </n-data-table>
    </n-spin>

    <n-drawer v-model:show="showCreate" :width="480">
      <n-drawer-content :title="t('domain.create')" closable>
        <n-form label-placement="top">
          <n-form-item :label="t('common.name')"
            ><n-input v-model:value="formData.name"
          /></n-form-item>
          <n-form-item :label="t('common.iri')"
            ><n-input v-model:value="formData.iri"
          /></n-form-item>
          <n-form-item :label="t('common.labelZh')"
            ><n-input v-model:value="formData.labelZh"
          /></n-form-item>
          <n-form-item :label="t('common.labelEn')"
            ><n-input v-model:value="formData.labelEn"
          /></n-form-item>
        </n-form>
        <template #footer>
          <n-space>
            <n-button type="primary" @click="handleCreate">{{ t('common.save') }}</n-button>
            <n-button @click="showCreate = false">{{ t('common.cancel') }}</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>

    <n-modal
      v-model:show="detailVisible"
      :width="640"
      :title="selectedDomain?.name || ''"
      preset="card"
    >
      <template v-if="selectedDomain">
        <n-space vertical>
          <n-space>
            <n-select
              v-model:value="addMemberTypeId"
              :options="typeOptions"
              filterable
              style="width: 300px"
            />
            <n-button @click="handleAddMember">{{ t('domain.addMember') }}</n-button>
          </n-space>
          <n-list bordered>
            <n-list-item v-for="m in members" :key="m.id">
              <n-thing>
                <template #header>{{ t('domain.memberNo', { n: m.resource_id }) }}</template>
                <template #description>{{ m.as_ref ? t('domain.asRef') : '' }}</template>
              </n-thing>
              <template #suffix>
                <n-button size="small" text type="error" @click="handleRemoveMember(m.id)">{{
                  t('common.delete')
                }}</n-button>
              </template>
            </n-list-item>
            <n-list-item v-if="!members.length">
              <n-empty :description="t('common.empty')" />
            </n-list-item>
          </n-list>
          <n-space>
            <n-button @click="handlePublishCheck">{{ t('domain.publishCheck') }}</n-button>
            <n-button type="primary" @click="handlePublish">{{ t('common.publish') }}</n-button>
          </n-space>
          <div v-if="publishCheckResult">
            <n-tag :type="publishCheckResult.can_publish ? 'success' : 'error'" size="small">
              {{
                publishCheckResult.can_publish ? t('domain.checkPassed') : t('domain.checkFailed')
              }}
            </n-tag>
            <ul v-if="publishCheckResult.issues.length">
              <li v-for="issue in publishCheckResult.issues" :key="issue">{{ issue }}</li>
            </ul>
          </div>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
}
.page-header {
  margin-bottom: 16px;
}
</style>
