import js from '@eslint/js';
import globals from 'globals';

export default [
  {
    files: ['**/*.{js,mjs,cjs}'],
    rules: js.configs.recommended.rules,
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'script',
      globals: {
        ...globals.browser,
        Drupal: 'readonly',
        drupalSettings: 'readonly',
        jQuery: 'readonly',
        once: 'readonly',
      },
    },
  },
  {files: ['**/*.mjs'], languageOptions: {sourceType: 'module'}},
  {files: ['**/*.cjs'], languageOptions: {sourceType: 'commonjs', globals: globals.node}},
];
