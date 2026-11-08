<script setup lang="ts">
import { NAutoComplete } from 'naive-ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useNavigation } from '@/layout/useNavigation'

const { t } = useI18n()
const router = useRouter()
const { groups } = useNavigation()
const query = ref('')
const input = ref<InstanceType<typeof NAutoComplete> | null>(null)
const options = computed(() => {
  const text = (query.value ?? '').trim().toLocaleLowerCase()
  const pages = [
    { key: 'dashboard', label: t('menu.dashboard') },
    ...groups.value.flatMap((group) => group.items),
  ]
  return pages
    .filter((item) => !text || item.label.toLocaleLowerCase().includes(text))
    .map((item) => ({ label: item.label, value: item.key }))
})
function select(value: string) {
  if (!options.value.some((item) => item.value === value)) return
  query.value = ''
  input.value?.blur()
  void router.push({ name: value })
}
function keyboard(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    input.value?.focus()
  }
}
onMounted(() => window.addEventListener('keydown', keyboard))
onUnmounted(() => window.removeEventListener('keydown', keyboard))
</script>

<template>
  <NAutoComplete
    ref="input"
    :value="query"
    class="quick-search"
    :options="options"
    :placeholder="t('ui.quickSearch')"
    :input-props="{ 'aria-label': t('ui.quickSearch') }"
    clearable
    @update:value="query = $event ?? ''"
    @select="select"
  />
</template>

<style scoped>
.quick-search {
  width: clamp(160px, 20vw, 280px);
}
@media (max-width: 900px) {
  .quick-search {
    width: 160px;
  }
}
@media (max-width: 600px) {
  .quick-search {
    width: 110px;
  }
}
</style>
