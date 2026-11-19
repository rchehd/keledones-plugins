#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.dont_write_bytecode = True
from dependency_support import PLUGIN, bundle_path, data_root, installed
from feedback import recent as feedback_records
from project import BASE, ensure_excluded, toplevel
from reports import all_tasks

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


def summary(directory):
    try:
        data = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        rounds = [item for item in data.get("rounds", []) if isinstance(item, dict)]
    except (OSError, ValueError, AttributeError):
        return []

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


def task_record(item, feedback):
    directory = item["directory"]
    keys = key_lines(directory / "report.md")
    rounds = summary(directory)
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
    return dict(tasks=tasks, totals=totals, areas=areas.most_common(), returns_per_week=sorted(weeks.items()),
                feedback_reasons=reasons)


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


def render_html(digest):
    totals, tasks = digest["totals"], digest["tasks"]
    library = chart_source()
    charts = dict(
        rounds=dict(type="bar", labels=[short(task["task_id"]) for task in tasks], values=[task["rounds"] or 0 for task in tasks]),
        outcomes=dict(type="doughnut", labels=["Passed in round 1", "Confirmed defects", "Returned after review"],
                      values=[totals["passed_first_round"], totals["with_defects"], totals["returned"]]),
        areas=dict(type="bar", labels=[short(area) for area, _ in digest["areas"][:8]], values=[count for _, count in digest["areas"][:8]]),
        weeks=dict(type="line", labels=[week for week, _ in digest["returns_per_week"]],
                   values=[count for _, count in digest["returns_per_week"]]),
    )
    titles = dict(rounds="Rounds per task", outcomes="Task outcomes", areas="Top error areas", weeks="Returns per week")
    cards = "".join(f'<section class="card"><h2>{titles[name]}</h2><div class="chart"><canvas id="{name}"></canvas></div></section>'
                    for name in charts)
    totals_rows = [("Tasks", totals["tasks"]), ("Passed in round 1", totals["passed_first_round"]),
                   ("With confirmed defects", totals["with_defects"]), ("Returned after review", totals["returned"]),
                   ("Returned and missed by Ready Check", totals["returned_missed"]),
                   ("QA cases that failed because of the test", totals["qa_test_problems"]),
                   ("Tasks without round summaries", totals["without_summary"])]
    task_rows = [(task["task_id"], re.sub(r"-[0-9a-f]{12}$", "", task["branch"] or ""), task["date"] or "unknown", task["rounds"] or "unknown", task["verdict"],
                  "yes" if task["returned"] else "no", "; ".join(r for r in task["return_reasons"] if r) or "") for task in tasks]
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
        cards = "".join(f'<section class="card"><h2>{titles[name]}</h2>' +
                        table(["Label", "Value"], list(zip(chart["labels"], chart["values"]))) + "</section>"
                        for name, chart in charts.items())

    tiles = "".join(f'<div class="tile"><span>{html.escape(label)}</span><strong>{number}</strong></div>' for label, number in (
        ("Tasks", totals["tasks"]), ("Passed in round 1", totals["passed_first_round"]),
        ("Returned after review", totals["returned"]), ("Missed by Ready Check", totals["returned_missed"])))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<title>Ready Check overview</title>
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
<header><div class="eyebrow">Ready Check</div><h1>Task overview</h1>
<p class="muted">Generated {date.today().isoformat()} from {totals["tasks"]} tasks.</p></header>
<div class="tiles">{tiles}</div>
<section class="card" style="margin-bottom:16px"><h2>Totals</h2>{table(["Metric", "Value"], totals_rows, "totals")}</section>
<div class="grid">{cards}</div>
<section class="card"><h2>Tasks</h2>{table(["Task", "Branch", "Date", "Rounds", "Verdict", "Returned", "Reason"], task_rows, "tasks")}</section>
<footer>Local, confidential report generated on this machine. It loads nothing from the network; do not publish or share it.</footer>
</main>{script}</body></html>
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Collect Ready Check task history, statistics and an optional HTML overview.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()
    result = dict(schema_version=1, action="reflect-collect", status="FAIL")

    try:
        top = toplevel(args.project)

        if not top:
            raise ValueError("reflect-collect needs a Git work tree")

        digest = collect(top, max(args.tasks, 1))

        if args.html:
            path = top / BASE / "reflect" / f"overview-{date.today().isoformat()}.html"
            ensure_excluded(top)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_html(digest), encoding="utf-8")
            digest["html"] = str(path)

        result.update(status="PASS", **digest)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
