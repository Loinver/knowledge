import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import vueI18n from '@intlify/eslint-plugin-vue-i18n'
import pluginVue from 'eslint-plugin-vue'
import simpleImportSort from 'eslint-plugin-simple-import-sort'
import globals from 'globals'
import tseslint from 'typescript-eslint'

// ESLint 9 flat config：统一从仓库根运行（eslint web / lint-staged 均如此）
export default tseslint.config(
  {
    ignores: ['**/dist/**', 'node_modules/**', '**/*.d.ts', 'web/vite.config.ts', 'demo/**'],
  },
  {
    files: ['web/**/*.{js,mjs,ts,tsx,vue}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      ...pluginVue.configs['flat/recommended'],
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { parser: tseslint.parser },
    },
    plugins: { 'simple-import-sort': simpleImportSort },
    rules: {
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'smart'],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'object-shorthand': ['error', 'always'],
      'prefer-template': 'error',
      'simple-import-sort/imports': 'error',
      'simple-import-sort/exports': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
      'vue/attributes-order': 'warn',
      'vue/no-v-html': 'error',
      'vue/require-default-prop': 'off',
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    files: ['web/**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
    extends: [...vueI18n.configs['flat/recommended']],
    settings: {
      'vue-i18n': {
        localeDir: './web/src/locales/*.{json,json5,yaml,yml}',
        messageSyntaxVersion: '^9.0.0',
      },
    },
    rules: {
      // 文案必须走 vue-i18n：禁止在模板里写裸文本
      '@intlify/vue-i18n/no-raw-text': [
        'error',
        { ignoreText: ['&nbsp;', '-', '·', ':', '|', '/'] },
      ],
    },
  },
  prettier,
)
