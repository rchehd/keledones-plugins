<p align="center">
  <img src="assets/logo.png" alt="Gnothi" width="96">
</p>

# Gnothi

*Gnothi seauton*: know yourself. A plugin for Claude Code, Codex and Cursor that reads your local session history
from all three clients and draws a portrait of how you work with AI agents: what you do well, where you lose time,
and what to try next. It looks at the content of your sessions, not at token spend, and backs every conclusion with
the sessions it came from. Everything stays on your machine.

## What the report shows

1. A radar of your profile axes, this period against the previous one.
2. Strengths and areas to grow, each with evidence sessions and a concrete tip.
3. Work style for fun (opt-in): Architect, Sprinter, Perfectionist, Explorer, Delegator or Detective. It describes
   behaviour in sessions only, not personality.
4. Tasks and themes by project.
5. Activity by weekday and hour.
6. Tools: skills, MCP servers and subagents you actually use.
7. Friction: corrections, repeated requests, interrupted turns, context compactions.
8. Spend: tokens for Claude Code and Codex (Cursor does not record them).
9. Checks after edits, with session counts for the current and previous periods.

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
- The model reads a digest, never the raw history: numbers plus short excerpts (at most 150 characters) with keys,
  tokens, passwords, emails, URLs and your home folder masked.
- The analysis runs on your client's model, the same provider that already sees these sessions; Gnothi adds no new
  recipient. Metrics-only mode sends the model numbers and no session text.
- The skills never publish or send the report. Asked to share, they offer a short summary without excerpts or
  project names.
- "Delete my Gnothi data" removes the whole data folder after confirmation.

## Sources

| Client | History read | Tokens |
| --- | --- | --- |
| Claude Code | `~/.claude/projects/<project>/*.jsonl` | Yes |
| Codex | `~/.codex/sessions/**/*.jsonl` | Yes |
| Cursor | `~/.cursor/projects/<project>/agent-transcripts/<id>/<id>.jsonl` | No; time comes from the request stamps |

`GNOTHI_CLAUDE_DIR`, `GNOTHI_CODEX_DIR` and `GNOTHI_CURSOR_DIR` point Gnothi elsewhere. Parsed sessions are cached,
so later runs read only new or changed files.

## Install

Claude Code:

```sh
claude plugin marketplace add rchehd/keledones
claude plugin install gnothi@keledones
```

Codex:

```sh
codex plugin marketplace add rchehd/keledones
codex plugin add gnothi@keledones
```

Cursor: **Customize → From GitHub Repository** with `rchehd/keledones`.

Gnothi needs Python 3.9 or newer and nothing else.

## Use

Ask "show my agent profile", "how do I work with AI?" or run the skill directly:

| Skill | Claude Code / Cursor / Codex | Purpose |
| --- | --- | --- |
| `portrait` | `/gnothi:portrait` · `/portrait` · `$gnothi:portrait` | Pick a period, build the portrait and the report |
| `setup` | `/gnothi:setup` · `/setup` · `$gnothi:setup` | Describe your work, edit the axes, set options |

Gnothi needs a local Codex chat to read the session logs. To test an updated install, refresh Gnothi from the
local marketplace and open a new local chat. Try the suggested starter prompt, then try a natural request such
as “проаналізуй мої чати з агентами”.

Each run asks for the period: all history, the last year, 6 months or month (the last choice is offered first). The
previous period of the same length is the comparison; for all history the report shows a monthly trend instead.
The report opens from the path the skill prints.

## Development

```sh
python3 -B scripts/validate-package.py
python3 -B -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md).
