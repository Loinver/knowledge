<script setup lang="ts">
import { NAlert, NButton, NSpin } from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { dashboardApi } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const { data: stats, loading, error, reload } = useAsyncData(dashboardApi.stats)

/**
 * 主流程六步。这是产品的心脏，所以放在首屏最上方而不是塞进卡片网格。
 * `count` 为 0 时整步走「未开始」样式 —— 深空即未知：没做的事就该看起来是空的。
 */
const pipeline = computed(() => [
  {
    key: 'model',
    step: t('dashboard.step1'),
    count: stats.value?.entity_types ?? 0,
    link: 'entity-types',
    hint: t('dashboard.goEntityTypes'),
  },
  {
    key: 'source',
    step: t('dashboard.step2'),
    count: stats.value?.datasources ?? 0,
    link: 'datasources',
    hint: t('dashboard.goDataSources'),
  },
  {
    key: 'mapping',
    step: t('dashboard.step3'),
    count: stats.value?.mappings ?? 0,
    link: 'mapping-wizard',
    hint: t('dashboard.goMappingWizard'),
  },
  {
    key: 'run',
    step: t('dashboard.step4'),
    count: stats.value?.runs ?? 0,
    link: 'extraction-runs',
    hint: t('dashboard.goExtractionRuns'),
  },
  {
    key: 'graph',
    step: t('dashboard.step5'),
    count: stats.value?.result_set_count ?? 0,
    link: 'graph-browse',
    hint: t('dashboard.goGraphBrowse'),
  },
  {
    key: 'report',
    step: t('dashboard.step6'),
    count: stats.value?.quarantine_count ?? 0,
    link: 'graph-reports',
    hint: t('dashboard.goGraphReports'),
  },
])

/** 资产总览：本体侧的四类资源。 */
const assets = computed(() => [
  { key: 'entityTypes', label: t('dashboard.entityTypes'), value: stats.value?.entity_types ?? 0 },
  {
    key: 'relationTypes',
    label: t('dashboard.relationTypes'),
    value: stats.value?.relation_types ?? 0,
  },
  { key: 'domains', label: t('dashboard.domains'), value: stats.value?.domains ?? 0 },
  { key: 'ontologies', label: t('dashboard.ontologies'), value: stats.value?.ontologies ?? 0 },
  { key: 'datasources', label: t('dashboard.datasources'), value: stats.value?.datasources ?? 0 },
  { key: 'runs', label: t('dashboard.runs'), value: stats.value?.runs ?? 0 },
])

const hasIssues = computed(
  () =>
    (stats.value && (stats.value.quarantine_count > 0 || stats.value.unpublished_count > 0)) ||
    false,
)
</script>

<template>
  <section class="dashboard">
    <PageHeader :title="t('page.dashboard')" :description="t('dashboard.description')" />

    <NAlert v-if="error" type="error" :title="error">
      <NButton size="small" @click="reload">{{ t('dashboard.retry') }}</NButton>
    </NAlert>

    <NSpin v-else-if="loading" :show="true">
      <div class="loading-state" role="status">{{ t('common.loading') }}</div>
    </NSpin>

    <template v-else-if="stats">
      <!-- 主流程：六步管线，未开始的步骤整步变暗 -->
      <section class="block">
        <h3 class="block-title">{{ t('dashboard.overview') }}</h3>
        <ol class="pipeline">
          <li v-for="(item, index) in pipeline" :key="item.key" class="pipe-cell">
            <RouterLink :to="{ name: item.link }" class="pipe-step" :class="{ empty: !item.count }">
              <span class="pipe-head">
                <span class="pipe-no mono">{{ index + 1 }}</span>
                <span class="pipe-name">{{ item.step.replace(/^\d+\.\s*/, '') }}</span>
              </span>
              <span class="pipe-count mono">{{ item.count }}</span>
              <span class="pipe-hint">{{ item.hint }}</span>
            </RouterLink>
          </li>
        </ol>
      </section>

      <!-- 当前结果集：图谱侧的三个关键指标 -->
      <section class="block">
        <div class="result-row">
          <article class="card result-main">
            <div class="card-label">{{ t('dashboard.currentGraph') }}</div>
            <div v-if="stats.current_graph_id !== null" class="result-value mono">
              {{ t('dashboard.resultSet', { id: stats.current_graph_id }) }}
            </div>
            <div v-else class="result-empty">
              <span class="result-none">{{ t('dashboard.none') }}</span>
              <span class="hint">{{ t('dashboard.noCurrentGraph') }}</span>
            </div>
          </article>

          <article class="card">
            <div class="card-label">{{ t('dashboard.resultSets') }}</div>
            <div class="metric mono">{{ stats.result_set_count }}</div>
          </article>

          <article class="card" :class="{ warn: !!stats.quarantine_count }">
            <div class="card-label">{{ t('dashboard.quarantine') }}</div>
            <div class="metric mono" :class="{ 'metric-warn': !!stats.quarantine_count }">
              {{ stats.quarantine_count }}
            </div>
            <div v-if="stats.quarantine_count" class="hint">
              {{ t('dashboard.quarantineHint') }}
            </div>
          </article>
        </div>
      </section>

      <!-- 资产总览 -->
      <section class="block">
        <h3 class="block-title">{{ t('dashboard.assets') }}</h3>
        <div class="asset-grid">
          <article v-for="item in assets" :key="item.key" class="card asset">
            <div class="asset-value mono">{{ item.value }}</div>
            <div class="card-label">{{ item.label }}</div>
          </article>
        </div>
      </section>

      <!-- 待处理问题：有问题才出现，没问题时不占视觉重量 -->
      <section class="block">
        <h3 class="block-title">{{ t('dashboard.issues') }}</h3>
        <div v-if="!hasIssues" class="empty-ok">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke="var(--s-pass)" stroke-width="1.5" />
            <path
              d="M8 12.4l2.6 2.6L16 9.6"
              stroke="var(--s-pass)"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
          <span>{{ t('dashboard.noIssues') }}</span>
        </div>
        <div v-else class="issue-list">
          <NAlert
            v-if="stats.quarantine_count"
            type="warning"
            :title="t('dashboard.quarantineCount', { count: stats.quarantine_count })"
          >
            {{ t('dashboard.quarantineHint') }}
          </NAlert>
          <NAlert
            v-if="stats.unpublished_count"
            type="info"
            :title="t('dashboard.draftResources', { count: stats.unpublished_count })"
          >
            {{ t('dashboard.unpublishedHint') }}
          </NAlert>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.dashboard {
  padding-bottom: var(--space-5);
}

.loading-state {
  padding: var(--space-5);
  text-align: center;
}

.block {
  margin-bottom: var(--space-5);
}

.block-title {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-caption);
  font-weight: 500;
  letter-spacing: 0.3px;
}

.card {
  padding: var(--space-4);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.card-label {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
}

/* ── 主流程管线 ─────────────────────────────────────────── */
.pipeline {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--space-3);
  padding: 0;
  margin: 0;
  list-style: none;
}

.pipe-cell {
  position: relative;
  min-width: 0;
}

/* 步骤之间的连接线：只在两个步骤都「已开始」时才亮起 */
.pipe-cell:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: calc(var(--space-3) / -2 - 3px);
  width: 6px;
  height: 1px;
  content: '';
  background: var(--border-strong);
}

.pipe-step {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  padding: var(--space-3) var(--space-3) 14px;
  color: var(--text);
  text-decoration: none;
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
  transition:
    box-shadow var(--dur-base) var(--ease-out),
    transform var(--dur-base) var(--ease-out);
}

.pipe-step:hover {
  box-shadow: var(--glow);
  transform: translateY(-1px);
}

/* 未开始的步骤：整步降对比度，一眼看出「这里还是空的」 */
.pipe-step.empty {
  background: transparent;
  box-shadow: 0 0 0 1px var(--border-subtle);
}

.pipe-head {
  display: flex;
  gap: 7px;
  align-items: center;
}

.pipe-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  color: var(--accent);
  font-size: 10px;
  background: var(--accent-soft);
  border-radius: var(--r-sm);
}

.pipe-step.empty .pipe-no {
  color: var(--text-disabled);
  background: transparent;
  box-shadow: 0 0 0 1px var(--border-subtle);
}

.pipe-name {
  overflow: hidden;
  font-size: var(--font-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pipe-count {
  font-size: 24px;
  font-weight: 500;
  line-height: 1.2;
}

.pipe-step.empty .pipe-count {
  color: var(--text-disabled);
}

.pipe-hint {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 当前结果集 ─────────────────────────────────────────── */
.result-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: var(--space-3);
}

.result-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-value {
  font-size: 20px;
  font-weight: 500;
  color: var(--g-current);
}

.result-empty {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.result-none {
  color: var(--text-disabled);
  font-size: 20px;
  font-weight: 500;
}

.metric {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 500;
  line-height: 1.2;
}

.metric-warn {
  color: var(--s-notrun);
}

.card.warn {
  box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.35);
}

.hint {
  margin-top: 6px;
  color: var(--text-tertiary);
  font-size: 11px;
  line-height: 1.6;
}

/* ── 资产总览 ───────────────────────────────────────────── */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: var(--space-3);
}

.asset-value {
  font-size: 22px;
  font-weight: 500;
  line-height: 1.2;
}

.asset .card-label {
  margin-top: 5px;
}

/* ── 待处理问题 ─────────────────────────────────────────── */
.empty-ok {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: var(--space-4);
  color: var(--text-secondary);
  font-size: var(--font-small);
  background: var(--bg-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--elev-1);
}

.issue-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* 窄屏：管线折成两行，指标卡竖排 */
@media (max-width: 1100px) {
  .pipeline {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .pipe-cell:nth-child(3n)::after {
    display: none;
  }
  .result-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .pipeline {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pipe-cell::after {
    display: none;
  }
}
</style>
