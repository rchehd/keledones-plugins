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
    with_summary = [task for task in tasks if task["has_summary"]]
    labels = Counter(finding.get("label", "unknown") for task in tasks for finding in task["findings"])
    areas = Counter(finding.get("area") or "unknown" for task in tasks for finding in task["findings"])
    weeks = Counter()

    for record in feedback:
        if record.get("returned") and record.get("task") in {task["task_id"] for task in tasks}:
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
                    missed=record.get("missed")) for record in feedback if record.get("returned")]
    return dict(tasks=tasks, totals=totals, areas=areas.most_common(), returns_per_week=sorted(weeks.items()),
                feedback_reasons=reasons)


def chart_source():
    source = PLUGIN / "dependencies/browser"
    folder = bundle_path(source, data_root(), "browser")
    path = folder / "node_modules/chart.js/dist/chart.umd.min.js"
    return path.read_text(encoding="utf-8") if installed(source, folder) and path.is_file() else None


def table(headers, rows):
    head = "".join(f"<th>{html.escape(str(cell))}</th>" for cell in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(digest):
    totals, tasks = digest["totals"], digest["tasks"]
    library = chart_source()
    charts = dict(
        rounds=dict(type="bar", labels=[task["task_id"] for task in tasks], values=[task["rounds"] or 0 for task in tasks]),
        outcomes=dict(type="doughnut", labels=["Passed in round 1", "Confirmed defects", "Returned after review"],
                      values=[totals["passed_first_round"], totals["with_defects"], totals["returned"]]),
        areas=dict(type="bar", labels=[area for area, _ in digest["areas"][:8]], values=[count for _, count in digest["areas"][:8]]),
        weeks=dict(type="line", labels=[week for week, _ in digest["returns_per_week"]],
                   values=[count for _, count in digest["returns_per_week"]]),
    )
    titles = dict(rounds="Rounds per task", outcomes="Task outcomes", areas="Top error areas", weeks="Returns per week")
    cards = "".join(f'<section class="card"><h2>{titles[name]}</h2><canvas id="{name}"></canvas></section>' for name in charts)
    totals_rows = [("Tasks", totals["tasks"]), ("Passed in round 1", totals["passed_first_round"]),
                   ("With confirmed defects", totals["with_defects"]), ("Returned after review", totals["returned"]),
                   ("Returned and missed by Ready Check", totals["returned_missed"]),
                   ("QA cases that failed because of the test", totals["qa_test_problems"]),
                   ("Tasks without round summaries", totals["without_summary"])]
    task_rows = [(task["task_id"], task["branch"], task["date"] or "unknown", task["rounds"] or "unknown", task["verdict"],
                  "yes" if task["returned"] else "no", "; ".join(r for r in task["return_reasons"] if r) or "") for task in tasks]
    script = ""

    if library:
        data = json.dumps(charts).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        script = f"<script>{library}</script><script>const DATA = {data};" + """
const css = getComputedStyle(document.documentElement);
const color = css.getPropertyValue('--accent').trim(), text = css.getPropertyValue('--text').trim();
const palette = ['#16794C', '#C2410C', '#2563EB', '#9333EA', '#0F766E', '#B45309', '#BE123C', '#4D7C0F'];
Chart.defaults.color = text;
for (const [id, c] of Object.entries(DATA)) {
  new Chart(document.getElementById(id), {
    type: c.type,
    data: { labels: c.labels, datasets: [{ data: c.values, backgroundColor: c.type === 'doughnut' ? palette : color,
            borderColor: color, tension: 0.3 }] },
    options: { plugins: { legend: { display: c.type === 'doughnut' } }, indexAxis: id === 'areas' ? 'y' : 'x',
               scales: c.type === 'doughnut' ? {} : { x: { beginAtZero: true, ticks: { autoSkip: false, precision: 0 } }, y: { beginAtZero: true, ticks: { precision: 0 } } } }
  });
}
</script>"""
    else:
        cards = "".join(f'<section class="card"><h2>{titles[name]}</h2>' +
                        table(["Label", "Value"], list(zip(chart["labels"], chart["values"]))) + "</section>"
                        for name, chart in charts.items())

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ready Check overview</title>
<style>
:root {{ --bg: #f7f8f6; --card: #ffffff; --text: #1d2420; --muted: #5d6762; --line: #dde3df; --accent: #16794C; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #111614; --card: #1a211e; --text: #e6ece8; --muted: #9aa6a0; --line: #2c3631; --accent: #3fb97f; }} }}
body {{ margin: 0; padding: 24px 16px; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; }} h1 {{ margin: 0 0 4px; }} p.muted {{ color: var(--muted); margin: 0 0 24px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 16px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; overflow-x: auto; }}
h2 {{ font-size: 16px; margin: 0 0 12px; }} table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }} th {{ color: var(--muted); font-weight: 600; }} td:not(:last-child) {{ white-space: nowrap; }}
</style></head><body><main>
<h1>Ready Check overview</h1><p class="muted">Generated {date.today().isoformat()} from {totals["tasks"]} tasks.</p>
<section class="card" style="margin-bottom:16px"><h2>Totals</h2>{table(["Metric", "Value"], totals_rows)}</section>
<div class="grid">{cards}</div>
<section class="card"><h2>Tasks</h2>{table(["Task", "Branch", "Date", "Rounds", "Verdict", "Returned", "Reason"], task_rows)}</section>
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
