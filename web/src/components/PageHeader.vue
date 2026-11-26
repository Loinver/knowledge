<script setup lang="ts">
defineProps<{ title: string; description?: string; eyebrow?: string; identity?: string }>()
</script>

<template>
  <header class="page-header">
    <div class="titles">
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <code v-if="identity" class="identity">{{ identity }}</code>
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
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding: 0;
  margin-bottom: var(--space-5);
}
.titles {
  flex: 1 1 240px;
  min-width: 0;
}
.titles h1 {
  margin: 0;
  font-size: var(--font-h1);
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.titles .eyebrow {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.06em;
}
.identity {
  display: block;
  margin-top: 6px;
  color: var(--text-tertiary);
  font-size: 11px;
  overflow-wrap: anywhere;
}
.titles p {
  max-width: 90ch;
  margin: var(--space-2) 0 0;
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
