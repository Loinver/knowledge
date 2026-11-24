import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'

import type { AuthUser, LoginInput, RegisterInput } from '@/api/auth'
import { authApi } from '@/api/auth'
import {
  clearTokens,
  getAccessToken,
  getSessionGeneration,
  hasSession,
  storeTokens,
  subscribeTokens,
} from '@/api/tokens'

/**
 * 登录态。
 *
 * token 是登录态的唯一凭据：刷新页面后靠 `/auth/me` 补全用户信息与角色，
 * 拿到角色之前按「已登录但角色未知」处理，受限路由会先补拉一次。
 */
export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const loading = ref(false)

  // token 存在 localStorage 里、不是响应式数据；用 epoch 承接订阅通知，
  // 使 isAuthenticated 在 token 被写入或清空后重新求值。
  // 否则：401 拦截器 clearTokens() 时 user 本就为 null（赋同值不触发更新），
  // computed 会一直返回清空前的旧值 true，登出后仍被判成"已登录"。
  const tokenEpoch = ref(0)
  let identityGeneration = getSessionGeneration()
  onScopeDispose(
    subscribeTokens(() => {
      const generation = getSessionGeneration()
      if (!hasSession() || identityGeneration !== generation) {
        user.value = null
        loading.value = false
      }
      identityGeneration = generation
      tokenEpoch.value += 1
    }),
  )

  const isAuthenticated = computed(() => {
    void tokenEpoch.value
    return hasSession()
  })
  const isAdmin = computed(() => user.value?.role === 'ADMIN')
  const displayName = computed(
    () => user.value?.display_name || user.value?.username || user.value?.email || '',
  )
  const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())

  async function loadMe(): Promise<void> {
    const generation = getSessionGeneration()
    if (!getAccessToken()) {
      user.value = null
      return
    }
    try {
      const next = await authApi.me()
      if (generation === getSessionGeneration() && hasSession()) user.value = next
    } catch (err) {
      const status = (err as { status?: number } | undefined)?.status
      // 401/403 才认定会话失效；5xx 或网络抖动不能把后端故障当成登出，
      // 保留现有登录态（isAuthenticated 还会看 token）。
      if (generation === getSessionGeneration() && (status === 401 || status === 403)) {
        user.value = null
      }
    }
  }

  async function login(payload: LoginInput): Promise<void> {
    clearTokens()
    const generation = getSessionGeneration()
    loading.value = true
    try {
      const tokens = await authApi.login(payload)
      if (generation !== getSessionGeneration()) return
      if (!storeTokens(tokens, generation)) return
      await loadMe()
    } finally {
      if (generation === getSessionGeneration()) loading.value = false
    }
  }

  async function register(payload: RegisterInput): Promise<void> {
    clearTokens()
    const generation = getSessionGeneration()
    loading.value = true
    try {
      const tokens = await authApi.register(payload)
      if (generation !== getSessionGeneration()) return
      if (!storeTokens(tokens, generation)) return
      await loadMe()
    } finally {
      if (generation === getSessionGeneration()) loading.value = false
    }
  }

  async function logout(): Promise<void> {
    const request = authApi.logout()
    clearTokens()
    const generation = getSessionGeneration()
    loading.value = true
    try {
      await request
    } catch {
      // 服务端吊销失败也要清掉本地会话，否则用户被困在已登录态
    } finally {
      if (generation === getSessionGeneration()) loading.value = false
    }
  }

  function setUser(next: AuthUser | null, generation: string): boolean {
    if (generation !== getSessionGeneration() || !hasSession()) return false
    if (next && user.value && next.id !== user.value.id) return false
    user.value = next
    return true
  }

  return {
    user,
    loading,
    isAuthenticated,
    isAdmin,
    displayName,
    initial,
    loadMe,
    login,
    register,
    logout,
    setUser,
  }
})
