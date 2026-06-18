import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**'],
  },
  js.configs.recommended,
  // 'essential' focuses on correctness/bug-prevention rules and avoids the
  // strongly-opinionated formatting rules in 'recommended' (low-noise).
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{js,mjs,cjs,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // Allow single-word component names (e.g. Home.vue, Process.vue).
      'vue/multi-word-component-names': 'off',
      // Ignore unused function arguments and caught-error bindings (common,
      // harmless), but still flag genuinely unused variables/imports.
      'no-unused-vars': [
        'error',
        { args: 'none', caughtErrors: 'none', varsIgnorePattern: '^_' },
      ],
    },
  },
]
