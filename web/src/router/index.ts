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
        component: () => import('@/views/ontology/EntityTypes.vue'),
      },
      {
        path: 'ontology/entity-types/:id',
        name: 'entity-detail',
        component: () => import('@/views/ontology/EntityDetail.vue'),
      },
      {
        path: 'ontology/relation-types',
        name: 'relation-types',
        component: () => import('@/views/ontology/RelationTypes.vue'),
      },
      {
        path: 'ontology/domains',
        name: 'domains',
        component: () => import('@/views/ontology/Domains.vue'),
      },
      {
        path: 'ontology/designer',
        name: 'designer',
        component: () => import('@/views/ontology/Designer.vue'),
      },

      {
        path: 'datasources',
        name: 'datasources',
        component: () => import('@/views/datasources/DataSources.vue'),
      },
      {
        path: 'datasources/catalog',
        name: 'data-catalog',
        component: () => import('@/views/datasources/DataCatalog.vue'),
      },
      {
        path: 'datasources/preview',
        name: 'sample-preview',
        component: () => import('@/views/datasources/SamplePreview.vue'),
      },

      {
        path: 'extraction',
        name: 'mapping-wizard',
        component: () => import('@/views/extraction/MappingWizard.vue'),
      },
      {
        path: 'extraction/runs',
        name: 'extraction-runs',
        component: () => import('@/views/extraction/ExtractionRuns.vue'),
      },

      {
        path: 'graph',
        name: 'graph-browse',
        component: () => import('@/views/graph/GraphBrowse.vue'),
      },
      {
        path: 'graph/entities',
        name: 'graph-entities',
        component: () => import('@/views/graph/GraphEntities.vue'),
      },
      {
        path: 'graph/entities/:id',
        name: 'graph-entity-detail',
        component: () => import('@/views/graph/GraphEntityDetail.vue'),
      },
      {
        path: 'graph/evidence',
        name: 'graph-evidence',
        component: () => import('@/views/graph/GraphEvidence.vue'),
      },
      {
        path: 'graph/reports',
        name: 'graph-reports',
        component: () => import('@/views/graph/GraphReports.vue'),
      },

      {
        path: 'governance/rules',
        name: 'governance-rules',
        component: () => import('@/views/governance/GovernanceRules.vue'),
      },
      {
        path: 'governance/clauses',
        name: 'governance-clauses',
        component: () => import('@/views/governance/StandardClauses.vue'),
      },
      {
        path: 'governance/enum-dictionaries',
        name: 'enum-dictionaries',
        component: () => import('@/views/governance/EnumDictionaries.vue'),
        meta: {},
      },
      {
        path: 'governance/templates',
        name: 'assembly-templates',
        component: () => import('@/views/governance/AssemblyTemplates.vue'),
      },
      {
        path: 'governance/export',
        name: 'ontology-export',
        component: () => import('@/views/governance/OntologyExport.vue'),
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
    if (!auth.isAdmin) return { name: 'forbidden' }
  }

  return true
})
