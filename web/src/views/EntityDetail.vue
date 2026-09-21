<script setup lang="ts">
import { useMessage } from 'naive-ui'
import {
  NButton,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import type { EntityType } from '@/api/client'
import { api } from '@/api/client'

const { t } = useI18n()
const message = useMessage()
const route = useRoute()
const loading = ref(false)
const data = ref<EntityType | null>(null)

async function loadDetail() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    data.value = await api.entityTypes.get(id)
  } catch {
    message.error(t('common.loading'))
  } finally {
    loading.value = false
  }
}

async function handlePublish() {
  if (!data.value) return
  try {
    await api.entityTypes.publish(data.value.id)
    message.success(t('common.publish'))
    await loadDetail()
  } catch {
    message.error(t('common.publish'))
  }
}

watch(() => route.params.id, loadDetail)
onMounted(loadDetail)
</script>

<template>
  <div class="page-container">
    <n-spin :show="loading">
      <template v-if="data">
        <n-tabs type="line" animated>
          <n-tab-pane :name="'basic'" :tab="t('entityType.basic')">
            <n-descriptions :column="2" bordered>
              <n-descriptions-item :label="t('common.name')">{{ data.name }}</n-descriptions-item>
              <n-descriptions-item :label="t('common.iri')">{{ data.iri }}</n-descriptions-item>
              <n-descriptions-item :label="t('common.status')">
                <n-tag :type="data.status === 'PUBLISHED' ? 'success' : 'default'" size="small">
                  {{ t(`resourceStatus.${data.status}`) }}
                </n-tag>
              </n-descriptions-item>
              <n-descriptions-item :label="t('common.revision')">{{
                data.current_revision
              }}</n-descriptions-item>
              <n-descriptions-item :label="t('common.label')">{{
                data.label_i18n?.['zh-CN']
              }}</n-descriptions-item>
              <n-descriptions-item :label="t('common.definition')">{{
                data.definition_i18n?.['zh-CN']
              }}</n-descriptions-item>
            </n-descriptions>
            <n-button
              style="margin-top: 16px"
              type="primary"
              :disabled="data.status === 'PUBLISHED'"
              @click="handlePublish"
            >
              {{ t('common.publish') }}
            </n-button>
          </n-tab-pane>
          <n-tab-pane :name="'dataProps'" :tab="t('entityType.dataProps')">
            <n-empty v-if="!data.data_props.length" :description="t('common.empty')" />
          </n-tab-pane>
          <n-tab-pane :name="'hierarchy'" :tab="t('entityType.hierarchy')">
            <n-empty v-if="!data.parent_ids.length" :description="t('common.empty')" />
          </n-tab-pane>
          <n-tab-pane :name="'relations'" :tab="t('entityType.relations')">
            <n-empty :description="t('common.empty')" />
          </n-tab-pane>
          <n-tab-pane :name="'rules'" :tab="t('entityType.rules')">
            <n-empty :description="t('common.empty')" />
          </n-tab-pane>
          <n-tab-pane :name="'references'" :tab="t('entityType.references')">
            <n-empty :description="t('common.empty')" />
          </n-tab-pane>
        </n-tabs>
      </template>
    </n-spin>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
}
</style>
