import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createRenderer, h, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

import { compile, settle } from '../../__tests__/view-harness.mjs'

const renderer = createRenderer({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null,
  insert() {},
  remove() {},
  patchProp() {},
})

async function guard(
  t,
  { initiallyOpen = false, initiallyReady, initialValue = { name: '' } } = {},
) {
  const built = await compile('composables/useDraftGuard.ts')
  const open = ref(initiallyOpen)
  const value = ref(initialValue)
  const ready = ref(initiallyReady ?? true)
  const dialogs = []
  const listeners = new Map()
  let accept = false
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      confirm: (message) => {
        dialogs.push(message)
        return accept
      },
      addEventListener: (name, listener) => listeners.set(name, listener),
      removeEventListener: (name, listener) => {
        if (listeners.get(name) === listener) listeners.delete(name)
      },
    },
  })
  let visible
  const page = {
    setup() {
      visible =
        initiallyReady === undefined
          ? built.mod.useDraftGuard(open, () => value.value)
          : built.mod.useDraftGuard(
              open,
              () => value.value,
              () => ready.value,
            )
      return () => null
    },
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: page },
      { path: '/other', component: { render: () => null } },
    ],
  })
  const app = renderer
    .createApp({ render: () => h(RouterView) })
    .use(router)
    .use(
      createI18n({
        legacy: false,
        locale: 'en-US',
        messages: { 'en-US': { ui: { unsaved: 'Discard unsaved changes?' } } },
      }),
    )
  await router.push('/')
  app.mount({})
  await settle()
  t.after(() => {
    app.unmount()
    assert.equal(listeners.size, 0, 'beforeunload listener is released')
    built.cleanup()
    if (previous) Object.defineProperty(globalThis, 'window', previous)
    else delete globalThis.window
  })
  return {
    open,
    value,
    ready,
    visible,
    dialogs,
    listeners,
    router,
    accept: (value) => {
      accept = value
    },
  }
}

test('default draft guard retains input on cancel, discards on confirmation and permits raw save closure', async (t) => {
  const ctx = await guard(t)
  ctx.open.value = true
  await settle()
  ctx.visible.value = false
  assert.equal(ctx.dialogs.length, 0, 'unchanged editor closes directly')
  ctx.open.value = true
  await settle()
  ctx.value.value.name = 'unsaved'
  ctx.visible.value = false
  assert.equal(ctx.open.value, true)
  assert.equal(ctx.value.value.name, 'unsaved')
  assert.deepEqual(ctx.dialogs, ['Discard unsaved changes?'])
  ctx.accept(true)
  ctx.visible.value = false
  assert.equal(ctx.open.value, false)
  ctx.value.value.name = 'new baseline'
  ctx.open.value = true
  await settle()
  ctx.value.value.name = 'saved through API'
  ctx.open.value = false
  assert.equal(ctx.dialogs.length, 2, 'successful writes use the raw ref, never confirmation')
  await ctx.router.push('/other')
  assert.equal(ctx.dialogs.length, 2)
})

test('ready defers the baseline until asynchronous fields settle and read-only views do not prompt', async (t) => {
  const ctx = await guard(t, { initiallyOpen: true, initiallyReady: false })
  ctx.value.value = { name: 'server loaded value' }
  ctx.ready.value = true
  await settle()
  ctx.visible.value = false
  assert.equal(ctx.dialogs.length, 0)
  ctx.open.value = true
  await settle()
  ctx.value.value.name = 'user edit'
  ctx.visible.value = false
  assert.equal(ctx.open.value, true)
  assert.equal(ctx.dialogs.length, 1)
  ctx.ready.value = false
  ctx.value.value.name = 'read-only history'
  ctx.visible.value = false
  assert.equal(ctx.open.value, false)
  assert.equal(ctx.dialogs.length, 1)
})

test('active route and reload guards protect edits and allow confirmed navigation', async (t) => {
  const ctx = await guard(t, { initiallyOpen: true })
  ctx.value.value.name = 'draft'
  let prevented = false
  const event = {
    preventDefault() {
      prevented = true
    },
    returnValue: undefined,
  }
  ctx.listeners.get('beforeunload')(event)
  assert.equal(prevented, true)
  assert.equal(event.returnValue, '')
  await ctx.router.push('/other')
  assert.equal(ctx.router.currentRoute.value.path, '/')
  assert.equal(ctx.value.value.name, 'draft')
  ctx.accept(true)
  await ctx.router.push('/other')
  assert.equal(ctx.router.currentRoute.value.path, '/other')
  assert.equal(ctx.dialogs.length, 2)
})
