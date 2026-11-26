#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

sys.dont_write_bytecode = True
from dependency_support import PLUGIN, bundle_path, data_root, installed
from feedback import recent as feedback_records
from ui_state import validate_label_map
from project import BASE, ensure_excluded, redirected, toplevel, write_json
from reports import all_tasks
from summary import COUNTED_DISPOSITIONS, DISPOSITIONS, disposition_key, saved_dispositions, read as read_summary

VERDICTS = ("READY TO PUSH", "PARTIAL CHECK COMPLETE", "BLOCKED", "INCOMPLETE")
KEY = re.compile(r"^(task_id|Round|Verdict):\s*(.+?)\s*$", re.M)
DAY = re.compile(r"(\d{4}-\d{2}-\d{2})$")


def key_lines(report):
    try:
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    found = {name.lower(): value.strip("*` ") for name, value in KEY.findall(text[:4000])}

    if "verdict" not in found:
        head = text[:3000].upper()
        found["verdict"] = next((verdict for verdict in VERDICTS if verdict in head), None)

    return found


def round_summaries(data):
    rounds = [item for item in data.get("rounds") or [] if isinstance(item, dict)]
    for item in rounds:
        item["findings"] = [entry for entry in item.get("findings") or [] if isinstance(entry, dict)]
        item["qa"] = [entry for entry in item.get("qa") or [] if isinstance(entry, dict)]

    return rounds


def test_problems(rounds):
    seen, problems = {}, set()

    for entry in rounds:
        for case in entry.get("qa") or []:
            key = (case.get("id"), entry.get("fingerprint"))

            if case.get("status") == "FAIL":
                seen[key] = True
            elif case.get("status") == "PASS" and seen.get(key):
                problems.add(case.get("id"))

    return sorted(problem for problem in problems if problem)


def widget_decisions(decision):
    from ui_state import gallery_actions

    if decision.get("view") == "review":
        for row in decision.get("rows", []):
            if isinstance(row, dict) and row.get("action") in DISPOSITIONS:
                yield row
    if decision.get("view") == "qa-results":
        for action in gallery_actions(decision):
            if action["action"] == "false-positive":
                yield dict(id=action["scenario"], action="false-positive", source="QA", reason=action["reason"])


def view_feedback(directory):
    from ui_state import object_at

    latest = {}
    for filename in sorted(directory.glob("ui-*-decision-*.json")):
        try:
            decision = object_at(filename)
            modified = filename.stat().st_mtime_ns
        except (ValueError, OSError):
            continue
        round_number = decision.get("round")
        if type(round_number) is not int:
            continue
        revision = decision.get("requirements_revision")
        order = (revision if type(revision) is int else 0, modified)
        for item in widget_decisions(decision):
            if not isinstance(item.get("id"), str):
                continue
            row = dict(item, round=round_number)
            key = disposition_key(row)
            if key not in latest or order >= latest[key][0]:
                latest[key] = (order, row)
    return (row for _, row in latest.values() if row["action"] in COUNTED_DISPOSITIONS)


def recorded_feedback(directory, data):
    recorded = saved_dispositions(data)
    history = [row for row in view_feedback(directory) if disposition_key(row) not in recorded]
    return history + [row for row in recorded.values() if row["action"] in COUNTED_DISPOSITIONS]


def task_record(item, feedback):
    directory = item["directory"]
    keys = key_lines(directory / "report.md")
    summary_data = read_summary(directory / "summary.json")
    rounds = round_summaries(summary_data)
    findings = {}

    for entry in rounds:
        for finding in entry.get("findings") or []:
            findings[finding.get("id")] = finding

    day = DAY.search(item["task_id"])
    returned = [record for record in feedback if record.get("task") == item["task_id"] and record.get("returned")]
    round_count = rounds[-1].get("round") if rounds else (int(keys["round"]) if str(keys.get("round", "")).isdigit() else None)
    return dict(task_id=item["task_id"], branch=item["branch_dir"], date=day.group(1) if day else None,
                rounds=round_count, verdict=(rounds[-1].get("verdict") if rounds else keys.get("verdict")) or "unknown",
                first_round_verdict=rounds[0].get("verdict") if rounds else "unknown",
                findings=list(findings.values()), qa_test_problems=test_problems(rounds),
                returned=bool(returned), returned_missed=any(record.get("missed") is True or record.get("missed") == "yes"
                                                              for record in returned),
                return_reasons=[record.get("reason") for record in returned], has_summary=bool(rounds),
                view_feedback=recorded_feedback(directory, summary_data),
                report=str(directory / "report.md"))


def collect(top, limit):
    feedback = feedback_records(top, 10000)
    tasks = [task_record(item, feedback) for item in all_tasks(top)[:limit]]
    selected_ids = {task["task_id"] for task in tasks}
    returns = [record for record in feedback if record.get("returned") and record.get("task") in selected_ids]
    with_summary = [task for task in tasks if task["has_summary"]]
    labels = Counter(finding.get("label", "unknown") for task in tasks for finding in task["findings"])
    areas = Counter(finding.get("area") or "unknown" for task in tasks for finding in task["findings"])
    weeks = Counter()

    for record in returns:
        try:
            year, week, _ = datetime.fromisoformat(record["ts"]).isocalendar()
            weeks[f"{year}-W{week:02d}"] += 1
        except (KeyError, ValueError, TypeError):
            weeks["unknown"] += 1

    totals = dict(
        tasks=len(tasks),
        with_summary=len(with_summary),
        passed_first_round=sum(task["rounds"] == 1 and task["verdict"] == "READY TO PUSH" for task in with_summary),
        with_defects=sum(any(str(f.get("label", "")).startswith("issue") for f in task["findings"]) for task in with_summary),
        findings_by_label=dict(labels),
        returned=sum(task["returned"] for task in tasks),
        returned_missed=sum(task["returned_missed"] for task in tasks),
        qa_test_problems=sum(len(task["qa_test_problems"]) for task in tasks),
        without_summary=len(tasks) - len(with_summary),
    )
    reasons = [dict(task=record.get("task"), reason=record.get("reason"), area=record.get("area"),
                    missed=record.get("missed")) for record in returns]
    dispositions = Counter(row["action"] for task in tasks for row in task["view_feedback"])
    return dict(tasks=tasks, totals=totals, areas=areas.most_common(), returns_per_week=sorted(weeks.items()),
                feedback_reasons=reasons, view_dispositions=dict(dispositions))


def summary_value(totals, key, empty="No data", coverage="tasks with summaries"):
    available = totals["with_summary"]
    if not available:
        return empty
    if key == "qa_test_problems":
        return f"{totals[key]} ({available} {coverage})"
    return f"{totals[key]} / {available}"


def disposition_metrics(digest, locale="en"):
    counts = digest.get("view_dispositions", {})
    labels = (
        ("false-positive", "False positives", "Хибні спрацювання"),
        ("accept-risk", "Accepted risks", "Прийняті ризики"),
    )
    return [(uk if locale == "uk" else en, counts[key]) for key, en, uk in labels if key in counts]


def dashboard(digest, locale):
    def label(en, uk):
        return uk if locale == "uk" else en

    totals = digest["totals"]
    empty = label("No data", "Немає даних")
    coverage = label("tasks with summaries", "задач із підсумками")
    summary_keys = {"passed_first_round", "with_defects", "qa_test_problems"}
    metrics = []
    for key, caption in (
        ("tasks", label("Tasks", "Задачі")),
        ("passed_first_round", label("Passed in round 1", "Пройшли з першого раунду")),
        ("with_defects", label("Tasks with defects", "Задачі з дефектами")),
        ("returned", label("Returned after review", "Повернули після рев’ю")),
        ("returned_missed", label("Missed by Ready Check", "Пропустив Ready Check")),
        ("qa_test_problems", label("QA test problems", "Збої QA-тестів")),
        ("without_summary", label("Missing round summaries", "Без підсумків раундів")),
    ):
        value = summary_value(totals, key, empty, coverage) if key in summary_keys else totals[key]
        metrics.append(dict(label=caption, value=value))
    words = reflect_labels(locale, None)
    task_rows = [[row["task_id"], row["date"], row["rounds"], words.get(row["verdict"], row["verdict"]),
                  ", ".join(value for value in row["return_reasons"] if value) or None] for row in digest["tasks"]]
    metrics.extend(dict(label=caption, value=value) for caption, value in disposition_metrics(digest, locale))
    return dict(locale=locale, title=label("Ready Check overview", "Статистика Ready Check"),
                labels=dict(empty=label("No data for these tasks.", "Для цих задач немає даних.")), metrics=metrics,
                sections=[
                    dict(title=label("Tasks", "Задачі"),
                         columns=[label("Task", "Задача"), label("Date", "Дата"), label("Rounds", "Раунди"),
                                  label("Verdict", "Результат"), label("Return reason", "Причина повернення")],
                         rows=task_rows),
                    dict(title=label("Finding areas", "Категорії знахідок"),
                         columns=[label("Area", "Категорія"), label("Count", "Кількість")], rows=digest["areas"]),
                    dict(title=label("Returns by week", "Повернення за тижнями"),
                         columns=[label("Week", "Тиждень"), label("Count", "Кількість")],
                         rows=digest["returns_per_week"]),
                ])


def snapshot_path(top, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Expected a valid Reflect snapshot ID")
    directory = top / BASE / "reflect"
    path = directory / f"snapshot-{identifier}.json"
    if any(redirected(item) for item in (path, directory, directory.parent, directory.parent.parent)):
        raise ValueError("Reflect snapshots require local files in the report directory")
    return path


def read_snapshot(top, identifier):
    path = snapshot_path(top, identifier)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError("Reflect snapshot is unavailable. Collect the overview again.") from error


def snapshot_data(digest):
    snapshot = {key: digest[key] for key in ("totals", "areas", "returns_per_week", "view_dispositions")}
    fields = ("task_id", "date", "rounds", "verdict", "return_reasons")
    snapshot["tasks"] = [{key: task[key] for key in fields} for task in digest["tasks"]]
    return snapshot


def chart_source():
    source = PLUGIN / "dependencies/browser"
    folder = bundle_path(source, data_root(), "browser")
    path = folder / "node_modules/chart.js/dist/chart.umd.min.js"
    return path.read_text(encoding="utf-8") if installed(source, folder) and path.is_file() else None


def table(headers, rows, kind=None):
    head = "".join(f"<th>{html.escape(str(cell))}</th>" for cell in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    css = f' class="{kind}"' if kind else ""
    return f"<table{css}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def short(label, size=22):
    label = str(label)
    return label if len(label) <= size else label[:size - 1].rstrip(" -,.") + "…"


def reflect_labels(locale, translations):
    if not isinstance(locale, str) or not re.fullmatch(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*", locale):
        raise ValueError("Reflect needs a valid report language tag")
    path = Path(__file__).resolve().parent.parent / "ui/reflect-labels.json"
    locales = json.loads(path.read_text(encoding="utf-8"))
    base = locale.split("-")[0].lower()
    if translations is None and base in locales:
        return locales[base]
    validate_label_map(locales["en"], translations)
    key = "Generated {date} from {count} tasks."
    template = translations[key]
    remaining = template.replace("{count}", "").replace("{date}", "")
    if re.search(r"[{}]", remaining) or any(template.count(field) != 1 for field in ("{count}", "{date}")):
        raise ValueError("Keep the date and count placeholders in the translated report generation note")
    return translations


def render_html(digest, locale="en", translations=None):
    words = reflect_labels(locale, translations)
    label = words.__getitem__
    totals, tasks = digest["totals"], digest["tasks"]
    library = chart_source()
    first = summary_value(totals, "passed_first_round", label("No data"))
    defects = summary_value(totals, "with_defects", label("No data"))
    charts = dict(
        rounds=dict(type="bar", labels=[short(task["task_id"]) for task in tasks], values=[task["rounds"] for task in tasks]),
        outcomes=dict(type="doughnut", labels=[f'{label("Passed in round 1")} ({first})', f'{label("Confirmed defects")} ({defects})', label("Returned after review")],
                      values=[totals["passed_first_round"] if totals["with_summary"] else None,
                              totals["with_defects"] if totals["with_summary"] else None, totals["returned"]]),
        areas=dict(type="bar", labels=[short(area) for area, _ in digest["areas"][:8]], values=[count for _, count in digest["areas"][:8]]),
        weeks=dict(type="line", labels=[week for week, _ in digest["returns_per_week"]],
                   values=[count for _, count in digest["returns_per_week"]]),
    )
    titles = dict(rounds="Rounds per task", outcomes="Task outcomes", areas="Top error areas", weeks="Returns per week")
    cards = "".join(f'<section class="card"><h2>{html.escape(label(titles[name]))}</h2><div class="chart"><canvas id="{name}"></canvas></div></section>'
                    for name in charts)
    totals_rows = [("Tasks", totals["tasks"]), ("Passed in round 1", first),
                   ("With confirmed defects", defects), ("Returned after review", totals["returned"]),
                   ("Returned and missed by Ready Check", totals["returned_missed"]),
                   ("QA cases that failed because of the test", summary_value(totals, "qa_test_problems", label("No data"), label("tasks with summaries"))),
                   ("Tasks without round summaries", totals["without_summary"])]
    totals_rows.extend(disposition_metrics(digest))
    totals_rows = [(label(name), number) for name, number in totals_rows]
    task_rows = [(task["task_id"], re.sub(r"-[0-9a-f]{12}$", "", task["branch"] or ""), task["date"] or label("unknown"), task["rounds"] or label("unknown"),
                  words.get(task["verdict"], task["verdict"]), label("yes" if task["returned"] else "no"), "; ".join(r for r in task["return_reasons"] if r) or "") for task in tasks]
    script = ""

    if library:
        data = json.dumps(charts).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        script = f"<script>{library}</script><script>const DATA = {data};" + """
const css = getComputedStyle(document.documentElement);
const value = name => css.getPropertyValue(name).trim();
const color = value('--accent'), gold = value('--gold'), line = value('--line');
const palette = [value('--accent'), value('--gold'), value('--danger')];
Chart.defaults.color = value('--muted');
Chart.defaults.borderColor = line;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
for (const [id, c] of Object.entries(DATA)) {
  const lineChart = c.type === 'line';
  new Chart(document.getElementById(id), {
    type: c.type,
    data: { labels: c.labels, datasets: [{ data: c.values, backgroundColor: c.type === 'doughnut' ? palette : lineChart ? gold : color,
            borderColor: c.type === 'doughnut' ? value('--card') : lineChart ? gold : color, borderWidth: lineChart ? 2 : 1,
            borderRadius: c.type === 'bar' ? 4 : 0, maxBarThickness: 24, tension: 0.3, pointRadius: lineChart ? 4 : 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: c.type === 'doughnut', position: 'right' } },
               indexAxis: id === 'areas' ? 'y' : 'x',
               scales: c.type === 'doughnut' ? {} : { x: { beginAtZero: true, ticks: { autoSkip: false, precision: 0 } }, y: { beginAtZero: true, ticks: { precision: 0 } } } }
  });
}
</script>"""
    else:
        cards = "".join(f'<section class="card"><h2>{html.escape(label(titles[name]))}</h2>' +
                        table([label("Label"), label("Value")], [(name, label("No data") if value is None else value)
                                                   for name, value in zip(chart["labels"], chart["values"])]) + "</section>"
                        for name, chart in charts.items())

    tiles = "".join(f'<div class="tile"><span>{html.escape(label(caption))}</span><strong>{number}</strong></div>' for caption, number in (
        ("Tasks", totals["tasks"]), ("Passed in round 1", first),
        ("Returned after review", totals["returned"]), ("Missed by Ready Check", totals["returned_missed"])))

    return f"""<!doctype html>
<html lang="{html.escape(locale)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<title>{html.escape(label("Ready Check overview"))}</title>
<style>
:root {{ --bg: #EFEBE1; --card: #FBF9F3; --text: #071218; --muted: #575450; --line: #E0DDD8; --accent: #1F5673;
         --gold: #D99A43; --danger: #B3423A; --soft: #E3EDF0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #102633; --card: #14303F; --text: #F4F0E6; --muted: #A9BBC2;
         --line: #23475A; --accent: #9CCBDD; --gold: #D99A43; --danger: #E58A7F; --soft: #173545; }} }}
body {{ margin: 0; padding: 32px 16px; background: var(--bg); color: var(--text);
       font: 15px/1.55 "Ubuntu Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; }}
header {{ margin-bottom: 24px; }} .eyebrow {{ display: flex; align-items: center; gap: 8px; color: var(--accent);
       font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }}
.eyebrow::before {{ content: ""; width: 9px; height: 9px; border-radius: 50%; background: var(--gold); }}
h1 {{ margin: 6px 0 4px; font-size: 28px; font-weight: 600; }} p.muted {{ color: var(--muted); margin: 0; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.tile {{ background: var(--soft); border-radius: 12px; padding: 14px 16px; }} .tile span {{ color: var(--muted); font-size: 13px; }}
.tile strong {{ display: block; font-size: 30px; font-weight: 600; color: var(--accent); font-variant-numeric: tabular-nums; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }}
@media (max-width: 760px) {{ .grid {{ grid-template-columns: minmax(0, 1fr); }} }}
.chart {{ position: relative; height: 260px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; overflow-x: auto; }}
h2 {{ font-size: 15px; font-weight: 600; margin: 0 0 12px; }} table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ color: var(--muted); font-weight: 600; font-size: 13px; white-space: nowrap; }}
.tasks td:not(:last-child) {{ white-space: nowrap; }} .tasks td:last-child {{ width: 100%; min-width: 200px; color: var(--muted); }}
.totals td:last-child, .totals th:last-child {{ text-align: right; width: 120px; font-variant-numeric: tabular-nums; }}
tbody tr:last-child td {{ border-bottom: 0; }} tbody tr:hover td {{ background: var(--soft); }}
td:first-child {{ font-weight: 500; }}
footer {{ margin-top: 24px; color: var(--muted); font-size: 13px; }}
</style></head><body><main>
<header><div class="eyebrow">Ready Check</div><h1>{html.escape(label("Task overview"))}</h1>
<p class="muted">{html.escape(label("Generated {date} from {count} tasks.").format(date=date.today().isoformat(), count=totals["tasks"]))}</p></header>
<div class="tiles">{tiles}</div>
<section class="card" style="margin-bottom:16px"><h2>{html.escape(label("Totals"))}</h2>{table([label("Metric"), label("Value")], totals_rows, "totals")}</section>
<div class="grid">{cards}</div>
<section class="card"><h2>{html.escape(label("Tasks"))}</h2>{table([label(name) for name in ("Task", "Branch", "Date", "Rounds", "Verdict", "Returned", "Reason")], task_rows, "tasks")}</section>
<footer>{html.escape(label("Local, confidential report generated on this machine. It loads nothing from the network; do not publish or share it."))}</footer>
</main>{script}</body></html>
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Collect Ready Check task history, statistics and an optional HTML overview.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--locale", default="en")
    parser.add_argument("--labels", type=Path, help="JSON object of translated HTML report labels")
    args = parser.parse_args()
    result = dict(schema_version=1, action="reflect-collect", status="FAIL")

    try:
        top = toplevel(args.project)

        if not top:
            raise ValueError("reflect-collect needs a Git work tree")

        digest = collect(top, max(args.tasks, 1))

        if args.html:
            identifier = uuid4().hex
            snapshot = snapshot_path(top, identifier)
            path = snapshot.with_name(f"overview-{date.today().isoformat()}-{identifier}.html")
            ensure_excluded(top)
            path.parent.mkdir(parents=True, exist_ok=True)
            translations = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else None
            path.write_text(render_html(digest, args.locale, translations), encoding="utf-8")
            write_json(snapshot, snapshot_data(digest), top)
            digest.update(html=str(path), snapshot_id=identifier)

        result.update(status="PASS", **digest)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
