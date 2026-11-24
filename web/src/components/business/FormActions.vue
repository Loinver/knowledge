<script setup lang="ts">
defineProps<{ submitting?: boolean }>()
</script>
<template>
  <div class="ui-form-actions" :aria-busy="submitting || undefined"><slot /></div>
</template>
