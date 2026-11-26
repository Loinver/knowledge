<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { UiButton } from '@/components/ui'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const localeStore = useLocaleStore()
const workflow = [
  { title: 'appUi.model' },
  { title: 'menu.datasources' },
  { title: 'page.graphEvidence' },
] as const
</script>

<template>
  <div class="auth-layout">
    <aside class="auth-brand">
      <div class="brand-head">
        <svg
          class="observatory-mark"
          width="26"
          height="26"
          viewBox="0 0 26 26"
          fill="none"
          aria-hidden="true"
        >
          <path d="M3 3h8v8H3zM15 3h8v8h-8zM3 15h8v8H3zM15 15h8v8h-8z" fill="currentColor" />
        </svg>
        <b>{{ t('app.title') }}</b>
      </div>

      <div class="brand-body">
        <span class="brand-kicker">{{ t('operationsUi.entry') }}</span>
        <p class="brand-tagline">{{ t('layout.authTagline') }}</p>
        <p class="brand-desc">{{ t('app.subtitle') }}</p>
      </div>

      <div class="brand-foot">
        <ol class="brand-workflow">
          <li v-for="(step, index) in workflow" :key="step.title">
            <span class="stage-no mono">{{ String(index + 1).padStart(2, '0') }}</span
            ><span>{{ t(step.title) }}</span
            ><svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" />
            </svg>
          </li>
        </ol>
        <p>{{ t('layout.authFooter') }}</p>
      </div>
    </aside>

    <!-- 右：表单区。工具栏浮在右上角，不占表单的视觉动线 -->
    <main class="auth-main">
      <div class="auth-toolbar">
        <UiButton
          quaternary
          size="small"
          :aria-label="t('layout.switchLocale')"
          @click="localeStore.change(localeStore.current === 'zh-CN' ? 'en-US' : 'zh-CN')"
          >{{ localeStore.label }}</UiButton
        >
        <UiButton
          quaternary
          size="small"
          circle
          :aria-label="ui.isDark ? t('layout.toLight') : t('layout.toDark')"
          @click="ui.toggleTheme()"
        >
          <AppIcon :name="ui.isDark ? 'sun' : 'moon'" :size="16" />
        </UiButton>
      </div>
      <div class="auth-form">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth-layout {
  display: grid;
  grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.6fr);
  min-height: 100dvh;
  background: var(--surface-panel);
  color: var(--text-primary, var(--text));
}
.auth-brand {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 40px clamp(24px, 4vw, 64px);
  background: var(--rail-background);
  color: var(--rail-selected);
}
.brand-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-head b {
  font-size: 14px;
  font-weight: 600;
}
.observatory-mark {
  color: var(--rail-selected);
  flex-shrink: 0;
}
.brand-body {
  margin: auto 0;
  padding: 64px 0;
}
.brand-kicker {
  color: var(--rail-foreground);
  font-size: 12px;
  letter-spacing: 0.06em;
}
.brand-tagline {
  max-width: 360px;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.5;
  margin: 16px 0 0;
}
.brand-desc {
  max-width: 360px;
  margin: 16px 0 32px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--rail-foreground);
}
.brand-workflow {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid color-mix(in srgb, var(--rail-foreground) 25%, transparent);
}
.brand-workflow li {
  display: grid;
  grid-template-columns: 28px 1fr 16px;
  align-items: center;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--rail-foreground) 25%, transparent);
  font-size: 13px;
}
.stage-no {
  font-size: 11px;
  color: var(--rail-foreground);
}
.brand-foot {
  color: var(--rail-foreground);
  font-size: 12px;
  line-height: 1.7;
}
.auth-main {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-width: 0;
  padding: 88px 32px 40px;
}
.auth-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  position: absolute;
  top: 24px;
  right: 24px;
}
.auth-form {
  width: 100%;
  max-width: 400px;
  padding: 0;
  box-sizing: border-box;
  background: var(--surface-panel);
}
.entry-label {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 24px;
}
@media (max-width: 860px) {
  .auth-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .auth-brand {
    padding: 24px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .brand-body,
  .brand-foot {
    display: none;
  }
  .auth-main {
    justify-content: flex-start;
    padding-top: 76px;
  }
  .auth-toolbar {
    top: 16px;
  }
}
@media (max-width: 480px) {
  .auth-brand {
    padding: 20px 16px;
  }
  .auth-main {
    padding: 72px 16px 32px;
  }
  .auth-form {
    padding: 0;
  }
  .auth-toolbar {
    right: 16px;
  }
  .auth-toolbar :deep(.ui-button) {
    min-height: 44px;
    min-width: 44px;
  }
}
</style>
