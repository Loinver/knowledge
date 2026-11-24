<script setup lang="ts">
defineProps<{ label?: string; span?: number }>()
</script>
<template>
  <div :style="{ gridColumn: span ? 'span ' + span : undefined, minWidth: 0 }">
    <dt class="ui-description-label">
      <slot name="label">{{ label }}</slot>
    </dt>
    <dd class="ui-description-value"><slot /></dd>
  </div>
</template>
