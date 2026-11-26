import base from '../../../eslint.config.js'

export default [
  ...base,
  {
    files: ['web/prototypes/knowledge-studio/**/*.vue'],
    settings: {
      'vue-i18n': {
        localeDir: './web/prototypes/knowledge-studio/locales/*.json',
        messageSyntaxVersion: '^9.0.0',
      },
    },
  },
]
