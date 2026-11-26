<script setup lang="ts">
import { useId } from 'vue'
import { useI18n } from 'vue-i18n'

import type { TableFilters } from '@/components/ui/tableTypes'

const props = withDefaults(
  defineProps<{
    query?: string
    loading?: boolean
    disabled?: boolean
    expanded?: boolean
    filters?: TableFilters
    label?: string
    placeholder?: string
  }>(),
  { query: '', expanded: false },
)
const emit = defineEmits<{
  'update:query': [value: string]
  'update:expanded': [value: boolean]
  'update:filters': [value: TableFilters]
  submit: [query: string, filters: TableFilters]
  reset: []
  clear: []
}>()
const { t } = useI18n()
const id = useId()
function submit() {
  if (!props.disabled) emit('submit', props.query.trim(), props.filters ?? {})
}
function input(event: Event) {
  if (!props.disabled) emit('update:query', (event.target as HTMLInputElement).value)
}
function clear() {
  if (props.disabled) return
  emit('update:query', '')
  emit('clear')
}
function reset() {
  if (!props.disabled) emit('reset')
}
function updateFilters(value: TableFilters) {
  if (!props.disabled) emit('update:filters', value)
}
</script>

<template>
  <form
    class="search-panel space-y-3"
    :aria-busy="loading"
    @submit.prevent="submit"
    @reset.prevent="reset"
  >
    <div class="flex flex-wrap items-end gap-2">
      <div class="search-query min-w-40 flex-1">
        <label :for="id" :class="label ? 'mb-1 block text-sm font-medium' : 'sr-only'">{{
          label ?? t('common.search')
        }}</label>
        <input
          :id="id"
          type="search"
          class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
          :value="query"
          :disabled="disabled"
          :placeholder="placeholder ?? label ?? t('common.search')"
          @input="input"
        />
      </div>
      <slot name="filter" :filters="filters ?? {}" :disabled="disabled" :update="updateFilters">
        <slot
          name="filters"
          :filters="filters ?? {}"
          :disabled="disabled"
          :update="updateFilters"
        />
      </slot>
      <slot name="actions" :submit="submit" :clear="clear" :reset="reset" :disabled="disabled">
        <button
          type="submit"
          :aria-busy="loading"
          class="h-9 rounded-md bg-primary px-3 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
          :disabled="disabled"
        >
          {{ t('common.search') }}
        </button>
        <button
          type="button"
          class="h-9 rounded-md border border-input px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
          :disabled="disabled || !query"
          @click="clear"
        >
          {{ t('ds.search.clear') }}
        </button>
        <button
          type="reset"
          class="h-9 rounded-md border border-input px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
          :disabled="disabled"
        >
          {{ t('ds.search.reset') }}
        </button>
      </slot>
      <button
        v-if="$slots.advanced"
        type="button"
        class="h-9 rounded-md px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
        :aria-expanded="expanded"
        :aria-controls="`${id}-advanced`"
        :disabled="disabled"
        @click="emit('update:expanded', !expanded)"
      >
        {{ t('kb.advanced') }}
      </button>
    </div>
    <div v-if="$slots.advanced" v-show="expanded" :id="`${id}-advanced`">
      <slot name="advanced" :filters="filters ?? {}" :disabled="disabled" :update="updateFilters" />
    </div>
    <slot :query="query" :filters="filters ?? {}" :submit="submit" />
  </form>
</template>

<style scoped>
.search-panel {
  min-width: 0;
  padding: 12px 0;
}
.search-query {
  flex-basis: 240px;
}
.search-panel :deep(.ui-field) {
  margin-bottom: 0;
}
input[type='search'] {
  background: var(--surface-panel);
}
@media (min-width: 1280px) {
  .search-query {
    max-width: 440px;
  }
}
</style>
