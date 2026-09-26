<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NAlert, NButton, NDataTable, NEmpty, NPopconfirm, NSpin, NTag } from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Namespace } from '@/api/namespaces'
import { namespacesApi } from '@/api/namespaces'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

import NamespaceCreateModal from './components/NamespaceCreateModal.vue'

const { t, locale } = useI18n()
const { toMessage } = useApiError()

const items = ref<Namespace[]>([])
const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const notice = ref('')
const showCreate = ref(false)
const deletingId = ref<number | null>(null)
let controller: AbortController | undefined

async function load() {
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
  return labels[locale.value] ?? labels['zh-CN'] ?? t('common.noneValue')
}

/** 受保护或仍被资源引用的命名空间不可删；把原因直接写在按钮提示里，而不是等后端报错。 */
function deleteBlocker(ns: Namespace): string {
  if (ns.protected) return t('namespace.protectedHint')
  if (ns.resource_count) return t('namespace.inUseHint', { count: ns.resource_count })
  return ''
}

async function remove(ns: Namespace) {
  actionError.value = ''
  notice.value = ''
  deletingId.value = ns.id
  try {
    await namespacesApi.remove(ns.id)
    notice.value = t('namespace.deleted', { prefix: ns.prefix })
    await load()
  } catch (err) {
    const body = err as { code?: string; params?: { count?: number } } | undefined
    actionError.value =
      body?.code === 'KG.RESOURCE_IN_USE'
        ? t('namespace.inUseHint', { count: body.params?.count ?? 0 })
        : toMessage(err)
  } finally {
    deletingId.value = null
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
    render: (row) => h('span', { class: 'iri' }, row.iri),
  },
  { title: t('common.label'), key: 'label', minWidth: 140, render: (row) => displayLabel(row) },
  {
    title: t('namespace.resourceCount'),
    key: 'resource_count',
    width: 110,
    render: (row) => h('span', { class: 'mono' }, String(row.resource_count ?? 0)),
  },
  {
    title: t('namespace.protected'),
    key: 'protected',
    width: 100,
    render: (row) =>
      row.protected
        ? h(NTag, { size: 'small', bordered: false }, { default: () => t('common.yes') })
        : h('span', { class: 'muted' }, t('common.no')),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 100,
    render: (row) => {
      const blocker = deleteBlocker(row)
      if (blocker) {
        return h(
          NButton,
          { size: 'small', quaternary: true, disabled: true, title: blocker },
          { default: () => t('common.delete') },
        )
      }
      return h(
        NPopconfirm,
        { onPositiveClick: () => void remove(row) },
        {
          trigger: () =>
            h(
              NButton,
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
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="page">
    <PageHeader :title="t('page.namespaces')" :description="t('namespace.description')">
      <template #actions>
        <NButton type="primary" @click="showCreate = true">{{ t('namespace.create') }}</NButton>
      </template>
    </PageHeader>

    <NAlert v-if="loadError" type="error" class="alert">{{ loadError }}</NAlert>
    <NAlert v-if="actionError" type="error" class="alert" closable>{{ actionError }}</NAlert>
    <NAlert v-if="notice" type="success" class="alert" closable>{{ notice }}</NAlert>

    <NSpin :show="loading">
      <div class="card">
        <NDataTable
          :columns="columns"
          :data="items"
          :bordered="false"
          :scroll-x="870"
          :row-key="(row: Namespace) => row.id"
        >
          <template #empty>
            <NEmpty :description="t('namespace.empty')">
              <template #extra>
                <NButton size="small" @click="showCreate = true">
                  {{ t('namespace.create') }}
                </NButton>
              </template>
            </NEmpty>
          </template>
        </NDataTable>
      </div>
    </NSpin>

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
