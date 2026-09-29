import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { AuthUser, LoginInput, RegisterInput } from '@/api/auth'
import { authApi } from '@/api/auth'
import { clearTokens, getAccessToken, hasSession, storeTokens, subscribeTokens } from '@/api/tokens'

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
  subscribeTokens(() => {
    tokenEpoch.value += 1
  })

  const isAuthenticated = computed(() => {
    void tokenEpoch.value
    return user.value !== null || hasSession()
  })
  const isAdmin = computed(() => user.value?.role === 'ADMIN')
  const displayName = computed(
    () => user.value?.display_name || user.value?.username || user.value?.email || '',
  )
  const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())

  async function loadMe(): Promise<void> {
    if (!getAccessToken()) {
      user.value = null
      return
    }
    try {
      user.value = await authApi.me()
    } catch (err) {
      const status = (err as { status?: number } | undefined)?.status
      // 401/403 才认定会话失效；5xx 或网络抖动不能把后端故障当成登出，
      // 保留现有登录态（isAuthenticated 还会看 token）。
      if (status === 401 || status === 403) {
        user.value = null
      }
    }
  }

  async function login(payload: LoginInput): Promise<void> {
    loading.value = true
    try {
      storeTokens(await authApi.login(payload))
      await loadMe()
    } finally {
      loading.value = false
    }
  }

  async function register(payload: RegisterInput): Promise<void> {
    loading.value = true
    try {
      storeTokens(await authApi.register(payload))
      await loadMe()
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    loading.value = true
    try {
      await authApi.logout()
    } catch {
      // 服务端吊销失败也要清掉本地会话，否则用户被困在已登录态
    } finally {
      clearTokens()
      user.value = null
      loading.value = false
    }
  }

  function setUser(next: AuthUser | null): void {
    user.value = next
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
