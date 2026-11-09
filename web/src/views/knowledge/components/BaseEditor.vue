<script setup lang="ts">
import { NAlert, NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteUpdate } from 'vue-router'

import { knowledgeApi, type KnowledgeBase } from '@/api/knowledge'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useAuthStore } from '@/stores/auth'

import { useKnowledgeAction } from '../composables/useKnowledge'

const props = defineProps<{ show: boolean; base?: KnowledgeBase | null }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; saved: [value: KnowledgeBase] }>()
const { t } = useI18n()
const auth = useAuthStore()
const open = ref(false)
const form = ref({ name: '', description: '' })
let target: KnowledgeBase | null = null
watch(
  () => props.show,
  (show) => {
    if (show) {
      target = props.base ? { ...props.base } : null
      form.value = { name: target?.name ?? '', description: target?.description ?? '' }
    }
    open.value = show
  },
  { immediate: true },
)
watch(open, (show) => emit('update:show', show))
const guarded = useDraftGuard(open, () => form.value)
const { busy, error, run } = useKnowledgeAction(() => `${props.show}:${props.base?.id ?? 'new'}`)
const visible = computed({
  get: () => guarded.value,
  set: (value: boolean) => {
    if (!busy.value) guarded.value = value
  },
})
onBeforeRouteUpdate((to, from) => {
  if (to.params.id !== from.params.id) {
    visible.value = false
    return !open.value
  }
  return true
})
async function save() {
  if (!['ADMIN', 'EDITOR'].includes(auth.user?.role ?? '') || !form.value.name.trim()) return
  const payload = { name: form.value.name.trim(), description: form.value.description }
  const current = target
  const result = await run((signal) =>
    current
      ? knowledgeApi.update(current.id, payload, current.revision, signal)
      : knowledgeApi.create(payload, signal),
  )
  if (result) {
    open.value = false
    emit('saved', result)
  }
}
</script>

<template>
  <NDrawer v-model:show="visible" :width="480" :close-on-esc="!busy" :mask-closable="!busy">
    <NDrawerContent :title="t(base ? 'kb.edit' : 'kb.create')" closable>
      <div class="kb-stack">
        <NAlert type="info">{{ t('kb.globalAccess') }}</NAlert>
        <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
        <NForm @submit.prevent="save">
          <NFormItem :label="t('kb.name')" :label-props="{ for: 'kb-name' }" required>
            <NInput
              v-model:value="form.name"
              :input-props="{ id: 'kb-name', 'aria-label': t('kb.name'), required: true }"
              :maxlength="200"
              :disabled="busy"
            />
          </NFormItem>
          <NFormItem :label="t('kb.description')" :label-props="{ for: 'kb-description' }">
            <NInput
              v-model:value="form.description"
              type="textarea"
              :input-props="{ id: 'kb-description' }"
              :maxlength="4000"
              :autosize="{ minRows: 4, maxRows: 10 }"
              :disabled="busy"
            />
          </NFormItem>
        </NForm>
      </div>
      <template #footer>
        <div class="kb-actions">
          <NButton :disabled="busy" @click="visible = false">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="busy" :disabled="!form.name.trim()" @click="save">{{
            t('common.save')
          }}</NButton>
        </div>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
