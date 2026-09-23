<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <header class="page-header">
    <div class="titles">
      <h2>{{ title }}</h2>
      <p v-if="description">{{ description }}</p>
    </div>
    <div class="actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.titles h2 {
  margin: 0;
  font-size: var(--font-h1);
  font-weight: 500;
  line-height: 1.4;
}
.titles p {
  max-width: 74ch;
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
}
.actions {
  display: flex;
  flex: 0 0 auto;
  gap: var(--space-2);
  align-items: center;
}
</style>
