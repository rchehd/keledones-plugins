import { App } from "@modelcontextprotocol/ext-apps";
import "@awesome.me/webawesome/dist/styles/webawesome.css";
import "@awesome.me/webawesome/dist/styles/themes/awesome.css";
import "@awesome.me/webawesome/dist/components/badge/badge.js";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/checkbox/checkbox.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "@awesome.me/webawesome/dist/components/option/option.js";
import "@awesome.me/webawesome/dist/components/select/select.js";
import "@awesome.me/webawesome/dist/components/textarea/textarea.js";
import "./ui.css";

const main = document.getElementById("ready-check");
const token = location.hash.slice(1);
const inApp = window.parent !== window;
const app = inApp ? new App({ name: "Ready Check", version: "1.0.0" }) : null;
const systemColor = matchMedia("(prefers-color-scheme: dark)");
const strings = {
  en: {
    qaPlan: "QA plan", qaResults: "QA results", review: "Review findings", settings: "Ready Check settings",
    round: "Round", revision: "Revision", required: "Required", optional: "Optional", expected: "Expected",
    actual: "Actual", approve: "Approve plan", revise: "Submit changes", cancel: "Cancel QA",
    edits: "Changes to this scenario", additions: "Add a scenario", charter: "Exploratory charter",
    environment: "Environment", preconditions: "Preconditions", execution: "Execution",
    testData: "Test data", cleanup: "Cleanup", recordingScope: "Recording scope and retention",
    pendingEdits: "Submit your changes first so you can approve the next revision.",
    record: "Approve recording", inspect: "View evidence", saved: "Decision saved. Return to the chat to continue.",
    loading: "Opening Ready Check…", unavailable: "The view could not be loaded.", artifact: "Open evidence",
    copyEvidenceUrl: "Copy this local address to open the evidence in your browser.",
    staleEvidence: "The evidence could not be loaded. Reopen the current QA round.",
    retest: "Retest", draft: "Draft comment", falsePositive: "False positive", reason: "Reason",
    triage: "Save decisions", fix: "Fix", accept: "Accept risk", outside: "Out of scope", choose: "Choose action",
    browser: "Browser mode", reminders: "Check reminders", capture: "Capture task context", save: "Save",
    connect: "Connect PhpStorm MCP", disable: "Disable integration", enabled: "Enabled", off: "Off",
    unverified: "The agent can verify IDE availability in the current client.",
    available: "IDE inspection is available.", notAvailable: "IDE inspection is unavailable in this client.",
    connectSaved: "Connection requested. Return to the chat to complete PhpStorm setup.",
    pendingConnection: "Connection requested", cancelConnection: "Cancel request",
    ask: "Ask", visible: "Visible", background: "Background",
    all: "All", status: "Status", severity: "Severity", file: "File",
    selected: "Selected", hiddenByFilter: "hidden by filter",
  },
  uk: {
    qaPlan: "План QA", qaResults: "Результати QA", review: "Знахідки рев’ю", settings: "Налаштування Ready Check",
    round: "Раунд", revision: "Ревізія", required: "Обов’язковий", optional: "Опційний", expected: "Очікувано",
    actual: "Фактично", approve: "Затвердити план", revise: "Надіслати правки", cancel: "Скасувати QA",
    edits: "Правки до сценарію", additions: "Додати сценарій", charter: "План дослідницької сесії",
    environment: "Середовище", preconditions: "Передумови", execution: "Спосіб запуску",
    testData: "Тестові дані", cleanup: "Прибирання", recordingScope: "Обсяг і зберігання запису",
    pendingEdits: "Спершу надішли правки, щоб затвердити наступну ревізію.",
    record: "Дозволити запис", inspect: "Переглянути докази", saved: "Рішення збережено. Повернися в чат, щоб продовжити.",
    loading: "Відкриваємо Ready Check…", unavailable: "Не вдалося відкрити екран.", artifact: "Відкрити доказ",
    copyEvidenceUrl: "Скопіюй цю локальну адресу, щоб відкрити доказ у браузері.",
    staleEvidence: "Не вдалося завантажити доказ. Відкрий поточний раунд QA ще раз.",
    retest: "Перетестувати", draft: "Підготувати коментар", falsePositive: "Хибне спрацювання", reason: "Причина",
    triage: "Зберегти рішення", fix: "Виправити", accept: "Прийняти ризик", outside: "Поза межами задачі", choose: "Обрати дію",
    browser: "Режим браузера", reminders: "Нагадування про перевірку", capture: "Зберігати контекст задачі",
    save: "Зберегти", connect: "Підключити PhpStorm MCP", disable: "Вимкнути інтеграцію", enabled: "Увімкнено",
    off: "Вимкнено", unverified: "Агент може перевірити доступність IDE в поточному клієнті.",
    available: "Інспекції IDE доступні.", notAvailable: "Інспекції IDE недоступні в цьому клієнті.",
    connectSaved: "Запит збережено. Повернися в чат, щоб завершити підключення PhpStorm.",
    pendingConnection: "Очікує підключення", cancelConnection: "Скасувати запит",
    ask: "Запитувати", visible: "Видимий", background: "Фоновий",
    all: "Усі", status: "Статус", severity: "Серйозність", file: "Файл",
    selected: "Вибрано", hiddenByFilter: "приховано фільтром",
  },
};
let labels = strings[navigator.language.startsWith("uk") ? "uk" : "en"];
let state;
let status;
let busy = false;
let saved = false;

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined && text !== null) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function button(text, action, primary = false) {
  const item = element("wa-button", text);
  item.type = "button";
  item.size = "small";
  item.variant = primary ? "brand" : "neutral";
  item.appearance = primary ? "accent" : "outlined";
  item.addEventListener("click", action);
  return item;
}

function field(text, input, className = "action-field") {
  input.classList.add(className);
  if (input.localName === "wa-checkbox") input.textContent = text;
  else input.label = text;
  return input;
}

function checkbox(checked = false, disabled = false) {
  const input = element("wa-checkbox");
  input.size = "small";
  input.checked = checked;
  input.disabled = disabled;
  return input;
}

function textarea() {
  const input = element("wa-textarea");
  input.size = "small";
  input.rows = 2;
  input.maxLength = 4000;
  return input;
}

function select(options) {
  const list = element("wa-select");
  list.size = "small";
  options.forEach(([value, caption]) => {
    const option = element("wa-option", caption);
    option.value = value;
    list.append(option);
  });
  list.value = options[0]?.[0];
  return list;
}

function surface() {
  const card = element("wa-card", undefined, "card");
  card.appearance = "outlined";
  return card;
}

function badge(label) {
  const flag = element("wa-badge", label);
  const variants = { pass: "success", fail: "danger", blocked: "danger", critical: "danger",
    error: "danger", warning: "warning", incomplete: "warning" };
  flag.variant = variants[String(label).toLowerCase()] || "neutral";
  flag.appearance = "filled";
  return flag;
}

function message(text, error = false) {
  status.classList.toggle("error", error);
  status.textContent = text;
}

function facts(card, caption, value) {
  if (!value) return;
  const line = element("p");
  if (Array.isArray(value)) {
    if (!value.length) return;
    line.append(element("strong", caption));
    card.append(line);
    const list = element("ul");
    value.forEach((item) => list.append(element("li", item)));
    card.append(list);
    return;
  }
  line.append(element("strong", caption + " · "), document.createTextNode(String(value)));
  card.append(line);
}

function heading(row, extra) {
  const card = surface();
  const top = element("div", undefined, "heading");
  const title = element("div");
  title.append(element("h2", [row.id, row.title].filter(Boolean).join(" · ")));
  const meta = [row.role, row.risk, row.source, row.file && [row.file, row.line].filter(Boolean).join(":"),
    row.elapsed, row.classification, row.blocking && "BLOCKED",
    ...(Array.isArray(row.requirements) ? row.requirements : [])].filter(Boolean);
  if (meta.length) title.append(element("small", meta.join(" · ")));
  top.append(title);
  if (extra) top.append(extra);
  card.append(top);
  return card;
}

function steps(card, values) {
  if (!Array.isArray(values) || !values.length) return;
  const list = element("ol");
  values.forEach((value) => list.append(element("li", value)));
  card.append(list);
}

function actions(pane, items) {
  const footer = element("div", undefined, "actions");
  items.forEach((item) => footer.append(item));
  pane.append(footer);
}

function filters(pane, rows, items, fields, onChange) {
  const bar = element("div", undefined, "filters");
  const controls = [];
  for (const [label, values] of fields) {
    const choices = [...new Set(items.flatMap(({ row }) => values(row)).filter(Boolean))].sort();
    if (!choices.length) continue;
    const input = select([["all", labels.all], ...choices.map((choice, index) => [String(index), choice])]);
    controls.push({ input, values, choices });
    input.addEventListener("change", () => {
      items.forEach(({ card, row }) => {
        card.hidden = !controls.every((control) => control.input.value === "all"
          || control.values(row).includes(control.choices[Number(control.input.value)]));
      });
      onChange();
    });
    bar.append(field(label, input, "choice"));
  }
  if (controls.length) pane.insertBefore(bar, rows);
}

function selectionSummary(pane, items, selected, describe) {
  const summary = element("p", undefined, "meta selection");
  summary.setAttribute("role", "status");
  pane.append(summary);
  const update = () => {
    const choices = selected().map((item) => describe(item) + (item.card.hidden ? " (" + labels.hiddenByFilter + ")" : ""));
    summary.textContent = choices.length ? labels.selected + " · " + choices.join(", ") : "";
  };
  for (const item of items) item.control.addEventListener("change", update);
  return update;
}

function qaPlan(pane, rows, data) {
  const inputs = [];
  for (const row of data.scenarios) {
    const include = checkbox(true, row.required);
    const checked = field(row.required ? labels.required : labels.optional, include, "choice");
    if (row.required && row.required_reason) checked.title = row.required_reason;
    const card = heading(row, checked);
    facts(card, labels.environment, row.environment);
    facts(card, labels.preconditions, row.preconditions);
    facts(card, labels.execution, row.execution);
    facts(card, labels.testData, row.test_data);
    steps(card, row.steps);
    facts(card, labels.expected, row.expected);
    facts(card, labels.cleanup, row.cleanup);
    facts(card, labels.recordingScope, row.recording_scope);
    if (row.evidence) card.append(element("small", row.evidence));
    let recording;
    if (row.recording) {
      recording = checkbox();
      card.append(field(labels.record + " · " + row.recording, recording, "choice"));
      include.addEventListener("change", () => {
        recording.disabled = !include.checked;
        if (!include.checked) recording.checked = false;
      });
    }
    const edit = textarea();
    card.append(field(labels.edits, edit));
    rows.append(card);
    inputs.push({ id: row.id, include, edit, recording });
  }
  const additions = textarea();
  const charter = textarea();
  charter.value = data.charter || "";
  pane.append(field(labels.additions, additions), field(labels.charter, charter));
  const edits = () => Object.fromEntries(inputs.filter((row) => row.edit.value.trim()).map((row) => [row.id, row.edit.value]));
  const changedCharter = () => charter.value !== (data.charter || "");
  actions(pane, [
    button(labels.approve, () => {
      if (Object.keys(edits()).length || additions.value.trim() || changedCharter()) {
        message(labels.pendingEdits, true);
        return;
      }
      submit({
        action: "approve", selected: inputs.filter((row) => row.include.checked).map((row) => row.id),
        recordings: inputs.filter((row) => row.recording?.checked).map((row) => row.id),
      });
    }, true),
    button(labels.revise, () => submit({
      action: "revise", additions: additions.value, edits: edits(),
      ...(changedCharter() ? { charter: charter.value } : {}),
    })),
    button(labels.cancel, () => submit({ action: "cancel" })),
  ]);
}

function openImage(src, title) {
  const dialog = element("wa-dialog");
  dialog.label = title;
  dialog.className = "preview";
  const image = element("img");
  image.src = src;
  image.alt = title;
  dialog.append(image);
  dialog.addEventListener("wa-after-hide", () => dialog.remove(), { once: true });
  document.body.append(dialog);
  dialog.open = true;
}

function artifact(card, asset) {
  const row = element("div", undefined, "evidence");
  const title = asset.title || labels.artifact;
  const isImage = /\.(png|jpe?g|webp|gif)$/i.test(asset.path);
  if (inApp) {
    const fallback = element("p", undefined, "meta");
    fallback.hidden = true;
    row.append(button(title, async () => {
      fallback.hidden = true;
      message("");
      let url;
      try {
        if (isImage) {
          const preview = await appTool("preview_image", { path: asset.path });
          if (!preview.open_local) {
            openImage("data:" + preview.mimeType + ";base64," + preview.data, title);
            return;
          }
        }
        ({ url } = await appTool("local_view", {}));
        const result = await app.openLink({ url });
        if (!result.isError) return;
      } catch (error) {
        if (!url) {
          message(error.message, true);
          return;
        }
      }
      fallback.textContent = url;
      fallback.hidden = false;
      message(labels.copyEvidenceUrl);
    }), fallback);
  } else {
    const url = "/asset?" + new URLSearchParams({ name: asset.path, access: token, revision: state.revision });
    if (/\.(mp4|webm)$/i.test(asset.path)) {
      const player = element("video");
      player.controls = true;
      player.preload = "metadata";
      player.src = url;
      player.setAttribute("aria-label", title);
      player.addEventListener("error", () => message(labels.staleEvidence, true));
      row.append(player);
      const chapters = Array.isArray(asset.chapters) ? asset.chapters : [];
      chapters.filter((chapter) => Number.isFinite(chapter.start) && chapter.start >= 0)
        .forEach((chapter) => row.append(button(chapter.title, () => { player.currentTime = chapter.start; })));
    } else {
      const link = element("a", title);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      if (isImage) {
        const image = element("img");
        image.alt = title;
        image.loading = "lazy";
        image.src = url;
        image.addEventListener("error", () => message(labels.staleEvidence, true));
        link.replaceChildren(image);
        link.addEventListener("click", (event) => {
          event.preventDefault();
          openImage(url, title);
        });
      }
      row.append(link);
    }
  }
  card.append(row);
}

function qaResults(pane, rows, data) {
  const items = [];
  for (const result of data.scenarios) {
    const include = checkbox();
    const card = heading(result, field(result.id, include, "choice"));
    card.append(badge(result.status));
    steps(card, result.steps);
    facts(card, labels.expected, result.expected);
    facts(card, labels.actual, result.actual);
    for (const asset of result.artifacts || []) artifact(card, asset);
    rows.append(card);
    items.push({ id: result.id, control: include, card, row: result });
  }
  const reason = textarea();
  pane.append(field(labels.reason, reason));
  const selected = () => items.filter((item) => item.control.checked);
  const update = selectionSummary(pane, items, selected, (item) => item.id);
  filters(pane, rows, items, [[labels.status, (row) => [row.status]], ["RC", (row) => row.requirements || []]], update);
  actions(pane, [["retest", labels.retest], ["draft", labels.draft], ["false-positive", labels.falsePositive]]
    .map(([action, caption]) => button(caption, () => submit({
      action, selected: selected().map((item) => item.id), reason: reason.value,
    }))));
}

function review(pane, rows, data) {
  const items = [];
  const choices = { none: labels.choose, fix: labels.fix, "accept-risk": labels.accept,
    "false-positive": labels.falsePositive, "out-of-scope": labels.outside };
  for (const row of data.findings) {
    const card = heading(row, badge(row.severity));
    if (row.description) card.append(element("p", row.description));
    if (row.snippet) card.append(element("pre", row.snippet));
    const action = select(Object.entries(choices));
    const reason = textarea();
    card.append(field(labels.choose, action), field(labels.reason, reason));
    rows.append(card);
    items.push({ id: row.id, control: action, reason, card, row });
  }
  const selected = () => items.filter((item) => item.control.value && item.control.value !== "none");
  const update = selectionSummary(pane, items, selected, (item) => item.id + " · " + choices[item.control.value]);
  filters(pane, rows, items, [[labels.severity, (row) => [row.severity]], [labels.file, (row) => [row.file]]], update);
  actions(pane, [button(labels.triage, () => submit({
    action: "triage",
    rows: selected().map((item) => ({
      id: item.id, action: item.control.value, reason: item.reason.value,
    })),
  }), true)]);
}

function settings(pane, rows, data) {
  const browser = select([["ask", labels.ask], ["visible", labels.visible], ["background", labels.background]]);
  browser.value = data.browser;
  const options = [
    ["browser", labels.browser, browser, () => browser.value],
    ["remind", labels.reminders, checkbox(data.remind), (input) => input.checked],
    ["captureTasks", labels.capture, checkbox(data.captureTasks), (input) => input.checked],
  ];
  for (const [key, label, input, value] of options) {
    const card = surface();
    const layout = element("div", undefined, "setting");
    layout.append(field(label, input, "choice"), button(labels.save, () => submit({ action: "set", key, value: value(input) })));
    card.append(layout);
    rows.append(card);
  }
  const card = surface();
  const layout = element("div", undefined, "setting");
  const description = element("div");
  const availability = { available: labels.available, unavailable: labels.notAvailable };
  const connection = data.phpstormMcp ? labels.enabled : data.phpstormPending ? labels.pendingConnection : labels.off;
  description.append(element("h2", "PhpStorm MCP"), element("p", connection),
    element("small", data.phpstormPending ? labels.connectSaved : availability[data.ideStatus] || labels.unverified));
  const control = data.phpstormMcp || data.phpstormPending ?
    button(data.phpstormMcp ? labels.disable : labels.cancelConnection,
      () => submit({ action: "set", key: "phpstormMcp", value: false })) :
    button(labels.connect, () => submit({ action: "connect-phpstorm" }), true);
  layout.append(description, control);
  card.append(layout);
  rows.append(card);
}

const screens = {
  "qa-plan": [qaPlan, "qaPlan"], "qa-results": [qaResults, "qaResults"],
  review: [review, "review"], settings: [settings, "settings"],
};

function render(value) {
  state = value;
  saved = ["qa-plan", "review"].includes(value.view) && Boolean(value.decision);
  const locale = value.data.locale === "uk" ? "uk" : value.data.locale === "en" ? "en" : document.documentElement.lang;
  document.documentElement.lang = locale;
  labels = strings[locale] || labels;
  const [screen, title] = screens[value.view];
  const pane = element("section");
  const header = element("header");
  header.append(element("h1", labels[title]));
  const data = value.data;
  const meta = [data.title, data.status, data.round && labels.round + " " + data.round,
    data.qa_plan_revision && labels.revision + " " + data.qa_plan_revision].filter(Boolean);
  if (meta.length) header.append(element("p", meta.join(" · "), "meta"));
  if (data.coverage) header.append(element("p", data.coverage, "meta"));
  if (data.limitations) header.append(element("p", data.limitations, "meta"));
  const rows = element("div", undefined, "rows");
  pane.append(header, rows);
  screen(pane, rows, data);
  status = element("p", saved ? labels.saved : "", "status");
  status.setAttribute("role", "status");
  pane.append(status);
  main.replaceChildren(pane);
  main.setAttribute("aria-busy", "false");
}

async function request(path, value) {
  const options = { headers: { Authorization: "Bearer " + token } };
  if (value) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(value);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || labels.unavailable);
  return result;
}

async function submit(value) {
  if (busy || saved) return;
  busy = true;
  message("");
  try {
    const decision = { ...value, revision: state.revision };
    const result = inApp ? await appTool("submit_decision", { decision }) : await request("/decision", decision);
    const connecting = value.action === "connect-phpstorm";
    if (state.view === "settings") render({ ...result, handle: state.handle });
    else saved = state.view !== "qa-results";
    message(connecting ? labels.connectSaved : labels.saved);
    const requestId = connecting && result.data.phpstormRequestId;
    if (inApp && (state.view !== "settings" || requestId)) {
      const text = requestId ? "A Ready Check settings request " + requestId
        + " was saved. Read the settings decision and continue only if that request is still pending." :
        "A Ready Check " + state.view + " decision was saved for task " + state.task + ". Read the saved decision.";
      app.sendMessage({ role: "user", content: [{ type: "text", text }] }).catch(() => {});
    }
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
  }
}

async function appTool(name, args) {
  const result = await app.callServerTool({ name, arguments: { ...args, handle: state.handle } });
  if (result.isError) throw new Error(result.content?.[0]?.text || labels.unavailable);
  return result.structuredContent;
}

function applyTheme(theme) {
  const dark = theme ? theme === "dark" : systemColor.matches;
  document.documentElement.classList.toggle("wa-dark", dark);
  document.documentElement.classList.toggle("wa-light", !dark);
}

async function openApp() {
  app.ontoolresult = ({ structuredContent }) => {
    if (structuredContent?.view) render(structuredContent);
  };
  app.onhostcontextchanged = (context) => applyTheme(context.theme ?? app.getHostContext()?.theme);
  app.onteardown = async () => ({});
  await app.connect();
  applyTheme(app.getHostContext()?.theme);
}

document.documentElement.lang = navigator.language.startsWith("uk") ? "uk" : "en";
applyTheme();
systemColor.addEventListener("change", () => applyTheme(app?.getHostContext()?.theme));
main.append(element("p", labels.loading, "status"));
(inApp ? openApp() : request("/state").then(render)).catch((error) => {
  main.replaceChildren(element("p", error.message || labels.unavailable, "status error"));
  main.setAttribute("aria-busy", "false");
});
