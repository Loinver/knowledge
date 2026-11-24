import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const manifest = root + 'docs/design-system/migration.json'
const previous = existsSync(manifest) ? JSON.parse(readFileSync(manifest, 'utf8')) : null

function files(directory) {
  return readdirSync(root + directory, { withFileTypes: true }).flatMap((entry) => {
    const path = directory + '/' + entry.name
    return entry.isDirectory() ? files(path) : [path]
  })
}

const source = files('web/src').filter((path) => /\.(vue|ts|css|mjs)$/.test(path))
const findings = source.flatMap((path) => {
  const text = readFileSync(root + path, 'utf8')
  const symbols = [
    ...text.matchAll(/import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['"]naive-ui['"]/gs),
  ].flatMap((match) =>
    match[1]
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean),
  )
  const css = [...new Set(text.match(/\.n-[a-z][a-z0-9_-]*/g) ?? [])]
  return symbols.length || css.length
    ? [{ path, symbols, css, test: path.includes('__tests__') }]
    : []
})
const original = previous?.initial ?? findings
const current = new Map(findings.map((finding) => [finding.path, finding]))
const routes = [
  ...readFileSync(root + 'web/src/router/index.ts', 'utf8').matchAll(
    /import\(['"]@\/(views\/[^'"]+)['"]\)/g,
  ),
].map((match) => 'web/src/' + match[1])
const result = {
  specification: '2026-11-23',
  baselineHead: '13b5a3a',
  initial: original,
  files: original.map((finding) => ({
    path: finding.path,
    sourceMigrated: !current.has(finding.path),
    remainingSymbols: current.get(finding.path)?.symbols ?? [],
    remainingCss: current.get(finding.path)?.css ?? [],
  })),
  routePages: [...new Set(routes)],
  remaining: findings,
  note: 'Source inventory is not acceptance evidence. See verification.md for actual checks.',
}
writeFileSync(manifest, JSON.stringify(result, null, 2) + '\n')
console.log(
  `Design system inventory: ${original.length} initial files, ${findings.length} remaining, ${result.routePages.length} route pages`,
)
