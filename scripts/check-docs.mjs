import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, posix, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const registryPath = 'docs/product/features.json'
const maintainedRoots = [
  'docs/product/',
  'docs/user-guide/',
  'docs/operations/',
  'docs/development/',
  'docs/maintenance/',
  '.agents/conventions/',
]
const entryDocs = [
  'README.md',
  'README.en.md',
  'CONTRIBUTING.md',
  'AGENTS.md',
  'samples/README.md',
  'docs/README.md',
  '.agents/README.md',
  '.agents/AGENTS.md',
  '.agents/conventions/documentation.md',
  '.agents/skills/knowledge-code-style/SKILL.md',
  '.github/PULL_REQUEST_TEMPLATE.md',
  'docs/design-system/README.md',
  'docs/design-system/tokens.md',
  'docs/design-system/components.md',
  'docs/design-system/table.md',
  'docs/design-system/controls.md',
  'docs/design-system/dependencies.md',
  'docs/design-system/preview.md',
]

export function routePaths(text) {
  const paths = new Set(['/'])
  for (const match of text.matchAll(/\bpath:\s*['"]([^'"]+)['"]/g)) {
    paths.add(match[1].startsWith('/') ? match[1] : `/${match[1]}`)
  }
  for (const match of text.matchAll(/\bauthRoute\(\s*['"]([^'"]+)['"]/g)) {
    paths.add(`/${match[1]}`)
  }
  return paths
}

export function validateRegistry(registry, snapshot) {
  const errors = []
  const ids = new Set()
  const coveredRoutes = new Set()
  const coveredModules = new Set()
  if (!registry.reviewedAt || !registry.baseline || !Array.isArray(registry.features)) {
    return ['功能登记缺少 reviewedAt / baseline / features']
  }
  for (const feature of registry.features) {
    if (!/^[A-Z]{3}-\d{3}$/.test(feature.id) || ids.has(feature.id)) {
      errors.push(`功能编号无效或重复: ${feature.id}`)
    }
    ids.add(feature.id)
    if (!feature.title) errors.push(`${feature.id}: 缺少名称`)
    for (const field of ['routes', 'sources', 'tests', 'docs', 'apiModules']) {
      if (!Array.isArray(feature[field])) errors.push(`${feature.id}: 缺少数组 ${field}`)
    }
    if (!feature.sources?.length || !feature.docs?.length) {
      errors.push(`${feature.id}: 必须关联实现和文档`)
    }
    for (const field of ['sources', 'tests', 'docs', 'apiModules']) {
      for (const path of feature[field] ?? []) {
        if (path.startsWith('/') || path.includes('..') || !snapshot.exists(path)) {
          errors.push(`${feature.id}: ${field} 路径不存在或越界 ${path}`)
        }
      }
    }
    for (const path of feature.routes ?? []) coveredRoutes.add(path)
    for (const path of feature.apiModules ?? []) coveredModules.add(path)
  }
  const actualRoutes = routePaths(snapshot.read('web/src/router/index.ts'))
  for (const path of actualRoutes) {
    if (!coveredRoutes.has(path)) errors.push(`未登记页面/重定向: ${path}`)
  }
  for (const path of coveredRoutes) {
    if (!actualRoutes.has(path)) errors.push(`登记的页面已不存在: ${path}`)
  }
  for (const path of snapshot.files) {
    if (
      path.startsWith('server/app/api/v1/') &&
      path.endsWith('.py') &&
      hasApiRoutes(snapshot.read(path)) &&
      !coveredModules.has(path)
    ) {
      errors.push(`未登记API模块: ${path}`)
    }
  }
  return errors
}

export function hasApiRoutes(text) {
  const routers = new Set(['router'])
  for (const match of text.matchAll(/\b(\w+)\s*(?::[^=\n]+)?=\s*(?:\w+\.)?APIRouter\s*\(/g)) {
    routers.add(match[1])
  }
  for (const match of text.matchAll(
    /@(\w+)\.(get|post|put|patch|delete|head|options|trace|api_route|websocket)\s*\(/g,
  )) {
    if (routers.has(match[1]) || match[1].endsWith('router')) return true
  }
  return false
}

function markdownWithoutCode(text) {
  let fence = null
  const lines = []
  for (const line of text.split('\n')) {
    const marker = /^ {0,3}(`{3,}|~{3,})/.exec(line)
    if (fence) {
      if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null
      continue
    }
    if (marker) {
      fence = marker[1]
      continue
    }
    lines.push(line)
  }
  return lines
    .join('\n')
    .replace(/(`+)[\s\S]*?\1(?!`)/g, '')
    .replace(/<!--[^]*?-->/g, '')
}

export function linkErrors(path, text, snapshot) {
  const errors = []
  const clean = markdownWithoutCode(text)
  const targets = []
  const definitions = new Map()
  const refKey = (value) => value.trim().replace(/\s+/g, ' ').toLowerCase()
  for (const match of clean.matchAll(/^ {0,3}\[([^\]]+)\]:\s*(<[^>]*>|\S+)/gm)) {
    definitions.set(refKey(match[1]), match[2])
    targets.push(match[2])
  }
  const body = clean.replace(/^ {0,3}\[[^\]]+\]:.*$/gm, '')
  for (const match of body.matchAll(
    /!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+["'][^]*?["'])?\s*\)/g,
  ))
    targets.push(match[1])
  for (const match of body.matchAll(/!?\[([^\]]+)\]\[([^\]]*)\]/g)) {
    if (!definitions.has(refKey(match[2] || match[1])))
      errors.push(`${path}: 引用链接未定义 ${match[2] || match[1]}`)
  }
  for (const rawTarget of new Set(targets)) {
    const target = rawTarget.replace(/^<|>$/g, '')
    if (/^(?:[a-z][\w+.-]*:|\/\/)/i.test(target)) continue
    const [rawPath, anchor] = target.split('#')
    let decoded
    try {
      decoded = decodeURIComponent(rawPath.split('?')[0])
    } catch {
      errors.push(`${path}: 无效链接编码 ${target}`)
      continue
    }
    const destination = decoded
      ? posix.normalize(posix.join(posix.dirname(path), decoded)).replace(/\/$/, '')
      : path
    if (decoded.startsWith('/') || destination.startsWith('../') || !snapshot.exists(destination)) {
      errors.push(`${path}: 目标不存在或非仓库相对路径 ${target}`)
      continue
    }
    if (anchor && destination.endsWith('.md')) {
      const content = markdownWithoutCode(snapshot.read(destination))
      const anchors = new Set()
      const counts = new Map()
      for (const heading of content.matchAll(/^#{1,6}\s+(.+)$/gm)) {
        const slug = heading[1]
          .toLowerCase()
          .replace(/[^\p{L}\p{N}\s_-]/gu, '')
          .replace(/\s/g, '-')
        const count = counts.get(slug) ?? 0
        counts.set(slug, count + 1)
        anchors.add(count ? `${slug}-${count}` : slug)
      }
      for (const id of content.matchAll(/\bid=["']([^"']+)["']/g)) anchors.add(id[1])
      try {
        if (!anchors.has(decodeURIComponent(anchor))) errors.push(`${path}: 锚点不存在 ${target}`)
      } catch {
        errors.push(`${path}: 无效锚点编码 ${target}`)
      }
    }
  }
  return errors
}

export function changeImpact(features, changed) {
  const paths = new Set(changed)
  const matches = (file, source) =>
    file === source || file.startsWith(`${source.replace(/\/$/, '')}/`)
  const affected = features
    .map((feature) => ({
      id: feature.id,
      title: feature.title,
      paths: changed.filter((path) => feature.sources.some((source) => matches(path, source))),
      docs: feature.docs,
      touchedDocs: feature.docs.filter((path) => paths.has(path)),
    }))
    .filter((feature) => feature.paths.length)
  const unmapped = changed.filter(
    (path) =>
      /^(web\/src\/|server\/app\/|server\/migrations\/)/.test(path) &&
      !affected.some((feature) => feature.paths.includes(path)),
  )
  const operational = changed.filter((path) =>
    /^(package\.json|web\/package\.json|server\/pyproject\.toml|Makefile|web\/vite\.config\.ts|\.github\/workflows\/|scripts\/seed_|scripts\/api-schema|playwright\.config)/.test(
      path,
    ),
  )
  return { affected, unmapped, operational }
}

function git(args) {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 })
}

function workingFiles() {
  const files = new Set(
    git(['ls-files', '--cached', '--others', '--exclude-standard', '-z'])
      .split('\0')
      .filter(Boolean),
  )
  const visit = (dir) => {
    if (!existsSync(join(root, dir))) return
    for (const entry of readdirSync(join(root, dir), { withFileTypes: true })) {
      const path = posix.join(dir, entry.name)
      if (entry.isDirectory()) visit(path)
      else files.add(path)
    }
  }
  for (const dir of [...maintainedRoots, 'server/app/api/v1/']) visit(dir)
  for (const path of entryDocs) if (existsSync(join(root, path))) files.add(path)
  return [...files].filter((path) => existsSync(join(root, path)))
}

function main() {
  const args = process.argv.slice(2)
  if (args.some((arg) => !['--staged', '--impact'].includes(arg))) {
    throw new Error('Usage: node scripts/check-docs.mjs [--staged] [--impact]')
  }
  const staged = args.includes('--staged')
  const files = staged ? git(['ls-files', '-z']).split('\0').filter(Boolean) : workingFiles()
  const fileSet = new Set(files)
  const cache = new Map()
  const snapshot = {
    files,
    exists: (path) => fileSet.has(path) || files.some((file) => file.startsWith(`${path}/`)),
    read: (path) => {
      if (!cache.has(path)) {
        cache.set(path, staged ? git(['show', `:${path}`]) : readFileSync(join(root, path), 'utf8'))
      }
      return cache.get(path)
    },
  }
  if (!fileSet.has(registryPath)) throw new Error(`缺少${staged ? '暂存的' : ''} ${registryPath}`)
  const registry = JSON.parse(snapshot.read(registryPath))
  const errors = validateRegistry(registry, snapshot)
  const docs = files.filter(
    (path) =>
      path.endsWith('.md') &&
      (entryDocs.includes(path) || maintainedRoots.some((dir) => path.startsWith(dir))),
  )
  for (const path of docs) errors.push(...linkErrors(path, snapshot.read(path), snapshot))
  if (staged || args.includes('--impact')) {
    const changed = staged
      ? git(['diff', '--cached', '--name-only', '-z', '--diff-filter=ACDMRT'])
          .split('\0')
          .filter(Boolean)
      : [
          ...new Set([
            ...git(['diff', '--name-only', '-z', '--diff-filter=ACDMRT']).split('\0'),
            ...git(['diff', '--cached', '--name-only', '-z', '--diff-filter=ACDMRT']).split('\0'),
            ...git(['ls-files', '--others', '--exclude-standard', '-z']).split('\0'),
          ]),
        ].filter(Boolean)
    const impact = changeImpact(registry.features, changed)
    for (const feature of impact.affected) {
      console.log(
        `${feature.id} ${feature.title}: ${feature.paths.length} 个实现文件；${feature.touchedDocs.length ? '相关文档已变更，需人工核对语义' : 'REVIEW_REQUIRED 请更新相关文档或在PR/交付说明具体无需更新依据'}`,
      )
      if (!feature.touchedDocs.length) console.log(`  对应文档: ${feature.docs.join(', ')}`)
    }
    if (impact.unmapped.length)
      console.log(`REVIEW_REQUIRED 未映射共享/新增实现: ${impact.unmapped.join(', ')}`)
    if (impact.operational.length)
      console.log(`REVIEW_REQUIRED 启动/部署/契约影响: ${impact.operational.join(', ')}`)
    console.log('影响报告只提示需要核对的范围；修改任意Markdown或存在测试不证明语义已同步。')
  }
  if (errors.length) {
    errors.forEach((error) => console.error(`ERROR ${error}`))
    process.exitCode = 1
  } else {
    console.log(
      `文档结构检查通过：${registry.features.length} 项功能，${routePaths(snapshot.read('web/src/router/index.ts')).size} 条页面/重定向，${docs.length} 份维护文档（${staged ? '暂存区' : '工作区'}）。`,
    )
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
