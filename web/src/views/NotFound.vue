<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="not-found">
    <NResult status="404" :title="t('page.notFound')" :description="t('page.notFoundHint')">
      <template #footer>
        <NButton type="primary" @click="router.push({ name: 'dashboard' })">
          {{ t('page.backToDashboard') }}
        </NButton>
      </template>
    </NResult>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
