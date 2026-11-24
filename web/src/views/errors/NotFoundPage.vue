<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { UiButton } from '@/components/ui'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const statusCode = 404
</script>

<template>
  <main class="error-workspace">
    <section class="error-panel">
      <div class="error-code">
        <strong>{{ statusCode }}</strong
        ><span>{{ t('operationsUi.error404') }}</span>
      </div>
      <div class="error-content">
        <span class="eyebrow">{{ t('operationsUi.recovery') }}</span>
        <h1>{{ t('page.notFound') }}</h1>
        <p>{{ t('page.notFoundHint') }}</p>
        <dl class="error-identity">
          <div>
            <dt>{{ t('operationsUi.path') }}</dt>
            <dd>{{ route.path }}</dd>
          </div>
        </dl>
        <div class="error-actions">
          <UiButton type="primary" @click="router.push({ name: 'dashboard' })">{{
            t('page.backToDashboard')
          }}</UiButton>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped src="./ErrorWorkspace.css"></style>
