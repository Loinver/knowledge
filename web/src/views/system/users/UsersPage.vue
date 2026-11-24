<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { AuthUser, Role, UserStatus } from '@/api/auth'
import { authApi } from '@/api/auth'
import { getSessionGeneration, subscribeTokens } from '@/api/tokens'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns, FormInst, FormRules } from '@/components/ui'
import {
  FormContainer,
  FormField,
  SearchTable,
  UiAlert,
  UiButton,
  UiCard,
  UiEmpty,
  UiInput,
  UiModal,
  UiSelect,
  UiSpace,
  UiTag,
  useMessage,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useDraftGuard } from '@/composables/useDraftGuard'
import { useOwnedMutation } from '@/composables/useOwnedMutation'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const { toMessage } = useApiError()
const auth = useAuthStore()

const items = ref<AuthUser[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const query = ref('')
const keyword = ref('')
const roleFilter = ref<Role | null>(null)
const statusFilter = ref<UserStatus | null>(null)
const loading = ref(false)
const error = ref('')
let listGeneration = 0
let alive = true
const listSession = ref(getSessionGeneration())
const stopListSession = subscribeTokens(() => {
  listSession.value = getSessionGeneration()
})
const listIdentity = computed(() =>
  JSON.stringify([listSession.value, auth.user?.id, auth.user?.role, auth.user?.status]),
)
const listQuery = computed(() => ({
  q: keyword.value || undefined,
  role: roleFilter.value ?? undefined,
  status: statusFilter.value ?? undefined,
  page: page.value,
  page_size: pageSize,
}))
const listKey = computed(() => JSON.stringify([listIdentity.value, listQuery.value]))
watch(
  listKey,
  () => {
    listGeneration++
    items.value = []
    total.value = 0
    error.value = ''
    loading.value = false
  },
  { flush: 'sync' },
)
watch(listIdentity, load)
onBeforeUnmount(() => {
  alive = false
  stopListSession()
  listGeneration++
})

const editing = ref<AuthUser | null>(null)
const showEdit = computed({
  get: () => editing.value !== null,
  set: (value: boolean) => {
    if (!value) editing.value = null
  },
})
const editForm = ref<{ role: Role; status: UserStatus }>({ role: 'VIEWER', status: 'ACTIVE' })
const editMutation = useOwnedMutation(
  () => [editing.value?.id, auth.user?.id, auth.isAdmin],
  toMessage,
)
const { busy: saving, error: editError } = editMutation
const editFormRef = ref<FormInst | null>(null)
const editRules = computed<FormRules>(() => ({
  role: {
    required: true,
    validator: (_rule, value) => ['ADMIN', 'EDITOR', 'VIEWER'].includes(String(value)),
    message: t('common.required'),
  },
  status: {
    required: true,
    validator: (_rule, value) => ['ACTIVE', 'DISABLED'].includes(String(value)),
    message: t('common.required'),
  },
}))

// 公开注册默认关闭，管理员建号是唯一的建号入口，所以这个入口必须存在。
const showCreate = ref(false)
const createMutation = useOwnedMutation(
  () => [showCreate.value, auth.user?.id, auth.isAdmin],
  toMessage,
)
const { busy: creating, error: createError } = createMutation
const createForm = ref({
  username: '',
  email: '',
  password: '',
  display_name: '',
  role: 'EDITOR' as Role,
})
const createFormRef = ref<FormInst | null>(null)
const editVisible = useDraftGuard(
  showEdit,
  () => editForm.value,
  () => auth.isAdmin,
)
const createVisible = useDraftGuard(
  showCreate,
  () => createForm.value,
  () => auth.isAdmin,
)

/** 与注册页同一套账号规则，文案复用 auth.rules.*，避免两处口径漂移。 */
const createRules = computed<FormRules>(() => ({
  username: [
    { required: true, message: t('auth.rules.usernameRequired'), trigger: ['blur', 'input'] },
    {
      pattern: /^[A-Za-z0-9_]{3,32}$/,
      message: t('auth.rules.usernamePattern'),
      trigger: ['blur', 'input'],
    },
  ],
  email: [
    { required: true, message: t('auth.rules.emailRequired'), trigger: ['blur', 'input'] },
    { type: 'email', message: t('auth.rules.emailPattern'), trigger: ['blur', 'input'] },
  ],
  password: [
    { required: true, message: t('auth.rules.passwordRequired'), trigger: ['blur', 'input'] },
    { min: 8, message: t('auth.rules.passwordMin'), trigger: ['blur', 'input'] },
  ],
  display_name: { max: 32, message: t('account.rules.displayNameMax'), trigger: ['blur', 'input'] },
  role: {
    required: true,
    validator: (_rule, value) => ['ADMIN', 'EDITOR', 'VIEWER'].includes(String(value)),
    message: t('common.required'),
    trigger: ['blur', 'change'],
  },
}))

function openCreate() {
  if (!auth.isAdmin || creating.value) return
  createForm.value = {
    username: '',
    email: '',
    password: '',
    display_name: '',
    role: 'EDITOR',
  }
  createMutation.invalidate()
  showCreate.value = true
  createFormRef.value?.restoreValidation()
}

async function submitCreate() {
  if (!alive || !showCreate.value || !createFormRef.value || !auth.isAdmin || creating.value) return
  const session = getSessionGeneration()
  const form = createForm.value
  const owns = () =>
    alive &&
    showCreate.value &&
    form === createForm.value &&
    auth.isAdmin &&
    session === getSessionGeneration()
  createMutation.invalidate()
  try {
    await createFormRef.value.validate()
  } catch {
    return
  }
  if (!owns() || creating.value) return
  const created = await createMutation.run(() =>
    authApi.createUser({
      username: form.username.trim(),
      email: form.email.trim(),
      password: form.password,
      role: form.role,
      display_name: form.display_name.trim() || null,
    }),
  )
  if (!created || !owns()) return
  showCreate.value = false
  message.success(t('system.userCreated'))
  page.value = 1
  await load()
}

const roleOptions = computed(() =>
  (['ADMIN', 'EDITOR', 'VIEWER'] as Role[]).map((value) => ({
    value,
    label: t(`account.roles.${value}`),
  })),
)
const statusOptions = computed(() =>
  (['ACTIVE', 'DISABLED'] as UserStatus[]).map((value) => ({
    value,
    label: t(`account.statuses.${value}`),
  })),
)

async function load() {
  const generation = ++listGeneration
  const session = getSessionGeneration()
  const key = listKey.value
  if (!alive || !auth.isAdmin) return
  const owns = () =>
    alive &&
    generation === listGeneration &&
    session === getSessionGeneration() &&
    key === listKey.value &&
    auth.isAdmin
  loading.value = true
  error.value = ''
  try {
    const result = await authApi.users(listQuery.value)
    if (!owns()) return
    if (page.value > Math.max(1, Math.ceil(result.total / pageSize))) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize))
      void load()
      return
    }
    items.value = result.items
    total.value = result.total
  } catch (err) {
    if (owns()) error.value = toMessage(err)
  } finally {
    if (owns()) loading.value = false
  }
}

function search() {
  keyword.value = query.value.trim()
  page.value = 1
  void load()
}
function clearSearch() {
  query.value = ''
  search()
}
function resetSearch() {
  query.value = ''
  roleFilter.value = null
  statusFilter.value = null
  search()
}

function openEdit(user: AuthUser) {
  if (!auth.isAdmin || saving.value || user.id === auth.user?.id) return
  editMutation.invalidate()
  editing.value = user
  editForm.value = { role: user.role, status: user.status }
  editFormRef.value?.restoreValidation()
}

async function save() {
  if (!alive || !editFormRef.value || !auth.isAdmin || saving.value) return
  const user = editing.value
  if (!user || user.id === auth.user?.id) return
  const session = getSessionGeneration()
  const form = editForm.value
  const owns = () =>
    alive &&
    editing.value === user &&
    editForm.value === form &&
    auth.isAdmin &&
    session === getSessionGeneration()
  try {
    await editFormRef.value.validate()
  } catch {
    return
  }
  if (!owns() || saving.value) return
  const updated = await editMutation.run(() => authApi.updateUser(user.id, { ...form }))
  if (!updated || !owns()) return
  editing.value = null
  message.success(t('system.userUpdated'))
  // Role/status may remove this user from the active remote filter or change its total.
  await load()
}

/**
 * 平台没有邮件服务，用户忘记密码时由管理员签发一次性链接并线下转交。
 * 链接只在这个弹窗里展示，关闭即丢弃，不落任何前端存储。
 */
const resetIssuing = ref<string | null>(null)
const resetLink = ref<{ username: string; url: string; minutes: number } | null>(null)
const showResetLink = computed({
  get: () => resetLink.value !== null,
  set: (value: boolean) => {
    if (!value) resetLink.value = null
  },
})

async function issueResetLink(user: AuthUser) {
  if (
    !alive ||
    !auth.isAdmin ||
    resetIssuing.value ||
    user.id === auth.user?.id ||
    user.status !== 'ACTIVE'
  )
    return
  const session = getSessionGeneration()
  resetIssuing.value = user.id
  try {
    const issued = await authApi.issuePasswordReset(user.id)
    if (!alive || !auth.isAdmin || session !== getSessionGeneration()) return
    const target = router.resolve({ name: 'reset-password', query: { token: issued.reset_token } })
    resetLink.value = {
      username: user.username,
      url: new URL(target.href, window.location.origin).toString(),
      minutes: Math.ceil(issued.expires_in / 60),
    }
  } catch (err) {
    if (alive && auth.isAdmin && session === getSessionGeneration()) message.error(toMessage(err))
  } finally {
    resetIssuing.value = null
  }
}

async function copyResetLink() {
  if (!resetLink.value) return
  try {
    await navigator.clipboard.writeText(resetLink.value.url)
    message.success(t('system.copied'))
  } catch {
    // 非安全上下文或权限被拒时剪贴板不可用，链接仍可在只读框里手动选中复制
    message.warning(t('system.copyFailed'))
  }
}

const columns = computed<DataTableColumns<AuthUser>>(() => [
  { title: t('auth.username'), key: 'username' },
  { title: t('auth.email'), key: 'email' },
  {
    title: t('account.role'),
    key: 'role',
    render: (row) => h(UiTag, { size: 'small' }, { default: () => t(`account.roles.${row.role}`) }),
  },
  {
    title: t('account.status'),
    key: 'status',
    render: (row) =>
      h(
        UiTag,
        { size: 'small', type: row.status === 'ACTIVE' ? 'success' : 'warning' },
        { default: () => t(`account.statuses.${row.status}`) },
      ),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 260,
    fixed: 'right',
    render: (row) => {
      // 后端不允许管理员把自己降级或禁用（最后一个管理员自锁就再也回不来），
      // 这里同步禁用，避免点下去必然报错。自己的密码走「账号安全」改密。
      const isSelf = row.id === auth.user?.id
      return h(UiSpace, { size: 'small', wrap: false }, () => [
        h(
          UiButton,
          {
            size: 'small',
            disabled: !auth.isAdmin || saving.value || isSelf,
            title: isSelf ? t('system.cannotEditSelf') : undefined,
            onClick: () => openEdit(row),
          },
          { default: () => t('common.edit') },
        ),
        h(
          UiButton,
          {
            size: 'small',
            disabled: !auth.isAdmin || !!resetIssuing.value || isSelf || row.status !== 'ACTIVE',
            loading: resetIssuing.value === row.id,
            title: isSelf ? t('system.cannotResetSelf') : undefined,
            onClick: () => issueResetLink(row),
          },
          { default: () => t('system.resetLink') },
        ),
      ])
    },
  },
])

onMounted(load)
watch(
  () => [auth.user?.id, auth.isAdmin],
  () => {
    editing.value = null
    showCreate.value = false
    resetLink.value = null
    createForm.value.password = ''
    editMutation.invalidate()
    createMutation.invalidate()
  },
  { flush: 'sync' },
)
</script>

<template>
  <section class="system-page users-page">
    <PageHeader :title="t('page.systemUsers')" :description="t('system.usersHint')">
      <template #actions>
        <UiButton type="primary" :disabled="!auth.isAdmin" @click="openCreate">
          {{ t('system.createUser') }}
        </UiButton>
      </template>
    </PageHeader>
    <div class="system-context">
      <div>
        <span class="context-label">{{ t('account.currentSession') }}</span
        ><strong>{{ auth.user?.username ?? t('common.noneValue') }}</strong>
      </div>
      <UiTag size="small">{{ t(`account.roles.${auth.user?.role ?? 'VIEWER'}`) }}</UiTag>
      <p>{{ t('system.cannotEditSelf') }}</p>
    </div>
    <UiCard size="small" class="ledger-panel">
      <header class="ledger-heading">
        <h2>{{ t('operationsUi.ledger') }}</h2>
        <span v-if="!error && !loading">{{ t('assetAudit.total', { count: total }) }}</span>
      </header>

      <SearchTable
        v-model:page="page"
        v-model:query="query"
        mode="remote"
        :total="total"
        :page-size="pageSize"
        :pagination="true"
        :search-placeholder="t('system.searchUsers')"
        :error="error"
        size="small"
        :columns="columns"
        :rows="items"
        :loading="loading"
        :row-key="(row: AuthUser) => row.id"
        :scroll-x="720"
        @submit="search"
        @clear="clearSearch"
        @reset="resetSearch"
        @retry="load"
        @update:page="load"
      >
        <template #filter
          ><div class="flex flex-wrap items-end gap-3">
            <FormField
              :label="t('account.role')"
              label-placement="top"
              :label-width="72"
              :show-feedback="false"
            >
              <UiSelect
                v-model:value="roleFilter"
                :options="roleOptions"
                clearable
                class="filter-select"
                @update:value="search"
              />
            </FormField>
            <FormField
              :label="t('account.status')"
              label-placement="top"
              :label-width="72"
              :show-feedback="false"
            >
              <UiSelect
                v-model:value="statusFilter"
                :options="statusOptions"
                clearable
                class="filter-select"
                @update:value="search"
              />
            </FormField>
            <UiButton :loading="loading" @click="load">{{ t('graph.refresh') }}</UiButton>
          </div></template
        >
        <template #empty>
          <UiEmpty :description="t('common.empty')" />
        </template>
      </SearchTable>
    </UiCard>

    <UiModal
      v-model:show="editVisible"
      preset="card"
      :title="t('system.editUser')"
      class="edit-modal"
      style="width: min(480px, calc(100vw - 32px))"
      :mask-closable="!saving"
      :close-on-esc="!saving"
      :closable="!saving"
    >
      <UiAlert v-if="editError" type="error" class="modal-alert">{{ editError }}</UiAlert>
      <div class="system-context">
        <div>
          <span class="context-label">{{ t('operationsUi.identity') }}</span
          ><strong>{{ editing?.username }}</strong>
        </div>
      </div>
      <FormContainer
        id="system-user-edit-form"
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        :submitting="saving"
        :disabled="!auth.isAdmin"
        @submit="save"
      >
        <fieldset class="settings-group">
          <legend>{{ t('operationsUi.access') }}</legend>
          <FormField :label="t('account.role')" path="role">
            <UiSelect v-model:value="editForm.role" :options="roleOptions" />
          </FormField>
          <FormField :label="t('account.status')" path="status">
            <UiSelect v-model:value="editForm.status" :options="statusOptions" />
          </FormField>
        </fieldset>
      </FormContainer>
      <template #footer>
        <UiSpace justify="end">
          <UiButton :disabled="saving" @click="editVisible = false">{{
            t('common.cancel')
          }}</UiButton>
          <UiButton
            type="primary"
            attr-type="submit"
            form="system-user-edit-form"
            :loading="saving"
            :disabled="!auth.isAdmin"
            >{{ t('common.save') }}</UiButton
          >
        </UiSpace>
      </template>
    </UiModal>

    <UiModal
      v-model:show="showResetLink"
      preset="card"
      :title="t('system.resetLinkTitle')"
      class="edit-modal"
      style="width: min(480px, calc(100vw - 32px))"
    >
      <template v-if="resetLink">
        <UiAlert type="warning" class="modal-alert">
          {{
            t('system.resetLinkHint', { minutes: resetLink.minutes, username: resetLink.username })
          }}
        </UiAlert>
        <UiInput :value="resetLink.url" readonly :aria-label="t('system.resetLink')" />
      </template>
      <template #footer>
        <UiSpace justify="end">
          <UiButton @click="resetLink = null">{{ t('common.close') }}</UiButton>
          <UiButton type="primary" @click="copyResetLink">{{ t('system.copy') }}</UiButton>
        </UiSpace>
      </template>
    </UiModal>

    <UiModal
      v-model:show="createVisible"
      preset="card"
      :title="t('system.createUser')"
      class="edit-modal"
      style="width: min(480px, calc(100vw - 32px))"
      :mask-closable="!creating"
      :close-on-esc="!creating"
      :closable="!creating"
    >
      <UiAlert v-if="createError" type="error" role="alert" class="modal-alert">
        {{ createError }}
      </UiAlert>
      <FormContainer
        id="system-user-create-form"
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        :submitting="creating"
        :disabled="!auth.isAdmin"
        label-placement="top"
        @submit="submitCreate"
      >
        <fieldset class="settings-group">
          <legend>{{ t('operationsUi.identity') }}</legend>
          <FormField :label="t('auth.username')" path="username">
            <UiInput
              v-model:value="createForm.username"
              :placeholder="t('system.usernamePlaceholder')"
              autocomplete="off"
            />
          </FormField>
          <FormField :label="t('auth.email')" path="email">
            <UiInput v-model:value="createForm.email" autocomplete="off" />
          </FormField>
        </fieldset>
        <fieldset class="settings-group">
          <legend>{{ t('operationsUi.access') }}</legend>
          <FormField :label="t('auth.password')" path="password">
            <UiInput
              v-model:value="createForm.password"
              type="password"
              show-password-on="click"
              autocomplete="new-password"
            />
          </FormField>
          <FormField :label="t('account.displayName')" path="display_name">
            <UiInput v-model:value="createForm.display_name" />
          </FormField>
          <FormField :label="t('account.role')" path="role">
            <UiSelect v-model:value="createForm.role" :options="roleOptions" />
          </FormField>
        </fieldset>
      </FormContainer>
      <template #footer>
        <UiSpace justify="end">
          <UiButton :disabled="creating" @click="createVisible = false">
            {{ t('common.cancel') }}
          </UiButton>
          <UiButton
            type="primary"
            attr-type="submit"
            form="system-user-create-form"
            :loading="creating"
            :disabled="!auth.isAdmin"
          >
            {{ t('common.create') }}
          </UiButton>
        </UiSpace>
      </template>
    </UiModal>
  </section>
</template>

<style scoped src="../SystemWorkspace.css"></style>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) auto repeat(2, minmax(130px, 1fr)) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
@media (max-width: 1100px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
  .filter-select {
    width: 100%;
  }
}
.filter-select {
  width: 100%;
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
.modal-alert {
  margin-bottom: var(--space-3);
}
</style>
