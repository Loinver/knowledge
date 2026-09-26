import type { MenuOption } from 'naive-ui'
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import type { IconName } from '@/components/icons'
import { useAuthStore } from '@/stores/auth'

/**
 * 导航单一真值源：侧栏菜单、面包屑都从这里派生。
 *
 * 关键约束：菜单项的 key **就是路由名**，高亮由 `route.name` 反推，
 * 不再维护「菜单 key → 路径」的硬编码映射表（旧实现是 9 个 if-else，
 * 刷新或前进后退后高亮会丢）。
 */

export const GROUP_PREFIX = 'group:'

/** 详情页没有独立菜单项，高亮与面包屑回到它的列表页。 */
const detailFallback: Record<string, string> = {
  'entity-detail': 'entity-types',
  'graph-entity-detail': 'graph-entities',
}

interface NavGroup {
  group: string
  icon: IconName
  label: string
  items: { key: string; label: string }[]
}

export function useNavigation() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()

  const activeKey = computed(() => {
    const name = typeof route.name === 'string' ? route.name : ''
    return detailFallback[name] ?? name
  })

  const groups = computed<NavGroup[]>(() => {
    const tree: NavGroup[] = [
      {
        group: 'entity-types',
        icon: 'ontology',
        label: t('menu.entityTypes'),
        items: [
          { key: 'entity-types', label: t('page.entityTypes') },
          { key: 'namespaces', label: t('page.namespaces') },
          { key: 'enum-dictionaries', label: t('enumDictionaries.title') },
        ],
      },
      {
        group: 'relation-types',
        icon: 'ontology',
        label: t('menu.relationTypes'),
        items: [{ key: 'relation-types', label: t('page.relationTypes') }],
      },
      {
        group: 'domains',
        icon: 'ontology',
        label: t('menu.domains'),
        items: [{ key: 'domains', label: t('page.domains') }],
      },
      {
        group: 'ontology',
        icon: 'ontology',
        label: t('menu.ontology'),
        items: [
          { key: 'ontologies', label: t('page.ontologies') },
          { key: 'assembly-templates', label: t('templates.title') },
          { key: 'ontology-export', label: t('export.title') },
        ],
      },
      {
        group: 'designer',
        icon: 'ontology',
        label: t('menu.designer'),
        items: [{ key: 'designer', label: t('page.designer') }],
      },
      {
        group: 'rules',
        icon: 'governance',
        label: t('menu.rules'),
        items: [
          { key: 'governance-rules', label: t('page.governanceRules') },
          { key: 'governance-clauses', label: t('page.governanceClauses') },
        ],
      },
      {
        group: 'extraction',
        icon: 'extraction',
        label: t('menu.extraction'),
        items: [
          { key: 'datasources', label: t('page.dataSources') },
          { key: 'data-catalog', label: t('page.dataCatalog') },
          { key: 'sample-preview', label: t('page.samplePreview') },
          { key: 'mapping-wizard', label: t('page.mappingWizard') },
          { key: 'extraction-runs', label: t('page.extractionRuns') },
          { key: 'ai-assist', label: t('page.aiAssist') },
        ],
      },
      {
        group: 'graph',
        icon: 'graph',
        label: t('menu.graph'),
        items: [
          { key: 'graph-browse', label: t('page.graphBrowse') },
          { key: 'graph-entities', label: t('page.graphEntities') },
          { key: 'graph-reports', label: t('page.graphReports') },
        ],
      },
      {
        group: 'evidence',
        icon: 'governance',
        label: t('menu.evidence'),
        items: [{ key: 'graph-evidence', label: t('page.graphEvidence') }],
      },
    ]
    // 系统管理仅管理员可见（前端改版计划 5.3）
    if (auth.isAdmin) {
      tree.push({
        group: 'system',
        icon: 'system',
        label: t('menu.system'),
        items: [
          { key: 'system-users', label: t('page.systemUsers') },
          { key: 'system-roles', label: t('page.systemRoles') },
          { key: 'system-audit-logs', label: t('page.systemAuditLogs') },
        ],
      })
    }
    return tree
  })

  function renderIcon(name: IconName) {
    return () => h(AppIcon, { name })
  }

  const menuOptions = computed<MenuOption[]>(() => [
    { label: () => t('menu.dashboard'), key: 'dashboard', icon: renderIcon('dashboard') },
    ...groups.value.map((group) => ({
      label: () => group.label,
      key: group.items.length === 1 ? group.items[0].key : `${GROUP_PREFIX}${group.group}`,
      icon: renderIcon(group.icon),
      children:
        group.items.length > 1
          ? group.items.map((item) => ({ label: () => item.label, key: item.key }))
          : undefined,
    })),
  ])

  const expandedKeys = ref<string[]>([])

  function ownerGroup(key: string): NavGroup | undefined {
    return groups.value.find((group) => group.items.some((item) => item.key === key))
  }

  watch(
    activeKey,
    (key) => {
      const owner = ownerGroup(key)
      expandedKeys.value = owner && owner.items.length > 1 ? [`${GROUP_PREFIX}${owner.group}`] : []
    },
    { immediate: true },
  )

  /** 面包屑：分组名 + 页面名（工作台只有一级）。 */
  const breadcrumb = computed(() => {
    const key = activeKey.value
    if (key === 'dashboard') return [{ key: 'dashboard', label: t('menu.dashboard') }]
    const owner = ownerGroup(key)
    const leaf = owner?.items.find((item) => item.key === key)
    if (!owner || !leaf) return []
    if (owner.items.length === 1) return [{ key: leaf.key, label: leaf.label }]
    return [
      { key: owner.group, label: owner.label, to: owner.items[0].key },
      { key: leaf.key, label: leaf.label },
    ]
  })

  function selectMenu(key: string) {
    if (key.startsWith(GROUP_PREFIX)) return
    void router.push({ name: key })
  }

  return { groups, menuOptions, activeKey, expandedKeys, breadcrumb, selectMenu, renderIcon }
}
