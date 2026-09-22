<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NCard, NDataTable, NEmpty, NTag } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { RoleInfo } from '@/api/auth'
import { authApi } from '@/api/auth'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t } = useI18n()
const { toMessage } = useApiError()

const items = ref<RoleInfo[]>([])
const loading = ref(false)
const error = ref('')

// 角色名与说明是界面文案，后端只给 code 与人数（硬规则：后端不下发中文句子）。
const columns = computed<DataTableColumns<RoleInfo>>(() => [
  {
    title: t('account.role'),
    key: 'code',
    render: (row) => h(NTag, { size: 'small' }, { default: () => t(`account.roles.${row.code}`) }),
  },
  { title: t('account.roleCode'), key: 'code', render: (row) => h('code', row.code) },
  {
    title: t('system.description'),
    key: 'description',
    render: (row) => t(`account.roleDescriptions.${row.code}`),
  },
  { title: t('system.memberCount'), key: 'member_count' },
])

onMounted(async () => {
  loading.value = true
  try {
    items.value = await authApi.roles()
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section>
    <PageHeader :title="t('page.systemRoles')" :description="t('system.rolesHint')" />
    <NCard size="small">
      <NDataTable
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: RoleInfo) => row.code"
      >
        <template #empty><NEmpty :description="error || t('common.empty')" /></template>
      </NDataTable>
    </NCard>
  </section>
</template>
