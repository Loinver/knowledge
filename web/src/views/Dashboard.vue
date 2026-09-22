<script setup lang="ts">
import { NAlert, NCard, NEmpty, NSpin, NStatistic, NTag } from 'naive-ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { dashboardApi, type DashboardStats } from '@/api/dashboard'
import { useAsyncData } from '@/composables/useAsyncData'

const { t } = useI18n()
const { data, loading, error, reload } = useAsyncData((signal) => dashboardApi.stats(signal))

const stats = computed<DashboardStats | null>(() => data.value)
const hasIssues = computed(
  () => (stats.value && (stats.value.quarantineCount > 0 || stats.value.unpublishedCount > 0)) || false,
)
const pipeline = computed(() => [
  { step: t('dashboard.step1'), count: stats.value?.entityTypes ?? 0, link: 'entity-types', label: t('dashboard.goEntityTypes') },
  { step: t('dashboard.step2'), count: stats.value?.datasources ?? 0, link: 'datasources', label: t('dashboard.goDataSources') },
  { step: t('dashboard.step3'), count: 0, link: 'mapping-wizard', label: t('dashboard.goMappingWizard') },
  { step: t('dashboard.step4'), count: stats.value?.runs ?? 0, link: 'extraction-runs', label: t('dashboard.goExtractionRuns') },
  { step: t('dashboard.step5'), count: stats.value?.resultSetCount ?? 0, link: 'graph-browse', label: t('dashboard.goGraphBrowse') },
  { step: t('dashboard.step6'), count: stats.value?.quarantineCount ?? 0, link: 'graph-reports', label: t('dashboard.goGraphReports') },
])
</script>

<template>
  <section class="dashboard">
    <h2>{{ t('page.dashboard') }}</h2>

    <NAlert v-if="error" type="error" :title="error" closable @close="reload" />

    <NSpin :show="loading">
      <div class="overview">
        <h3>{{ t('dashboard.overview') }}</h3>
        <div class="stat-grid">
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.entityTypes')" :value="stats?.entityTypes ?? 0" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.relationTypes')" :value="stats?.relationTypes ?? 0" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.domains')" :value="stats?.domains ?? 0" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.ontologies')" :value="stats?.ontologies ?? 0" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.datasources')" :value="stats?.datasources ?? 0" />
          </NCard>
          <NCard size="small" class="stat-card">
            <NStatistic :label="t('dashboard.runs')" :value="stats?.runs ?? 0" />
          </NCard>
        </div>
      </div>

      <div class="current-row">
        <NCard size="small">
          <NStatistic
            :label="t('dashboard.currentGraph')"
            :value="stats?.currentGraphId ? t('dashboard.resultSet', { id: stats.currentGraphId }) : t('dashboard.none')"
          />
          <p v-if="!stats?.currentGraphId" class="hint">{{ t('dashboard.noCurrentGraph') }}</p>
        </NCard>
        <NCard size="small">
          <NStatistic :label="t('dashboard.resultSets')" :value="stats?.resultSetCount ?? 0" />
        </NCard>
        <NCard size="small">
          <NStatistic :label="t('dashboard.quarantine')" :value="stats?.quarantineCount ?? 0" />
          <NTag v-if="stats?.quarantineCount" type="warning" size="small" style="margin-top: 8px">
            {{ t('dashboard.quarantineHint') }}
          </NTag>
        </NCard>
      </div>

      <div class="pipeline">
        <h3>{{ t('dashboard.quickStart') }}</h3>
        <div class="pipeline-grid">
          <RouterLink
            v-for="item in pipeline"
            :key="item.link"
            :to="{ name: item.link }"
            class="pipeline-card"
          >
            <span class="step-label">{{ item.step }}</span>
            <span class="step-count">{{ item.count }}</span>
            <span class="step-link">{{ item.label }}</span>
          </RouterLink>
        </div>
      </div>

      <div class="issues">
        <h3>{{ t('dashboard.issues') }}</h3>
        <NEmpty v-if="!hasIssues" :description="t('dashboard.noIssues')" />
        <div v-else class="issue-list">
          <NAlert
            v-if="stats?.quarantineCount"
            type="warning"
            :title="t('dashboard.quarantineCount', { count: stats.quarantineCount })"
            class="issue-alert"
          >
            {{ t('dashboard.quarantineHint') }}
          </NAlert>
          <NAlert
            v-if="stats?.unpublishedCount"
            type="info"
            :title="t('dashboard.draftResources', { count: stats.unpublishedCount })"
            class="issue-alert"
          >
            {{ t('dashboard.unpublishedHint') }}
          </NAlert>
        </div>
      </div>
    </NSpin>
  </section>
</template>

<style scoped>
.dashboard {
  padding: 0 0 24px;
}
h2,
h3 {
  color: var(--text);
  margin: 0 0 16px;
}
.overview {
  margin-bottom: 24px;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.stat-card {
  text-align: center;
}
.current-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.hint {
  color: var(--text-tertiary);
  font-size: 12px;
  margin: 8px 0 0;
}
.pipeline {
  margin-bottom: 24px;
}
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.pipeline-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-medium);
  text-decoration: none;
  color: var(--text);
  transition: border-color 0.2s;
}
.pipeline-card:hover {
  border-color: var(--pri);
}
.step-label {
  font-size: 12px;
  color: var(--text-tertiary);
}
.step-count {
  font-size: 28px;
  font-weight: 700;
  color: var(--pri);
}
.step-link {
  font-size: 12px;
  color: var(--text-secondary);
}
.issues {
  margin-bottom: 24px;
}
.issue-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.issue-alert {
  margin: 0;
}
</style>
