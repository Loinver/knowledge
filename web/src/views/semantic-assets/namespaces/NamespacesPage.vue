<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import PageHeader from '@/components/PageHeader.vue'
import type { DataTableColumns } from '@/components/ui'
import {
  UiAlert,
  UiButton,
  UiDataTable,
  UiEmpty,
  UiPopconfirm,
  UiSpin,
  UiTag,
} from '@/components/ui'
import { useApiError } from '@/composables/useApiError'
import { useAuthStore } from '@/stores/auth'

import NamespaceCreateModal from '../components/NamespaceCreateModal.vue'

const auth = useAuthStore()
const canWrite = computed(() => ['ADMIN', 'EDITOR'].includes(auth.user?.role ?? ''))
const { t, locale } = useI18n()
const { toMessage } = useApiError()
const numbers = computed(() => new Intl.NumberFormat(locale.value))

const items = ref<Namespace[]>([])
const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const notice = ref('')
const showCreate = ref(false)
const deletingId = ref<number | null>(null)
let controller: AbortController | undefined
let alive = true

async function load() {
  if (!alive) return
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  loadError.value = ''
  try {
    const data = await namespacesApi.list(current.signal)
    if (current.signal.aborted) return
    items.value = data
  } catch (err) {
    if (current.signal.aborted) return
    items.value = []
    loadError.value = toMessage(err)
  } finally {
    if (!current.signal.aborted) loading.value = false
  }
}

function displayLabel(ns: Namespace): string {
  const labels = ns.label_i18n ?? {}
  return (
    labels[locale.value]?.trim() ||
    (Object.keys(labels).length ? t('enumDictionaries.untranslated') : t('common.noneValue'))
  )
}

/** 受保护或仍被资源引用的命名空间不可删；把原因直接写在按钮提示里，而不是等后端报错。 */
function deleteBlocker(ns: Namespace): string {
  if (!canWrite.value) return t('ui.readonly')
  if (ns.protected) return t('namespace.protectedHint')
  if (ns.resource_count) return t('namespace.inUseHint', { count: ns.resource_count })
  return ''
}

async function remove(ns: Namespace) {
  if (deleteBlocker(ns) || deletingId.value !== null) return
  actionError.value = ''
  notice.value = ''
  deletingId.value = ns.id
  try {
    await namespacesApi.remove(ns.id)
    if (!alive) return
    notice.value = t('namespace.deleted', { prefix: ns.prefix })
    await load()
  } catch (err) {
    if (!alive) return
    const body = err as { code?: string; params?: { count?: number } } | undefined
    actionError.value =
      body?.code === 'KG.RESOURCE_IN_USE'
        ? t('namespace.inUseHint', { count: body.params?.count ?? 0 })
        : toMessage(err)
  } finally {
    if (alive) deletingId.value = null
  }
}

async function onCreated(ns: Namespace) {
  actionError.value = ''
  notice.value = t('namespace.created', { prefix: ns.prefix })
  await load()
}

const columns = computed<DataTableColumns<Namespace>>(() => [
  {
    title: t('namespace.prefix'),
    key: 'prefix',
    width: 140,
    render: (row) => h('span', { class: 'mono prefix' }, row.prefix),
  },
  {
    title: t('namespace.iri'),
    key: 'iri',
    minWidth: 280,
    render: (row) => h('span', { class: 'iri', title: row.iri }, row.iri),
  },
  { title: t('common.label'), key: 'label', minWidth: 140, render: (row) => displayLabel(row) },
  {
    title: t('namespace.resourceCount'),
    key: 'resource_count',
    width: 110,
    render: (row) => h('span', { class: 'mono' }, numbers.value.format(row.resource_count ?? 0)),
  },
  {
    title: t('namespace.protected'),
    key: 'protected',
    width: 100,
    render: (row) =>
      row.protected
        ? h(UiTag, { size: 'small', bordered: false }, { default: () => t('common.yes') })
        : h('span', { class: 'muted' }, t('common.no')),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    fixed: 'right',
    width: 100,
    render: (row) => {
      const blocker = deleteBlocker(row)
      if (blocker) {
        return h(
          UiButton,
          { size: 'small', quaternary: true, disabled: true, title: blocker },
          { default: () => t('common.delete') },
        )
      }
      return h(
        UiPopconfirm,
        { onPositiveClick: () => void remove(row) },
        {
          trigger: () =>
            h(
              UiButton,
              {
                size: 'small',
                quaternary: true,
                type: 'error',
                loading: deletingId.value === row.id,
              },
              { default: () => t('common.delete') },
            ),
          default: () => t('namespace.deleteConfirm', { prefix: row.prefix }),
        },
      )
    },
  },
])

onMounted(load)
onBeforeUnmount(() => {
  alive = false
  controller?.abort()
})
</script>

<template>
  <section class="page asset-page">
    <PageHeader :title="t('page.namespaces')" :description="t('namespace.description')">
      <template #actions>
        <UiButton type="primary" :disabled="!canWrite" @click="showCreate = true">{{
          t('namespace.create')
        }}</UiButton>
      </template>
    </PageHeader>
    <UiAlert v-if="!canWrite" type="info" class="alert">{{ t('ui.readonly') }}</UiAlert>

    <UiAlert v-if="loadError" type="error" class="alert"
      >{{ loadError }} <UiButton @click="load">{{ t('ui.retry') }}</UiButton></UiAlert
    >
    <UiAlert v-if="actionError" type="error" class="alert" closable @close="actionError = ''">{{
      actionError
    }}</UiAlert>
    <UiAlert v-if="notice" type="success" class="alert" closable @close="notice = ''">{{
      notice
    }}</UiAlert>

    <div class="ledger-workspace">
      <aside class="ledger-rail">
        <div class="ledger-reading">
          <strong>{{
            loading || loadError ? t('common.noneValue') : numbers.format(items.length)
          }}</strong
          ><span>{{ t('page.namespaces') }}</span>
        </div>
        <div class="ledger-reading">
          <strong>{{
            loading || loadError
              ? t('common.noneValue')
              : numbers.format(items.reduce((sum, ns) => sum + (ns.resource_count ?? 0), 0))
          }}</strong
          ><span>{{ t('namespace.resourceCount') }}</span>
        </div>
        <div class="ledger-reading">
          <strong>{{
            loading || loadError
              ? t('common.noneValue')
              : numbers.format(items.filter((ns) => ns.protected).length)
          }}</strong
          ><span>{{ t('namespace.protected') }}</span>
        </div>
      </aside>
      <div class="ledger-main">
        <UiSpin :show="loading">
          <div class="ledger-surface">
            <header class="ledger-caption">
              <h2>{{ t('page.namespaces') }}</h2>
              <span>{{
                loading || loadError
                  ? t('common.noneValue')
                  : t('assetLedger.resultCount', { count: numbers.format(items.length) })
              }}</span>
            </header>
            <UiDataTable
              :columns="columns"
              :rows="items"
              :bordered="false"
              size="small"
              :max-height="600"
              :scroll-x="870"
              :row-key="(row: Namespace) => row.id"
            >
              <template #empty>
                <UiEmpty v-if="!loadError && !loading" :description="t('namespace.empty')">
                  <template #extra>
                    <UiButton size="small" :disabled="!canWrite" @click="showCreate = true">
                      {{ t('namespace.create') }}
                    </UiButton>
                  </template>
                </UiEmpty>
              </template>
            </UiDataTable>
          </div>
        </UiSpin>
      </div>
    </div>

    <NamespaceCreateModal v-model:show="showCreate" @created="onCreated" />
  </section>
</template>

<style scoped>
.page {
  padding-bottom: var(--space-5);
}

.alert {
  margin-bottom: var(--space-3);
}

.card {
  padding: var(--space-2) var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

:deep(.prefix) {
  font-weight: 500;
}

:deep(.muted) {
  color: var(--text-tertiary);
}
</style>

<style scoped src="../styles/observatory.css"></style>
