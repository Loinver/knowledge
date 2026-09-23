<script setup lang="ts">
import { NButton } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import StarMark from '@/components/StarMark.vue'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const localeStore = useLocaleStore()
</script>

<template>
  <div class="auth-layout">
    <!-- 左：品牌星图。这一栏是产品气质的第一印象，不做成空白或纯色块 -->
    <aside class="auth-brand" aria-hidden="true">
      <div class="brand-head">
        <StarMark :size="26" />
        <b>{{ t('app.title') }}</b>
      </div>

      <div class="brand-body">
        <svg class="brand-chart" viewBox="0 0 420 220" fill="none">
          <path d="M210 108C250 86 276 74 306 70" stroke="var(--g-relation)" stroke-width="1.6" />
          <path
            d="M210 108C176 128 150 140 122 144"
            stroke="var(--g-relation)"
            stroke-width="1.6"
          />
          <path
            d="M210 108C232 136 244 152 258 172"
            stroke="var(--g-derived)"
            stroke-width="1.6"
            stroke-dasharray="6 5"
          />
          <path
            d="M306 70C336 82 352 100 356 126"
            stroke="var(--g-derived)"
            stroke-width="1.6"
            stroke-dasharray="6 5"
          />
          <circle cx="210" cy="108" r="22" stroke="var(--accent-soft)" stroke-width="1" />
          <circle cx="210" cy="108" r="13" fill="var(--accent-soft)" />
          <circle cx="210" cy="108" r="7" fill="var(--g-entity)" />
          <circle cx="306" cy="70" r="5" fill="var(--g-relation)" />
          <circle cx="122" cy="144" r="5" fill="var(--g-evidence)" />
          <circle cx="258" cy="172" r="4.5" fill="var(--g-derived)" />
          <circle cx="356" cy="126" r="4.5" fill="var(--g-current)" />
          <circle cx="68" cy="62" r="3" fill="var(--border-strong)" />
          <circle cx="370" cy="40" r="3" fill="var(--border-strong)" />
          <circle cx="60" cy="186" r="3" fill="var(--border-subtle)" />
          <circle cx="150" cy="34" r="2.5" fill="var(--border-subtle)" />
          <circle cx="392" cy="176" r="2.5" fill="var(--border-subtle)" />
        </svg>

        <p class="brand-tagline">{{ t('layout.authTagline') }}</p>
        <p class="brand-desc">{{ t('app.subtitle') }}</p>
      </div>

      <div class="brand-foot">{{ t('layout.authFooter') }}</div>
    </aside>

    <!-- 右：表单区。工具栏浮在右上角，不占表单的视觉动线 -->
    <main class="auth-main">
      <div class="auth-toolbar">
        <NButton
          quaternary
          size="small"
          :aria-label="t('layout.switchLocale')"
          @click="localeStore.change(localeStore.current === 'zh-CN' ? 'en-US' : 'zh-CN')"
          >{{ localeStore.label }}</NButton
        >
        <NButton
          quaternary
          size="small"
          circle
          :aria-label="ui.isDark ? t('layout.toLight') : t('layout.toDark')"
          @click="ui.toggleTheme()"
        >
          <AppIcon :name="ui.isDark ? 'sun' : 'moon'" :size="16" />
        </NButton>
      </div>
      <div class="auth-form">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth-layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-base);
}

/* ── 品牌栏 ─────────────────────────────────────────────── */
.auth-brand {
  display: flex;
  flex: 0 0 46%;
  flex-direction: column;
  padding: 44px 40px;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 20% 15%, rgba(47, 111, 228, 0.14), transparent 62%),
    radial-gradient(90% 70% at 85% 80%, rgba(124, 58, 237, 0.12), transparent 58%), var(--bg-inset);
}

/* 星图底色需要网格来暗示「坐标系」，这是设计语言的一部分 */
[data-theme='dark'] .auth-brand {
  background-image:
    radial-gradient(120% 90% at 20% 15%, rgba(79, 141, 247, 0.2), transparent 62%),
    radial-gradient(90% 70% at 85% 80%, rgba(139, 92, 246, 0.18), transparent 58%),
    linear-gradient(var(--border-subtle) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px);
  background-size:
    auto,
    auto,
    24px 24px,
    24px 24px;
}

.brand-head {
  display: flex;
  gap: 10px;
  align-items: center;
}

.brand-head b {
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.3px;
}

.brand-body {
  margin-top: auto;
}

.brand-chart {
  width: 100%;
  max-width: 400px;
  margin-bottom: 26px;
}

.brand-tagline {
  max-width: 340px;
  margin: 0;
  font-size: 22px;
  font-weight: 500;
  line-height: 1.45;
  letter-spacing: 0.2px;
}

.brand-desc {
  max-width: 330px;
  margin: 12px 0 0;
  color: var(--text-secondary);
  font-size: var(--font-small);
  line-height: 1.8;
}

.brand-foot {
  margin-top: 32px;
  color: var(--text-disabled);
  font-size: 11px;
}

/* ── 表单区 ─────────────────────────────────────────────── */
.auth-main {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

.auth-toolbar {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  display: flex;
  gap: var(--space-2);
}

.auth-form {
  width: 100%;
  max-width: 340px;
}

/* 窄屏收起品牌栏，表单占满 —— 认证页在手机上也要能用 */
@media (max-width: 860px) {
  .auth-brand {
    display: none;
  }
}
</style>
