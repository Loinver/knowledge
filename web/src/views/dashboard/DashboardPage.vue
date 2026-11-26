<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { dashboardApi } from '@/api/dashboard'
import AppIcon from '@/components/AppIcon.vue'
import PageHeader from '@/components/PageHeader.vue'
import { UiAlert, UiButton, UiSpin } from '@/components/ui'
import { useAsyncData } from '@/composables/useAsyncData'

const { t, locale } = useI18n()
const number = (value: number) => new Intl.NumberFormat(locale.value).format(value)
const { data: stats, loading, error, reload } = useAsyncData(dashboardApi.stats)

/**
 * 六个任务阶段。数量仅表示已有资产或运行记录，不能代表环节已通过。
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
              <h2>{{ t('assetStudio.currentWork') }}</h2>
            </div>
            <span class="scope-note">{{ t('dashboard.currentGraph') }}</span>
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
              <p>
                {{
                  stats.current_graph_id !== null ? t('appUi.continueGraph') : t('appUi.startHint')
                }}
              </p>
            </div>
            <RouterLink
              :to="
                stats.current_graph_id !== null
                  ? { name: 'graph-browse', query: { graph: stats.current_graph_id } }
                  : { name: 'designer' }
              "
              ><UiButton type="primary">{{
                stats.current_graph_id !== null
                  ? t('dashboard.goGraphBrowse')
                  : t('dashboard.goDesigner')
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
            <article v-if="stats.unpublished_count" class="attention-item">
              <div class="attention-icon"><AppIcon name="ontology" /></div>
              <div class="attention-copy">
                <h3>
                  {{ t('dashboard.draftResources', { count: number(stats.unpublished_count) }) }}
                </h3>
                <p>{{ t('assetStudio.draftScope') }}</p>
                <p>{{ t('assetStudio.publishPrerequisite') }}</p>
                <nav class="draft-links" :aria-label="t('dashboard.assets')">
                  <RouterLink
                    v-for="item in assets.slice(0, 4)"
                    :key="item.key"
                    :to="{ name: item.link, query: { status: 'DRAFT' } }"
                    >{{ item.label }}</RouterLink
                  >
                </nav>
              </div>
              <span class="attention-count">{{ number(stats.unpublished_count) }}</span>
            </article>
            <RouterLink
              v-if="stats.quarantine_count"
              :to="{ name: 'extraction-runs' }"
              class="attention-item"
            >
              <div class="attention-icon"><AppIcon name="governance" /></div>
              <div class="attention-copy">
                <h3>
                  {{ t('dashboard.quarantineCount', { count: number(stats.quarantine_count) }) }}
                </h3>
                <p>{{ t('dashboard.quarantineHint') }}</p>
              </div>
              <span class="attention-count">{{ number(stats.quarantine_count) }}</span>
            </RouterLink>
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
              :class="{ 'asset-secondary': ['datasources', 'mappings', 'runs'].includes(item.key) }"
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
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 1fr);
  gap: 28px;
}
.panel {
  min-width: 0;
}
.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 0 0 16px;
}
.panel-heading h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.eyebrow,
.scope-note {
  color: var(--foreground-muted);
  font-size: 12px;
}
.observation-panel {
  background: var(--surface-inset);
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  overflow: hidden;
}
.observation-panel .panel-heading {
  padding: 22px 24px 0;
}
.observation-panel h2 {
  margin-top: 8px;
  font-size: 22px;
}
.observation-readout {
  padding: 16px 24px 0;
}
.result-value {
  color: var(--action-primary);
  font-size: 18px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.result-empty {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: baseline;
  color: var(--foreground-muted);
  font-size: 13px;
}
.result-none {
  font-size: 18px;
  color: var(--foreground-primary);
}
.readout-hint {
  margin: 8px 0 16px;
  color: var(--foreground-muted);
  font-size: 12px;
  line-height: 1.7;
}
.work-assets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding-bottom: 18px;
}
.work-assets a {
  display: grid;
  gap: 6px;
  color: inherit;
  text-decoration: none;
}
.work-assets span {
  color: var(--foreground-muted);
  font-size: 12px;
}
.work-assets strong {
  font-size: 26px;
  font-weight: 600;
}
.result-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--border-muted);
}
.readout {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 12px 0;
  color: var(--foreground-muted);
  font-size: 12px;
}
.metric {
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground-primary);
}
.warn .metric {
  color: var(--status-not-run);
}
.continue-work {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 24px 22px;
}
.continue-work strong {
  font-size: 13px;
}
.continue-work p {
  margin: 5px 0 0;
  font-size: 12px;
  color: var(--foreground-muted);
}
.attention-panel {
  align-self: start;
}
.attention-panel .eyebrow {
  display: none;
}
.issue-list {
  display: grid;
}
.attention-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 20px 0;
  border-bottom: 1px solid var(--border-muted);
  color: inherit;
  text-decoration: none;
}
.attention-icon {
  display: grid;
  place-items: center;
  flex: 0 0 34px;
  height: 34px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--status-not-run) 10%, var(--surface-panel));
  color: var(--status-not-run);
  font-size: 20px;
}
.attention-copy {
  flex: 1;
  min-width: 0;
}
.attention-copy h3 {
  margin: 0 0 6px;
  font-size: 14px;
}
.attention-copy p {
  margin: 0 0 5px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--foreground-muted);
}
.attention-count {
  color: var(--foreground-secondary);
  font-size: 20px;
}
.draft-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 10px;
}
.draft-links a {
  color: var(--action-primary);
  font-size: 12px;
}
.empty-ok {
  padding: 24px 0;
  color: var(--foreground-muted);
  font-size: 13px;
}
.attention-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 16px 0;
}
.attention-actions a {
  color: var(--action-primary);
  font-size: 12px;
}
.pipeline-panel,
.asset-panel {
  grid-column: 1 / -1;
}
.pipeline {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  list-style: none;
  padding: 0;
  margin: 0;
  border-block: 1px solid var(--border-muted);
}
.pipe-cell {
  min-width: 0;
  border-right: 1px solid var(--border-muted);
}
.pipe-cell:last-child {
  border-right: 0;
}
.pipe-step {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px 6px;
  padding: 20px 16px;
  text-decoration: none;
  color: var(--foreground-primary);
}
.pipe-head {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pipe-no {
  font-size: 11px;
  color: var(--foreground-muted);
}
.pipe-name {
  font-size: 14px;
  font-weight: 600;
}
.pipe-count,
.pipe-action {
  align-self: end;
  color: var(--action-primary);
  font-size: 18px;
}
.pipe-hint {
  grid-column: 1 / -1;
  color: var(--foreground-muted);
  font-size: 12px;
  line-height: 1.6;
}
.asset-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.asset {
  display: flex;
  flex-direction: column-reverse;
  min-width: 0;
  gap: 6px;
  padding: 16px 20px;
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-panel);
  color: var(--foreground-primary);
  text-decoration: none;
}
.asset-value {
  font-size: 26px;
  line-height: 1.2;
}
.card-label {
  color: var(--foreground-muted);
  font-size: 12px;
}
.asset-secondary {
  grid-row: 2;
  flex-direction: row-reverse;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--surface-muted);
}
.asset-secondary .asset-value {
  font-size: 18px;
}
.pipe-step:hover,
.asset:hover {
  background: var(--surface-hover);
}
a:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.loading-state {
  min-height: 250px;
  display: grid;
  place-items: center;
}
@media (max-width: 1100px) {
  .console-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
  }
  .pipeline {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .pipe-cell {
    border-bottom: 1px solid var(--border-muted);
  }
  .pipe-cell:nth-child(3n) {
    border-right: 0;
  }
  .pipe-cell:nth-last-child(-n + 3) {
    border-bottom: 0;
  }
}
@media (max-width: 640px) {
  .asset-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .asset-secondary {
    grid-row: auto;
  }
  .pipeline {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pipe-cell:nth-child(3n) {
    border-right: 1px solid var(--border-muted);
  }
  .pipe-cell:nth-child(2n) {
    border-right: 0;
  }
  .pipe-cell:nth-last-child(3) {
    border-bottom: 1px solid var(--border-muted);
  }
  .work-assets {
    gap: 8px;
  }
}
</style>
