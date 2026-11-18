# TypeScript static checks

The profile detects `tsconfig.json` and `tsconfig.*.json`. `doctor` reports the resolved project compiler and
ESLint executable, their versions, and the configs selected for the diff. Install the app's dependencies with
its normal package manager. If TypeScript or ESLint is absent, Ready Check can use its pinned TypeScript and
ESLint with the official typescript-eslint recommended rules. Setup puts the bundle outside the repository.

- Type checking uses the TypeScript compiler's solution builder for the selected configs. It honors
  `extends`, compiler options and project references. Build outputs and caches stay in memory. Compiler
  errors across those projects can block the task, including an unchanged consumer affected by a change.
  Changed TypeScript files outside the compiler inputs are reported as incomplete.
- ESLint checks changed TypeScript files and reports diagnostics on changed lines. It uses the closest
  project config, including a shared config above a package root. Without a project config, ESLint 9 uses
  the bundled recommended config. A broken project tool or config is reported and needs investigation.
- The Git diff check reports whitespace errors and conflict markers in the selected application.

Inspect the project's documented lint and type-check commands. Run required framework-specific checks such
as `vue-tsc` with the project's tools and record their results in the task report. Generated inputs required
by a project must be prepared separately. Browser tests apply to user-facing browser flows.

[TypeScript project references](https://www.typescriptlang.org/docs/handbook/project-references.html) ·
[TypeScript Compiler API](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API) ·
[typescript-eslint setup](https://typescript-eslint.io/getting-started/)
