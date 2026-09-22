import './styles/tokens.css'

import { createApp } from 'vue'

import { registerUnauthorizedHandler } from './api/client'
import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import { pinia } from './stores'

// 认证失效后的跳转属于应用级编排：由启动处注册给 http 客户端，
// 客户端自身不依赖路由与页面（见 .agents/conventions/application-architecture.md）。
registerUnauthorizedHandler(() => {
  const { pathname, search, hash } = window.location
  if (pathname === '/login') return
  void router.replace({ name: 'login', query: { redirect: `${pathname}${search}${hash}` } })
})

createApp(App).use(pinia).use(router).use(i18n).mount('#app')
