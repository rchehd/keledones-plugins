import "@awesome.me/webawesome/dist/styles/webawesome.css";
import "@awesome.me/webawesome/dist/styles/themes/awesome.css";
import "@awesome.me/webawesome/dist/components/badge/badge.js";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "@awesome.me/webawesome/dist/translations/ru.js";
import "@awesome.me/webawesome/dist/translations/uk.js";
import "./ui.css";
import strings from "./qa-labels.json";
import { renderDashboard } from "./dashboard.js";

const main = document.getElementById("ready-check");
const token = location.hash.slice(1);
const systemColor = matchMedia("(prefers-color-scheme: dark)");
function displayLocale(locale) {
  const language = typeof locale === "string" ? locale.toLowerCase().split("-")[0] : "";
  return Object.hasOwn(strings, language) ? language : "en";
}

let labels = strings[displayLocale(navigator.language)];
let state;
let status;

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined && text !== null) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function statusLabel(statusCode) {
  return labels.statuses?.[statusCode] ?? statusCode;
}

function scenarioLabel(options, value) {
  if (typeof value !== "string") return;
  const key = value.trim().toLowerCase();
  return Object.hasOwn(options, key) ? options[key] : undefined;
}

function button(text, action) {
  const item = element("wa-button", text);
  item.type = "button";
  item.size = "small";
  item.appearance = "outlined";
  item.addEventListener("click", action);
  return item;
}

function message(text, error = false) {
  status.classList.toggle("error", error);
  status.textContent = text;
}

function facts(card, caption, value, className = "qa-fact") {
  if (!value || (Array.isArray(value) && !value.length)) return;
  const line = element("p", undefined, className);
  line.append(element("strong", caption), element("span", Array.isArray(value) ? value.join(" · ") : value));
  card.append(line);
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

function addVideo(row, asset, src, title, onError) {
  const player = element("video");
  player.controls = true;
  player.playsInline = true;
  player.preload = "metadata";
  player.setAttribute("aria-label", title);
  player.addEventListener("error", onError, { once: true });
  player.src = src;
  row.replaceChildren(element("strong", title), player);
  const chapters = Array.isArray(asset.chapters) ? asset.chapters : [];
  for (const chapter of chapters) {
    if (Number.isFinite(chapter.start) && chapter.start >= 0) {
      row.append(button(chapter.title, () => { player.currentTime = chapter.start; }));
    }
  }
}

function isScreenshot(asset) {
  return /\.(png|jpe?g|webp|gif)$/i.test(asset.path);
}

function isRecording(asset) {
  return /\.(mp4|webm)$/i.test(asset.path);
}

function localAssetUrl(asset) {
  return "/asset?" + new URLSearchParams({ name: asset.path, access: token, revision: state.revision });
}

function screenshotButton(url, title) {
  const control = element("button", undefined, "screenshot-preview");
  control.type = "button";
  const image = element("img");
  image.alt = title;
  image.loading = "lazy";
  image.addEventListener("error", () => message(labels.staleEvidence, true), { once: true });
  image.src = url;
  control.append(image);
  control.addEventListener("click", () => openImage(url, title));
  return control;
}

function screenshotFigure(title, view) {
  const figure = element("figure", undefined, "screenshot-figure");
  figure.append(element("figcaption", title), view);
  return figure;
}

function screenshotPair(card, assets) {
  const row = element("div", undefined, "evidence");
  const pair = element("div", undefined, "screenshot-pair");
  for (const [index, asset] of assets.entries()) {
    const title = asset.title || labels.screenshot + " " + (index + 1);
    pair.append(screenshotFigure(title, screenshotButton(localAssetUrl(asset), title)));
  }
  row.append(pair);
  card.append(row);
}

function artifact(card, asset) {
  const row = element("div", undefined, "evidence");
  const title = asset.title || labels.artifact;
  const url = localAssetUrl(asset);
  if (isRecording(asset)) {
    addVideo(row, asset, url, title, () => message(labels.staleEvidence, true));
  } else if (isScreenshot(asset)) {
    row.append(screenshotButton(url, title));
  } else {
    const link = element("a", title);
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    row.append(link);
  }
  card.append(row);
}

function qaResults(rows, data) {
  const scenarios = [...data.scenarios].sort((first, second) => Number(second.status === "FAIL") - Number(first.status === "FAIL"));
  for (const result of scenarios) {
    const card = element("wa-card", undefined, "card");
    card.appearance = "outlined";
    const heading = element("div", undefined, "heading");
    const title = element("h2", [result.id, result.title].filter(Boolean).join(" · "));
    const tags = [
      scenarioLabel(labels.scenarioKinds, result.kind),
      scenarioLabel(labels.scenarioCategories, result.category),
    ].filter(Boolean);
    if (tags.length) title.append(" ", element("span", "[" + tags.join("; ") + "]", "qa-tags"));
    heading.append(title);
    if (result.status) {
      card.dataset.status = result.status;
      const badge = element("wa-badge", statusLabel(result.status));
      const variants = { PASS: "success", FAIL: "danger", BLOCKED: "danger", INCOMPLETE: "warning" };
      badge.variant = variants[result.status] || "neutral";
      badge.appearance = "filled";
      heading.append(badge);
    }
    card.append(heading);
    facts(card, labels.expected, result.expected);
    facts(card, labels.actual, result.actual, "qa-fact qa-actual");
    const assets = result.artifacts || [];
    const screenshots = assets.filter(isScreenshot);
    const hasPair = screenshots.length === 2;
    if (hasPair) screenshotPair(card, screenshots);
    for (const asset of hasPair ? assets.filter((asset) => !isScreenshot(asset)) : assets) {
      artifact(card, asset);
    }
    if (!assets.length) card.append(element("small", labels.noMedia));
    rows.append(card);
  }
}

function showError(text) {
  state = undefined;
  main.replaceChildren(element("p", text || labels.unavailable, "status error"));
  main.setAttribute("aria-busy", "false");
}

function render(value) {
  state = value;
  const locale = value.data.locale || navigator.language;
  const reflect = value.view === "reflect";
  document.documentElement.lang = locale;
  labels = reflect ? strings[displayLocale(locale)] : value.data.labels || strings[displayLocale(locale)];
  const data = value.data;
  document.documentElement.classList.toggle("qa-evidence", !reflect);
  const pane = element("section");
  const header = element("header", undefined, reflect ? undefined : "qa-toolbar");
  const summary = reflect ? header : element("div", undefined, "qa-summary");
  if (!reflect) header.append(summary);
  summary.append(element("h1", reflect ? data.title : labels.qaResults));
  const meta = [reflect ? data.summary : data.title, statusLabel(data.status), data.round && labels.round + " " + data.round].filter(Boolean);
  if (meta.length) summary.append(element("p", meta.join(" · "), "meta"));
  if (data.coverage) summary.append(element("p", data.coverage, "meta"));
  if (data.limitations) summary.append(element("p", data.limitations, "meta"));
  const rows = element("div", undefined, "rows");
  pane.append(header, rows);
  if (reflect) renderDashboard(pane, data);
  else qaResults(rows, data);
  status = element("p", "", "status");
  status.setAttribute("role", "status");
  pane.append(status);
  main.replaceChildren(pane);
  main.setAttribute("aria-busy", "false");
}

async function openLocal() {
  const response = await fetch("/state", { headers: { Authorization: "Bearer " + token } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || labels.unavailable);
  render(result);
}

function applyTheme() {
  const dark = systemColor.matches;
  const root = document.documentElement;
  root.classList.toggle("wa-dark", dark);
  root.classList.toggle("wa-light", !dark);
}

document.documentElement.lang = displayLocale(navigator.language);
applyTheme();
systemColor.addEventListener("change", () => applyTheme());
main.append(element("p", labels.loading, "status"));
openLocal().catch((error) => showError(error.message));
