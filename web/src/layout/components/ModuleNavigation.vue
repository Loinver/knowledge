<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { menuLeaves } from '@/layout/navigation/menuConfig'
import { useNavigation } from '@/layout/navigation/useNavigation'

const { t, locale } = useI18n()
const { trail, activeKey } = useNavigation()
const sections = computed(() => trail.value[0]?.children ?? [])
const navigation = ref<HTMLElement | null>(null)
function reveal(target?: HTMLElement | null) {
  const element = navigation.value
  const active = target ?? element?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!element || !active) return
  const bounds = element.getBoundingClientRect()
  const item = active.getBoundingClientRect()
  if (item.left < bounds.left + 12) element.scrollLeft += item.left - bounds.left - 12
  else if (item.right > bounds.right - 12) element.scrollLeft += item.right - bounds.right + 12
}
let resizeObserver: ResizeObserver | undefined
watch(navigation, (element) => {
  resizeObserver?.disconnect()
  if (!element) return
  resizeObserver = new ResizeObserver(() => reveal())
  resizeObserver.observe(element)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
watch(
  [activeKey, locale],
  async () => {
    await nextTick()
    reveal()
  },
  { immediate: true },
)
</script>

<template>
  <nav
    v-if="sections.length"
    ref="navigation"
    class="module-navigation"
    :aria-label="t('studio.moduleNavigation')"
    @focusin="reveal($event.target as HTMLElement)"
  >
    <template v-for="section in sections" :key="section.key">
      <span v-if="section.children" class="section-caption">{{ t(section.labelKey) }}</span>
      <RouterLink
        v-for="leaf in menuLeaves([section])"
        :key="leaf.key"
        :to="{ name: leaf.key }"
        class="module-link"
        :class="{ 'is-active': activeKey === leaf.key }"
        :aria-current="activeKey === leaf.key ? 'page' : undefined"
        >{{ t(leaf.labelKey) }}</RouterLink
      >
    </template>
  </nav>
</template>

<style scoped>
.module-navigation {
  display: flex;
  flex: none;
  align-items: stretch;
  gap: 24px;
  min-height: var(--module-nav-height);
  padding: 0 var(--page-gutter);
  overflow-x: auto;
  background: var(--surface-panel);
  border-bottom: 1px solid var(--border-muted);
  scrollbar-width: none;
}
.module-link {
  display: inline-flex;
  flex: none;
  align-items: center;
  min-height: var(--module-nav-height);
  color: var(--foreground-secondary);
  font-size: var(--font-small);
  text-decoration: none;
  border-bottom: 2px solid transparent;
}
.module-link:hover {
  color: var(--action-primary);
}
.module-link.is-active {
  color: var(--action-primary);
  font-weight: 600;
  border-bottom-color: var(--action-primary);
}
.module-link:focus-visible {
  outline-offset: -3px;
}
.section-caption {
  display: inline-flex;
  flex: none;
  align-items: center;
  white-space: nowrap;
  margin-left: 6px;
  padding-left: 24px;
  color: var(--foreground-muted);
  font-size: 11px;
  border-left: 1px solid var(--border-muted);
}
@media (max-width: 767px) {
  .module-navigation {
    gap: 18px;
  }
}
</style>
