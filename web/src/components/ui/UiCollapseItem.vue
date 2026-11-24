<script setup lang="ts">
import { ChevronDown } from '@lucide/vue'
import { AccordionContent, AccordionHeader, AccordionItem, AccordionTrigger } from 'reka-ui'

import type { SelectionKey } from './selectionTypes'
import { selectionKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  name: SelectionKey
  title?: string
  disabled?: boolean
  readonly?: boolean
  displayDirective?: 'if' | 'show'
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
</script>
<template>
  <AccordionItem class="collapse-item" :value="selectionKey(name)" :disabled="disabled || readonly">
    <AccordionHeader
      ><AccordionTrigger
        v-bind="attributes"
        class="collapse-trigger"
        @blur="field?.validate('blur')"
        ><slot name="header">{{ title }}</slot
        ><ChevronDown :size="16" /></AccordionTrigger
    ></AccordionHeader>
    <AccordionContent class="collapse-content" :force-mount="displayDirective === 'show'"
      ><slot
    /></AccordionContent>
  </AccordionItem>
</template>
<style scoped>
.collapse-item {
  border-bottom: 1px solid var(--border-muted);
}
.collapse-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: var(--control-height);
  padding: var(--space-2) 0;
  color: var(--foreground-primary);
  background: transparent;
  border: 0;
  font-size: var(--font-body);
  text-align: start;
}
.collapse-trigger[data-state='open'] svg {
  transform: rotate(180deg);
}
.collapse-content {
  padding: var(--space-3) 0;
}
.collapse-content[data-state='closed'] {
  display: none;
}
</style>
