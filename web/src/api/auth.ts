import { http } from '@/api/client'
import type { components, operations } from '@/api/schema'
import { getRefreshToken } from '@/api/tokens'

/**
 * 账号接口客户端。
 *
 * 类型全部来自后端 OpenAPI 生成的 `schema.d.ts`（禁止手写接口类型），
 * 后端实现见 `server/app/api/v1/auth.py` 与 `accounts.py`，
 * 契约说明见 `docs/frontend-redesign-plan.zh-CN.md` 第 3 节。
 */

type Schemas = components['schemas']

export type Role = Schemas['UserRole']
export type UserStatus = Schemas['UserStatus']
export type AuthUser = Schemas['UserOut']
export type TokenPair = Schemas['TokenPair']
export type AuthConfig = Schemas['AuthConfigOut']
export type LoginInput = Schemas['LoginRequest']
export type RegisterInput = Schemas['RegisterRequest']
export type ProfileUpdate = Schemas['ProfileUpdate']
export type PasswordChange = Schemas['PasswordChange']
export type UserCreateInput = Schemas['UserCreate']
export type UserPatchInput = Schemas['UserPatch']
export type UserPage = Schemas['UserPage']
export type RoleInfo = Schemas['RoleOut']
export type AuditAction = Schemas['AuditAction']
export type AuditLog = Schemas['AuditLogOut']
export type AuditLogPage = Schemas['AuditLogPage']
export type ForgotPasswordResult = Schemas['ForgotPasswordResult']
export type PasswordResetIssued = Schemas['PasswordResetIssued']

export type UserListQuery = NonNullable<
  operations['list_users_api_v1_users_get']['parameters']['query']
>
export type AuditLogQuery = NonNullable<
  operations['list_audit_logs_api_v1_audit_logs_get']['parameters']['query']
>

export const authApi = {
  /** 公开配置：是否开放注册、口令长度下限。登录页与注册页据此决定展示内容。 */
  config: () => http.get<AuthConfig>('/auth/config').then((r) => r.data),

  login: (payload: LoginInput) => http.post<TokenPair>('/auth/login', payload).then((r) => r.data),

  register: (payload: RegisterInput) =>
    http.post<TokenPair>('/auth/register', payload).then((r) => r.data),

  me: () => http.get<AuthUser>('/auth/me').then((r) => r.data),

  /** 带上刷新令牌，服务端才能把整个会话吊销；只发访问令牌等于只登出一半。 */
  logout: () => http.post('/auth/logout', { refresh_token: getRefreshToken() }),

  forgotPassword: (email: string) =>
    http.post<ForgotPasswordResult>('/auth/forgot-password', { email }).then((r) => r.data),

  resetPassword: (token: string, password: string) =>
    http.post('/auth/reset-password', { token, password }),

  updateProfile: (payload: ProfileUpdate) =>
    http.patch<AuthUser>('/users/me/profile', payload).then((r) => r.data),

  changePassword: (payload: PasswordChange) => http.put('/users/me/password', payload),

  users: (query: UserListQuery) =>
    http.get<UserPage>('/users', { params: query }).then((r) => r.data),

  createUser: (payload: UserCreateInput) =>
    http.post<AuthUser>('/users', payload).then((r) => r.data),

  updateUser: (id: string, payload: UserPatchInput) =>
    http.patch<AuthUser>(`/users/${id}`, payload).then((r) => r.data),

  /** 管理员为他人签发一次性重置令牌；平台没有邮件服务时由管理员线下转交。 */
  issuePasswordReset: (id: string) =>
    http.post<PasswordResetIssued>(`/users/${id}/password-reset`).then((r) => r.data),

  roles: () => http.get<RoleInfo[]>('/roles').then((r) => r.data),

  auditLogs: (query: AuditLogQuery) =>
    http.get<AuditLogPage>('/audit-logs', { params: query }).then((r) => r.data),
}
