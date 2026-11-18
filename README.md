<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Keledones" width="120">
  </picture>
</p>

# Keledones

Plugins for AI coding agents (Claude Code, Codex, Cursor). Each plugin lives in its own folder under `plugins/`; the
root holds one catalog per client.

| Plugin | Folder | Description | Clients |
| --- | --- | --- | --- |
| Ready Check · Review & QA (`ready`) | [plugins/ready-check](plugins/ready-check) | Checks a task before push: requirements, static checks, review, browser QA and a PR draft | Claude Code, Codex, Cursor |
| Keledones themes (`keledones-themes`) | [plugins/keledones-themes](plugins/keledones-themes) | Looks for the Claude app: Keledones and Graphite, switched with `/look` | Claude Code (desktop and mobile app) |
| Gnothi · AI Work Profile (`gnothi`) | [plugins/gnothi](plugins/gnothi) | A private portrait of how you work with AI, from agent sessions and ordinary chats | Claude Code, Codex, Cursor |

## Install

Claude Code:

```sh
claude plugin marketplace add rchehd/keledones-plugins
claude plugin install ready@keledones
claude plugin install keledones-themes@keledones
claude plugin install gnothi@keledones
```

Codex:

```sh
codex plugin marketplace add rchehd/keledones-plugins
codex plugin add ready@keledones
codex plugin add gnothi@keledones
```

Then open `/hooks` in Codex and trust the plugin's three hooks; Codex runs them only after that and may ask
again after each plugin update.

Cursor: **Customize → From GitHub Repository** with `rchehd/keledones-plugins`, or a team admin adds it under
**Dashboard → Plugins & MCPs → Add Marketplace → Import from Repo**.

For local development, pass the path of this checkout to your client.

### Install an individual plugin

Sign in to GitHub with access to the repository and download the ZIP you want from the
[release assets](https://github.com/rchehd/keledones-plugins/releases). The filenames start with `ready-`,
`gnothi-` or `keledones-themes-`. Each ZIP contains one plugin folder.

- **Claude Desktop**. Upload the ZIP from **Customize → Plugins**. Keledones Themes applies the looks in the Claude app.
  [Claude plugin installation](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)
- **Claude Code CLI**. Extract the ZIP and start Claude Code with `claude --plugin-dir /path/to/plugin-folder`.
- **Codex**. Extract Ready Check or Gnothi and add that folder to your personal local marketplace. Select the plugin
  in the Plugins Directory. Trust Ready Check's hooks from `/hooks` after installation.
  [Codex local plugin setup](https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually)
- **Cursor**. Extract the `ready-check` or `gnothi` folder into `~/.cursor/plugins/local/` and reload Cursor.
  You can also load the extracted folder for a CLI session with `agent --plugin-dir /path/to/plugin-folder`.
  [Cursor local plugin setup](https://cursor.com/docs/plugins)

## CI and releases

Pull requests run the catalog checks and the Ready Check and Gnothi test matrices on Linux, macOS and Windows.
Ready Check also runs its package, regression and installation checks in Ubuntu 24.04 on WSL 2.
To run the full suite on `main`, go to **Actions → CI → Run workflow** and select `main`.

To release, push a new marketplace version tag such as `v0.1.0`. The **Plugin release** workflow runs the same
checks against the tagged commit. After they pass, it builds the ZIPs and publishes them together on GitHub Releases.
Each asset uses its plugin's manifest version, independently of the marketplace tag.

To build the ZIPs locally from the current Git commit, run `python3 -B scripts/build-plugin-zips.py "$(mktemp -d)"`.

## Layout

| Path | Purpose |
| --- | --- |
| `.claude-plugin/marketplace.json` | Claude Code catalog |
| `.agents/plugins/marketplace.json` | Codex catalog |
| `.cursor-plugin/marketplace.json` | Cursor catalog |
| `plugins/<name>/` | One plugin with its own manifests, tests and docs |
| `.github/workflows/<name>.yml` | Plugin test matrices for pull requests, releases and manual runs |
| `.github/workflows/catalog.yml` | Catalog checks |
| `.github/workflows/ci.yml` | Full suite for pull requests, manual runs and the release workflow |
| `.github/workflows/release.yml` | Release checks, ZIP build and publication |

## Add a plugin

1. Put the plugin in `plugins/<name>/` with a manifest for each client it supports: `.claude-plugin/plugin.json`,
   `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`.
2. Add one entry to the catalog of each of those clients.
3. If the plugin needs its own CI, add a reusable workflow with `working-directory: plugins/<name>` and call it from `ci.yml`.
4. Run `python3 -B scripts/validate-catalog.py` and `python3 -B -m unittest discover -s tests`.

Users get an update when the plugin raises `version` in its manifests.
