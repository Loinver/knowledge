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
  NSelect,
  NSpace,
  NSpin,
  NTag,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { EntityTypeBrief } from '@/api/client'
import { api, type Namespace } from '@/api/client'

const { t } = useI18n()
const message = useMessage()

const loading = ref(false)
const items = ref<EntityTypeBrief[]>([])
const searchQuery = ref('')
const showCreate = ref(false)
const namespaces = ref<Namespace[]>([])

const columns = computed(() => [
  { title: t('common.name'), key: 'name', resizable: true },
  { title: t('common.iri'), key: 'iri', resizable: true },
  {
    title: t('common.status'),
    key: 'status',
    render(row: EntityTypeBrief) {
      const color = row.status === 'PUBLISHED' ? 'success' : 'default'
      return h(
        NTag,
        { type: color, size: 'small' },
        { default: () => t(`resourceStatus.${row.status}`) },
      )
    },
  },
  { title: t('common.revision'), key: 'current_revision' },
  {
    title: t('common.actions'),
    key: 'actions',
    render(row: EntityTypeBrief) {
      return h(
        NButton,
        { size: 'small', text: true, onClick: () => goToDetail(row.id) },
        { default: () => t('common.edit') },
      )
    },
  },
])

const formData = ref({
  name: '',
  namespace_id: 0,
  labelZh: '',
  labelEn: '',
})

const nsOptions = computed(() => namespaces.value.map((ns) => ({ label: ns.prefix, value: ns.id })))

function goToDetail(id: number) {
  window.location.hash = `#/ontology/entity-types/${id}`
}

async function loadList() {
  loading.value = true
  try {
    items.value = await api.entityTypes.list({ q: searchQuery.value })
  } catch {
    message.error(t('common.loading'))
  } finally {
    loading.value = false
  }
}

async function loadNamespaces() {
  try {
    namespaces.value = await api.namespaces.list()
  } catch {
    // ignore
  }
}

async function handleCreate() {
  if (!formData.value.name || !formData.value.namespace_id || !formData.value.labelZh) {
    message.warning(t('entityType.create'))
    return
  }
  try {
    await api.entityTypes.create({
      name: formData.value.name,
      namespace_id: formData.value.namespace_id,
      label_i18n: {
        'zh-CN': formData.value.labelZh,
        'en-US': formData.value.labelEn || formData.value.name,
      },
    })
    message.success(t('common.save'))
    showCreate.value = false
    await loadList()
  } catch (err) {
    const e = err as { code?: string }
    message.error(e.code || t('common.save'))
  }
}

onMounted(async () => {
  await Promise.all([loadList(), loadNamespaces()])
})
</script>

<template>
  <div class="page-container">
    <n-space align="center" justify="space-between" class="page-header">
      <h2>{{ t('page.entityTypes') }}</h2>
      <n-button type="primary" @click="showCreate = true">{{ t('common.create') }}</n-button>
    </n-space>
    <n-space class="toolbar">
      <n-input
        v-model:value="searchQuery"
        :placeholder="t('common.search')"
        clearable
        @update:value="loadList"
      />
      <n-button @click="loadList">{{ t('common.search') }}</n-button>
    </n-space>
    <n-spin :show="loading">
      <n-data-table
        :columns="columns"
        :data="items"
        :bordered="false"
        :pagination="{ pageSize: 20 }"
      >
        <template #empty>
          <n-empty :description="t('common.empty')" />
        </template>
      </n-data-table>
    </n-spin>

    <n-drawer v-model:show="showCreate" :width="480">
      <n-drawer-content :title="t('entityType.create')" closable>
        <n-form>
          <n-form-item :label="t('common.name')">
            <n-input v-model:value="formData.name" placeholder="Employee" />
          </n-form-item>
          <n-form-item :label="t('common.namespace')">
            <n-select v-model:value="formData.namespace_id" :options="nsOptions" />
          </n-form-item>
          <n-form-item :label="t('common.labelZh')">
            <n-input v-model:value="formData.labelZh" />
          </n-form-item>
          <n-form-item :label="t('common.labelEn')">
            <n-input v-model:value="formData.labelEn" />
          </n-form-item>
        </n-form>
        <template #footer>
          <n-space>
            <n-button type="primary" @click="handleCreate">{{ t('common.save') }}</n-button>
            <n-button @click="showCreate = false">{{ t('common.cancel') }}</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
}
.page-header {
  margin-bottom: 16px;
}
.toolbar {
  margin-bottom: 16px;
}
</style>
