import assert from 'node:assert/strict'
import test from 'node:test'
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { changeImpact, linkErrors, routePaths, validateRegistry } from '../check-docs.mjs'

function fixture(extra = {}) {
  const content = {
    'web/src/router/index.ts': "authRoute('login', 'login', x); { path: 'objects/:id' }",
    'web/src/views/objects.vue': '<template />',
    'server/app/api/v1/objects.py': '@router.get(\"/objects\")',
    'docs/user-guide/objects.md': '# 对象\n\n## 如何使用\n',
    ...extra,
  }
  const snapshot = {
    files: Object.keys(content),
    exists: (path) => Object.hasOwn(content, path),
    read: (path) => content[path],
  }
  const feature = {
    id: 'OBJ-001',
    title: '对象',
    routes: ['/', '/login', '/objects/:id'],
    sources: ['web/src/views/objects.vue'],
    tests: [],
    docs: ['docs/user-guide/objects.md'],
    apiModules: ['server/app/api/v1/objects.py'],
  }
  return {
    snapshot,
    registry: { reviewedAt: '2026-11-26', baseline: 'working-tree', features: [feature] },
  }
}

test('新增页面与API模块必须有功能登记', () => {
  const { registry, snapshot } = fixture({ 'server/app/api/v1/new.py': '@router.post("/new")' })
  snapshot.read = ((read) => (path) =>
    path.endsWith('index.ts') ? `${read(path)}; { path: 'new' }` : read(path))(snapshot.read)
  assert.deepEqual(validateRegistry(registry, snapshot), [
    '未登记页面/重定向: /new',
    '未登记API模块: server/app/api/v1/new.py',
  ])
})

test('删除实现或重复编号会拒绝过时台账', () => {
  const { registry, snapshot } = fixture()
  registry.features.push({ ...registry.features[0], sources: ['removed.vue'] })
  const errors = validateRegistry(registry, snapshot)
  assert(errors.some((value) => value.includes('编号无效或重复')))
  assert(errors.some((value) => value.includes('removed.vue')))
})

test('相对链接和中文锚点可核验，缺失文件及锚点被报告', () => {
  const { snapshot } = fixture()
  assert.deepEqual(
    linkErrors('docs/README.md', '[使用](user-guide/objects.md#如何使用)', snapshot),
    [],
  )
  assert.equal(
    linkErrors(
      'docs/README.md',
      '[缺失](user-guide/no.md) [错锚点](user-guide/objects.md#缺失)',
      snapshot,
    ).length,
    2,
  )
})

test('无关Markdown不算受影响功能文档，未映射代码仍需人工核对', () => {
  const { registry } = fixture()
  const result = changeImpact(registry.features, [
    'web/src/views/objects.vue',
    'README.md',
    'server/app/new.py',
  ])
  assert.deepEqual(result.affected[0].touchedDocs, [])
  assert.deepEqual(result.unmapped, ['server/app/new.py'])
})

test('公共认证、动态详情和重定向都计入路由，不重复计算根路径', () => {
  assert.deepEqual(
    [
      ...routePaths(
        "authRoute(\n 'reset-password', x); {path: '/', children:[{path: ''},{path:'objects/:id'},{path:'old',redirect:'/'}]}",
      ),
    ],
    ['/', '/objects/:id', '/old', '/reset-password'],
  )
})

test('支持引用式链接与标题，代码示例不参与链接检查', () => {
  const { snapshot } = fixture()
  const valid =
    '[使用](<user-guide/objects.md> "Title")\n`[示例](missing.md)`\n~~~md\n[示例](missing.md)\n~~~'
  assert.deepEqual(linkErrors('docs/README.md', valid, snapshot), [])
  assert.equal(linkErrors('docs/README.md', '[缺失][ref]\n\n[ref]: missing.md', snapshot).length, 1)
  assert.equal(linkErrors('docs/README.md', '[缺失][ref]', snapshot).length, 1)
})

test('任意命名APIRouter的api_route及HTTP方法都必须登记', () => {
  for (const method of ['api_route', 'head', 'options', 'get', 'websocket']) {
    const { registry, snapshot } = fixture({
      'server/app/api/v1/new.py': `endpoints = APIRouter()\n@endpoints.${method}("/new")`,
    })
    assert(validateRegistry(registry, snapshot).some((value) => value.includes('未登记API模块')))
  }
})

test('真实Git索引与工作区分离：新文件与未暂存修复不会掩盖提交缺口', () => {
  const repo = mkdtempSync(join(tmpdir(), 'knowledge-docs-index-'))
  try {
    const put = (path, content) => {
      mkdirSync(dirname(join(repo, path)), { recursive: true })
      writeFileSync(join(repo, path), content)
    }
    const git = (...args) => execFileSync('git', args, { cwd: repo, stdio: 'pipe' })
    git('init', '-q')
    put('scripts/check-docs.mjs', '')
    copyFileSync(
      new URL('../check-docs.mjs', import.meta.url),
      join(repo, 'scripts/check-docs.mjs'),
    )
    put('web/src/router/index.ts', "{path:'/'}")
    put('web/src/views/new.vue', '<template />')
    put('docs/user-guide/new.md', '# 功能\n')
    put(
      'docs/product/features.json',
      JSON.stringify({
        reviewedAt: '2026-11-26',
        baseline: 'fixture',
        features: [
          {
            id: 'NEW-001',
            title: '新功能',
            routes: ['/'],
            sources: ['web/src/views/new.vue'],
            tests: [],
            docs: ['docs/user-guide/new.md'],
            apiModules: [],
          },
        ],
      }),
    )
    const run = (...args) =>
      spawnSync(process.execPath, ['scripts/check-docs.mjs', ...args], {
        cwd: repo,
        encoding: 'utf8',
      })
    assert.equal(run().status, 0, '工作区必须接受存在的未跟踪实现')
    const workingImpact = run('--impact')
    assert.equal(workingImpact.status, 0, workingImpact.stderr)
    assert.match(workingImpact.stdout, /相关文档已变更/)
    git('add', 'scripts', 'web/src/router', 'docs')
    const missing = run('--staged')
    assert.equal(missing.status, 1)
    assert.match(missing.stderr, /new.vue/)
    git('add', 'web/src/views')
    assert.equal(run('--staged').status, 0)
    put('docs/user-guide/new.md', '[坏链接](missing.md)')
    git('add', 'docs/user-guide/new.md')
    put('docs/user-guide/new.md', '# 未暂存的修复')
    assert.equal(run().status, 0)
    assert.equal(run('--staged').status, 1, '暂存模式必须仍看到坏链接')
  } finally {
    rmSync(repo, { recursive: true, force: true })
  }
})
