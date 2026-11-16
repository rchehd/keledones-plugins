# Keledones

Plugins for AI coding agents (Claude Code, Codex, Cursor). Each plugin lives in its own folder under `plugins/`; the
root holds one catalog per client.

| Plugin | Folder | Description |
| --- | --- | --- |
| Ready Check (`ready`) | [plugins/ready-check](plugins/ready-check) | Checks a task before push: requirements, static checks, review, browser QA and a PR draft |

## Install

Claude Code:

```sh
claude plugin marketplace add rchehd/keledones
claude plugin install ready@keledones
```

Codex:

```sh
codex plugin marketplace add rchehd/keledones
codex plugin add ready@keledones
```

Cursor: **Customize → From GitHub Repository** with `rchehd/keledones`, or a team admin adds it under
**Dashboard → Plugins & MCPs → Add Marketplace → Import from Repo**.

For local development use the path of this checkout instead of `rchehd/keledones`.

## Layout

| Path | Purpose |
| --- | --- |
| `.claude-plugin/marketplace.json` | Claude Code catalog |
| `.agents/plugins/marketplace.json` | Codex catalog |
| `.cursor-plugin/marketplace.json` | Cursor catalog |
| `plugins/<name>/` | One plugin with its own manifests, tests and docs |
| `.github/workflows/<name>.yml` | CI of one plugin, run only when its folder changes |
| `.github/workflows/catalog.yml` | Catalog checks |

## Add a plugin

1. Put the plugin in `plugins/<name>/` with `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and
   `.cursor-plugin/plugin.json`.
2. Add one entry to each of the three catalogs.
3. Add `.github/workflows/<name>.yml` with `paths: ["plugins/<name>/**"]` and `working-directory: plugins/<name>`.
4. Run `python3 -B scripts/validate-catalog.py` and `python3 -B -m unittest discover -s tests`.

Users get an update when the plugin raises `version` in its manifests.
