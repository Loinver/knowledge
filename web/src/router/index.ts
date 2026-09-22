import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

import AdminLayout from '@/layout/AdminLayout.vue'
import AuthLayout from '@/layout/AuthLayout.vue'
import { pinia } from '@/stores'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    /** 免登录页面（登录、注册、找回与重置密码） */
    public?: boolean
    /** 仅管理员可访问；路由守卫与侧栏菜单可见性共用同一判定 */
    adminOnly?: boolean
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
  authRoute('login', 'login', () => import('@/views/auth/Login.vue')),
  authRoute('register', 'register', () => import('@/views/auth/Register.vue')),
  authRoute('forgot-password', 'forgot-password', () => import('@/views/auth/ForgotPassword.vue')),
  authRoute('reset-password', 'reset-password', () => import('@/views/auth/ResetPassword.vue')),
  {
    path: '/',
    component: AdminLayout,
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },

      { path: 'ontology', redirect: { name: 'entity-types' } },
      {
        path: 'ontology/entity-types',
        name: 'entity-types',
        component: () => import('@/views/EntityTypes.vue'),
      },
      {
        path: 'ontology/entity-types/:id',
        name: 'entity-detail',
        component: () => import('@/views/EntityDetail.vue'),
      },
      {
        path: 'ontology/relation-types',
        name: 'relation-types',
        component: () => import('@/views/RelationTypes.vue'),
      },
      { path: 'ontology/domains', name: 'domains', component: () => import('@/views/Domains.vue') },
      {
        path: 'ontology/designer',
        name: 'designer',
        component: () => import('@/views/Designer.vue'),
      },

      {
        path: 'datasources',
        name: 'datasources',
        component: () => import('@/views/DataSources.vue'),
      },
      {
        path: 'datasources/catalog',
        name: 'data-catalog',
        component: () => import('@/views/DataCatalog.vue'),
      },
      {
        path: 'datasources/preview',
        name: 'sample-preview',
        component: () => import('@/views/SamplePreview.vue'),
      },

      {
        path: 'extraction',
        name: 'mapping-wizard',
        component: () => import('@/views/MappingWizard.vue'),
      },
      {
        path: 'extraction/runs',
        name: 'extraction-runs',
        component: () => import('@/views/ExtractionRuns.vue'),
      },

      { path: 'graph', name: 'graph-browse', component: () => import('@/views/GraphBrowse.vue') },
      {
        path: 'graph/entities',
        name: 'graph-entities',
        component: () => import('@/views/GraphEntities.vue'),
      },
      {
        path: 'graph/entities/:id',
        name: 'graph-entity-detail',
        component: () => import('@/views/GraphEntityDetail.vue'),
      },
      {
        path: 'graph/evidence',
        name: 'graph-evidence',
        component: () => import('@/views/GraphEvidence.vue'),
      },
      {
        path: 'graph/reports',
        name: 'graph-reports',
        component: () => import('@/views/GraphReports.vue'),
      },

      {
        path: 'governance/rules',
        name: 'governance-rules',
        component: () => import('@/views/GovernanceRules.vue'),
      },
      {
        path: 'governance/templates',
        name: 'assembly-templates',
        component: () => import('@/views/AssemblyTemplates.vue'),
      },
      {
        path: 'governance/export',
        name: 'ontology-export',
        component: () => import('@/views/OntologyExport.vue'),
      },

      {
        path: 'account/profile',
        name: 'account-profile',
        component: () => import('@/views/account/Profile.vue'),
      },
      {
        path: 'account/security',
        name: 'account-security',
        component: () => import('@/views/account/Security.vue'),
      },

      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('@/views/system/Users.vue'),
        meta: { adminOnly: true },
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('@/views/system/Roles.vue'),
        meta: { adminOnly: true },
      },
      {
        path: 'system/audit-logs',
        name: 'system-audit-logs',
        component: () => import('@/views/system/AuditLogs.vue'),
        meta: { adminOnly: true },
      },

      { path: 'forbidden', name: 'forbidden', component: () => import('@/views/Forbidden.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFound.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

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
    if (!auth.isAdmin) return { name: 'forbidden' }
  }

  return true
})
