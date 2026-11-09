<script setup lang="ts">
import { NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'

import type { KnowledgeDocument } from '@/api/knowledge'

import { useKnowledgeMessage } from '../composables/useKnowledge'
defineProps<{ document: KnowledgeDocument }>()
const { t } = useI18n()
const { reason } = useKnowledgeMessage()
</script>

<template>
  <div class="kb-stack" data-testid="kb-document-status">
    <div>
      <NTag size="small" :bordered="false" :type="document.searchable ? 'success' : 'default'">{{
        t(document.searchable ? 'kb.searchable' : 'kb.notSearchable')
      }}</NTag>
      <span class="kb-muted">{{
        t('kb.indexGeneration', { n: document.active_generation ?? '—' })
      }}</span>
    </div>
    <div class="kb-muted">
      {{ t('kb.semantic') }} · {{ t(`kb.semanticStatus.${document.semantic_status}`) }}
    </div>
    <div
      v-if="document.latest_task"
      data-testid="kb-latest-task"
      :class="
        ['FAILED', 'INTERRUPTED'].includes(document.latest_task.status)
          ? 'kb-task-failed'
          : 'kb-muted'
      "
    >
      {{ t('kb.latestTask') }} · {{ t(`kb.taskStatus.${document.latest_task.status}`) }} ·
      {{ t('kb.generation', { n: document.latest_task.generation }) }}
      <div v-if="document.latest_task.error_reason">
        {{ reason(document.latest_task.error_reason) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-task-failed {
  color: var(--danger);
  font-size: var(--font-small);
}
</style>
