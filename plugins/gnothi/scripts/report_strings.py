from string import Formatter


ENGLISH = {
    "title": "Gnothi portrait",
    "your_portrait": "Your portrait",
    "header": "{period} ({range}) · Sessions: {count} · {clients} · Generated {date}",
    "brand_description": "A portrait of your work with AI",
    "generated_offline": "Generated {date} · Offline",
    "report_sections": "Report sections",
    "nav_summary": "Highlights",
    "nav_workflow": "Workflow",
    "nav_stats": "Statistics",
    "summary_title": "At a glance",
    "finding_strength": "Strength",
    "finding_growth": "Area to grow",
    "finding_details": "View finding",
    "all_styles": "All styles",
    "findings_title": "Strengths and areas to grow",
    "back_to_top": "Back to top",
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
    "project_count": "Projects: {count}",
    "requests_per_session": "{count} per session on average",
    "minutes_per_session": "{count} min per agent session on average",
    "profile": "Profile",
    "profile_scale": "Scores on a scale of 0 to 10.",
    "profile_comparison": "The bar shows this period. The marker shows the previous period.",
    "personal_axes": "Personal axes",
    "universal_axes": "Universal axes",
    "score_up": "Improved",
    "score_down": "Declined",
    "score_unchanged": "Unchanged",
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
    "try": "Next step",
    "no_findings": "Nothing with enough evidence in this period.",
    "work_style": "Work style",
    "leading_style": "Closest style",
    "architect": "Architect",
    "sprinter": "Sprinter",
    "perfectionist": "Perfectionist",
    "explorer": "Explorer",
    "delegator": "Delegator",
    "detective": "Detective",
    "project_themes": "Tasks and themes by project",
    "project_list": "Projects: {projects}",
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
    "workflow_title": "How you work with agents",
    "workflow_note": "Counts describe recorded interactions. Review references and repeated checks are observable signals.",
    "workflow_coverage": "Mixed sessions: {mixed}. Unclassified sessions: {unclassified}.",
    "workflow_sessions": "{count} sessions",
    "workflow_path_count": "({count} sessions)",
    "workflow_primary": "Most common sequence",
    "workflow_details": "View criteria and scenarios",
    "workflow_criteria": "Criteria",
    "workflow_paths": "Recorded scenarios",
    "workflow_more_steps": "More steps in scenarios",
    "detailed_statistics": "Detailed statistics",
    "workflow_review": "Code review",
    "workflow_bug_fix": "Bug fixes",
    "workflow_user": "You",
    "workflow_agent": "Agent",
    "workflow_criterion": "Criterion",
    "workflow_observed": "Observed",
    "workflow_gap": "Recorded gap",
    "workflow_unknown": "Insufficient evidence",
    "workflow_not_applicable": "Not applicable",
    "workflow_step_review_request": "Request review",
    "workflow_step_fix_request": "Request fix",
    "workflow_step_scope": "Set scope",
    "workflow_step_redirect": "Restate scope",
    "workflow_step_approve": "Authorize edits",
    "workflow_step_findings": "Present findings",
    "workflow_step_read": "Inspect",
    "workflow_step_cause": "Record a likely cause",
    "workflow_step_edit": "Edit",
    "workflow_step_check": "Run a check",
    "review_scope": "Review boundaries set up front",
    "review_evidence": "Finding with a file and line reference",
    "review_permission": "Edit attempt follows explicit authorization",
    "fix_expected": "Expected behavior stated before editing",
    "fix_cause": "Likely cause with a code reference before editing",
    "fix_recheck": "Same check run before and after the final edit",
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
    "chat_input": "Chat history source",
    "chat_skipped": "Unreadable conversations in input",
    "chat_export": "Export",
    "chat_sample": "Retrieved sample",
    "chat_limits": "Chat messages contribute to request and activity metrics. Agent logs supply focus, task completion, tool range, verification and work-style metrics.",
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
