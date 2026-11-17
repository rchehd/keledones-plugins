---
name: setup
description: Install, reinstall or diagnose Ready Check tools (Playwright, the browser and framework-profile checkers) and change the install decision or project type, when the automatic first run did not cover it.
---

# Ready Check setup

Respond in the user's language. The command is `/ready:setup` in Claude Code, `/setup` (or the skill picker) in
Cursor and `$setup` in Codex. Normally nobody needs it: on the first session in a project the plugin's session
hook asks once whether to install and confirms the profiles. Use this skill when the user asks to install,
reinstall, repair or diagnose the tools, to change the earlier install decision, or to correct the selections.

## Resolve the application and plugin

Resolve this skill's installed location; the plugin root is two directories above its directory. Read the
packaged [setup guide](../../dependencies/SETUP.md). Resolve the application from the conversation or workspace;
if none is open, ask which local project to prepare. The plugin directory is never the application.

Detect the host Python 3 interpreter: `python3` on Linux/macOS/WSL, `py -3` or `python` on native Windows.
Use the portable entry point `<plugin>/scripts/ready-check.py`; Bash and WSL are not required.

Run `ready-check.py profiles --project <repo>` to get the detected or configured profiles, application roots
relative to the repository, runners and detection evidence. Keep independent matches, including several
profiles in one root. When the result lists conflicts, clarify those selections before persisting or installing.

## Choose the action

- **First install, or changing a declined decision:**
  `ready-check.py consent yes --project <repo> [--selection PROFILE:RUNNER:APPLICATION ...]`.
  Repeat `--selection` for every confirmed entry, using `.` for the repository root. Without selection
  arguments the command uses the same discovery results. The single-profile flags remain available.
  It records the selections and the install decision, installs in the foreground, prints one line per
  component and ends with `Ready Check is ready: …` or `Ready Check setup incomplete: …`.
- **Decline downloads:** use `consent no` with the same project and selections.
- **Reinstall or a single component:** preview with
  `ready-check.py setup --project <app> --profile <id> --component all|browser|profile --dry-run`, show the
  components, runner and data locations, then run the same command without `--dry-run`. Omit `--profile`
  to set up all selections under the given directory. The browser component is shared.
- **Selections only:** `ready-check.py config set profiles '<JSON array>' --project <repo>`. Each entry
  has `profile`, `runner` and `application` keys. This does not change the install decision.

An explicit setup request authorizes these commands under the harness's normal permissions; do not ask for a
second blanket approval. Show the command output in the chat and finish with the installer's final line.

## Run safely

Setup can exceed the default command timeout: run it with the maximum timeout or in the background and wait.
Do not kill or rerun an active setup, and never remove a lock because a run is slow. The installer downloads
pinned dependencies outside the project, checks compatibility and smoke-tests a real browser launch; do not
duplicate that with ad hoc package-manager commands. Application manifests, lock files, source, client settings
and project instruction files stay unchanged.

Read the JSON statuses and exit code: `0` is `PASS` or preview `PLANNED`, `2` is `INCOMPLETE`. A missing or
malformed result is `INCOMPLETE`. On failure read the specific log and report the concrete cause: missing
runtimes or extensions, OS browser libraries, a stopped container. This command does not install OS packages or
start containers. For a managed-storage ownership conflict, keep the existing directory; never forge or remove
ownership markers.

The browser tools serve every client: the plugin ships the `ready-playwright` MCP server and the clients start
it themselves, so no MCP configuration is written. In Codex, hooks need a one-time trust step in `/hooks`; if
the session rule or first-run question never appears there, tell the user to trust the Ready Check hooks.

## Finish

Report the profiles with their application roots and runners, the components, versions and remaining prerequisites. Setup results are
not a task-readiness verdict. If the user also asked to check a task, continue with the packaged
[check skill](../check/SKILL.md) in this chat; otherwise show the `check` command as the next step.

Do not commit, push, publish, install another plugin, or modify global skills.
