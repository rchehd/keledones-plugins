from __future__ import annotations

import json
from datetime import date
from math import isfinite
from uuid import uuid4

import storage


PLACEHOLDER = '<script id="portrait-data" type="application/json">null</script>'
ASSET = storage.PLUGIN / "report/widget/portrait.html"


def model(digest, language, strings=None):
    locale = language or "en"

    def label(key, en, uk):
        if strings is not None:
            return strings[key]
        return uk if locale == "uk" else en

    def number(value):
        return value if type(value) in (int, float) and isfinite(value) else None

    def period_name(period):
        if not period:
            return None
        end = date.fromisoformat(period["end"]).isoformat()
        if period["start"]:
            return date.fromisoformat(period["start"]).isoformat() + " – " + end
        return label("metrics_all_through", "All history through {end}", "Уся історія до {end}").format(end=end)

    now, earlier = digest["current"], digest.get("previous") or {}
    metrics = []
    for key, caption in (
        ("sessions", label("sessions", "Sessions", "Сесії")),
        ("requests", label("requests", "Requests", "Запити")),
        ("active_days", label("active_days", "Active days", "Дні активності")),
        ("edit_sessions", label("metrics_edit_sessions", "Sessions with edits", "Сесії з правками")),
        ("checks_after_edit_sessions", label("metrics_checked_after_edit", "Checked after edits", "Перевірили після правок")),
    ):
        metrics.append(dict(label=caption, value=number(now["summary"].get(key)),
                            previous=number(earlier.get("summary", {}).get(key))))
    for key, caption in (
        ("clarity", label("clarity", "Request clarity", "Ясність запитів")),
        ("focus", label("focus", "Focus", "Фокус")),
        ("completion", label("completion", "Task completion", "Завершення задач")),
        ("tool_range", label("tool_range", "Tool range", "Різноманітність інструментів")),
    ):
        metrics.append(dict(label=caption, value=number((now.get("axes") or {}).get(key)),
                            previous=number((earlier.get("axes") or {}).get(key))))
    insights = [[caption, number(now["summary"].get(key))] for key, caption in (
        ("corrections", label("corrections", "Corrections", "Виправлення")),
        ("repeats", label("repeats", "Repeated requests", "Повторні запити")),
        ("interrupted", label("interrupted", "Interrupted turns", "Перервані відповіді")),
        ("compactions", label("compactions", "Context compactions", "Стиснення контексту")),
    )]
    return dict(locale=locale, title=label("metrics_title", "Gnothi work portrait", "Робочий портрет Gnothi"),
                summary=label("metrics_summary", "Aggregate metrics from the selected period.", "Агреговані метрики за вибраний період."),
                labels=dict(previous=label("metrics_previous", "Previous", "Попередній"),
                            compare=label("metrics_compare", "Compare with the previous period", "Порівняти з попереднім періодом"),
                            empty=label("metrics_empty", "No data for this period.", "За цей період немає даних.")),
                periods=dict(current=period_name(digest["period"]), previous=period_name(digest["period"].get("previous"))),
                metrics=metrics, sections=[dict(title=label("friction", "Friction", "Труднощі"),
                    columns=[label("metric", "Metric", "Метрика"), label("metrics_count", "Count", "Кількість")], rows=insights, collapsed=True)])


def prepare(digest, language, strings=None):
    data = model(digest, language, strings)
    asset = ASSET.read_text(encoding="utf-8")
    if asset.count(PLACEHOLDER) != 1:
        raise ValueError("Gnothi's packaged metrics report could not be loaded")
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    identifier = uuid4().hex
    root = storage.guard(storage.data_root())
    target = root / "reports" / f"dashboard-{identifier}.html"
    if target.resolve() != target:
        raise ValueError("The Gnothi metrics report requires a file in its private data folder")
    page = asset.replace(PLACEHOLDER, PLACEHOLDER.replace(">null<", ">" + encoded + "<", 1))
    storage.write_private(target, page)
    return {"widget_id": identifier, "widget_html": str(target)}
