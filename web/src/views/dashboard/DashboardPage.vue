<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { dashboardApi } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import { UiAlert, UiButton, UiSpin } from '@/components/ui'
import { useAsyncData } from '@/composables/useAsyncData'

const { t, locale } = useI18n()
const number = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const { data: stats, loading, error, reload } = useAsyncData(dashboardApi.stats)

/**
 * 与完整性核验的九个环节一致。数量仅表示已有资产或运行记录，不能代表环节已通过。
 * 暂无聚合统计的环节展示操作入口，不用零值推断其完成情况。
 */
const pipeline = computed(() => [
  {
    key: 'model',
    step: t('appUi.model'),
    count: stats.value?.ontologies ?? 0,
    link: 'designer',
    hint: t('dashboard.goDesigner'),
  },
  {
    key: 'source',
    step: t('menu.datasources'),
    count: stats.value?.datasources ?? 0,
    link: 'datasources',
    hint: t('appUi.sourceHint'),
  },
  {
    key: 'mapping',
    step: t('appUi.mapping'),
    count: stats.value?.mappings ?? 0,
    link: 'mapping-wizard',
    hint: t('appUi.mappingHint'),
  },
  {
    key: 'execute',
    step: t('page.extractionRuns'),
    count: stats.value?.runs ?? 0,
    link: 'extraction-runs',
    hint: t('dashboard.goExtractionRuns'),
  },
  {
    key: 'explore',
    step: t('page.graphBrowse'),
    count: stats.value?.result_set_count ?? 0,
    link: 'graph-browse',
    hint: t('dashboard.goGraphBrowse'),
  },
  {
    key: 'govern',
    step: t('appUi.govern'),
    count: null,
    link: 'graph-reports',
    hint: t('appUi.governHint'),
  },
])

/** 资产总览：仅指向已登录角色可访问的现有列表。 */
const assets = computed(() => [
  {
    key: 'entityTypes',
    label: t('dashboard.entityTypes'),
    value: stats.value?.entity_types ?? 0,
    link: 'entity-types',
  },
  {
    key: 'relationTypes',
    label: t('dashboard.relationTypes'),
    value: stats.value?.relation_types ?? 0,
    link: 'relation-types',
  },
  {
    key: 'domains',
    label: t('dashboard.domains'),
    value: stats.value?.domains ?? 0,
    link: 'domains',
  },
  {
    key: 'ontologies',
    label: t('dashboard.ontologies'),
    value: stats.value?.ontologies ?? 0,
    link: 'ontologies',
  },
  {
    key: 'datasources',
    label: t('dashboard.datasources'),
    value: stats.value?.datasources ?? 0,
    link: 'datasources',
  },
  {
    key: 'mappings',
    label: t('dashboard.mappings'),
    value: stats.value?.mappings ?? 0,
    link: 'mapping-wizard',
  },
  {
    key: 'runs',
    label: t('dashboard.runs'),
    value: stats.value?.runs ?? 0,
    link: 'extraction-runs',
  },
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

    <UiAlert v-if="error" type="error" :title="error">
      <UiButton size="small" @click="reload">{{ t('dashboard.retry') }}</UiButton>
    </UiAlert>

    <UiSpin v-else-if="loading" :show="true">
      <div class="loading-state" role="status">{{ t('common.loading') }}</div>
    </UiSpin>

    <template v-else-if="stats">
      <div class="console-grid">
        <section class="observation-panel panel">
          <header class="panel-heading">
            <div>
              <span class="eyebrow">{{ t('operationsUi.console') }}</span>
              <h2>{{ t('dashboard.currentGraph') }}</h2>
            </div>
            <span class="scope-note">{{ t('operationsUi.scope') }}</span>
          </header>
          <div class="observation-readout">
            <div v-if="stats.current_graph_id !== null" class="result-value mono">
              {{ t('dashboard.resultSet', { id: stats.current_graph_id }) }}
            </div>
            <div v-else class="result-empty">
              <strong class="result-none">{{ t('dashboard.none') }}</strong
              ><span>{{ t('dashboard.noCurrentGraph') }}</span>
            </div>
            <p class="readout-hint">{{ t('operationsUi.readoutHint') }}</p>
            <div class="result-row">
              <article class="readout">
                <span>{{ t('dashboard.resultSets') }}</span
                ><strong class="metric mono">{{ number(stats.result_set_count) }}</strong>
              </article>
              <article class="readout" :class="{ warn: !!stats.quarantine_count }">
                <span>{{ t('dashboard.quarantine') }}</span
                ><strong class="metric mono">{{ number(stats.quarantine_count) }}</strong>
              </article>
            </div>
          </div>
          <div class="continue-work">
            <div>
              <strong>{{ t('appUi.continueWork') }}</strong>
              <p>{{ stats.current_graph_id ? t('appUi.continueGraph') : t('appUi.startHint') }}</p>
            </div>
            <RouterLink
              :to="
                stats.current_graph_id
                  ? { name: 'graph-browse', query: { graph: stats.current_graph_id } }
                  : { name: 'designer' }
              "
              ><UiButton type="primary">{{
                stats.current_graph_id ? t('dashboard.goGraphBrowse') : t('dashboard.goDesigner')
              }}</UiButton></RouterLink
            >
          </div>
        </section>
        <section class="attention-panel panel">
          <header class="panel-heading">
            <div>
              <span class="eyebrow">{{ t('dashboard.issues') }}</span>
              <h2>{{ t('operationsUi.attentionHint') }}</h2>
            </div>
          </header>
          <div v-if="!hasIssues" class="empty-ok">{{ t('appUi.noPending') }}</div>
          <div v-else class="issue-list">
            <UiAlert
              v-if="stats.quarantine_count"
              type="warning"
              :title="t('dashboard.quarantineCount', { count: stats.quarantine_count })"
              >{{ t('dashboard.quarantineHint') }}</UiAlert
            >
            <UiAlert
              v-if="stats.unpublished_count"
              type="info"
              :title="t('dashboard.draftResources', { count: stats.unpublished_count })"
              >{{ t('dashboard.unpublishedHint') }}</UiAlert
            >
          </div>
          <div class="attention-actions">
            <RouterLink :to="{ name: 'extraction-runs' }">{{
              t('dashboard.goExtractionRuns')
            }}</RouterLink>
            <RouterLink :to="{ name: 'graph-reports' }">{{
              t('dashboard.goGraphReports')
            }}</RouterLink>
          </div>
        </section>
        <!-- 数量只表示已有资产，不代表业务阶段已完成。 -->
        <section class="pipeline-panel panel">
          <header class="panel-heading">
            <h2>{{ t('dashboard.overview') }}</h2>
            <span class="scope-note">{{ t('operationsUi.scopeHint') }}</span>
          </header>
          <ol class="pipeline">
            <li v-for="(item, index) in pipeline" :key="item.key" class="pipe-cell">
              <RouterLink
                :to="{ name: item.link }"
                class="pipe-step"
                :class="{ empty: item.count === 0 }"
              >
                <span class="pipe-head">
                  <span class="pipe-no mono">{{ index + 1 }}</span>
                  <span class="pipe-name">{{ item.step }}</span>
                </span>
                <span v-if="item.count !== null" class="pipe-count mono">{{
                  number(item.count ?? 0)
                }}</span>
                <span v-else class="pipe-action">{{ t('dashboard.open') }}</span>
                <span class="pipe-hint">{{ item.hint }}</span>
              </RouterLink>
            </li>
          </ol>
        </section>

        <!-- 资产总览 -->
        <section class="asset-panel panel">
          <header class="panel-heading">
            <h2>{{ t('dashboard.assets') }}</h2>
          </header>
          <div class="asset-grid">
            <RouterLink
              v-for="item in assets"
              :key="item.key"
              :to="{ name: item.link }"
              class="asset"
            >
              <div class="asset-value mono">{{ number(item.value) }}</div>
              <div class="card-label">{{ item.label }}</div>
            </RouterLink>
          </div>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.dashboard {
  min-width: 0;
  padding-bottom: 24px;
}
.console-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 1fr);
  gap: 16px;
}
.panel {
  min-width: 0;
  background: var(--bg-panel, var(--bg-surface));
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  overflow: hidden;
}
.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.panel-heading h2 {
  font-size: var(--font-h2);
  font-weight: 600;
  margin: 4px 0 0;
}
.eyebrow,
.scope-note {
  color: var(--text-secondary);
  font-size: 12px;
}
.observation-readout {
  padding: 24px 20px 0;
  background: var(--bg-inset);
}
.result-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--accent);
  overflow-wrap: anywhere;
}
.result-empty {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-secondary);
}
.result-none {
  font-size: 24px;
  color: var(--text-primary, var(--text));
}
.readout-hint {
  max-width: 60ch;
  margin: 12px 0 20px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.7;
}
.result-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--border);
}
.readout {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 16px 16px 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.readout + .readout {
  border-left: 1px solid var(--border);
  padding-left: 16px;
}
.metric {
  color: var(--text-primary, var(--text));
  font-size: 24px;
  font-weight: 500;
}
.warn .metric {
  color: var(--s-notrun);
}
.continue-work {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 20px;
  border-top: 1px solid var(--border);
}
.continue-work strong {
  font-size: 14px;
}
.continue-work p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}
.attention-panel {
  align-self: start;
}
.issue-list {
  display: grid;
  gap: 12px;
  padding: 20px;
}
.empty-ok {
  padding: 24px 20px;
  color: var(--text-secondary);
  font-size: 13px;
}
.attention-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.attention-actions a {
  color: var(--accent);
  font-size: 12px;
}
.pipeline-panel {
  grid-column: 1 / -1;
}
.pipeline {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  list-style: none;
  padding: 0;
  margin: 0;
}
.pipe-cell {
  min-width: 0;
  border-right: 1px solid var(--border);
}
.pipe-cell:last-child {
  border-right: 0;
}
.pipe-step {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 136px;
  padding: 16px;
  text-decoration: none;
  color: var(--text-primary, var(--text));
  transition: background 120ms;
}
.pipe-step:hover,
.asset:hover {
  background: var(--bg-inset);
}
.pipe-step:focus-visible,
.asset:focus-visible,
.attention-actions a:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.pipe-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pipe-no {
  color: var(--accent);
  font-size: 11px;
}
.pipe-name {
  font-size: 12px;
}
.pipe-count {
  font-size: 24px;
  line-height: 1.2;
}
.pipe-action {
  color: var(--accent);
  font-size: 14px;
  line-height: 1.8;
}
.pipe-hint {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.6;
}
.asset-panel {
  grid-column: 1 / -1;
}
.asset-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}
.asset {
  min-width: 0;
  padding: 16px 20px;
  color: var(--text-primary, var(--text));
  text-decoration: none;
  border-right: 1px solid var(--border);
}
.asset:last-child {
  border-right: 0;
}
.asset-value {
  font-size: 22px;
}
.card-label {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}
.loading-state {
  min-height: 250px;
  display: grid;
  place-items: center;
}
@media (max-width: 1279px) {
  .pipeline {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .pipe-cell {
    border-bottom: 1px solid var(--border);
  }
  .pipe-cell:nth-child(3n) {
    border-right: 0;
  }
  .pipe-cell:nth-last-child(-n + 3) {
    border-bottom: 0;
  }
  .asset-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .asset {
    border-bottom: 1px solid var(--border);
  }
}
@media (max-width: 767px) {
  .console-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .pipeline-panel,
  .asset-panel {
    grid-column: auto;
  }
  .asset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pipeline {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pipe-cell:nth-child(3n) {
    border-right: 1px solid var(--border);
  }
  .pipe-cell:nth-child(2n) {
    border-right: 0;
  }
  .pipe-cell:nth-last-child(3) {
    border-bottom: 1px solid var(--border);
  }
  .panel-heading,
  .continue-work {
    padding: 16px;
  }
  .continue-work :deep(.ui-button) {
    min-height: 44px;
    max-width: 100%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pipe-step {
    transition: none;
  }
}
</style>
