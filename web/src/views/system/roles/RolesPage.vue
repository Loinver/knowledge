<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { RoleInfo } from '@/api/auth'
import { authApi } from '@/api/auth'
import { getSessionGeneration } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns } from '@/components/ui'
import { SearchTable, UiButton, UiCard, UiEmpty, UiTag } from '@/components/ui'
import { useApiError } from '@/composables/useApiError'

const { t } = useI18n()
const router = useRouter()
const { toMessage } = useApiError()

const items = ref<RoleInfo[]>([])
const loading = ref(false)
const error = ref('')
let generation = 0
onBeforeUnmount(() => generation++)

function goUsers() {
  void router.push({ name: 'system-users' })
}

// 角色名与说明是界面文案，后端只给 code 与人数（硬规则：后端不下发中文句子）。
const columns = computed<DataTableColumns<RoleInfo>>(() => [
  {
    title: t('account.role'),
    key: 'code',
    render: (row) => h(UiTag, { size: 'small' }, { default: () => t(`account.roles.${row.code}`) }),
  },
  { title: t('account.roleCode'), key: 'roleCode', render: (row) => h('code', row.code) },
  {
    title: t('system.description'),
    key: 'description',
    render: (row) => t(`account.roleDescriptions.${row.code}`),
  },
  { title: t('system.memberCount'), key: 'member_count' },
  { title: t('appUi.readCapability'), key: 'read', render: () => t('common.yes') },
  { title: t('appUi.testCapability'), key: 'test', render: () => t('common.yes') },
  {
    title: t('appUi.writeCapability'),
    key: 'write',
    render: (row) => t(row.code === 'VIEWER' ? 'common.no' : 'common.yes'),
  },
  {
    title: t('appUi.adminCapability'),
    key: 'admin',
    render: (row) => t(row.code === 'ADMIN' ? 'common.yes' : 'common.no'),
  },
])

async function load() {
  const current = ++generation
  const session = getSessionGeneration()
  loading.value = true
  error.value = ''
  try {
    const result = await authApi.roles()
    if (current === generation && session === getSessionGeneration()) items.value = result
  } catch (err) {
    if (current === generation && session === getSessionGeneration()) error.value = toMessage(err)
  } finally {
    if (current === generation) loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <section class="system-page roles-page">
    <PageHeader :title="t('page.systemRoles')" :description="t('system.rolesHint')">
      <template #actions>
        <UiButton secondary @click="goUsers">{{ t('page.systemUsers') }}</UiButton>
      </template>
    </PageHeader>

    <div class="system-context">
      <div>
        <span class="context-label">{{ t('operationsUi.access') }}</span
        ><strong>{{ t('appUi.capabilityScope') }}</strong>
        <p>{{ t('operationsUi.accessHint') }}</p>
      </div>
    </div>
    <UiCard size="small" class="ledger-panel"
      ><header class="ledger-heading">
        <h2>{{ t('page.systemRoles') }}</h2>
        <UiButton size="small" :loading="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
      </header>
      <SearchTable
        :searchable="false"
        mode="none"
        :error="error"
        size="small"
        :columns="columns"
        :rows="items"
        :loading="loading"
        :row-key="(row: RoleInfo) => row.code"
        :scroll-x="1080"
        @retry="load"
      >
        <template #empty><UiEmpty :description="t('common.empty')" /></template>
      </SearchTable>
    </UiCard>
  </section>
</template>

<style scoped src="../SystemWorkspace.css"></style>
