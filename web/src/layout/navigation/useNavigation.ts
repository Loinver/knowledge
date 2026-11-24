import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import type { MenuOption } from '@/components/ui/menuTypes'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

import { GROUP_PREFIX, menuLeaves, type MenuNode, menuTrail, visibleMenu } from './menuConfig'
import { identityFor } from './routeIdentity'
import { searchIndex } from './searchIndex'
import { currentPageIdentity } from './usePageIdentity'

export function useNavigation() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const ui = useUiStore()
  const objectIdentity = currentPageIdentity()
  const identity = computed(() => identityFor(route.name))
  const activeKey = computed(() => identity.value?.owner ?? String(route.name ?? ''))
  const tree = computed(() => visibleMenu(auth.isAdmin))
  const trail = computed(() => menuTrail(activeKey.value, tree.value))
  const expandedKeys = ref<string[]>([])
  function expandMenuPath(keys: string[]) {
    const allowed = keys.filter((key) => menuTrail(key, tree.value).length)
    return allowed
  }
  const options = (nodes: MenuNode[]): MenuOption[] =>
    nodes.map((node) => ({
      key: node.key,
      label: t(node.labelKey),
      ...(node.icon ? { icon: () => h(AppIcon, { name: node.icon! }) } : {}),
      ...(node.children ? { children: options(node.children) } : {}),
    }))
  const menuOptions = computed(() => options(tree.value))
  watch(
    trail,
    () => {
      expandedKeys.value = [
        ...new Set([
          ...expandMenuPath(expandedKeys.value),
          ...trail.value.filter((node) => node.children).map((node) => node.key),
        ]),
      ]
    },
    { immediate: true },
  )
  const breadcrumb = computed(() => {
    const crumbs: { key: string; label: string; to?: string }[] = trail.value.map((node) => ({
      key: node.key,
      label: t(node.labelKey),
      ...(!node.children && route.name !== node.key ? { to: node.key } : {}),
    }))
    if (identity.value && route.name !== activeKey.value) {
      const label = objectIdentity.value?.path === route.fullPath ? objectIdentity.value.label : ''
      crumbs.push({
        key: String(route.name),
        label: identity.value.object
          ? label || String(route.params.id ?? t(identity.value.title))
          : t(identity.value.title),
      })
      if (route.name === 'knowledge-base-search') {
        crumbs[crumbs.length - 1].to = 'knowledge-base-detail'
        crumbs.push({ key: 'search', label: t(identity.value.title) })
      } else if (route.name === 'knowledge-base-detail' && route.query.doc) {
        crumbs.push({
          key: 'document',
          label: t('navigation.documentIdentity', { id: route.query.doc }),
        })
      }
    }
    if (!crumbs.length && identity.value)
      crumbs.push({ key: activeKey.value, label: t(identity.value.title) })
    return crumbs
  })
  function selectMenu(key: string) {
    if (key.startsWith(GROUP_PREFIX) || !menuLeaves(tree.value).some((node) => node.key === key))
      return
    ui.closeMobileSider()
    void router.push({ name: key })
  }
  const searchPages = (query: string) => searchIndex(auth.isAdmin, t, query)
  return {
    menuOptions,
    activeKey,
    expandedKeys,
    breadcrumb,
    selectMenu,
    searchPages,
    expandMenuPath,
  }
}
