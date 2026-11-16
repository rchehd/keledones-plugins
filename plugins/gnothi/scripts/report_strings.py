from string import Formatter


ENGLISH = {
    "title": "Gnothi portrait",
    "your_portrait": "Your portrait",
    "header": "{period} ({range}) · Sessions: {count} · {clients} · Generated {date}",
    "no_clients": "No clients",
    "all": "All history",
    "year": "Last year",
    "half": "Last 6 months",
    "month": "Last month",
    "through": "Through {end}",
    "sessions": "Sessions",
    "requests": "Requests",
    "active_days": "Active days",
    "hours_with_agents": "Hours with agents",
    "profile": "Profile",
    "metrics_only": "Metrics-only mode shows the universal axes.",
    "current_period": "This period",
    "previous_period": "Previous period",
    "earlier_portrait": "Earlier portrait",
    "period_legend": "{period} ({range})",
    "no_scores": "{period} · No scores",
    "radar_note": "Select a point on the chart to see the metric and its score.",
    "metric": "Metric:",
    "why_score": "Why {score}",
    "previous_score": "Previous: {score}",
    "previous_count": "Previous: {count}",
    "score_out_of_ten": "{score} / 10",
    "evidence": "Evidence from sessions ({count})",
    "clarity": "Clarity of requests",
    "clarity_meaning": "Fewer corrections and repeated requests raise the score.",
    "focus": "Focus",
    "focus_meaning": "Fewer project switches per active day and fewer abandoned sessions raise the score.",
    "completion": "Task completion",
    "completion_meaning": "More finished sessions and fewer interrupted turns raise the score.",
    "tool_range": "Tool range",
    "tool_range_meaning": "Distinct skills and MCP servers add one point each. Using subagents adds one more.",
    "strengths": "Strengths",
    "growth": "Areas to grow",
    "why": "Why",
    "try": "Try",
    "no_findings": "Nothing with enough evidence in this period.",
    "work_style": "Work style",
    "architect": "Architect",
    "sprinter": "Sprinter",
    "perfectionist": "Perfectionist",
    "explorer": "Explorer",
    "delegator": "Delegator",
    "detective": "Detective",
    "project_themes": "Tasks and themes by project",
    "project": "Project",
    "topics": "Topics",
    "weekday_activity": "Activity by weekday",
    "hour_activity": "Activity by hour",
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
    "monthly_axes": "Universal axes by month",
    "tools": "Tools",
    "skill": "Skill",
    "mcp": "MCP server",
    "subagent": "Subagent",
    "subagent_turns": "Turns that started subagents",
    "action_counts": "Agent actions: {counts}",
    "edit": "Edit",
    "read": "Read",
    "shell": "Terminal",
    "test": "Check",
    "plan": "Plan",
    "other": "Other",
    "kind": "Kind",
    "name": "Name",
    "uses": "Uses",
    "edit_checks": "Checks after edits",
    "edit_checks_note": "Counts sessions with a recorded test, lint, or build call after the last recorded edit call.",
    "period": "Period",
    "sessions_with_edits": "Sessions with edits",
    "sessions_with_check": "Sessions with a later check",
    "share": "Share",
    "friction": "Friction",
    "corrections": "Corrections",
    "repeats": "Repeated requests",
    "interrupted": "Interrupted turns",
    "compactions": "Context compactions",
    "spend": "Spend",
    "client": "Client",
    "tokens": "Tokens",
    "not_recorded": "Not recorded",
    "cursor_tokens": "Cursor not counted.",
    "observations": "Observations",
    "coverage": "Share of work beyond the profile axes: {share}%.",
    "coverage_tip": "Consider asking Gnothi to update your profile.",
    "footer": "Local, confidential report generated on this machine. It works offline. Keep it private."
}


def strings_for(portrait):
    return {**ENGLISH, **(portrait.get("ui") or {})}


def placeholders(value):
    result = set()

    for _, field, spec, conversion in Formatter().parse(value):
        if field is not None:
            if not field.isidentifier() or spec or conversion:
                raise ValueError("use plain named placeholders")

            result.add(field)

    return result


def check_ui(overrides):
    if not isinstance(overrides, dict):
        return ["ui must be an object of translated labels"]

    problems = []

    for key, value in overrides.items():
        if key not in ENGLISH:
            problems.append(f"ui: unknown label {key}")
        elif not isinstance(value, str) or not value.strip() or len(value) > 1024:
            problems.append(f"ui: {key} must be a nonempty string of at most 1024 characters")
        else:
            try:
                if placeholders(value) == placeholders(ENGLISH[key]):
                    continue
            except ValueError:
                pass

            problems.append(f"ui: {key} must keep the placeholders from ui-strings")

    return problems
