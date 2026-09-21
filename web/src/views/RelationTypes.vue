<script setup lang="ts">
import { useMessage } from 'naive-ui'
import {
  NButton,
  NCheckbox,
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

import type { RelationTypeBrief } from '@/api/client'
import { api, type EntityTypeBrief, type Namespace } from '@/api/client'

const { t } = useI18n()
const message = useMessage()
const loading = ref(false)
const items = ref<RelationTypeBrief[]>([])
const showCreate = ref(false)
const namespaces = ref<Namespace[]>([])
const typeList = ref<EntityTypeBrief[]>([])

const columns = computed(() => [
  { title: t('common.name'), key: 'name' },
  { title: t('common.iri'), key: 'iri' },
  {
    title: t('common.status'),
    key: 'status',
    render(row: RelationTypeBrief) {
      return h(
        NTag,
        { type: row.status === 'PUBLISHED' ? 'success' : 'default', size: 'small' },
        { default: () => t(`resourceStatus.${row.status}`) },
      )
    },
  },
  { title: t('common.revision'), key: 'current_revision' },
])

const formData = ref({
  name: '',
  namespace_id: 0,
  labelZh: '',
  labelEn: '',
  domainType: 0,
  rangeType: 0,
  enableAttrs: false,
})
const nsOptions = computed(() => namespaces.value.map((ns) => ({ label: ns.prefix, value: ns.id })))
const typeOptions = computed(() => typeList.value.map((tp) => ({ label: tp.name, value: tp.id })))

async function load() {
  loading.value = true
  try {
    items.value = await api.relations.list()
  } finally {
    loading.value = false
  }
}
async function handleCreate() {
  if (
    !formData.value.name ||
    !formData.value.namespace_id ||
    !formData.value.labelZh ||
    !formData.value.domainType ||
    !formData.value.rangeType
  ) {
    message.warning(t('relation.create'))
    return
  }
  try {
    await api.relations.create({
      name: formData.value.name,
      namespace_id: formData.value.namespace_id,
      label_i18n: {
        'zh-CN': formData.value.labelZh,
        'en-US': formData.value.labelEn || formData.value.name,
      },
      domain_spec: { type_id: formData.value.domainType, cardinality: { min: 0, max: -1 } },
      range_spec: { type_id: formData.value.rangeType, cardinality: { min: 0, max: -1 } },
      enable_attributes: formData.value.enableAttrs,
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
    api.namespaces.list().then((r) => {
      namespaces.value = r
    }),
    api.entityTypes.list().then((r) => {
      typeList.value = r
    }),
  ])
})
</script>

<template>
  <div class="page-container">
    <n-space align="center" justify="space-between" class="page-header">
      <h2>{{ t('page.relationTypes') }}</h2>
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

    <n-drawer v-model:show="showCreate" :width="520">
      <n-drawer-content :title="t('relation.create')" closable>
        <n-form label-placement="top">
          <n-form-item :label="t('common.name')"
            ><n-input v-model:value="formData.name" placeholder="WorksIn"
          /></n-form-item>
          <n-form-item :label="t('common.namespace')"
            ><n-select v-model:value="formData.namespace_id" :options="nsOptions"
          /></n-form-item>
          <n-form-item :label="t('common.labelZh')"
            ><n-input v-model:value="formData.labelZh"
          /></n-form-item>
          <n-form-item :label="t('common.labelEn')"
            ><n-input v-model:value="formData.labelEn"
          /></n-form-item>
          <n-form-item :label="t('relation.domain')"
            ><n-select v-model:value="formData.domainType" :options="typeOptions" filterable
          /></n-form-item>
          <n-form-item :label="t('relation.range')"
            ><n-select v-model:value="formData.rangeType" :options="typeOptions" filterable
          /></n-form-item>
          <n-form-item :label="t('relation.enableAttributes')"
            ><n-checkbox v-model:checked="formData.enableAttrs"
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
