import "./dashboard.css";

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

export function renderDashboard(container, data) {
  const dashboard = node("div", undefined, "dashboard");
  const { labels, periods, metrics, sections } = data;
  if (periods) dashboard.append(node("p", periods.current, "dashboard-period"));
  const tiles = node("dl", undefined, "dashboard-metrics");
  const comparisons = [];
  for (const metric of metrics) {
    const tile = node("div", undefined, "dashboard-tile");
    tile.append(node("dt", metric.label), node("dd", metric.value ?? "—"));
    if (periods?.previous && Object.hasOwn(metric, "previous")) {
      const earlier = node("dd", labels.previous + " · " + (metric.previous ?? "—"), "dashboard-previous");
      comparisons.push(earlier);
      tile.append(earlier);
    }
    tiles.append(tile);
  }
  if (comparisons.length) {
    const option = node("label", undefined, "dashboard-compare");
    const toggle = node("input");
    toggle.type = "checkbox";
    toggle.checked = true;
    toggle.addEventListener("change", () => {
      comparisons.forEach((row) => { row.hidden = !toggle.checked; });
      previousRange.hidden = !toggle.checked;
    });
    const previousRange = node("p", periods.previous, "dashboard-period");
    option.append(toggle, document.createTextNode(labels.compare));
    dashboard.append(option, previousRange);
  }
  dashboard.append(tiles);
  for (const section of sections) {
    const panel = node("details", undefined, "dashboard-section");
    panel.open = !section.collapsed;
    panel.append(node("summary", section.title));
    if (!section.rows.length) {
      panel.append(node("p", labels.empty, "dashboard-period"));
    } else {
      const table = node("table");
      table.setAttribute("aria-label", section.title);
      const header = node("tr");
      section.columns.forEach((label) => {
        const cell = node("th", label);
        cell.scope = "col";
        header.append(cell);
      });
      const head = node("thead");
      head.append(header);
      const body = node("tbody");
      for (const row of section.rows) {
        const line = node("tr");
        row.forEach((value) => line.append(node("td", value ?? "—")));
        body.append(line);
      }
      table.append(head, body);
      const scroll = node("div", undefined, "dashboard-table");
      scroll.append(table);
      panel.append(scroll);
    }
    dashboard.append(panel);
  }
  container.append(dashboard);
}
