<p align="center">
  <img src="assets/logo.png" alt="Gnothi" width="96">
</p>

# Gnothi · AI Work Profile

*Gnothi seauton*: know yourself. Gnothi draws a private portrait of how you work with AI from ordinary ChatGPT
and Claude chats and from local Claude Code, Codex and Cursor sessions. The local report can combine both
sources and open offline. In a browser, Gnothi returns a portrait in the current chat using the history the
client makes available or a selection you provide.

## What the report shows

1. A radar of your profile axes, this period against the previous one.
2. Strengths with supporting sessions, and areas to grow with examples and a concrete next step.
3. Work style for fun (opt-in): Architect, Sprinter, Perfectionist, Explorer, Delegator or Detective. It describes
   behaviour in sessions only, not personality.
4. Tasks and themes by project.
5. Activity by weekday and hour.
6. Tools: skills, MCP servers and subagents you actually use.
7. Friction: corrections, repeated requests, interrupted turns, context compactions.
8. Spend: tokens for Claude Code and Codex (Cursor does not record them).
9. Checks after edits, with session counts for the current and previous periods.
10. How you work with agents, with common paths and observed criteria for review and bug-fix sessions.

Personal axes and findings with evidence expand to the sessions behind them. Clicking a radar point opens its axis.
The chart legend shows the calendar ranges it compares. Gnothi writes the report labels and analysis in the
chat language, with English fallback labels.

## Profile and axes

On first use Gnothi asks what you do and what you use AI for, or detects it from your sessions, and proposes 4–6
personal axes for that work. Templates for developers, designers, product managers and QA engineers are starting
points, not a fixed list of roles. You edit the axes before they are saved. Four universal axes are computed the
same way for everyone: clarity of requests, focus, task completion and tool range.

Changing the axes starts a new epoch: earlier portraits stay, and only portraits of the same epoch compare. The
universal axes compare across epochs. When most of your work no longer fits your axes, the report suggests
updating the profile; it never changes it on its own.

## Checks after edits

The goal is to understand verification habits in recorded agent sessions. The question is how often a session
with an edit call contains a test, lint, or build call after its last edit call. The report shows the matching
session count, the total with edit calls, and their ratio. The ratio is unavailable when there are zero sessions
with edit calls. The measure uses recognized tool calls in log order and covers check attempts.

## Workflow analysis

The workflow card groups recognizable review and bug-fix sessions. It shows who acted at each step and which
criteria the available logs support. The most frequent path appears first, with other paths, criteria and session
examples available on expansion. Detailed statistics have a separate expandable section.
Use [workflow analysis](skills/portrait/references/workflow-analysis.md) to
interpret the findings. For a project-level overview of review rounds, QA gaps and returned tasks, use
[Ready Check reflect](https://github.com/rchehd/keledones-plugins/tree/main/plugins/ready-check#customize-and-improve).

## Foundations

| Stage | Built on |
| --- | --- |
| Defining a metric | [Goal/Question/Metric](https://drum.lib.umd.edu/items/8119803a-362b-42ec-b6ce-2311713e7236). For verification habits, the question is whether a check followed the last edit. The measure is the share of sessions with edits that meet this condition. |
| Reading workflow events | Ordered event logs from the [Process Mining Manifesto](https://www.vdaalst.com/publications/p658.pdf). Each agent session is a case. Gnothi uses the order of edit and check calls to measure verification attempts. |
| Interpreting the portrait | Gnothi uses several dimensions and compares periods for the same person. [The SPACE of AI](https://www.microsoft.com/en-us/research/publication/the-space-of-ai-real-world-lessons-on-ais-impact-on-developers/) gives research context for multidimensional analysis of AI-assisted work. |
| Describing work styles | The optional archetypes use Gnothi's fixed, descriptive rules. [Anthropic Economic Index](https://www.anthropic.com/research/anthropic-economic-index-september-2025-report#chapter-1) is related research on how people interact with AI across sessions. |

## Privacy

- Scripts make no network requests, and the report page loads nothing from the network (Chart.js is bundled and a
  Content-Security-Policy blocks external requests).
- The profile, cache, history and reports live only in the Gnothi data folder, readable by you alone:
  `~/.local/share/gnothi` on Linux, `~/Library/Application Support/Gnothi` on macOS, `%LOCALAPPDATA%\Gnothi` on
  Windows (`GNOTHI_DATA_DIR` overrides it). Gnothi refuses to write inside any Git work tree.
- For a local collection, the script reads history and the model receives a digest with numbers and short
  excerpts (at most 150 characters). Keys, tokens, passwords, emails, URLs and your home folder are masked.
  Metrics-only mode gives the model numbers. Keep an export local to use this mode without giving it to the model.
- In a browser, native retrieval and supplied conversation files are read by the current client.
- The skills never publish or send the report. Asked to share, they offer a short summary without excerpts or
  project names.
- "Delete my Gnothi data" removes the whole data folder after confirmation.

## Sources

| Client | History read | Tokens |
| --- | --- | --- |
| Claude Code | `~/.claude/projects/<project>/*.jsonl` | Yes |
| Codex | `~/.codex/sessions/**/*.jsonl` | Yes |
| Cursor | `~/.cursor/projects/<project>/agent-transcripts/<id>/<id>.jsonl` | No; time comes from the request stamps |
| ChatGPT | Available past-chat tool or supplied conversation JSON/ZIP | No |
| Claude.ai | Available past-chat tool or supplied conversation JSON/ZIP | No |

`GNOTHI_CLAUDE_DIR`, `GNOTHI_CODEX_DIR` and `GNOTHI_CURSOR_DIR` point Gnothi elsewhere. Parsed sessions are cached,
so later runs read only new or changed files.

Ordinary chats contribute dated user requests. The report counts chats by source and labels retrieved samples.
Agent logs supply tool, task completion, verification, focus, work-style and elapsed-time metrics.

## Install

Claude Code:

```sh
claude plugin marketplace add rchehd/keledones-plugins
claude plugin install gnothi@keledones
```

Codex:

```sh
codex plugin marketplace add rchehd/keledones-plugins
codex plugin add gnothi@keledones
```

Cursor: **Customize → From GitHub Repository** with `rchehd/keledones-plugins`.

To install Gnothi on its own, follow the
[individual plugin instructions](https://github.com/rchehd/keledones-plugins#install-an-individual-plugin).

The local report needs Python 3.9 or newer.

## Use

Ask "show my agent profile", "how do I work with AI?" or run the skill directly:

| Skill | Claude Code / Cursor / Codex | Purpose |
| --- | --- | --- |
| `portrait` | `/gnothi:portrait` · `/portrait` · `$gnothi:portrait` | Pick a period, build the portrait and the report |
| `setup` | `/gnothi:setup` · `/setup` · `$gnothi:setup` | Describe your work, edit the axes, set options |

In the browser, ask to use your ordinary chats. Gnothi uses past-chat retrieval when the client exposes it.
If the client cannot retrieve past chats, supply conversation JSON or selected chats. Account memory can
provide context, while the portrait uses actual conversation evidence.

On your computer, give the portrait skill the local path to a
[ChatGPT export](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data) or a
[Claude export](https://support.claude.com/en/articles/9450526-how-can-i-export-my-claude-data). From the
plugin directory, you can also collect the combined digest directly:

```sh
python3 scripts/gnothi.py collect --period month --chat-export "/path/to/chatgpt.zip" --chat-export "/path/to/claude.json"
```

The importer reads only `conversations.json` or numbered conversation JSON entries from a ZIP. The export
remains at its original path. Each run discovers local agent logs and uses the export paths supplied for that run.

Each run asks for the period: all history, the last year, 6 months or month (the last choice is offered first). The
previous period of the same length is the comparison; for all history the report shows a monthly trend instead.
The report opens from the path the skill prints.

### Windows storage access

From the plugin directory, run `py -3 scripts/gnothi.py storage-check` to test the private data folder. An access
error includes the affected path. If the check succeeds in PowerShell but fails inside the client, use the client's
filesystem approval for the Gnothi folder. You can set `GNOTHI_DATA_DIR` to a private writable folder outside Git
work trees and the plugin package. For a portrait in chat without saving files, use `collect --no-save`.

## Development

```sh
python3 -B scripts/validate-package.py
python3 -B -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md).
