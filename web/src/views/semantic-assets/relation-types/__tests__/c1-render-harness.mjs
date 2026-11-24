import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import { build } from 'esbuild'

export const root = fileURLToPath(new URL('../../../../../../', import.meta.url))
const resolvePackage = createRequire(path.join(root, 'web/package.json'))
registerTS(() => resolvePackage('typescript'))

/** Compile actual SFCs and their imported UI controls for SSR, including template-only primitives. */
export async function load(entry, seed = '') {
  const filename = path.join(root, 'web/src', entry)
  const id = randomUUID().replaceAll('-', '')
  const outfile = `/private/tmp/c1_render_${id}.mjs`
  const result = await build({
    stdin: {
      contents: `export { default } from ${JSON.stringify(filename)}; export { default as FormContainer } from '@/components/business/FormContainer.vue'`,
      resolveDir: root,
      loader: 'ts',
    },
    bundle: true,
    format: 'esm',
    platform: 'node',
    write: false,
    loader: { '.css': 'empty' },
    plugins: [
      {
        name: 'c1-real-sfc',
        setup(builder) {
          builder.onResolve({ filter: /^@\// }, ({ path: value, kind, resolveDir }) =>
            builder.resolve(path.join(root, 'web/src', value.slice(2)), { kind, resolveDir }),
          )
          builder.onResolve({ filter: /^[^./]/ }, async ({ path: value, pluginData }) => {
            if (pluginData?.externalize) return undefined
            const resolved = await builder.resolve(value, {
              kind: 'import-statement',
              resolveDir: path.join(root, 'web'),
              pluginData: { externalize: true },
            })
            if (resolved.errors.length) return { errors: resolved.errors }
            return { path: resolved.path, external: true }
          })
          builder.onLoad({ filter: /\.vue$/ }, async ({ path: file }) => {
            let source = await readFile(file, 'utf8')
            if (file === filename && seed)
              source = source.replace('</script>', `${seed}\n</script>`)
            const { descriptor } = parse(source, { filename: file })
            if (!descriptor.script && !descriptor.scriptSetup) {
              const compiled = compileTemplate({
                source: descriptor.template.content,
                filename: file,
                id,
                ssr: true,
              })
              if (compiled.errors.length) throw new Error(compiled.errors.join('\n'))
              return {
                contents: `${compiled.code}\nexport default {ssrRender}`,
                loader: 'ts',
                resolveDir: path.dirname(file),
              }
            }
            return {
              contents: compileScript(descriptor, {
                id,
                inlineTemplate: true,
                templateOptions: { ssr: true },
                fs: { fileExists: existsSync, readFile: (value) => readFileSync(value, 'utf8') },
              }).content,
              loader: 'ts',
              resolveDir: path.dirname(file),
            }
          })
        },
      },
    ],
  })
  await writeFile(outfile, result.outputFiles[0].text)
  try {
    return await import(pathToFileURL(outfile).href)
  } finally {
    await unlink(outfile)
  }
}
