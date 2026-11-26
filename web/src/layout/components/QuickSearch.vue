<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { UiButton, UiEmpty, UiInput, UiModal } from '@/components/ui'
import { useNavigation } from '@/layout/navigation/useNavigation'

const { t } = useI18n()
const router = useRouter()
const { searchPages } = useNavigation()
const show = ref(false)
const query = ref('')
const selected = ref(0)
const input = ref<InstanceType<typeof UiInput> | null>(null)
const options = computed(() => searchPages(query.value))
function nextTickFocus() {
  void nextTick(() => input.value?.focus())
}
function modalFormOpen() {
  return !!document.querySelector('.ui-dialog:not(.command-palette), .ui-sheet')
}
function open() {
  query.value = ''
  selected.value = 0
  show.value = true
  nextTickFocus()
}
watch(show, (visible) => {
  if (!visible) return
  query.value = ''
  selected.value = 0
  nextTickFocus()
})
function select(index: number) {
  const option = options.value[index]
  if (!option) return
  show.value = false
  void router.push({ name: option.routeName })
}
function keyboard(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    // Some platform/browser combinations still deliver the shortcut while a
    // modal form owns the active element. The command palette must not replace
    // an in-progress modal editing session.
    if (show.value || modalFormOpen()) return
    event.preventDefault()
    open()
  }
}
function navigate(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    selected.value = Math.max(
      0,
      Math.min(options.value.length - 1, selected.value + (event.key === 'ArrowDown' ? 1 : -1)),
    )
    document.getElementById(`command-${selected.value}`)?.scrollIntoView({ block: 'nearest' })
  } else if (event.key === 'Enter') {
    event.preventDefault()
    select(selected.value)
  }
}
onMounted(() => window.addEventListener('keydown', keyboard))
onUnmounted(() => window.removeEventListener('keydown', keyboard))
</script>

<template>
  <UiButton class="search-trigger" quaternary :aria-label="t('ui.quickSearch')" @click="open">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="1.5" />
      <path d="m16 16 5 5" stroke="currentColor" stroke-width="1.5" />
    </svg>
    <span class="search-label">{{ t('ui.quickSearch') }}</span>
    <kbd aria-hidden="true">{{ t('navigation.shortcut') }}</kbd>
  </UiButton>
  <UiModal
    v-model:show="show"
    preset="card"
    :title="t('navigation.searchHint')"
    class="command-palette"
    style="width: min(600px, calc(100vw - 24px))"
    @after-enter="nextTickFocus"
  >
    <UiInput
      ref="input"
      v-model:value="query"
      :placeholder="t('ui.quickSearch')"
      :input-props="{
        'aria-label': t('ui.quickSearch'),
        'aria-controls': 'command-results',
        'aria-activedescendant': `command-${selected}`,
      }"
      clearable
      @update:value="selected = 0"
      @keydown="navigate"
    />
    <div
      id="command-results"
      class="command-results"
      role="listbox"
      :aria-label="t('navigation.searchHint')"
    >
      <button
        v-for="(option, index) in options"
        :id="`command-${index}`"
        :key="option.key"
        type="button"
        role="option"
        :aria-selected="selected === index"
        class="command-result"
        @click="select(index)"
        @focus="selected = index"
      >
        <span>{{ option.label }}</span
        ><span class="command-route">{{ option.routeName }}</span>
      </button>
      <UiEmpty v-if="!options.length" :description="t('navigation.noResults')" />
    </div>
  </UiModal>
</template>

<style scoped>
.search-trigger {
  gap: 8px;
  border: 0;
}
.search-label {
  margin: 0 12px 0 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
kbd {
  padding: 1px 4px;
  color: var(--text-tertiary);
  background: var(--bg-inset);
  border: 1px solid var(--border);
  border-radius: 3px;
  font-size: 10px;
}
.command-results {
  max-height: min(460px, 60vh);
  margin-top: 12px;
  overflow-y: auto;
}
.command-result {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 12px;
  text-align: left;
  color: var(--text);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
}
.command-result:hover,
.command-result[aria-selected='true'] {
  background: var(--accent-soft);
  color: var(--accent);
}
.command-route {
  color: var(--text-tertiary);
  font: 11px var(--font-mono);
}
@media (max-width: 1024px) {
  .search-label,
  kbd {
    display: none;
  }
}
@media (max-width: 480px) {
  .command-route {
    display: none;
  }
}
</style>
