import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

import AdminLayout from '@/layout/AdminLayout.vue'
import AuthLayout from '@/layout/AuthLayout.vue'
import { menuTrail } from '@/layout/navigation/menuConfig'
import { identityFor } from '@/layout/navigation/routeIdentity'
import { pinia } from '@/stores'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    /** 免登录页面（登录、注册、找回与重置密码） */
    public?: boolean
    /** 仅管理员可访问；路由守卫与侧栏菜单可见性共用同一判定 */
    adminOnly?: boolean
    /**
     * 全屏页面：内容区不施加统一留白，由页面自己铺满。
     *
     * 必须走这个开关，而不是在页面里用负边距「顶出」留白——naive 在
     * NLayoutContent 内部套了一层 `overflow: hidden` 的滚动容器，
     * 负边距会让内容超出这层容器，被裁掉一条（设计器的顶部工具条就被裁过）。
     */
    fullBleed?: boolean
  }
}

/** 懒加载页面组件：非首屏路由一律按需加载（见 .agents/conventions/application-architecture.md）。 */
type LazyView = () => Promise<{ default: Component }>

/** AuthLayout 需要包住每个公开页，这里用「路径即父、页面为唯一子项」的写法保持 URL 与计划一致。 */
function authRoute(path: string, name: string, component: LazyView): RouteRecordRaw {
  return {
    path: `/${path}`,
    component: AuthLayout,
    children: [{ path: '', name, component, meta: { public: true } }],
  }
}

const routes: RouteRecordRaw[] = [
  authRoute('login', 'login', () => import('@/views/auth/LoginPage.vue')),
  authRoute('register', 'register', () => import('@/views/auth/RegisterPage.vue')),
  authRoute(
    'forgot-password',
    'forgot-password',
    () => import('@/views/auth/ForgotPasswordPage.vue'),
  ),
  authRoute('reset-password', 'reset-password', () => import('@/views/auth/ResetPasswordPage.vue')),
  {
    path: '/',
    component: AdminLayout,
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/dashboard/DashboardPage.vue'),
      },

      {
        path: 'knowledge-bases',
        name: 'knowledge-bases',
        component: () => import('@/views/knowledge/KnowledgeBaseListPage.vue'),
        meta: { title: 'kb.title' },
      },
      {
        path: 'knowledge-bases/:id',
        name: 'knowledge-base-detail',
        component: () => import('@/views/knowledge/KnowledgeBaseDetailPage.vue'),
        meta: { title: 'kb.detail' },
      },
      {
        path: 'knowledge-bases/:id/search',
        name: 'knowledge-base-search',
        component: () => import('@/views/knowledge/KnowledgeSearchPage.vue'),
        meta: { title: 'kb.searchTitle' },
      },

      { path: 'ontology', redirect: { name: 'entity-types' } },
      {
        path: 'ontology/ontologies',
        name: 'ontologies',
        component: () => import('@/views/ontology/ontologies/OntologiesPage.vue'),
      },
      {
        path: 'ontology/namespaces',
        name: 'namespaces',
        component: () => import('@/views/semantic-assets/namespaces/NamespacesPage.vue'),
      },
      {
        path: 'ontology/entity-types',
        name: 'entity-types',
        component: () => import('@/views/semantic-assets/entity-types/EntityTypesPage.vue'),
      },
      {
        path: 'ontology/entity-types/:id',
        name: 'entity-detail',
        component: () => import('@/views/semantic-assets/entity-types/EntityTypeDetailPage.vue'),
      },
      {
        path: 'ontology/relation-types',
        name: 'relation-types',
        component: () => import('@/views/semantic-assets/relation-types/RelationTypesPage.vue'),
      },
      {
        path: 'ontology/relation-types/:id',
        name: 'relation-detail',
        component: () =>
          import('@/views/semantic-assets/relation-types/RelationTypeDetailPage.vue'),
      },
      {
        path: 'ontology/domains',
        name: 'domains',
        component: () => import('@/views/semantic-assets/business-domains/BusinessDomainsPage.vue'),
      },
      {
        path: 'ontology/designer',
        name: 'designer',
        component: () => import('@/views/ontology/designer/DesignerPage.vue'),
        meta: { fullBleed: true },
      },

      {
        path: 'datasources',
        name: 'datasources',
        component: () => import('@/views/data-integration/sources/DataSourcesPage.vue'),
      },
      {
        path: 'datasources/catalog',
        name: 'data-catalog',
        component: () => import('@/views/data-integration/catalog/DataCatalogPage.vue'),
      },
      {
        path: 'datasources/preview',
        name: 'sample-preview',
        component: () => import('@/views/data-integration/catalog/preview/SamplePreviewPage.vue'),
      },

      {
        path: 'extraction',
        name: 'mapping-wizard',
        component: () => import('@/views/data-integration/mapping/MappingWorkbenchPage.vue'),
      },
      {
        path: 'extraction/runs',
        name: 'extraction-runs',
        component: () => import('@/views/data-integration/runs/ExtractionRunsPage.vue'),
      },
      {
        path: 'extraction/tasks',
        name: 'extraction-tasks',
        component: () => import('@/views/data-integration/tasks/ExtractionTasksPage.vue'),
      },
      {
        path: 'extraction/ai-assist',
        name: 'ai-assist',
        component: () => import('@/views/data-integration/mapping/ai-assist/AiAssistPage.vue'),
      },

      {
        path: 'graph',
        name: 'graph-browse',
        component: () => import('@/views/graph/browse/GraphBrowsePage.vue'),
        meta: { fullBleed: true },
      },
      {
        path: 'graph/entities',
        name: 'graph-entities',
        component: () => import('@/views/graph/entities/GraphEntitiesPage.vue'),
      },
      {
        path: 'graph/entities/:id',
        name: 'graph-entity-detail',
        component: () => import('@/views/graph/entities/GraphEntityDetailPage.vue'),
      },
      {
        path: 'graph/evidence',
        name: 'graph-evidence',
        component: () => import('@/views/graph/evidence/GraphEvidencePage.vue'),
      },
      {
        path: 'graph/reports',
        name: 'graph-reports',
        component: () => import('@/views/ontology/validation/ValidationReportsPage.vue'),
      },

      {
        path: 'governance/rules',
        name: 'governance-rules',
        component: () => import('@/views/governance/rules/GovernanceRulesPage.vue'),
      },
      {
        path: 'governance/clauses',
        name: 'governance-clauses',
        component: () => import('@/views/governance/clauses/StandardClausesPage.vue'),
      },
      {
        path: 'governance/enum-dictionaries',
        name: 'enum-dictionaries',
        component: () =>
          import('@/views/semantic-assets/configuration/enum-dictionaries/EnumDictionariesPage.vue'),
        meta: {},
      },
      {
        path: 'governance/templates',
        name: 'assembly-templates',
        component: () =>
          import('@/views/semantic-assets/configuration/assembly-templates/AssemblyTemplatesPage.vue'),
      },
      {
        path: 'governance/export',
        name: 'ontology-export',
        component: () => import('@/views/governance/exchange/OntologyExchangePage.vue'),
      },

      {
        path: 'account/profile',
        name: 'account-profile',
        component: () => import('@/views/account/ProfilePage.vue'),
      },
      {
        path: 'account/security',
        name: 'account-security',
        component: () => import('@/views/account/SecurityPage.vue'),
      },

      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('@/views/system/users/UsersPage.vue'),
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('@/views/system/roles/RolesPage.vue'),
      },
      {
        path: 'system/audit-logs',
        name: 'system-audit-logs',
        component: () => import('@/views/system/audit-logs/AuditLogsPage.vue'),
      },
      {
        path: 'system/ai-models',
        name: 'system-ai-models',
        component: () => import('@/views/system/ai-models/AiModelsPage.vue'),
      },

      {
        path: 'forbidden',
        name: 'forbidden',
        component: () => import('@/views/errors/ForbiddenPage.vue'),
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/errors/NotFoundPage.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Titles and access metadata share the navigation identity registry. URLs stay stable.
for (const route of router.getRoutes()) {
  const identity = identityFor(route.name)
  if (!identity) continue
  route.meta.title = identity.title
  const adminByMenu = menuTrail(identity.owner).some((node) => node.adminOnly)
  // The route guard, menu and search all read the same navigation identity.
  route.meta.adminOnly = adminByMenu
}

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)

  if (to.meta.public) {
    // 已登录还停留在登录/注册页 → 直接进工作台
    if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
      return { name: 'dashboard' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.adminOnly) {
    // 角色来自 /auth/me，首次进入受限页时补拉一次
    if (!auth.user) await auth.loadMe()
    // loadMe 失败说明会话已失效（401 拦截器已清空凭据）；
    // 此时应回登录页并保留 redirect，而不是判成"已登录但无权限"。
    //
    // 这里判 `auth.user` 而不是 `auth.isAuthenticated`：后者是
    // `user !== null || hasSession()` 的 computed，而 hasSession() 读的是
    // localStorage、不是响应式依赖；凭据被清空时 user 本就是 null（无变化），
    // computed 不会失效，会一直返回清空前的旧值 true。
    if (!auth.user) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (!auth.isAdmin) return { name: 'forbidden', query: { redirect: to.fullPath } }
  }

  return true
})
