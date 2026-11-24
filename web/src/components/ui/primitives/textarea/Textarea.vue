<!-- Source: https://www.shadcn-vue.com/r/styles/reka-nova/textarea.json; original registry SHA256: d53ac9b8bb98d49b4fa494039a2c38beff25bb46bd8c3739e68c8a0461bc401f. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md. -->
<script setup lang="ts">
import { useVModel } from '@vueuse/core'
import type { HTMLAttributes } from 'vue'

import { cn } from '@/components/ui/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  defaultValue?: string | number
  modelValue?: string | number
}>()

const emits = defineEmits<{
  (e: 'update:modelValue', payload: string | number): void
}>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue,
})
</script>

<template>
  <textarea
    v-model="modelValue"
    data-slot="textarea"
    :class="
      cn(
        'border-input dark:bg-input/30 focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:aria-invalid:border-destructive/50 disabled:bg-input/50 dark:disabled:bg-input/80 rounded-[var(--radius-control)] border bg-transparent px-2.5 py-2 text-[length:var(--font-body)] transition-colors focus-visible:ring-3 aria-invalid:ring-3 md:text-[length:var(--font-body)] flex field-sizing-content min-h-[calc(var(--space-1)*16)] w-full outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50',
        props.class,
      )
    "
  />
</template>
