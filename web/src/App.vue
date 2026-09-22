<script setup lang="ts">
import type { MenuOption } from 'naive-ui'
import {
  enUS,
  NButton,
  NConfigProvider,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  zhCN,
} from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView, useRouter } from 'vue-router'

import { useLocaleStore } from '@/stores/locale'
const { t, locale } = useI18n()
const router = useRouter()
const localeStore = useLocaleStore()
const themeOverrides = {
  common: {
    primaryColor: '#315ee7',
    primaryColorHover: '#2a54d1',
    primaryColorPressed: '#2349b8',
    borderRadius: '4px',
  },
}
const menuOptions = computed<MenuOption[]>(() => [
  { label: () => t('menu.dashboard'), key: 'dashboard' },
  { label: () => t('menu.ontology'), key: 'ontology' },
  { label: () => t('menu.datasources'), key: 'datasources' },
  { label: () => t('menu.extraction'), key: 'extraction' },
  { label: () => t('menu.graph'), key: 'graph' },
  {
    label: () => t('menu.governance'),
    key: 'governance',
    children: [
      { label: () => t('page.governanceRules'), key: 'governance-rules' },
      { label: () => t('export.title'), key: 'ontology-export' },
      { label: () => t('templates.title'), key: 'assembly-templates' },
    ],
  },
])
function handleMenuSelect(key: string) {
  if (key === 'dashboard') router.push('/')
  else if (key === 'ontology') router.push('/ontology/entity-types')
  else if (key === 'datasources') router.push('/datasources')
  else if (key === 'extraction') router.push('/extraction')
  else if (key === 'graph') router.push('/graph')
  else if (key === 'governance') router.push('/governance/rules')
  else if (key === 'governance-rules') router.push('/governance/rules')
  else if (key === 'ontology-export') router.push('/governance/export')
  else if (key === 'assembly-templates') router.push('/governance/templates')
}
function toggleLocale() {
  localeStore.change(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN')
}
</script>
<template>
  <NConfigProvider :theme-overrides="themeOverrides" :locale="locale === 'zh-CN' ? zhCN : enUS">
    <NLayout style="min-height: 100vh">
      <NLayoutHeader
        bordered
        style="
          height: 56px;
          padding: 0 24px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        "
      >
        <div style="display: flex; align-items: baseline; gap: 16px">
          <span style="font-size: 18px; font-weight: 700; color: var(--pri)">{{
            t('app.title')
          }}</span>
          <span style="font-size: 12px; color: var(--text-tertiary)">{{ t('app.subtitle') }}</span>
        </div>
        <NButton size="small" quaternary @click="toggleLocale">{{ localeStore.label }}</NButton>
      </NLayoutHeader>
      <NLayout has-sider>
        <NLayoutSider bordered style="width: 200px">
          <NMenu :options="menuOptions" @update:value="handleMenuSelect" />
        </NLayoutSider>
        <NLayoutContent style="padding: 24px">
          <RouterView />
        </NLayoutContent>
      </NLayout>
    </NLayout>
  </NConfigProvider>
</template>
<style scoped></style>
