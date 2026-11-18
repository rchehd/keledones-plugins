import tseslint from 'typescript-eslint';

export default tseslint.config({
  files: ['**/*.{ts,tsx,mts,cts}'],
  extends: tseslint.configs.recommended,
});
