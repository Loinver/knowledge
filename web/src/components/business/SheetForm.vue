<script setup lang="ts">
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiDrawerContent from '@/components/ui/UiDrawerContent.vue'
defineProps<{ show: boolean; title: string; submitting?: boolean; width?: number | string }>()
const emit = defineEmits<{ 'update:show': [show: boolean] }>()
</script>
<template>
  <UiDrawer
    :show="show"
    :width="width"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    @update:show="emit('update:show', $event)"
    ><UiDrawerContent :title="title" :closable="!submitting"
      ><slot /><template v-if="$slots.actions" #footer
        ><slot name="actions" /></template></UiDrawerContent
  ></UiDrawer>
</template>
