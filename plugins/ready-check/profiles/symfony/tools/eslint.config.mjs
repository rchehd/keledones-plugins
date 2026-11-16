import js from '@eslint/js';
import globals from 'globals';

export default [
  {
    files: ['**/*.{js,mjs,cjs}'],
    rules: js.configs.recommended.rules,
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {...globals.browser},
    },
  },
  {files: ['**/*.cjs'], languageOptions: {sourceType: 'commonjs', globals: globals.node}},
];
