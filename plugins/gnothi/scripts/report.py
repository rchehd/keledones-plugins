from __future__ import annotations

import html
import json
import re
from datetime import date, timedelta
from pathlib import Path

import profiles
import storage
from report_strings import check_ui, strings_for
from sessions import CHAT_CLIENTS
from signals import ARCHETYPES, AXES
from workflows import STATUSES, STEP_ACTORS

PACKAGE = Path(__file__).resolve().parent.parent
CLIENTS = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor", **CHAT_CLIENTS}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:"


def text(value):
    return str(value or "").strip()


def is_score(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 10


def check_evidence(where, ids, known, problems):
    if not isinstance(ids, list):
        problems.append(f"{where}: evidence must be a list of session ids")
        return []

    if not all(isinstance(ident, str) for ident in ids):
        problems.append(f"{where}: evidence ids must be strings")
        return [ident for ident in ids if isinstance(ident, str)]

    for ident in ids:
        if ident not in known:
            problems.append(f"{where}: unknown evidence session {ident}")

    return ids


def check_list(name, items, keys, problems):
    if not isinstance(items, list):
        problems.append(f"{name} must be a list")
        return

    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or any(not isinstance(item.get(key), kind) for key, kind in keys.items()):
            problems.append(f"{name} {index}: must be an object with {', '.join(keys)}")
        elif any(not isinstance(topic, str) for topic in item.get("topics", [])):
            problems.append(f"{name} {index}: topics must be strings")


def check_findings(name, items, known, metrics_only, workflow_counts, problems):
    if not isinstance(items, list) or len(items) > 5:
        problems.append(f"{name}: give at most 5 items")
        return

    required = ("title", "detail", "tip") if name == "growth" else ("title", "detail")
    for index, item in enumerate(items, 1):
        where = f"{name} {index}"

        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue

        for key in required:
            if not text(item.get(key)):
                problems.append(f"{where}: needs {key}")

        ids = set(check_evidence(where, item.get("evidence", []), known, problems))
        cause = text(item.get("cause"))

        if metrics_only:
            if not cause:
                problems.append(f"{where}: in metrics-only mode a finding needs a cause from the numbers")
        elif len(ids) < 2 and not (cause and ids):
            problems.append(f"{where}: needs at least two evidence sessions, or a cause and one session")

        criterion = item.get("criterion")
        if criterion is not None:
            status = "observed" if name == "strengths" else "gap"
            if not isinstance(criterion, str) or not workflow_counts.get(criterion, {}).get(status):
                problems.append(f"{where}: criterion needs matching workflow counts")
            elif not metrics_only and any(known.get(ident, {}).get("workflow", {}).get("criteria", {})
                                          .get(criterion) != status for ident in ids):
                problems.append(f"{where}: evidence does not support workflow criterion {criterion}")


def validate(portrait, digest, profile):
    problems = []

    if not isinstance(portrait, dict) or portrait.get("schema_version") != 1:
        return ["portrait.json must be an object with schema_version 1"]

    language = portrait.get("language", "en")
    if not isinstance(language, str) or not re.fullmatch(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*", language):
        problems.append("language must be a language tag such as en or uk")

    if "ui" in portrait:
        problems.extend(check_ui(portrait["ui"]))

    known = {item["id"]: item for item in digest.get("evidence", [])}
    metrics_only = digest.get("metrics_only")
    includes_chats = any(source["client"] in CHAT_CLIENTS and source["sessions"] for source in digest.get("sources", []))
    epoch = profiles.current_epoch(profile)
    axes = portrait.get("axes")

    if not isinstance(axes, list):
        problems.append("axes must be a list")
        axes = []

    if metrics_only:
        if axes:
            problems.append("axes: metrics-only mode scores no personal axes; leave axes empty")
    elif not epoch:
        problems.append("No profile axes yet: run the setup skill first")
    else:
        expected = [axis["id"] for axis in epoch["axes"]]
        given = [item.get("id") for item in axes if isinstance(item, dict)]

        for ident in given:
            if ident not in expected:
                problems.append(f"axes: {ident} is not an axis of the current profile")

        for ident in expected:
            if given.count(ident) != 1:
                problems.append(f"axes: score {ident} exactly once")

        for item in axes:
            if isinstance(item, dict):
                unavailable = includes_chats and "score" in item and item["score"] is None
                if not unavailable and not is_score(item.get("score")):
                    problems.append(f"axes: {item.get('id')} needs a score from 0 to 10")

                if not text(item.get("reason")):
                    problems.append(f"axes: {item.get('id')} needs a reason")

                for field in ("name", "measures"):
                    if field in item and (not isinstance(item[field], str) or not item[field].strip()):
                        problems.append(f"axes: {item.get('id')} has an invalid localized {field}")

                check_evidence(f"axes: {item.get('id')}", item.get("evidence", []), known, problems)

    workflow_counts = {ident: counts for group in digest.get("workflow", {}).get("groups", [])
                       for ident, counts in group["criteria"].items()}
    check_findings("strengths", portrait.get("strengths", []), known, metrics_only, workflow_counts, problems)
    check_findings("growth", portrait.get("growth", []), known, metrics_only, workflow_counts, problems)
    archetype = portrait.get("archetype")

    if archetype is not None:
        if not digest["current"].get("archetypes"):
            problems.append("archetype: work-style archetypes are off; set archetype to null")
        elif not isinstance(archetype, dict) or archetype.get("lead") not in ARCHETYPES or \
                archetype.get("second") not in (None, *ARCHETYPES) or not text(archetype.get("text")):
            problems.append(f"archetype: lead and second must be among {', '.join(ARCHETYPES)}, with text")

    coverage = portrait.get("coverage")

    if coverage is not None and not (isinstance(coverage, dict) and isinstance(coverage.get("uncovered_share"), (int, float))
                                     and 0 <= coverage["uncovered_share"] <= 1):
        problems.append("coverage: uncovered_share must be between 0 and 1")

    check_list("themes", portrait.get("themes", []), {"project": str, "topics": list}, problems)
    check_list("observations", portrait.get("observations", []), {"title": str, "detail": str}, problems)
    return problems


def history_path():
    return storage.data_root() / "history.jsonl"


def read_history():
    try:
        lines = history_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    entries = []

    for line in lines:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue

    return entries


def previous_entry(digest, epoch_id):
    previous = digest["period"].get("previous")

    if not previous:
        return None

    start, end = (date.fromisoformat(digest["period"][key]) for key in ("start", "end"))
    limit = (end - timedelta(days=((end - start).days + 1) // 2)).isoformat()
    matches = [entry for entry in read_history() if entry.get("period") == digest["period"]["name"] and
               entry.get("epoch") == epoch_id and str(entry.get("end")) <= limit]
    return max(matches, key=lambda entry: (same_range(entry, previous), entry["end"], entry["date"]), default=None)


def same_range(first, second):
    return bool(first and second and all(first.get(key) == second.get(key) for key in ("start", "end")))


def date_range(period, ui):
    end = period["end"]
    return f"{period['start']} – {end}" if period.get("start") else ui["through"].format(end=end)


def escape(value):
    return html.escape(str(value if value is not None else ""))


def evidence(ids, by_id, ui, *, show_workflow=False):
    rows = []

    for ident in ids or []:
        item = by_id.get(ident)

        if item:
            quotes = "".join(f"<q>{escape(line)}</q>" for line in item["excerpts"])
            if show_workflow:
                for entry in item.get("workflow", {}).get("support", []):
                    question = f' · {escape(entry["question"])}' if entry["question"] else ""
                    quotes += (f'<q><strong>{escape(ui["workflow_" + entry["actor"]])}{question}</strong> '
                               f'{escape(entry["text"])}</q>')
            client = CLIENTS.get(item["client"], item["client"])
            rows.append(f"<li><strong>{escape(client)} · {escape(item['project'])} · {escape(item['date'])}</strong>"
                        f"{quotes}</li>")

    if not rows:
        return ""

    label = escape(ui["evidence"].format(count=len(rows)))
    return f'<details class="session-evidence"><summary>{label}</summary><ul>{"".join(rows)}</ul></details>'


def table(headers, rows, numeric=()):
    head = "".join(f'<th class="num">{escape(cell)}</th>' if index in numeric else f"<th>{escape(cell)}</th>"
                   for index, cell in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="num">{escape(cell)}</td>' if index in numeric else f"<td>{escape(cell)}</td>"
                                    for index, cell in enumerate(row)) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_edit_checks(current, previous, ui):
    rows = []

    for period, summary in ((ui["current_period"], current), (ui["previous_period"], previous)):
        if "edit_sessions" in summary:
            edits = summary["edit_sessions"]
            checks = summary["checks_after_edit_sessions"]
            rows.append((period, edits, checks, f"{checks / edits:.1%}" if edits else "—"))

    if not rows:
        return ""

    headings = [ui[key] for key in ("period", "sessions_with_edits", "sessions_with_check", "share")]
    counts = table(headings, rows, numeric=(1, 2, 3))
    return (f'<section class="card"><h3>{escape(ui["edit_checks"])}</h3>{counts}'
            f'<p class="note">{escape(ui["edit_checks_note"])}</p></section>')


def radar_data(digest, portrait, profile, previous):
    ui = strings_for(portrait)
    epoch = profiles.current_epoch(profile)
    scores = {item["id"]: item for item in portrait.get("axes", [])}
    before = (previous or {}).get("axes", {})
    period = digest["period"]
    previous_period = period.get("previous")
    aligned = same_range(previous, previous_period)
    earlier_range = date_range(previous, ui) if previous and previous.get("end") and not aligned else None
    labels, anchors, now, then, earlier, rows = [], [], [], [], [], []

    if not digest["metrics_only"] and epoch:
        for axis in epoch["axes"]:
            ident = axis["id"]
            item = scores.get(ident, {})
            name, measures = item.get("name", axis["name"]), item.get("measures", axis["measures"])
            anchor, score, prior_score = f"axis-p-{ident}", item.get("score"), before.get(ident)
            labels.append(name)
            anchors.append(anchor)
            now.append(score)
            then.append(prior_score if aligned else None)
            earlier.append(prior_score if earlier_range else None)
            rows.append((anchor, name, measures, score, prior_score, earlier_range, item.get("reason"), item.get("evidence")))

    universal_before = (digest.get("previous") or {}).get("axes") or {}

    for key in AXES:
        score = (digest["current"]["axes"] or {}).get(key)
        name, anchor = ui[key], f"axis-u-{key}"
        labels.append(name)
        anchors.append(anchor)
        now.append(score)
        then.append(universal_before.get(key))
        earlier.append(None)
        rows.append((anchor, name, ui[f"{key}_meaning"], score, universal_before.get(key), None, None, None))

    current_label = ui["period_legend"].format(period=ui["current_period"], range=date_range(period, ui))
    previous_label = ui["period_legend"].format(period=ui["previous_period"], range=date_range(previous_period, ui)) \
        if previous_period else None
    earlier_label = ui["period_legend"].format(period=ui["earlier_portrait"], range=earlier_range) \
        if any(score is not None for score in earlier) else None
    return {"labels": labels, "anchors": anchors, "current": now, "previous": then, "earlier": earlier,
            "current_label": current_label, "previous_label": previous_label, "earlier_label": earlier_label}, rows


def score_bar(score, prior=None):
    fill = f'<span style="width:{score * 10:g}%"></span>' if is_score(score) else ""
    marker = f'<i style="inset-inline-start:{prior * 10:g}%"></i>' if is_score(prior) else ""
    return f'<div class="score-bar" aria-hidden="true">{fill}{marker}</div>'


def render_axes(rows, by_id, ui):
    groups = {"personal_axes": [], "universal_axes": []}

    for anchor, name, measures, score, before, earlier_range, reason, ids in rows:
        shown = "—" if score is None else f"{score:.1f}"
        prior = ""

        if is_score(before):
            baseline = ui["previous_score"].format(score=f"{before:.1f}")
            if earlier_range:
                baseline += f" · {earlier_range}"

            prior = f'<span class="prior-score">{escape(baseline)}</span>'

        reason_line = ""
        if reason:
            label = escape(ui["why_score"].format(score=shown))
            reason_line = f'<details class="axis-reason"><summary>{label}</summary><p>{escape(reason)}</p></details>'

        delta = ""
        if is_score(score) and is_score(before) and not earlier_range:
            change = round(score - before, 1)
            tone = "up" if change > 0 else "down" if change < 0 else "unchanged"
            shown_change = f"{change:+.1f}" if change else "0.0"
            delta = (f'<span class="pill score-{tone}" aria-label="{escape(ui[f"score_{tone}"])} {shown_change}">'
                     f'{shown_change}</span>')

        group = "personal_axes" if anchor.startswith("axis-p-") else "universal_axes"
        groups[group].append(
            f'<div class="axis" id="{escape(anchor)}"><div class="axis-heading"><div>'
            f'<h4>{escape(name)}</h4><p class="axis-meaning">{escape(measures)}</p></div>'
            f'<div class="axis-comparison">{score_bar(score, before if not earlier_range else None)}'
            f'<div class="axis-scores"><strong class="score">{shown}</strong>{delta}{prior}</div></div></div>'
            f'{reason_line}{evidence(ids, by_id, ui)}</div>'
        )

    return "".join(f'<div class="card axes"><h3>{escape(ui[group])}</h3>{"".join(items)}</div>'
                   for group, items in groups.items() if items)


def render_profile_legend(radar, ui):
    keys = [(radar["current_label"], "current")]
    if radar["previous_label"]:
        if any(is_score(score) for score in radar["previous"]):
            keys.append((radar["previous_label"], "previous"))
        else:
            keys.append((ui["no_scores"].format(period=radar["previous_label"]), "missing"))
    if radar["earlier_label"]:
        keys.append((radar["earlier_label"], "earlier"))

    entries = "".join(f'<li class="chart-key chart-key-{kind}">{escape(label)}</li>' for label, kind in keys)
    changes = [round(now - before, 1) for now, before in zip(radar["current"], radar["previous"])
               if is_score(now) and is_score(before)]
    counts = (("up", sum(change > 0 for change in changes)), ("down", sum(change < 0 for change in changes)),
              ("unchanged", changes.count(0)))
    pills = "".join(f'<span class="pill score-{kind}">{escape(ui[f"score_{kind}"])} · {count}</span>'
                    for kind, count in counts) if changes else ""
    return (f'<div class="profile-legend"><ul role="list">{entries}</ul><div class="pills">{pills}</div>'
            f'<p class="note">{escape(ui["radar_note"])}</p></div>')


def render_metric_tiles(summary, period, project_count, ui):
    sessions = summary["sessions"]
    agents = summary.get("agent_sessions", sessions)
    hours = round(summary["minutes"] / 60) if agents else "—"
    day_count = (date.fromisoformat(period["end"]) - date.fromisoformat(period["start"])).days + 1 if period.get("start") else 0
    day_total = f'<small class="tile-total"> / {day_count}</small>' if day_count > 0 else ""
    metrics = (
        ("sessions", sessions, ui["project_count"].format(count=project_count)),
        ("requests", summary["requests"], ui["requests_per_session"].format(count=f'{summary["requests"] / sessions:.1f}')
         if sessions else ""),
        ("active_days", summary["active_days"], ""),
        ("hours_with_agents", hours, ui["minutes_per_session"].format(count=round(summary["minutes"] / agents))
         if agents else ""),
    )
    return "".join(f'<div class="card tile"><span>{escape(ui[key])}</span><strong>{value}'
                   f'{day_total if key == "active_days" else ""}</strong><small>{escape(note)}</small></div>'
                   for key, value, note in metrics)


def render_findings(kind, items, by_id, start, ui):
    cards = []

    for index, item in enumerate(items, start):
        cause = (f'<p class="muted"><strong>{escape(ui["why"])}</strong> — {escape(item["cause"])}</p>'
                 if text(item.get("cause")) else "")
        action = (f'<div class="finding-action"><p class="finding-action-label"><strong>{escape(ui["try"])}</strong></p>'
                  f'<p>{escape(item["tip"])}</p></div>' if kind == "growth" else "")
        cards.append(f'<article class="card finding" id="finding-{index}"><h4>{escape(item["title"])}</h4>'
                     f'<p class="muted">{escape(item["detail"])}</p>'
                     f'{cause}{action}'
                     f'{evidence(item.get("evidence"), by_id, ui, show_workflow=bool(item.get("criterion")))}</article>')

    body = "".join(cards) or f'<p class="card muted">{escape(ui["no_findings"])}</p>'
    return f'<section class="findings-column {kind}"><h3>{escape(ui[kind])}</h3>{body}</section>'


def render_highlights(strengths, growth, lead, description, styles, ui):
    cards = []
    for kind, items, index in (("strength", strengths, 1), ("growth", growth, len(strengths) + 1)):
        if items:
            item = items[0]
            cards.append((kind, ui[f"finding_{kind}"], item["title"], item["detail"], f"finding-{index}",
                          ui["finding_details"]))
    if lead:
        score = ui["score_out_of_ten"].format(score=f"{styles[lead]:.1f}")
        cards.append(("style", ui["work_style"], f"{ui[lead]} · {score}", description, "style", ui["all_styles"]))
    return "".join(f'<article class="card highlight"><span class="pill highlight-{kind}">{escape(badge)}</span>'
                   f'<h3>{escape(title)}</h3><p>{escape(detail)}</p>'
                   f'<a href="#{target}">{escape(link)} <span aria-hidden="true">→</span></a></article>'
                   for kind, badge, title, detail, target, link in cards)


def workflow_path(steps, ui):
    items = []
    for step in steps:
        if step == "continues":
            items.append(f'<li class="workflow-more">{escape(ui["workflow_more_steps"])}</li>')
        else:
            actor = STEP_ACTORS[step]
            items.append(f'<li class="workflow-step workflow-step-{actor}">'
                         f'<span class="workflow-actor">{escape(ui["workflow_" + actor])}</span>'
                         f'<span>{escape(ui["workflow_step_" + step])}</span></li>')
    return f'<ol class="workflow-steps" role="list">{"".join(items)}</ol>'


def workflow_criteria(criteria, ui):
    items = []
    for ident, values in criteria.items():
        bands = "".join(f'<span class="band-{status}" style="flex-grow:{values[status]}"></span>'
                        for status in STATUSES if values[status])
        statuses = "".join(
            f'<div class="workflow-status workflow-status-{status}{" is-zero" if not values[status] else ""}">'
            f'<dt>{escape(ui[f"workflow_{status}"])}</dt><dd>{escape(values[status])}</dd></div>'
            for status in STATUSES
        )
        items.append(f'<li><h5>{escape(ui[ident])}</h5><div class="criterion-results">'
                     f'<div class="criterion-bar" aria-hidden="true">{bands}</div><dl>{statuses}</dl></div></li>')
    return f'<ul class="workflow-criteria" role="list">{"".join(items)}</ul>'


def render_workflow(workflow, by_id, ui):
    if not workflow or not (workflow["groups"] or workflow["mixed"]):
        return ""
    contents = []
    for group in workflow["groups"]:
        heading = escape(ui[f'workflow_{group["kind"]}'])
        total = escape(ui["workflow_sessions"].format(count=group["sessions"]))
        rows = []
        for path in group["paths"]:
            refs = [ident for ident, item in by_id.items() if item.get("workflow", {}).get("kind") == group["kind"]
                    and item["workflow"]["steps"] == path["steps"]][:2]
            count = escape(ui["workflow_sessions"].format(count=path["count"]))
            rows.append(f'<li><strong>{count}</strong>{workflow_path(path["steps"], ui)}'
                        f'{evidence(refs, by_id, ui, show_workflow=True)}</li>')
        preview = ""
        if group["paths"]:
            primary = group["paths"][0]
            steps = primary["steps"]
            shortened = steps if len(steps) <= 6 else [*steps[:6], "continues"]
            count = escape(ui["workflow_path_count"].format(count=primary["count"]))
            preview = (f'<div class="workflow-preview"><p><strong>{escape(ui["workflow_primary"])}</strong> '
                       f'{count}</p>{workflow_path(shortened, ui)}</div>')
        criteria = (f'<section><h4>{escape(ui["workflow_criteria"])}</h4>'
                    f'{workflow_criteria(group["criteria"], ui)}</section>')
        paths = (f'<details class="workflow-details"><summary>{escape(ui["workflow_paths"])}</summary>'
                 f'<ul class="workflow-scenarios" role="list">{"".join(rows)}</ul></details>') if rows else ""
        contents.append(f'<section class="card workflow-group"><div class="workflow-heading">'
                        f'<h3>{heading}</h3><span>{total}</span></div>{preview}{criteria}{paths}</section>')
    coverage = ui["workflow_coverage"].format(mixed=workflow["mixed"], unclassified=workflow["unclassified"])
    return (f'<section class="report-section" id="workflow"><h2>{escape(ui["workflow_title"])}</h2>'
            f'<p class="section-intro">{escape(ui["workflow_note"])} {escape(coverage)}</p>'
            f'<div class="workflow-groups">{"".join(contents)}</div></section>')


def render_html(digest, portrait, profile, previous):
    ui = strings_for(portrait)
    label = {key: escape(value) for key, value in ui.items()}
    by_id = {item["id"]: item for item in digest["evidence"]}
    summary, period = digest["current"]["summary"], digest["period"]
    radar, rows = radar_data(digest, portrait, profile, previous)
    clients = [CLIENTS[item["client"]] for item in digest["sources"] if item["sessions"]] or [ui["no_clients"]]
    chips = "".join(f'<span class="pill">{escape(client)}</span>' for client in clients)
    if 0 < len(digest["projects"]) <= 3:
        project_names = ", ".join(item["name"] for item in digest["projects"])
        chips += f'<a class="pill" href="#projects">{escape(ui["project_list"].format(projects=project_names))}</a>'
    generated = escape(ui["generated_offline"].format(date=date.today().isoformat()))
    previous_block = digest.get("previous") or {}
    before = previous_block["summary"] if previous_block.get("axes") else {}
    styles = digest["current"].get("archetypes") or {}
    ranked_styles = sorted((name for name in ARCHETYPES if name in styles), key=styles.get, reverse=True)
    chat_sources = [item for item in digest["sources"] if item["client"] in CHAT_CLIENTS]
    source_note = ""
    if chat_sources:
        source_rows = [(CLIENTS[item["client"]], item["sessions"],
                        ", ".join(ui[f"chat_{mode}"] for mode in item["imports"]), item["skipped_conversations"])
                       for item in chat_sources]
        source_note = table([ui[key] for key in ("client", "sessions", "chat_input", "chat_skipped")],
                            source_rows, numeric=(1, 3))
    data = {
        "radar": radar,
        "style": {"title": ui["work_style"], "labels": [ui[name] for name in ranked_styles],
                  "values": [styles[name] for name in ranked_styles]} if ranked_styles else None,
        "weekday": {"labels": [ui[day] for day in WEEKDAYS], "values": digest["activity"]["by_weekday"]},
        "hour": {"labels": [f"{hour:02d}" for hour in range(24)], "values": digest["activity"]["by_hour"]},
        "trend": {"labels": [item["month"] for item in digest["trend"]],
                  "series": [{"label": ui[key], "values": [item["axes"][key] for item in digest["trend"]]}
                             for key in AXES]} if len(digest["trend"]) > 1 else None,
    }
    tiles = render_metric_tiles(summary, period, len(digest["projects"]), ui)
    friction = "".join(f'<div class="tile"><span>{label[key]}</span><strong>{summary[key]}</strong>'
                       f'<small>{escape(ui["previous_count"].format(count=before[key])) if key in before else ""}</small></div>'
                       for key in ("corrections", "repeats", "interrupted", "compactions"))
    coverage = portrait.get("coverage") or {}
    banner = ""

    if coverage.get("uncovered_share", 0) > 0.5:
        share = escape(ui["coverage"].format(share=round(coverage["uncovered_share"] * 100)))
        banner = f'<div class="banner">{share} {escape(coverage.get("note"))} {label["coverage_tip"]}</div>'

    profile_notes = [label["profile_scale"]]
    if any(is_score(score) for score in radar["previous"]):
        profile_notes.append(label["profile_comparison"])
    if digest["metrics_only"]:
        profile_notes.append(label["metrics_only"])
    if chat_sources:
        profile_notes.append(label["chat_limits"])
    themes = {item.get("project"): ", ".join(item.get("topics") or []) for item in portrait.get("themes", [])}
    projects = table([ui[key] for key in ("project", "sessions", "requests", "topics")],
                     [(item["name"], item["sessions"], item["turns"], themes.get(item["name"], "")) for item in digest["projects"]],
                     numeric=(1, 2))
    tools = digest["tools"]
    tool_rows = ([(ui["skill"], name, count) for name, count in sorted(tools["skills"].items(), key=lambda pair: -pair[1])] +
                 [(ui["mcp"], name, count) for name, count in sorted(tools["mcp"].items(), key=lambda pair: -pair[1])] +
                 [(ui["subagent"], ui["subagent_turns"], tools["subagent_turns"])])
    kinds = ", ".join(f"{ui.get(kind, kind)} {count}" for kind, count in sorted(tools["kinds"].items(), key=lambda pair: -pair[1]))
    action_counts = escape(ui["action_counts"].format(counts=kinds))
    tokens = digest["tokens"]
    spend = table([ui["client"], ui["tokens"]],
                  [(name, f"{tokens[key]:,}" if tokens.get(key) is not None else ui["not_recorded"])
                   for key, name in CLIENTS.items()
                   if key in tokens or any(item["client"] == key for item in chat_sources)], numeric=(1,))
    observations = "".join(f"<li><strong>{escape(item.get('title'))}</strong> — {escape(item.get('detail'))}</li>"
                           for item in portrait.get("observations", []))
    style_card, lead, description = "", None, ""

    if ranked_styles:
        archetype = portrait.get("archetype") or {}
        lead = archetype.get("lead")
        if lead not in styles:
            lead = ranked_styles[0]
        description = archetype.get("text", "")
        lead_score = escape(ui["score_out_of_ten"].format(score=f"{styles[lead]:.1f}"))
        ranks = "".join(f'<li><span>{label[name]}</span><strong>'
                        f'{escape(ui["score_out_of_ten"].format(score=f"{styles[name]:.1f}"))}</strong>'
                        f'{score_bar(styles[name])}</li>'
                        for name in ranked_styles)
        style_card = (f'<section class="report-section" id="style"><h2>{label["work_style"]}</h2><div class="card style-card">'
                      f'<div><p class="eyebrow">{label["leading_style"]}</p><h3>{label[lead]}</h3>'
                      f'<p class="style-score">{lead_score}</p><p class="muted">{escape(description)}</p></div>'
                      f'<div class="radar"><canvas id="style-radar" role="img" aria-label="{label["work_style"]}"></canvas></div>'
                      f'<ol class="style-scores" role="list">{ranks}</ol></div></section>')

    strengths, growth = portrait.get("strengths", []), portrait.get("growth", [])
    highlights = render_highlights(strengths, growth, lead, description, styles, ui)
    workflow = render_workflow(digest.get("workflow"), by_id, ui)
    sections = (("summary", "nav_summary", highlights), ("profile", "profile", True),
                ("findings", "findings_title", True), ("workflow", "nav_workflow", workflow),
                ("style", "work_style", style_card), ("stats", "nav_stats", True))
    navigation = "".join(f'<a href="#{target}">{label[key]}</a>' for target, key, shown in sections if shown)
    overview = (f'<section class="report-section" id="summary"><h2>{label["summary_title"]}</h2>'
                f'<div class="highlights">{highlights}</div></section>') if highlights else ""
    trend = (f'<section class="card"><h3>{label["monthly_axes"]}</h3><div class="chart">'
             f'<canvas id="trend" role="img" aria-label="{label["monthly_axes"]}"></canvas></div></section>') if data["trend"] else ""
    sources = (f'<details class="card source-details"><summary>{label["chat_input"]}</summary>'
               f'{source_note}</details>') if source_note else ""
    css = (PACKAGE / "report/style.css").read_text(encoding="utf-8")
    library = (PACKAGE / "report/vendor/chart.umd.min.js").read_text(encoding="utf-8")
    payload = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return f"""<!doctype html>
<html lang="{escape(portrait.get('language') or 'en')}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{label['title']}</title><style>{css}</style></head><body>
<header class="site-header" id="top"><div class="container header-inner">
<div class="brand"><span class="brand-mark" aria-hidden="true"></span><strong>Gnothi</strong>
<span class="brand-description">· {label['brand_description']}</span></div><span class="pill generated">{generated}</span>
</div></header>
<main class="container">
<section class="hero">
<p class="eyebrow">{label[period['name']]} · {escape(date_range(period, ui))}</p>
<h1>{label['your_portrait']}</h1><p class="lead">{escape(portrait.get('summary'))}</p>
<div class="pills">{chips}</div>
<div class="tiles">{tiles}</div>
<nav class="section-nav" aria-label="{label['report_sections']}">{navigation}</nav>
</section>
{banner}
{overview}
<section class="report-section" id="profile"><h2>{label['profile']}</h2>
<p class="section-intro">{' '.join(profile_notes)}</p>
<div class="card profile-card">
<div class="radar"><canvas id="profile-radar" role="img" aria-label="{label['profile']}"></canvas></div>
{render_profile_legend(radar, ui)}</div>
{render_axes(rows, by_id, ui)}
</section>
<section class="report-section" id="findings"><h2>{label['findings_title']}</h2><div class="grid findings-grid">
{render_findings("strengths", strengths, by_id, 1, ui)}
{render_findings("growth", growth, by_id, len(strengths) + 1, ui)}</div></section>
{workflow}
{style_card}
<section class="report-section" id="stats"><h2>{label['detailed_statistics']}</h2>
<div class="grid report-stats">
<section class="card"><h3>{label['weekday_activity']}</h3><div class="chart"><canvas id="weekday" role="img" aria-label="{label['weekday_activity']}"></canvas></div></section>
<section class="card"><h3>{label['hour_activity']}</h3><div class="chart"><canvas id="hour" role="img" aria-label="{label['hour_activity']}"></canvas></div></section>
<section class="card" id="projects"><h3>{label['project_themes']}</h3>{projects}</section>
{render_edit_checks(summary, previous_block.get("summary", {}), ui)}
<section class="card"><h3>{label['friction']}</h3><div class="tiles">{friction}</div></section>
<section class="card"><h3>{label['spend']}</h3>{spend}<p class="note">{label['cursor_tokens']}</p></section>
{trend}
<section class="card"><h3>{label['tools']}</h3>{table([ui[key] for key in ("kind", "name", "uses")], tool_rows, numeric=(2,))}<p class="note">{action_counts}</p></section>
{sources}
{f'<section class="card"><h3>{label["observations"]}</h3><ul>{observations}</ul></section>' if observations else ''}
</div></section>
<footer><span>{label['footer']}</span><a href="#top">{label['back_to_top']} <span aria-hidden="true">↑</span></a></footer>
</main><script>{library}</script><script>const DATA = {payload};
{SCRIPT}</script></body></html>
"""


SCRIPT = """const css = getComputedStyle(document.documentElement);
const value = name => css.getPropertyValue(name).trim();
const accent = value('--accent'), gold = value('--gold');
Chart.defaults.animation = false;
Chart.defaults.color = value('--muted');
Chart.defaults.borderColor = value('--line');
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
const radar = (id, labels, sets, anchors) => new Chart(document.getElementById(id), {
  type: 'radar', data: { labels, datasets: sets },
  options: { maintainAspectRatio: false, spanGaps: false,
    scales: { r: { min: 0, max: 10, ticks: { stepSize: 2, backdropColor: 'transparent' }, grid: { color: value('--line') },
                   angleLines: { color: value('--line') }, pointLabels: { font: { size: 12 } } } },
    plugins: { legend: { display: false } },
    onClick: (event, items, chart) => {
      const hit = chart.getElementsAtEventForMode(event, 'nearest', { intersect: false }, true)[0];
      if (anchors && hit) location.hash = anchors[hit.index];
    } } });
const sets = [{ label: DATA.radar.current_label, data: DATA.radar.current, borderColor: accent, backgroundColor: accent + '33',
                pointBackgroundColor: accent, borderWidth: 2 }];
if (DATA.radar.previous.some(item => item !== null)) {
  const previousColor = value('--text');
  sets.push({ label: DATA.radar.previous_label, data: DATA.radar.previous, borderColor: previousColor, backgroundColor: 'transparent',
              borderDash: [6, 4], pointBackgroundColor: previousColor, borderWidth: 2 });
}
if (DATA.radar.earlier_label) {
  const earlierColor = value('--good');
  sets.push({ label: DATA.radar.earlier_label, data: DATA.radar.earlier, borderColor: earlierColor, backgroundColor: 'transparent',
              borderDash: [2, 4], pointBackgroundColor: earlierColor, borderWidth: 2 });
}
radar('profile-radar', DATA.radar.labels, sets, DATA.radar.anchors);
if (DATA.style) {
  radar('style-radar', DATA.style.labels, [{ label: DATA.style.title, data: DATA.style.values, borderColor: accent,
        backgroundColor: accent + '33', pointBackgroundColor: accent, borderWidth: 2 }]);
}
const bars = (id, source) => new Chart(document.getElementById(id), {
  type: 'bar', data: { labels: source.labels, datasets: [{ data: source.values, backgroundColor: accent, borderRadius: 4,
                                                           maxBarThickness: 24 }] },
  options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
             scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });
bars('weekday', DATA.weekday);
bars('hour', DATA.hour);
if (DATA.trend) {
  const palette = [accent, gold, value('--danger'), value('--good')];
  new Chart(document.getElementById('trend'), {
    type: 'line', data: { labels: DATA.trend.labels, datasets: DATA.trend.series.map((series, index) => ({
      label: series.label, data: series.values, borderColor: palette[index], backgroundColor: palette[index],
      tension: 0.3, borderWidth: 2 })) },
    options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 10 } } } });
}"""


def render(portrait_path=None):
    root = storage.data_root()

    try:
        digest = json.loads((root / "tmp/digest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("No digest yet: run collect first")

    path = Path(portrait_path) if portrait_path else root / "tmp/portrait.json"

    try:
        portrait = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read {path}: {error}")

    profile = profiles.read()
    problems = validate(portrait, digest, profile)

    if problems:
        raise ValueError("Fix portrait.json: " + "; ".join(problems))

    epoch = profiles.current_epoch(profile)
    epoch_id = epoch["id"] if epoch else None
    previous = previous_entry(digest, epoch_id)
    page = render_html(digest, portrait, profile, previous)
    today = date.today().isoformat()
    target = storage.write_private(root / "reports" / f"portrait-{digest['period']['name']}-{today}.html", page)
    entry = {"date": today, "period": digest["period"]["name"], "epoch": epoch_id, "start": digest["period"]["start"],
             "end": digest["period"]["end"], "axes": {item["id"]: item["score"] for item in portrait.get("axes", [])},
             "universal": digest["current"]["axes"]}
    lines = [json.dumps(item, ensure_ascii=False) for item in read_history()] + [json.dumps(entry, ensure_ascii=False)]
    storage.write_private(history_path(), "\n".join(lines) + "\n")
    warnings = []

    if (portrait.get("coverage") or {}).get("uncovered_share", 0) > 0.5:
        warnings.append("Most work fits no personal axis: suggest updating the profile with the setup skill")

    if digest["period"].get("previous") and not previous and not digest["metrics_only"]:
        warnings.append("No earlier portrait for the previous period: personal axes show no comparison yet")

    return {"html": str(target), "warnings": warnings}
