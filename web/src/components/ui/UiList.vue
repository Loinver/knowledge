<script setup lang="ts">
defineProps<{ bordered?: boolean }>()
</script>
<template>
  <ul class="ui-list" :class="{ 'ui-card': bordered }">
    <slot />
  </ul>
</template>
<style scoped>
.ui-list {
  padding: 0;
  margin: 0;
  list-style: none;
}
</style>
