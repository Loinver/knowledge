<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="forbidden">
    <NResult status="403" :title="t('page.forbiddenTitle')" :description="t('page.forbiddenHint')">
      <template #footer>
        <NButton type="primary" @click="router.push({ name: 'dashboard' })">
          {{ t('page.backToDashboard') }}
        </NButton>
      </template>
    </NResult>
  </div>
</template>

<style scoped>
.forbidden {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
