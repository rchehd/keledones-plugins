from __future__ import annotations

import json
import re
from datetime import date
from math import isfinite
from uuid import uuid4

import storage


PLACEHOLDER = '<script id="portrait-data" type="application/json">null</script>'
ASSET = storage.PLUGIN / "report/widget/portrait.html"


def model(digest, language):
    locale = "uk" if language == "uk" else "en"

    def label(en, uk):
        return uk if locale == "uk" else en

    def number(value):
        return value if type(value) in (int, float) and isfinite(value) else None

    def period_name(period):
        if not period:
            return None
        end = date.fromisoformat(period["end"]).isoformat()
        if period["start"]:
            return date.fromisoformat(period["start"]).isoformat() + " – " + end
        return label("All history through ", "Уся історія до ") + end

    now, earlier = digest["current"], digest.get("previous") or {}
    metrics = []
    for key, caption in (
        ("sessions", label("Sessions", "Сесії")),
        ("requests", label("Requests", "Запити")),
        ("active_days", label("Active days", "Дні активності")),
        ("edit_sessions", label("Sessions with edits", "Сесії з правками")),
        ("checks_after_edit_sessions", label("Checked after edits", "Перевірили після правок")),
    ):
        metrics.append(dict(label=caption, value=number(now["summary"].get(key)),
                            previous=number(earlier.get("summary", {}).get(key))))
    for key, caption in (
        ("clarity", label("Request clarity", "Ясність запитів")),
        ("focus", label("Focus", "Фокус")),
        ("completion", label("Task completion", "Завершення задач")),
        ("tool_range", label("Tool range", "Різноманітність інструментів")),
    ):
        metrics.append(dict(label=caption, value=number((now.get("axes") or {}).get(key)),
                            previous=number((earlier.get("axes") or {}).get(key))))
    insights = [[caption, number(now["summary"].get(key))] for key, caption in (
        ("corrections", label("Corrections", "Виправлення")),
        ("repeats", label("Repeated requests", "Повторні запити")),
        ("interrupted", label("Interrupted turns", "Перервані відповіді")),
        ("compactions", label("Context compactions", "Стиснення контексту")),
    )]
    return dict(locale=locale, title=label("Gnothi work portrait", "Робочий портрет Gnothi"),
                summary=label("Aggregate metrics from the selected period.", "Агреговані метрики за вибраний період."),
                labels=dict(previous=label("Previous", "Попередній"),
                            compare=label("Compare with the previous period", "Порівняти з попереднім періодом"),
                            empty=label("No data for this period.", "За цей період немає даних.")),
                periods=dict(current=period_name(digest["period"]), previous=period_name(digest["period"].get("previous"))),
                metrics=metrics, sections=[dict(title=label("Friction", "Труднощі"),
                    columns=[label("Metric", "Метрика"), label("Count", "Кількість")], rows=insights, collapsed=True)])


def prepare(digest, language):
    data = model(digest, language)
    asset = ASSET.read_text(encoding="utf-8")
    if asset.count(PLACEHOLDER) != 1:
        raise ValueError("Gnothi's packaged widget could not be loaded")
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    identifier = uuid4().hex
    source, target = widget_paths(identifier)
    page = asset.replace(PLACEHOLDER, PLACEHOLDER.replace(">null<", ">" + encoded + "<", 1))
    storage.write_private(target, page)
    storage.write_private(source, encoded)
    return {"widget_id": identifier, "widget_html": str(target)}


def widget_paths(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Select an approved Gnothi metrics view")
    root = storage.guard(storage.data_root())
    source = root / "tmp" / f"dashboard-{identifier}.json"
    target = root / "reports" / f"dashboard-{identifier}.html"
    if any(path.resolve() != path for path in (source, target)):
        raise ValueError("The Gnothi metrics view requires files in its private data folder")
    return source, target


def load(identifier):
    source, target = widget_paths(identifier)
    if not source.is_file() or not target.is_file():
        raise ValueError("The Gnothi metrics view is unavailable. Prepare it again after approval.")
    return json.loads(source.read_text(encoding="utf-8")), str(target)
