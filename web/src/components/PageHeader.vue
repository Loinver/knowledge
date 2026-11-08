<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <header class="page-header">
    <div class="titles">
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
      <slot name="context" />
    </div>
    <div class="actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.titles {
  flex: 1 1 240px;
  min-width: 0;
}
.titles h1 {
  margin: 0;
  font-size: var(--font-h1);
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.titles p {
  max-width: 74ch;
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  max-width: 100%;
  gap: var(--space-2);
  align-items: center;
}
@media (max-width: 640px) {
  .page-header {
    flex-wrap: wrap;
  }
  .titles,
  .actions {
    width: 100%;
  }
  .actions {
    flex-wrap: wrap;
  }
}
</style>
