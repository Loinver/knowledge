import { execFileSync } from 'node:child_process'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import prettier from 'prettier'

const args = process.argv.slice(2)
if (args.length > 1 || (args.length === 1 && args[0] !== '--check')) {
  throw new Error('Usage: node scripts/api-schema.mjs [--check]')
}

const root = fileURLToPath(new URL('../', import.meta.url))
const requireFromWeb = createRequire(new URL('../web/package.json', import.meta.url))
const { default: openapiTS, astToString, COMMENT_HEADER } = requireFromWeb('openapi-typescript')
const target = join(root, 'web/src/api/schema.d.ts')
const schema = JSON.parse(
  execFileSync(
    join(root, 'server/.venv/bin/python'),
    ['-c', 'import json; from app.main import app; print(json.dumps(app.openapi()))'],
    {
      cwd: join(root, 'server'),
      encoding: 'utf8',
      // 仅导出模型，不执行 lifespan；即使以后导入时建连，也只能访问内存数据库。
      env: { ...process.env, KG_DATABASE_URL: 'sqlite:///:memory:' },
      maxBuffer: 16 * 1024 * 1024,
      timeout: 30_000,
    },
  ),
)
const generated = await prettier.format(COMMENT_HEADER + astToString(await openapiTS(schema)), {
  ...(await prettier.resolveConfig(target)),
  filepath: target,
})

if (args[0] === '--check') {
  if ((await readFile(target, 'utf8')) !== generated) {
    console.error('OpenAPI types are outdated. Run pnpm -C web gen:api.')
    process.exitCode = 1
  } else {
    console.log('OpenAPI types are up to date.')
  }
} else {
  await writeFile(target, generated)
  console.log('Generated web/src/api/schema.d.ts.')
}
