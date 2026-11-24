<template>
  <li class="ui-list-item"><slot /></li>
</template>
<style scoped>
.ui-list-item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-muted);
}
.ui-list-item:last-child {
  border-bottom: 0;
}
</style>
