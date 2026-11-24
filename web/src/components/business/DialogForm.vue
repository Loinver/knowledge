<script setup lang="ts">
import UiModal from '@/components/ui/UiModal.vue'
defineProps<{ show: boolean; title: string; submitting?: boolean }>()
const emit = defineEmits<{ 'update:show': [show: boolean] }>()
</script>
<template>
  <UiModal
    :show="show"
    :title="title"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    :closable="!submitting"
    @update:show="emit('update:show', $event)"
    ><slot /><template v-if="$slots.actions" #footer><slot name="actions" /></template
  ></UiModal>
</template>
