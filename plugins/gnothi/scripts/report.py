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


def check_findings(name, items, known, metrics_only, problems):
    if not isinstance(items, list) or len(items) > 5:
        problems.append(f"{name}: give at most 5 items")
        return

    for index, item in enumerate(items, 1):
        where = f"{name} {index}"

        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue

        for key in ("title", "detail", "tip"):
            if not text(item.get(key)):
                problems.append(f"{where}: needs {key}")

        ids = set(check_evidence(where, item.get("evidence", []), known, problems))
        cause = text(item.get("cause"))

        if metrics_only:
            if not cause:
                problems.append(f"{where}: in metrics-only mode a finding needs a cause from the numbers")
        elif len(ids) < 2 and not (cause and ids):
            problems.append(f"{where}: needs at least two evidence sessions, or a cause and one session")


def validate(portrait, digest, profile):
    problems = []

    if not isinstance(portrait, dict) or portrait.get("schema_version") != 1:
        return ["portrait.json must be an object with schema_version 1"]

    language = portrait.get("language", "en")
    if not isinstance(language, str) or not re.fullmatch(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*", language):
        problems.append("language must be a language tag such as en or uk")

    if "ui" in portrait:
        problems.extend(check_ui(portrait["ui"]))

    known = {item["id"] for item in digest.get("evidence", [])}
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

    check_findings("strengths", portrait.get("strengths", []), known, metrics_only, problems)
    check_findings("growth", portrait.get("growth", []), known, metrics_only, problems)
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


def evidence(ids, by_id, ui):
    rows = []

    for ident in ids or []:
        item = by_id.get(ident)

        if item:
            quotes = "".join(f"<q>{escape(line)}</q>" for line in item["excerpts"])
            client = CLIENTS.get(item["client"], item["client"])
            rows.append(f"<li><strong>{escape(client)} · {escape(item['project'])} · {escape(item['date'])}</strong>"
                        f"{quotes}</li>")

    if not rows:
        return ""

    label = escape(ui["evidence"].format(count=len(rows)))
    return f"<details><summary>{label}</summary><ul>{''.join(rows)}</ul></details>"


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
    return (f'<section class="card"><h2>{escape(ui["edit_checks"])}</h2>{counts}'
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


def render_axes(rows, by_id, ui):
    items = []

    for anchor, name, measures, score, before, earlier_range, reason, ids in rows:
        shown = "—" if score is None else f"{score:.1f}"
        prior = ""

        if isinstance(before, (int, float)):
            baseline = ui["previous_score"].format(score=f"{before:.1f}")
            if earlier_range:
                baseline += f" · {earlier_range}"

            prior = f'<span class="prior-score">{escape(baseline)}</span>'

        reason_line = ""
        if reason:
            label = escape(ui["why_score"].format(score=shown))
            reason_line = f'<p class="axis-reason"><strong>{label}</strong> — {escape(reason)}</p>'

        items.append(f'<div class="axis" id="{anchor}"><div class="axis-heading">'
                     f'<h3><span class="metric-label">{escape(ui["metric"])}</span> {escape(name)} '
                     f'<span class="axis-meaning">({escape(measures)})</span></h3>'
                     f'<div class="axis-scores"><strong class="score">{shown}</strong>{prior}</div></div>'
                     f'{reason_line}{evidence(ids, by_id, ui)}</div>')

    return f'<div class="axes">{"".join(items)}</div>'


def render_findings(kind, items, by_id, start, ui):
    cards = []

    for index, item in enumerate(items, start):
        cause = (f'<p class="muted"><strong>{escape(ui["why"])}</strong> — {escape(item["cause"])}</p>'
                 if text(item.get("cause")) else "")
        cards.append(f'<div class="finding" id="finding-{index}"><h3>{escape(item["title"])}</h3><p>{escape(item["detail"])}</p>'
                     f'{cause}<p class="tip"><strong>{escape(ui["try"])}</strong> — {escape(item["tip"])}</p>'
                     f'{evidence(item.get("evidence"), by_id, ui)}</div>')

    body = "".join(cards) or f'<p class="muted">{escape(ui["no_findings"])}</p>'
    return f'<section class="card card-{kind}"><h2>{escape(ui[kind])}</h2><div class="findings">{body}</div></section>'


def render_html(digest, portrait, profile, previous):
    ui = strings_for(portrait)
    label = {key: escape(value) for key, value in ui.items()}
    by_id = {item["id"]: item for item in digest["evidence"]}
    summary, period = digest["current"]["summary"], digest["period"]
    radar, rows = radar_data(digest, portrait, profile, previous)
    clients = ", ".join(CLIENTS[item["client"]] for item in digest["sources"] if item["sessions"]) or ui["no_clients"]
    report_header = ui["header"].format(period=ui[period["name"]], range=date_range(period, ui),
                                       count=summary["sessions"], clients=clients, date=date.today().isoformat())
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
        source_note = (table([ui[key] for key in ("client", "sessions", "chat_input", "chat_skipped")],
                             source_rows, numeric=(1, 3)) + f'<p class="note">{label["chat_limits"]}</p>')
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
    hours = "—" if summary.get("agent_sessions") == 0 else round(summary["minutes"] / 60)
    tiles = "".join(f'<div class="tile"><span>{label[key]}</span><strong>{value}</strong></div>'
                    for key, value in (("sessions", summary["sessions"]), ("requests", summary["requests"]),
                                       ("active_days", summary["active_days"]),
                                       ("hours_with_agents", hours)))
    friction = "".join(f'<div class="tile"><span>{label[key]}</span><strong>{summary[key]}</strong>'
                       f'<small>{escape(ui["previous_count"].format(count=before[key])) if key in before else ""}</small></div>'
                       for key in ("corrections", "repeats", "interrupted", "compactions"))
    coverage = portrait.get("coverage") or {}
    banner = ""

    if coverage.get("uncovered_share", 0) > 0.5:
        share = escape(ui["coverage"].format(share=round(coverage["uncovered_share"] * 100)))
        banner = f'<div class="banner">{share} {escape(coverage.get("note"))} {label["coverage_tip"]}</div>'

    metrics_note = f'<p class="note">{label["metrics_only"]}</p>' if digest["metrics_only"] else ""
    period_notes = [radar["current_label"]]
    if radar["previous_label"]:
        previous_label = radar["previous_label"]
        if not any(score is not None for score in radar["previous"]):
            previous_label = ui["no_scores"].format(period=previous_label)

        period_notes.append(previous_label)

    if radar["earlier_label"]:
        period_notes.append(radar["earlier_label"])

    periods_note = escape(" · ".join(period_notes))
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
    style_card = ""

    if ranked_styles:
        ranks = "".join(f'<li><span>{label[name]}</span><strong>'
                        f'{escape(ui["score_out_of_ten"].format(score=f"{styles[name]:.1f}"))}</strong></li>'
                        for name in ranked_styles)
        archetype = portrait.get("archetype") or {}
        description = f'<p>{escape(archetype["text"])}</p>' if archetype.get("text") else ""
        style_card = (f'<section class="card"><h2>{label["work_style"]}</h2>'
                      f'<div class="chart"><canvas id="style-radar"></canvas></div>'
                      f'<ol class="style-scores">{ranks}</ol>{description}</section>')

    trend = (f'<section class="card"><h2>{label["monthly_axes"]}</h2><div class="chart"><canvas id="trend"></canvas></div></section>'
             if data["trend"] else "")
    css = (PACKAGE / "report/style.css").read_text(encoding="utf-8")
    library = (PACKAGE / "report/vendor/chart.umd.min.js").read_text(encoding="utf-8")
    payload = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return f"""<!doctype html>
<html lang="{escape(portrait.get('language') or 'en')}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{label['title']}</title><style>{css}</style></head><body><main>
<header><div class="eyebrow">Gnothi</div><h1>{label['your_portrait']}</h1>
<p class="muted">{escape(report_header)}</p>
{source_note}
<p class="lead">{escape(portrait.get('summary'))}</p></header>
{banner}
<div class="tiles">{tiles}</div>
<section class="card"><h2>{label['profile']}</h2><div class="radar"><canvas id="profile-radar"></canvas></div>{metrics_note}
<p class="note">{periods_note}<br>{label['radar_note']}</p>
{render_axes(rows, by_id, ui)}</section>
<div class="grid">{render_findings("strengths", portrait.get("strengths", []), by_id, 1, ui)}
{render_findings("growth", portrait.get("growth", []), by_id, len(portrait.get("strengths", [])) + 1, ui)}</div>
{style_card}
<section class="card"><h2>{label['project_themes']}</h2>{projects}</section>
<div class="grid"><section class="card"><h2>{label['weekday_activity']}</h2><div class="chart"><canvas id="weekday"></canvas></div></section>
<section class="card"><h2>{label['hour_activity']}</h2><div class="chart"><canvas id="hour"></canvas></div></section></div>
{trend}
<section class="card"><h2>{label['tools']}</h2>{table([ui[key] for key in ("kind", "name", "uses")], tool_rows, numeric=(2,))}<p class="note">{action_counts}</p></section>
{render_edit_checks(summary, previous_block.get("summary", {}), ui)}
<h2>{label['friction']}</h2><div class="tiles">{friction}</div>
<section class="card"><h2>{label['spend']}</h2>{spend}<p class="note">{label['cursor_tokens']}</p></section>
{f'<section class="card"><h2>{label["observations"]}</h2><ul>{observations}</ul></section>' if observations else ''}
<footer>{label['footer']}</footer>
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
    plugins: { legend: { display: Boolean(anchors), position: 'bottom' } },
    onClick: (event, items, chart) => {
      const hit = chart.getElementsAtEventForMode(event, 'nearest', { intersect: false }, true)[0];
      if (anchors && hit) location.hash = anchors[hit.index];
    } } });
const sets = [{ label: DATA.radar.current_label, data: DATA.radar.current, borderColor: accent, backgroundColor: accent + '33',
                pointBackgroundColor: accent, borderWidth: 2 }];
if (DATA.radar.previous.some(item => item !== null)) {
  sets.push({ label: DATA.radar.previous_label, data: DATA.radar.previous, borderColor: gold, backgroundColor: 'transparent',
              borderDash: [6, 4], pointBackgroundColor: gold, borderWidth: 2 });
}
if (DATA.radar.earlier_label) {
  const earlierColor = value('--good');
  sets.push({ label: DATA.radar.earlier_label, data: DATA.radar.earlier, borderColor: earlierColor, backgroundColor: 'transparent',
              borderDash: [2, 4], pointBackgroundColor: earlierColor, borderWidth: 2 });
}
radar('profile-radar', DATA.radar.labels, sets, DATA.radar.anchors);
if (DATA.style) {
  radar('style-radar', DATA.style.labels, [{ label: DATA.style.title, data: DATA.style.values, borderColor: gold,
        backgroundColor: gold + '33', pointBackgroundColor: gold, borderWidth: 2 }]);
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
