import './studio.css'

import { createApp } from 'vue'
import { createI18n } from 'vue-i18n'

import zhCN from './locales/zh-CN.json'
import App from './Studio.vue'

createApp(App)
  .use(createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zhCN } }))
  .mount('#app')
