<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import {
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NTag,
} from 'naive-ui'
import { computed, h, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Clause, ClauseInput } from '@/api/clauses'
import { clausesApi } from '@/api/clauses'
import PageHeader from '@/components/PageHeader.vue'
import { useApiError } from '@/composables/useApiError'

const { t, locale } = useI18n()
const { toMessage } = useApiError()
const items = ref<Clause[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const showEditor = ref(false)
const saved = ref<Clause | null>(null)
const form = ref<ClauseInput>(emptyClause())
let readController: AbortController | undefined
let alive = true

/** 附录性质是枚举码，标签走 i18n，不直出英文。 */
const NATURES = computed(() => [
  { label: t('clauses.nature.NORMATIVE'), value: 'NORMATIVE' },
  { label: t('clauses.nature.INFORMATIVE'), value: 'INFORMATIVE' },
])

function emptyClause(): ClauseInput {
  return {
    standard: '',
    clause_number: '',
    title_i18n: { 'zh-CN': '', 'en-US': '' },
    self_authored_description: { 'zh-CN': '', 'en-US': '' },
    product_fallback: '',
    appendix_nature: 'NORMATIVE',
    date_lexicon: '',
    clause_disambiguation: '',
    example_domain: '',
  }
}

function payload(c: Clause): ClauseInput {
  return {
    standard: c.standard,
    clause_number: c.clause_number,
    title_i18n: { ...c.title_i18n },
    self_authored_description: { ...c.self_authored_description },
    product_fallback: c.product_fallback ?? '',
    appendix_nature: c.appendix_nature as 'NORMATIVE' | 'INFORMATIVE',
    date_lexicon: c.date_lexicon ?? '',
    clause_disambiguation: c.clause_disambiguation ?? '',
    example_domain: c.example_domain ?? '',
  }
}

function failText(err: unknown): string {
  const e = err as { message?: string; code?: string }
  if (!e) return t('clauses.failed', { reason: '' })
  if (e.code === 'KG.ALREADY_EXISTS') return t('clauses.duplicate')
  if (e.code === 'KG.REVISION_CONFLICT') return t('clauses.conflict')
  // 其余错误按 code 走统一 i18n 码表，不直出后端英文 message
  return toMessage(err)
}

async function load() {
  readController?.abort()
  const controller = new AbortController()
  readController = controller
  loading.value = true
  error.value = ''
  try {
    const data = await clausesApi.list(
      { page: page.value, page_size: 20, q: search.value },
      controller.signal,
    )
    if (!alive) return
    items.value = data.items as unknown as Clause[]
    total.value = data.total
  } catch (err) {
    if (!alive) return
    error.value = failText(err)
  } finally {
    if (alive) loading.value = false
  }
}

function openCreate() {
  saved.value = null
  form.value = emptyClause()
  error.value = ''
  notice.value = ''
  showEditor.value = true
}

function openEdit(c: Clause) {
  saved.value = c
  form.value = payload(c)
  error.value = ''
  notice.value = ''
  showEditor.value = true
}

async function submit() {
  // 必填约束在界面上先拦一层：standard/clause_number/标题(中) 为空直接提示，
  // 不再空表单直发、靠后端 422 兜底
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    if (saved.value) {
      const rest = { ...form.value }
      delete (rest as Partial<ClauseInput>).standard
      delete (rest as Partial<ClauseInput>).clause_number
      const updated = await clausesApi.update(saved.value, rest)
      saved.value = updated
      notice.value = t('clauses.saved')
      await load()
    } else {
      const created = await clausesApi.create(form.value)
      saved.value = created
      notice.value = t('clauses.saved')
      await load()
    }
  } catch (err) {
    error.value = failText(err)
  } finally {
    busy.value = false
  }
}

const formRef = ref<FormInst | null>(null)
// 必填约束在界面上先拦一层：standard/clause_number/标题(中) 为空直接提示，
// 不再空表单直发、靠后端 422 兜底。键名与 NFormItem 的 path 对齐（lodash get 语法）。
const rules: FormRules = {
  standard: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  clause_number: { required: true, message: t('common.required'), trigger: ['blur', 'input'] },
  "title_i18n['zh-CN']": {
    required: true,
    message: t('common.required'),
    trigger: ['blur', 'input'],
  },
}

async function remove(c: Clause) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await clausesApi.remove(c)
    notice.value = t('clauses.deleted')
    await load()
  } catch (err) {
    error.value = failText(err)
  } finally {
    busy.value = false
  }
}

watch([page, search], load, { immediate: true })

function doSearch() {
  if (page.value === 1) load()
  else page.value = 1
}

onBeforeUnmount(() => {
  alive = false
  readController?.abort()
})

const columns = computed(() => [
  { title: t('clauses.standard'), key: 'standard', width: 160 },
  { title: t('clauses.clauseNumber'), key: 'clause_number', width: 110 },
  {
    title: t('clauses.title'),
    key: 'title',
    minWidth: 240,
    render: (row: Clause) => row.title_i18n[locale.value] ?? row.title_i18n['zh-CN'] ?? '',
  },
  {
    title: t('clauses.nature'),
    key: 'appendix_nature',
    width: 120,
    render: (row: Clause) =>
      row.appendix_nature === 'NORMATIVE' ? t('clauses.normative') : t('clauses.informative'),
  },
  {
    title: t('clauses.productFallback'),
    key: 'product_fallback',
    width: 200,
    render: (row: Clause) => row.product_fallback ?? '',
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 160,
    render: (row: Clause) =>
      h('div', { style: 'display:flex;gap:8px' }, [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, () => t('common.edit')),
        h(
          NPopconfirm,
          { onPositiveClick: () => remove(row) },
          {
            trigger: () => h(NButton, { size: 'small', type: 'error' }, () => t('common.delete')),
            default: () => t('clauses.deleteConfirm'),
          },
        ),
      ]),
  },
])
</script>

<template>
  <div class="clauses-page">
    <PageHeader :title="t('page.governanceClauses')" :description="t('clauses.intro')">
      <template #actions>
        <n-button type="primary" @click="openCreate">{{ t('clauses.create') }}</n-button>
      </template>
    </PageHeader>
    <n-card :bordered="false">
      <n-space class="toolbar" align="center">
        <n-form-item
          :label="t('common.search')"
          label-placement="left"
          :label-width="72"
          :show-feedback="false"
        >
          <n-input
            v-model:value="search"
            :placeholder="t('clauses.searchPlaceholder')"
            clearable
            style="width: 280px"
            @keyup.enter="doSearch"
            @clear="doSearch"
          />
        </n-form-item>
        <n-button @click="doSearch">{{ t('common.search') }}</n-button>
      </n-space>
      <n-empty v-if="!loading && items.length === 0" :description="t('clauses.empty')" />
      <n-data-table
        v-else
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(row: Clause) => row.id"
        :scroll-x="1000"
        remote
      />
      <n-pagination
        v-if="total > 0"
        v-model:page="page"
        :item-count="total"
        :page-size="20"
        show-quick-jumper
      />
    </n-card>

    <n-drawer v-model:show="showEditor" :width="560">
      <n-drawer-content :title="saved ? t('clauses.edit') : t('clauses.create')" closable>
        <n-form ref="formRef" :model="form" :rules="rules">
          <n-form-item :label="t('clauses.standard')" path="standard">
            <n-input
              v-model:value="form.standard"
              :disabled="!!saved"
              :placeholder="t('clauses.standardPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('clauses.clauseNumber')" path="clause_number">
            <n-input
              v-model:value="form.clause_number"
              :disabled="!!saved"
              :placeholder="t('clauses.clauseNumberPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('clauses.title') + ' (zh-CN)'" path="title_i18n['zh-CN']">
            <n-input v-model:value="form.title_i18n['zh-CN']" />
          </n-form-item>
          <n-form-item :label="t('clauses.title') + ' (en-US)'">
            <n-input v-model:value="form.title_i18n['en-US']" />
          </n-form-item>
          <n-form-item :label="t('clauses.description') + ' (zh-CN)'">
            <n-input
              v-model:value="form.self_authored_description['zh-CN']"
              type="textarea"
              :rows="3"
            />
          </n-form-item>
          <n-form-item :label="t('clauses.description') + ' (en-US)'">
            <n-input
              v-model:value="form.self_authored_description['en-US']"
              type="textarea"
              :rows="3"
            />
          </n-form-item>
          <n-form-item :label="t('clauses.nature')">
            <n-select v-model:value="form.appendix_nature" :options="NATURES" />
          </n-form-item>
          <n-form-item :label="t('clauses.productFallback')">
            <n-input v-model:value="form.product_fallback" />
          </n-form-item>
          <n-form-item :label="t('clauses.dateLexicon')">
            <n-input v-model:value="form.date_lexicon" />
          </n-form-item>
          <n-form-item :label="t('clauses.disambiguation')">
            <n-input v-model:value="form.clause_disambiguation" type="textarea" :rows="2" />
          </n-form-item>
          <n-form-item :label="t('clauses.exampleDomain')">
            <n-input v-model:value="form.example_domain" />
          </n-form-item>
        </n-form>
        <n-space v-if="notice" align="center">
          <n-tag type="success">{{ notice }}</n-tag>
        </n-space>
        <n-space v-if="error" align="center">
          <n-tag type="error">{{ error }}</n-tag>
        </n-space>
        <template #footer>
          <n-space>
            <n-button :loading="busy" type="primary" @click="submit">{{
              t('common.save')
            }}</n-button>
            <n-button @click="showEditor = false">{{ t('common.cancel') }}</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.clauses-page {
  display: grid;
  gap: var(--space-4);
}
.clauses-page .toolbar {
  margin-bottom: 16px;
}
</style>
