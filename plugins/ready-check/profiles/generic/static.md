# Generic static checks

Use `generic` for a Git repository in any language, including mixed-language repositories and collections of scripts. The shared Git check detects whitespace errors and conflict markers across the in-scope code and configuration. Files in excluded generated/dependency directories and Markdown, patch and diff files are excluded from that check.

The built-in syntax checks apply to changed Python files, plain JSON and `.sh` or `.bash` files for POSIX `sh` or Bash. Python files are compiled in memory using Ready Check's Python interpreter. Shell files use the interpreter's `-n` mode. Native Windows discovers Bash and sh from Git for Windows. The JSON check skips JSONC and common JSON-with-comments layouts such as VS Code settings and TypeScript, JavaScript and Dev Container configs.

For the check skill, identify additional in-scope lint, type-check, build and test commands from the project's docs and CI. Use the project's existing toolchain and the agreed check scope. Record each command, its working directory, outcome and evidence. Include required project commands in the static gate and mark unavailable prerequisites or results as `INCOMPLETE`. Describe the file types and checks covered by the results.

The `doctor` and `static` CLI commands run the built-in profile checks. The check skill coordinates the project's own commands. `setup --component profile` prepares the profile without downloading tools. Browser setup is available separately for Playwright QA.
