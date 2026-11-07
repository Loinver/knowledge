import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { build } from 'esbuild'

const webRoot = fileURLToPath(new URL('../../../', import.meta.url))
const oldTokens = { access_token: 'old-access', refresh_token: 'old-refresh', expires_in: 3600 }
const newTokens = { access_token: 'new-access', refresh_token: 'new-refresh', expires_in: 3600 }
const oldUser = { id: 'old', username: 'old-admin', role: 'ADMIN' }
const newUser = { id: 'new', username: 'new-viewer', role: 'VIEWER' }
const loginInput = { account: 'new-viewer', password: 'synthetic-password' }

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function success(config, data) {
  return { config, status: 200, headers: {}, data: { code: 'KG.OK', message: 'OK', data } }
}

function failure(config, status = 401) {
  throw {
    config,
    message: 'Synthetic failure',
    response: status
      ? { status, data: { code: 'AUTH.TOKEN_EXPIRED', message: '', params: {}, data: null } }
      : undefined,
  }
}

async function setup(t) {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  }
  const tempRoot = path.join(webRoot, 'node_modules/.tmp')
  await mkdir(tempRoot, { recursive: true })
  const temp = await mkdtemp(path.join(tempRoot, 'auth-'))
  t.after(async () => {
    delete globalThis.localStorage
    await rm(temp, { recursive: true, force: true })
  })
  const outfile = path.join(temp, 'auth.mjs')
  await build({
    stdin: {
      contents: `export * from '@/api/tokens'
        export { http, registerUnauthorizedHandler } from '@/api/client'
        export { useAuthStore } from '@/stores/auth'
        export { pinia } from '@/stores'
        export { router } from '@/router'`,
      resolveDir: webRoot,
      loader: 'ts',
    },
    outfile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    packages: 'external',
    logLevel: 'silent',
    alias: { '@': path.join(webRoot, 'src') },
    plugins: [
      {
        name: 'memory-router-and-empty-views',
        setup(bundler) {
          bundler.onLoad({ filter: /router\/index\.ts$/ }, async ({ path: filename }) => ({
            contents: (await readFile(filename, 'utf8')).replaceAll(
              'createWebHistory',
              'createMemoryHistory',
            ),
            loader: 'ts',
            resolveDir: path.dirname(filename),
          }))
          bundler.onLoad({ filter: /\.vue$/ }, () => ({
            contents: 'export default { render: () => null }',
          }))
        },
      },
    ],
  })
  const mod = await import(pathToFileURL(outfile).href)
  globalThis.window = new EventTarget()
  t.after(() => {
    delete globalThis.window
  })
  const auth = mod.useAuthStore(mod.pinia)
  t.after(() => auth.$dispose())
  mod.storeTokens(oldTokens)
  mod.http.defaults.adapter = async (config) => {
    assert.equal(config.url, '/auth/me')
    return success(config, oldUser)
  }
  await auth.loadMe()
  await mod.router.push('/?source=auth#overview')
  let redirects = 0
  let navigation = Promise.resolve()
  mod.registerUnauthorizedHandler(() => {
    assert.equal(auth.user, null)
    assert.equal(auth.isAdmin, false)
    assert.equal(auth.isAuthenticated, false)
    redirects += 1
    navigation = mod.router.replace({
      name: 'login',
      query: { redirect: mod.router.currentRoute.value.fullPath },
    })
  })
  return {
    ...mod,
    otherTab: () => import(`${pathToFileURL(outfile).href}?other-tab`),
    auth,
    get redirects() {
      return redirects
    },
    navigated: () => navigation,
  }
}

test('loaded identity + business 401 + shared refresh 401 clears identity before one login redirect', async (t) => {
  const ctx = await setup(t)
  const bothRequests = deferred()
  let requests = 0
  let refreshes = 0
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/auth/refresh') {
      refreshes += 1
      await bothRequests.promise
      return failure(config)
    }
    requests += 1
    if (requests === 2) bothRequests.resolve()
    return failure(config)
  }
  const results = await Promise.allSettled([ctx.http.get('/first'), ctx.http.get('/second')])
  assert.ok(results.every((result) => result.status === 'rejected'))
  await ctx.navigated()
  assert.equal(refreshes, 1)
  assert.equal(ctx.redirects, 1)
  assert.equal(ctx.getAccessToken(), null)
  assert.equal(ctx.getRefreshToken(), null)
  assert.equal(ctx.auth.user, null)
  assert.equal(ctx.auth.displayName, '')
  assert.equal(ctx.auth.isAdmin, false)
  assert.equal(ctx.auth.isAuthenticated, false)
  assert.equal(ctx.router.currentRoute.value.name, 'login')
  assert.equal(ctx.router.currentRoute.value.query.redirect, '/?source=auth#overview')
})

test('another tab logout invalidates a pending refresh and clears reactive identity', async (t) => {
  const ctx = await setup(t)
  const other = await ctx.otherTab()
  const started = deferred()
  const release = deferred()
  ctx.http.defaults.adapter = async (config) => {
    if (config.url !== '/auth/refresh') return failure(config)
    started.resolve()
    await release.promise
    return success(config, newTokens)
  }
  const pending = Promise.allSettled([ctx.http.get('/business')])
  await started.promise
  other.clearTokens()
  const event = new Event('storage')
  Object.assign(event, { key: ctx.SESSION_KEY, storageArea: globalThis.localStorage })
  window.dispatchEvent(event)
  assert.equal(ctx.auth.user, null)
  assert.equal(ctx.auth.isAdmin, false)
  release.resolve()
  await pending
  assert.equal(ctx.getAccessToken(), null)
  assert.equal(ctx.auth.isAuthenticated, false)
})

test('late profile save cannot overwrite the user or role of a new session', async (t) => {
  const ctx = await setup(t)
  const oldGeneration = ctx.getSessionGeneration()
  ctx.http.defaults.adapter = async (config) =>
    success(config, config.url === '/auth/login' ? newTokens : newUser)
  await ctx.auth.login(loginInput)
  assert.equal(ctx.auth.setUser(oldUser, oldGeneration), false)
  assert.deepEqual(ctx.auth.user, newUser)
  assert.equal(ctx.auth.isAdmin, false)
  assert.equal(ctx.getAccessToken(), newTokens.access_token)
})

test('concurrent me and business requests share refresh and normal rotation still completes loadMe', async (t) => {
  const ctx = await setup(t)
  ctx.auth.setUser(null, ctx.getSessionGeneration())
  const bothRequests = deferred()
  let expired = 0
  let refreshes = 0
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/auth/refresh') {
      refreshes += 1
      assert.equal(JSON.parse(config.data).refresh_token, oldTokens.refresh_token)
      await bothRequests.promise
      return success(config, newTokens)
    }
    if (config.headers.get('Authorization') === `Bearer ${oldTokens.access_token}`) {
      expired += 1
      if (expired === 2) bothRequests.resolve()
      return failure(config)
    }
    assert.equal(config.headers.get('Authorization'), `Bearer ${newTokens.access_token}`)
    return success(config, config.url === '/auth/me' ? oldUser : { ok: true })
  }
  const [, business] = await Promise.all([ctx.auth.loadMe(), ctx.http.get('/business')])
  assert.deepEqual(business.data, { ok: true })
  assert.equal(refreshes, 1)
  assert.deepEqual(ctx.auth.user, oldUser)
  assert.equal(ctx.auth.isAdmin, true)
  assert.equal(ctx.auth.isAuthenticated, true)
  assert.equal(ctx.getRefreshToken(), newTokens.refresh_token)
  assert.equal(ctx.redirects, 0)
})

for (const status of [503, null]) {
  test(`refresh ${status ?? 'network failure'} preserves loaded user, role and tokens`, async (t) => {
    const ctx = await setup(t)
    ctx.http.defaults.adapter = async (config) =>
      failure(config, config.url === '/auth/refresh' ? status : 401)
    await ctx.auth.loadMe()
    assert.deepEqual(ctx.auth.user, oldUser)
    assert.equal(ctx.auth.isAdmin, true)
    assert.equal(ctx.auth.isAuthenticated, true)
    assert.equal(ctx.getAccessToken(), oldTokens.access_token)
    assert.equal(ctx.getRefreshToken(), oldTokens.refresh_token)
    assert.equal(ctx.redirects, 0)
  })
}

for (const pendingRequest of ['refresh', 'me']) {
  test(`logout clears identity immediately and late ${pendingRequest} cannot restore it`, async (t) => {
    const ctx = await setup(t)
    const started = deferred()
    const release = deferred()
    const logoutRelease = deferred()
    ctx.http.defaults.adapter = async (config) => {
      if (config.url === '/auth/logout') {
        assert.equal(config.headers.get('Authorization'), `Bearer ${oldTokens.access_token}`)
        assert.equal(JSON.parse(config.data).refresh_token, oldTokens.refresh_token)
        await logoutRelease.promise
        return success(config, null)
      }
      if (config.url === '/business') return failure(config)
      assert.equal(config.url, `/auth/${pendingRequest}`)
      started.resolve()
      await release.promise
      return success(config, pendingRequest === 'refresh' ? newTokens : oldUser)
    }
    const pending = Promise.allSettled([
      pendingRequest === 'refresh' ? ctx.http.get('/business') : ctx.auth.loadMe(),
    ])
    await started.promise
    const logout = ctx.auth.logout()
    assert.equal(ctx.getAccessToken(), null)
    assert.equal(ctx.auth.user, null)
    assert.equal(ctx.auth.isAdmin, false)
    release.resolve()
    await pending
    assert.equal(ctx.getAccessToken(), null)
    assert.equal(ctx.getRefreshToken(), null)
    assert.equal(ctx.auth.user, null)
    assert.equal(ctx.auth.isAuthenticated, false)
    logoutRelease.resolve()
    await logout
    assert.equal(ctx.redirects, 0)
  })
}

for (const lateStatus of [200, 401]) {
  test(`new login survives old refresh and me responses with status ${lateStatus}`, async (t) => {
    const ctx = await setup(t)
    const refreshStarted = deferred()
    const meStarted = deferred()
    const release = deferred()
    let loggedIn = false
    let refreshes = 0
    ctx.http.defaults.adapter = async (config) => {
      if (config.url === '/auth/login') {
        loggedIn = true
        return success(config, newTokens)
      }
      if (config.url === '/auth/me' && loggedIn) return success(config, newUser)
      if (config.url === '/business') return failure(config)
      if (config.url === '/auth/refresh') {
        refreshes += 1
        refreshStarted.resolve()
      } else {
        assert.equal(config.url, '/auth/me')
        meStarted.resolve()
      }
      await release.promise
      if (lateStatus === 401) return failure(config)
      return success(config, config.url === '/auth/me' ? oldUser : oldTokens)
    }
    const pending = Promise.allSettled([ctx.auth.loadMe(), ctx.http.get('/business')])
    await Promise.all([refreshStarted.promise, meStarted.promise])
    await ctx.auth.login(loginInput)
    assert.deepEqual(ctx.auth.user, newUser)
    release.resolve()
    await pending
    assert.equal(refreshes, 1)
    assert.equal(ctx.getAccessToken(), newTokens.access_token)
    assert.equal(ctx.getRefreshToken(), newTokens.refresh_token)
    assert.deepEqual(ctx.auth.user, newUser)
    assert.equal(ctx.auth.isAdmin, false)
    assert.equal(ctx.auth.isAuthenticated, true)
    assert.equal(ctx.redirects, 0)
  })
}

test('an old logout response does not clear a subsequent login', async (t) => {
  const ctx = await setup(t)
  const release = deferred()
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/auth/logout') {
      await release.promise
      return failure(config)
    }
    return success(config, config.url === '/auth/login' ? newTokens : newUser)
  }
  const logout = ctx.auth.logout()
  await ctx.auth.login(loginInput)
  release.resolve()
  await logout
  assert.equal(ctx.getAccessToken(), newTokens.access_token)
  assert.deepEqual(ctx.auth.user, newUser)
  assert.equal(ctx.redirects, 0)
})

test('authentication rejected during login user loading clears its loading state', async (t) => {
  const ctx = await setup(t)
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/auth/login') return success(config, newTokens)
    return failure(config)
  }
  await ctx.auth.login(loginInput)
  await ctx.navigated()
  assert.equal(ctx.auth.loading, false)
  assert.equal(ctx.auth.user, null)
  assert.equal(ctx.auth.isAuthenticated, false)
  assert.equal(ctx.redirects, 1)
})

test('a new session refresh is independent and an old refresh completion cannot release its shared flight', async (t) => {
  const ctx = await setup(t)
  const firstStarted = deferred()
  const secondStarted = deferred()
  const firstRelease = deferred()
  const secondRelease = deferred()
  let refreshes = 0
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/auth/login') return success(config, newTokens)
    if (config.url === '/auth/me') return success(config, newUser)
    if (config.url === '/auth/refresh') {
      refreshes += 1
      const isOld = JSON.parse(config.data).refresh_token === oldTokens.refresh_token
      ;(isOld ? firstStarted : secondStarted).resolve()
      await (isOld ? firstRelease : secondRelease).promise
      return success(config, isOld ? oldTokens : newTokens)
    }
    if (!config._retried) return failure(config)
    return success(config, { ok: true })
  }
  const oldRequest = Promise.allSettled([ctx.http.get('/old')])
  await firstStarted.promise
  await ctx.auth.login(loginInput)
  const nextRequest = ctx.http.get('/new')
  await secondStarted.promise
  firstRelease.resolve()
  await oldRequest
  const concurrentRequest = ctx.http.get('/concurrent')
  // Axios 响应拦截器跑完当前 microtask 队列后，两请求应共享仍挂起的刷新。
  await new Promise(setImmediate)
  assert.equal(refreshes, 2)
  secondRelease.resolve()
  await Promise.all([nextRequest, concurrentRequest])
  assert.equal(ctx.getAccessToken(), newTokens.access_token)
  assert.deepEqual(ctx.auth.user, newUser)
  assert.equal(ctx.redirects, 0)
})

test('a token write interleaved with another tab login cannot overwrite the new identity', async (t) => {
  const ctx = await setup(t)
  const other = await ctx.otherTab()
  const generation = ctx.getSessionGeneration()
  const write = localStorage.setItem
  let interleave = true
  localStorage.setItem = (key, value) => {
    if (interleave && key.startsWith('kg-token-pair:')) {
      interleave = false
      other.clearTokens()
      other.storeTokens(newTokens)
    }
    write(key, value)
  }
  assert.equal(ctx.storeTokens(oldTokens, generation), false)
  assert.equal(ctx.getAccessToken(), newTokens.access_token)
})

test('an old credential invalidation never removes a newly logged-in session', async (t) => {
  const ctx = await setup(t)
  const generation = ctx.getSessionGeneration()
  const other = await ctx.otherTab()
  const write = localStorage.setItem
  localStorage.setItem = (key, value) => {
    if (key.startsWith('kg-invalid-access:')) {
      other.clearTokens()
      other.storeTokens(newTokens)
    }
    write(key, value)
  }
  ctx.invalidateTokens(generation, oldTokens.access_token)
  assert.equal(ctx.getAccessToken(), newTokens.access_token)
  assert.equal(ctx.hasSession(), true)
})

test('two tabs coordinate refresh through one shared browser lock', async (t) => {
  const ctx = await setup(t)
  const other = await ctx.otherTab()
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  const queues = new Map()
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      locks: {
        request: (name, action) => {
          const next = (queues.get(name) ?? Promise.resolve()).then(action)
          queues.set(
            name,
            next.catch(() => {}),
          )
          return next
        },
      },
    },
  })
  t.after(() =>
    previous
      ? Object.defineProperty(globalThis, 'navigator', previous)
      : delete globalThis.navigator,
  )
  let refreshes = 0
  const both = deferred()
  let requests = 0
  const adapter = async (config) => {
    if (config.url === '/auth/refresh') {
      refreshes++
      return success(config, newTokens)
    }
    if (!config._retried) {
      if (++requests === 2) both.resolve()
      await both.promise
      return failure(config)
    }
    assert.equal(config.headers.get('Authorization'), `Bearer ${newTokens.access_token}`)
    return success(config, {})
  }
  ctx.http.defaults.adapter = adapter
  other.http.defaults.adapter = adapter
  await Promise.all([ctx.http.get('/business'), other.http.get('/business')])
  assert.equal(refreshes, 1)
  assert.equal(ctx.hasSession(), true)
})

test('an old 401 cannot remove the rejection of a newer token in the same session', async (t) => {
  const ctx = await setup(t)
  const late = deferred()
  const started = deferred()
  ctx.http.defaults.adapter = async (config) => {
    if (config.url === '/old') {
      started.resolve()
      await late.promise
    }
    return failure(config)
  }
  const old = ctx.http.get('/old').catch(() => null)
  await started.promise
  ctx.storeTokens(newTokens)
  await ctx.http.get('/current').catch(() => null)
  assert.equal(ctx.hasSession(), false)
  late.resolve()
  await old
  assert.equal(ctx.hasSession(), false)
  assert.equal(ctx.auth.isAuthenticated, false)
})
