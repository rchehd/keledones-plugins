# How the user works with agents

Compare the observed order of user decisions, agent replies, and tool calls with the criteria below.
Measurements describe the recorded interaction at the stated source coverage. The same transcript
can contain a clear request, an agent mistake, and a successful recovery.

| Criterion ID | When it applies | What the script can observe |
| --- | --- | --- |
| `review_scope` | A request for code review | An explicit scope at the start, or a later correction that makes the intended scope visible |
| `review_evidence` | A review has a visible finding | A file and line reference in a visible finding excerpt, which supports checking the claim in context |
| `review_permission` | The agent starts edits during a review | A prior explicit authorization, or a prior explicit review-only instruction that the edit conflicts with |
| `fix_expected` | A bug-fix request | Explicit expected behavior in the user's words before the first recorded edit |
| `fix_cause` | A bug-fix session with a visible explanation | A likely cause with a code reference before editing, after a recorded inspection or check |
| `fix_recheck` | A bug-fix session with a check before editing | The same recognized check command after the final edit, or a completed trace with an edit and no later recognized check |

Use the `workflow` digest section for counts and common paths. A path frequency is the number of sessions
with that recorded sequence. The script marks ambiguous or mixed work separately. Mark unsupported
criteria as insufficient evidence. A tool call establishes an attempt. A reference or a repeated
command is a signal whose interpretation depends on the visible evidence.

In strengths and growth, set `criterion` when an item interprets one of these checks. Use evidence IDs
with the matching status, or explain aggregate figures in metrics-only mode. Attribute each observation
to the user, the agent, or their interaction. For example, an edit against a review-only request is
evidence about agent behavior. An explicit correction may show how the user recovered control.

For ordinary chat imports containing dated user requests, describe the request and follow-up patterns
that are visible. Keep incomplete agent-side criteria unknown. For a chat-only portrait use the same
criteria where the available messages support them and label the scope of the sample.

Methodology follows the [Process Mining Manifesto](https://vdaalst.com/publications/p658.pdf) and
[Goal, Question, Metric](https://drum.lib.umd.edu/items/8119803a-362b-42ec-b6ce-2311713e7236).
