<script setup lang="ts">
import { computed } from 'vue'

import UiDropdown from './UiDropdown.vue'
const props = defineProps<{
  options: Array<{ label: string; value: string | number; disabled?: boolean }>
  trigger?: string
}>()
const emit = defineEmits<{ 'update:value': [value: string | number] }>()
const options = computed(() => props.options.map((option) => ({ ...option, key: option.value })))
</script>
<template>
  <UiDropdown :options="options" @select="emit('update:value', $event)"><slot /></UiDropdown>
</template>
