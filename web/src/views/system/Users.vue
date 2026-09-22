<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPagination,
  NSelect,
  NSpace,
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AuthUser, Role, UserStatus } from '@/api/auth'
import { authApi } from '@/api/auth'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
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

const editing = ref<AuthUser | null>(null)
const showEdit = computed({
  get: () => editing.value !== null,
  set: (value: boolean) => {
    if (!value) editing.value = null
  },
})
const editForm = ref<{ role: Role; status: UserStatus }>({ role: 'VIEWER', status: 'ACTIVE' })
const saving = ref(false)

// 公开注册默认关闭，管理员建号是唯一的建号入口，所以这个入口必须存在。
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const createForm = ref({
  username: '',
  email: '',
  password: '',
  display_name: '',
  role: 'EDITOR' as Role,
})

function openCreate() {
  createForm.value = {
    username: '',
    email: '',
    password: '',
    display_name: '',
    role: 'EDITOR',
  }
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  createError.value = ''
  const form = createForm.value
  if (form.password.length < 8) {
    createError.value = t('auth.rules.passwordMin')
    return
  }
  creating.value = true
  try {
    await authApi.createUser({
      username: form.username.trim(),
      email: form.email.trim(),
      password: form.password,
      role: form.role,
      display_name: form.display_name.trim() || null,
    })
    showCreate.value = false
    message.success(t('system.userCreated'))
    page.value = 1
    await load()
  } catch (err) {
    createError.value = toMessage(err)
  } finally {
    creating.value = false
  }
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
  loading.value = true
  error.value = ''
  try {
    const result = await authApi.users({
      q: keyword.value || undefined,
      role: roleFilter.value ?? undefined,
      status: statusFilter.value ?? undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items
    total.value = result.total
    if (!items.value.length && page.value > 1) page.value--
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    loading.value = false
  }
}

function search() {
  keyword.value = query.value.trim()
  page.value = 1
  void load()
}

function openEdit(user: AuthUser) {
  editing.value = user
  editForm.value = { role: user.role, status: user.status }
}

async function save() {
  if (!editing.value) return
  saving.value = true
  try {
    const updated = await authApi.updateUser(editing.value.id, editForm.value)
    items.value = items.value.map((item) => (item.id === updated.id ? updated : item))
    editing.value = null
    message.success(t('system.userUpdated'))
  } catch (err) {
    error.value = toMessage(err)
  } finally {
    saving.value = false
  }
}

const columns = computed<DataTableColumns<AuthUser>>(() => [
  { title: t('auth.username'), key: 'username' },
  { title: t('auth.email'), key: 'email' },
  {
    title: t('account.role'),
    key: 'role',
    render: (row) => h(NTag, { size: 'small' }, { default: () => t(`account.roles.${row.role}`) }),
  },
  {
    title: t('account.status'),
    key: 'status',
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.status === 'ACTIVE' ? 'success' : 'warning' },
        { default: () => t(`account.statuses.${row.status}`) },
      ),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    render: (row) => {
      // 后端不允许管理员把自己降级或禁用（最后一个管理员自锁就再也回不来），
      // 这里同步禁用，避免点下去必然报错。
      const isSelf = row.id === auth.user?.id
      return h(
        NButton,
        {
          size: 'small',
          disabled: isSelf,
          title: isSelf ? t('system.cannotEditSelf') : undefined,
          onClick: () => openEdit(row),
        },
        { default: () => t('common.edit') },
      )
    },
  },
])

onMounted(load)
</script>

<template>
  <section>
    <PageHeader :title="t('page.systemUsers')" :description="t('system.usersHint')">
      <template #actions>
        <NButton type="primary" @click="openCreate">
          {{ t('system.createUser') }}
        </NButton>
      </template>
    </PageHeader>
    <NCard size="small">
      <NSpace class="filters" align="end">
        <NFormItem :label="t('common.search')" :show-feedback="false">
          <NInput
            v-model:value="query"
            clearable
            :placeholder="t('system.searchUsers')"
            @keyup.enter="search"
          />
        </NFormItem>
        <NButton @click="search">{{ t('common.search') }}</NButton>
        <NFormItem :label="t('account.role')" :show-feedback="false">
          <NSelect
            v-model:value="roleFilter"
            :options="roleOptions"
            clearable
            class="filter-select"
            @update:value="search"
          />
        </NFormItem>
        <NFormItem :label="t('account.status')" :show-feedback="false">
          <NSelect
            v-model:value="statusFilter"
            :options="statusOptions"
            clearable
            class="filter-select"
            @update:value="search"
          />
        </NFormItem>
        <NButton :loading="loading" @click="load">{{ t('graph.refresh') }}</NButton>
      </NSpace>
      <NDataTable
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: AuthUser) => row.id"
        :scroll-x="720"
      >
        <template #empty>
          <NEmpty :description="error || t('common.empty')" />
        </template>
      </NDataTable>
      <NPagination
        v-if="total > pageSize"
        v-model:page="page"
        :page-size="pageSize"
        :item-count="total"
        class="pagination"
        @update:page="load"
      />
    </NCard>

    <NModal
      v-model:show="showEdit"
      preset="card"
      :title="t('system.editUser')"
      class="edit-modal"
      :mask-closable="!saving"
    >
      <NFormItem :label="t('auth.username')">{{ editing?.username }}</NFormItem>
      <NFormItem :label="t('account.role')">
        <NSelect v-model:value="editForm.role" :options="roleOptions" />
      </NFormItem>
      <NFormItem :label="t('account.status')">
        <NSelect v-model:value="editForm.status" :options="statusOptions" />
      </NFormItem>
      <template #footer>
        <NSpace justify="end">
          <NButton :disabled="saving" @click="editing = null">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="saving" @click="save">{{ t('common.save') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="showCreate"
      preset="card"
      :title="t('system.createUser')"
      class="edit-modal"
      :mask-closable="!creating"
    >
      <NAlert v-if="createError" type="error" role="alert" class="modal-alert">
        {{ createError }}
      </NAlert>
      <NForm label-placement="top" @submit.prevent="submitCreate">
        <NFormItem :label="t('auth.username')">
          <NInput
            v-model:value="createForm.username"
            :placeholder="t('system.usernamePlaceholder')"
            autocomplete="off"
          />
        </NFormItem>
        <NFormItem :label="t('auth.email')">
          <NInput v-model:value="createForm.email" autocomplete="off" />
        </NFormItem>
        <NFormItem :label="t('auth.password')">
          <NInput
            v-model:value="createForm.password"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
          />
        </NFormItem>
        <NFormItem :label="t('account.displayName')">
          <NInput v-model:value="createForm.display_name" />
        </NFormItem>
        <NFormItem :label="t('account.role')">
          <NSelect v-model:value="createForm.role" :options="roleOptions" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton :disabled="creating" @click="showCreate = false">
            {{ t('common.cancel') }}
          </NButton>
          <NButton type="primary" :loading="creating" @click="submitCreate">
            {{ t('common.create') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.filters {
  margin-bottom: var(--space-4);
}
.filter-select {
  width: 150px;
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
.edit-modal {
  width: min(480px, 100vw);
}
.modal-alert {
  margin-bottom: var(--space-3);
}
</style>
