<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { UiDropdown, useDialog, useMessage } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const dialog = useDialog()
const message = useMessage()

const options = computed(() => [
  { key: 'profile', label: t('account.profile') },
  { key: 'security', label: t('account.security') },
  { type: 'divider' as const, key: 'd1' },
  { key: 'logout', label: t('account.logout') },
])

function onSelect(key: string | number) {
  if (key === 'profile') void router.push({ name: 'account-profile' })
  else if (key === 'security') void router.push({ name: 'account-security' })
  else if (key === 'logout') confirmLogout()
}

function confirmLogout() {
  dialog.warning({
    restoreFocusTo: document.getElementById('account-menu-trigger'),
    title: () => t('account.logoutConfirmTitle'),
    content: () => t('account.logoutConfirmBody'),
    positiveText: () => t('common.confirm'),
    negativeText: () => t('common.cancel'),
    onPositiveClick: async () => {
      await auth.logout()
      message.success(() => t('account.loggedOut'))
      await router.push({ name: 'login' })
    },
  })
}
</script>

<template>
  <UiDropdown :options="options" trigger="click" @select="onSelect">
    <button
      id="account-menu-trigger"
      class="user-trigger"
      type="button"
      :aria-label="t('account.menu')"
    >
      <span class="avatar" aria-hidden="true">
        <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" alt="" />
        <template v-else>{{ auth.initial || '?' }}</template>
      </span>
      <span class="name">{{ auth.displayName || t('account.anonymous') }}</span>
      <AppIcon name="chevron" :size="14" />
    </button>
  </UiDropdown>
</template>

<style scoped>
.user-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: var(--control-height);
  padding: 0 var(--space-2);
  color: var(--text);
  background: transparent;
  border: 0;
  border-radius: var(--radius-medium);
  cursor: pointer;
  transition: background-color var(--transition-base);
}
.user-trigger:hover {
  background: var(--bg-hover);
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  overflow: hidden;
  color: var(--accent);
  font-size: var(--font-caption);
  font-weight: 500;
  background: var(--accent-soft);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
}
.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.name {
  max-width: 120px;
  overflow: hidden;
  font-size: var(--font-body);
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 767px) {
  .user-trigger {
    padding: 0 var(--space-1);
  }

  .name,
  .user-trigger > :deep(svg) {
    display: none;
  }
}
</style>
