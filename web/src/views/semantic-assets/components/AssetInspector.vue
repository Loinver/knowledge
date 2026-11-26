<script setup lang="ts">
import { onBeforeMount, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { UiButton, UiDrawer } from '@/components/ui'
import { useUiStore } from '@/stores/ui'

import AssetIdentity from './AssetIdentity.vue'

defineProps<{
  label: string
  name: string
  iri: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  revision: number
}>()
defineEmits<{ close: []; open: [] }>()
const { t } = useI18n()
const ui = useUiStore()
let origin: HTMLElement | null = null
onBeforeMount(() => {
  origin = document.activeElement instanceof HTMLElement ? document.activeElement : null
})
onUnmounted(() => {
  if (origin?.isConnected) origin.focus()
})
</script>

<template>
  <component
    :is="ui.narrow ? UiDrawer : 'aside'"
    :show="ui.narrow"
    width="min(360px, 100vw)"
    class="asset-inspector"
    :aria-label="t('ui.view')"
    @update:show="!$event && $emit('close')"
  >
    <header class="inspector-heading">
      <span>{{ t('ui.view') }}</span>
      <UiButton size="small" quaternary @click="$emit('close')">{{ t('common.close') }}</UiButton>
    </header>
    <div class="inspector-identity">
      <h2>{{ label }}</h2>
      <AssetIdentity :name="name" :iri="iri" :status="status" :revision="revision" />
      <p>
        {{
          t(
            status === 'PUBLISHED'
              ? 'assetStudio.publishedVersion'
              : status === 'DRAFT'
                ? 'ui.working'
                : 'resourceStatus.ARCHIVED',
          )
        }}
      </p>
    </div>
    <div class="inspector-content"><slot /></div>
    <footer class="inspector-footer">
      <UiButton type="primary" @click="$emit('open')">{{ t('ui.view') }}</UiButton>
      <slot name="actions" />
    </footer>
  </component>
</template>

<style scoped>
.asset-inspector {
  min-width: 0;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  background: var(--surface-panel);
  align-self: start;
}
.inspector-heading,
.inspector-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px;
}
.inspector-heading {
  border-bottom: 1px solid var(--border-muted);
  color: var(--foreground-muted);
  font-size: 12px;
}
.inspector-identity {
  padding: 20px 16px;
  background: var(--surface-muted);
}
h2 {
  margin: 0 0 12px;
  font-size: 18px;
  overflow-wrap: anywhere;
}
p {
  margin: 12px 0 0;
  color: var(--foreground-muted);
  font-size: 12px;
  line-height: 1.7;
}
.inspector-content {
  padding: 16px;
  overflow-wrap: anywhere;
}
.inspector-footer {
  border-top: 1px solid var(--border-muted);
  flex-wrap: wrap;
}
</style>
