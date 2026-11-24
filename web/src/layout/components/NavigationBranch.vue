<script setup lang="ts">
import { computed } from 'vue'

import type { MenuOption } from '@/components/ui/menuTypes'

const props = defineProps<{
  node: MenuOption
  active: string
  expanded: string[]
  collapsed?: boolean
  depth?: number
}>()
const emit = defineEmits<{ select: [key: string]; toggle: [key: string]; expand: [] }>()
const key = computed(() => String(props.node.key ?? ''))
const label = computed(() => (typeof props.node.label === 'string' ? props.node.label : key.value))
const opened = computed(() => props.expanded.includes(key.value))
function activate() {
  if (props.node.disabled) return
  if (props.node.children?.length) {
    if (props.collapsed) emit('expand')
    emit('toggle', key.value)
  } else emit('select', key.value)
}
</script>
<template>
  <li v-if="node.show !== false" class="nav-branch">
    <button
      type="button"
      class="nav-item"
      :class="{ 'is-active': active === key, 'is-group': node.children?.length }"
      :style="{
        paddingLeft: collapsed ? undefined : 'calc(var(--space-3) + ' + (depth || 0) * 12 + 'px)',
      }"
      :aria-label="label"
      :title="collapsed ? label : undefined"
      :aria-current="active === key ? 'page' : undefined"
      :aria-expanded="node.children?.length && !collapsed ? opened : undefined"
      :disabled="node.disabled"
      @click="activate"
    >
      <span v-if="node.icon" class="nav-icon" aria-hidden="true"
        ><component :is="node.icon"
      /></span>
      <span v-if="!collapsed" class="nav-label">{{ label }}</span>
      <svg
        v-if="node.children?.length && !collapsed"
        class="nav-chevron"
        :class="{ opened }"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <path d="m9 6 6 6-6 6" stroke="currentColor" stroke-width="1.5" />
      </svg>
    </button>
    <ul v-if="node.children?.length && opened && !collapsed" class="nav-children">
      <NavigationBranch
        v-for="child in node.children"
        :key="String(child.key)"
        :node="child"
        :active="active"
        :expanded="expanded"
        :depth="(depth || 0) + 1"
        @select="emit('select', $event)"
        @toggle="emit('toggle', $event)"
      />
    </ul>
  </li>
</template>
<style scoped>
.nav-children {
  padding: 0;
  margin: 2px 0 6px;
  list-style: none;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-height: var(--control-height);
  padding: 7px var(--space-3);
  margin: 2px 0;
  font-size: var(--font-small);
  text-align: left;
  color: var(--foreground-secondary);
  background: transparent;
  border: 0;
  border-radius: var(--radius-control);
}
.nav-item:hover {
  color: var(--foreground-primary);
  background: var(--surface-hover);
}
.nav-item.is-active {
  color: var(--action-primary);
  background: var(--surface-selected);
  font-weight: 600;
}
.nav-icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 20px;
}
.nav-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nav-chevron {
  flex: none;
  transition: transform var(--duration-fast);
}
.nav-chevron.opened {
  transform: rotate(90deg);
}
</style>
