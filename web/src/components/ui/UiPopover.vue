<script setup lang="ts">
import { PopoverContent, PopoverPortal } from 'reka-ui'
import { computed, ref } from 'vue'

import { Popover, PopoverTrigger } from './primitives/popover'

const props = withDefaults(
  defineProps<{
    show?: boolean
    trigger?: 'click' | 'hover' | 'manual'
    disabled?: boolean
    placement?: string
    width?: number | string
  }>(),
  { trigger: 'click' },
)
const emit = defineEmits<{ 'update:show': [show: boolean] }>()
const local = ref(false)
const open = computed({
  get: () => props.show ?? local.value,
  set: (value) => {
    if (!props.disabled) {
      local.value = value
      emit('update:show', value)
    }
  },
})
</script>
<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child><slot name="trigger" /></PopoverTrigger>
    <PopoverPortal
      ><PopoverContent
        class="ui-popup"
        :side-offset="6"
        :style="{ width: typeof width === 'number' ? width + 'px' : width }"
        ><slot /></PopoverContent
    ></PopoverPortal>
  </Popover>
</template>
