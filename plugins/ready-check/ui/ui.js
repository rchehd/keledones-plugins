import { App, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import "@awesome.me/webawesome/dist/styles/webawesome.css";
import "@awesome.me/webawesome/dist/styles/themes/awesome.css";
import "@awesome.me/webawesome/dist/components/badge/badge.js";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "./ui.css";
import { renderDashboard } from "./dashboard.js";

const main = document.getElementById("ready-check");
const token = location.hash.slice(1);
const inApp = window.parent !== window;
const app = inApp ? new App({ name: "Ready Check", version: "1.0.0" }) : null;
const systemColor = matchMedia("(prefers-color-scheme: dark)");
const strings = {
  en: {
    qaResults: "QA results", round: "Round", expected: "Expected", actual: "Actual",
    loading: "Opening Ready Check…", unavailable: "The view could not be loaded.",
    artifact: "View evidence", play: "Play", localReport: "Open local report", noMedia: "No media evidence.",
    compareScreenshots: "Compare screenshots", screenshot: "Screenshot",
    copyEvidenceUrl: "Copy this local address to open the evidence in your browser.",
    requestLocalReport: "Ask the agent for the local QA report link.",
    staleEvidence: "The evidence could not be loaded. Reopen the current QA round.",
    videoFallback: "This client could not play the video. Open the local report to watch it.",
  },
  uk: {
    qaResults: "Результати QA", round: "Раунд", expected: "Очікувано", actual: "Фактично",
    loading: "Відкриваємо Ready Check…", unavailable: "Не вдалося відкрити звіт.",
    artifact: "Переглянути доказ", play: "Відтворити", localReport: "Відкрити локальний звіт",
    compareScreenshots: "Порівняти скріншоти", screenshot: "Скріншот",
    noMedia: "Медіадоказів немає.",
    copyEvidenceUrl: "Скопіюй цю локальну адресу, щоб відкрити докази у браузері.",
    requestLocalReport: "Попроси агента дати посилання на локальний звіт QA.",
    staleEvidence: "Не вдалося завантажити доказ. Відкрий поточний раунд QA ще раз.",
    videoFallback: "Клієнт не зміг відтворити відео. Відкрий локальний звіт, щоб його переглянути.",
  },
};
let labels = strings[navigator.language.startsWith("uk") ? "uk" : "en"];
let state;
let status;
let hostTheme;
let appliedDark;
const hostColors = new Set();

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined && text !== null) item.textContent = text;
  if (className) item.className = className;
  return item;
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

function facts(card, caption, value) {
  if (!value || (Array.isArray(value) && !value.length)) return;
  const line = element("p", undefined, "qa-fact");
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

async function appTool(name, args = {}) {
  const result = await app.callServerTool({ name, arguments: { ...args, handle: state.handle } });
  if (result.isError) throw new Error(result.content?.[0]?.text || labels.unavailable);
  return result.structuredContent;
}

async function openLocalReport(address) {
  const snapshot = state;
  address.hidden = true;
  try {
    const capabilities = app.getHostCapabilities();
    const { url } = capabilities?.serverTools ? await appTool("local_view") : snapshot;
    if (state !== snapshot) return;
    if (!url) {
      message(labels.requestLocalReport, true);
      return;
    }
    if (capabilities?.openLinks) {
      const opened = await app.openLink({ url }).catch(() => null);
      if (state !== snapshot || (opened && !opened.isError)) return;
    }
    address.textContent = url;
    address.hidden = false;
    message(labels.copyEvidenceUrl);
  } catch (error) {
    if (state === snapshot) message(error.message, true);
  }
}

function addVideo(row, asset, src, title, errorMessage) {
  const player = element("video");
  player.controls = true;
  player.playsInline = true;
  player.preload = "metadata";
  player.setAttribute("aria-label", title);
  player.addEventListener("error", () => message(errorMessage, true));
  player.src = src;
  row.replaceChildren(element("strong", title), player);
  const chapters = Array.isArray(asset.chapters) ? asset.chapters : [];
  for (const chapter of chapters) {
    if (Number.isFinite(chapter.start) && chapter.start >= 0) {
      row.append(button(chapter.title, () => { player.currentTime = chapter.start; }));
    }
  }
  return player;
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

async function previewUrl(asset) {
  const preview = await appTool("preview_media", { path: asset.path });
  if (preview.open_local || (isRecording(asset) && !document.createElement("video").canPlayType(preview.mimeType))) {
    return null;
  }
  return "data:" + preview.mimeType + ";base64," + preview.data;
}

function mediaButton(text, assets, address, show) {
  const snapshot = state;
  const control = button(text, async () => {
    control.disabled = true;
    address.hidden = true;
    message("");
    try {
      if (!app.getHostCapabilities()?.serverTools) {
        await openLocalReport(address);
        return;
      }
      const urls = [];
      let failure;
      for (const asset of assets) {
        const url = await previewUrl(asset).catch((error) => {
          failure ??= error;
          return undefined;
        });
        if (state !== snapshot) return;
        urls.push(url);
      }
      if (urls.some(Boolean)) show(urls);
      else if (urls.includes(null)) await openLocalReport(address);
      else throw failure;
    } catch (error) {
      if (state === snapshot) message(error.message, true);
    } finally {
      control.disabled = false;
    }
  });
  return control;
}

function screenshotButton(url, title) {
  const control = element("button", undefined, "screenshot-preview");
  control.type = "button";
  const image = element("img");
  image.alt = title;
  image.loading = inApp ? "eager" : "lazy";
  image.src = url;
  image.addEventListener("error", () => message(labels.staleEvidence, true));
  control.append(image);
  control.addEventListener("click", () => openImage(url, title));
  return control;
}

function screenshotPair(card, assets, address) {
  const row = element("div", undefined, "evidence");
  card.append(row);
  function show(urls) {
    const pair = element("div", undefined, "screenshot-pair");
    for (const [index, url] of urls.entries()) {
      const title = assets[index].title || labels.screenshot + " " + (index + 1);
      const figure = element("figure");
      const view = url ? screenshotButton(url, title) : button(labels.localReport, () => openLocalReport(address));
      figure.append(element("figcaption", title), view);
      pair.append(figure);
    }
    row.replaceChildren(pair);
    if (inApp) pair.querySelector("button").focus();
  }
  if (inApp) row.append(mediaButton(labels.compareScreenshots, assets, address, show));
  else show(assets.map(localAssetUrl));
}

function artifact(card, asset, address) {
  const row = element("div", undefined, "evidence");
  const title = asset.title || labels.artifact;
  const isImage = isScreenshot(asset);
  const isVideo = isRecording(asset);
  if (inApp) {
    if (!isImage && !isVideo) return false;
    row.append(mediaButton(isVideo ? labels.play + " · " + title : title, [asset], address, ([url]) => {
      if (isImage) {
        openImage(url, title);
        return;
      }
      const player = addVideo(row, asset, url, title, labels.videoFallback);
      player.focus();
      player.play().catch(() => {});
    }));
  } else if (isVideo) {
    addVideo(row, asset, localAssetUrl(asset), title, labels.staleEvidence);
  } else if (isImage) {
    row.append(screenshotButton(localAssetUrl(asset), title));
  } else {
    const link = element("a", title);
    link.href = localAssetUrl(asset);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    row.append(link);
  }
  card.append(row);
  return true;
}

function qaResults(header, rows, data) {
  const address = element("p", undefined, "meta qa-address");
  address.hidden = true;
  if (inApp) {
    const report = button(labels.localReport, () => openLocalReport(address));
    report.className = "qa-report";
    header.append(report, address);
  }
  for (const result of data.scenarios) {
    const card = element("wa-card", undefined, "card");
    card.appearance = "outlined";
    const heading = element("div", undefined, "heading");
    heading.append(element("h2", [result.id, result.title].filter(Boolean).join(" · ")));
    if (result.status) {
      const badge = element("wa-badge", result.status);
      const variants = { PASS: "success", FAIL: "danger", BLOCKED: "danger", INCOMPLETE: "warning" };
      badge.variant = variants[result.status] || "neutral";
      badge.appearance = "filled";
      heading.append(badge);
    }
    card.append(heading);
    facts(card, labels.expected, result.expected);
    facts(card, labels.actual, result.actual);
    const assets = result.artifacts || [];
    const screenshots = assets.filter(isScreenshot);
    const hasPair = screenshots.length === 2;
    if (hasPair) screenshotPair(card, screenshots, address);
    let hasMedia = hasPair;
    for (const asset of hasPair ? assets.filter((asset) => !isScreenshot(asset)) : assets) {
      if (artifact(card, asset, address)) hasMedia = true;
    }
    if (!hasMedia) card.append(element("small", labels.noMedia));
    rows.append(card);
  }
}

function closePreviews() {
  document.querySelectorAll("wa-dialog.preview").forEach((dialog) => dialog.remove());
}

function showError(text) {
  closePreviews();
  state = undefined;
  main.replaceChildren(element("p", text || labels.unavailable, "status error"));
  main.setAttribute("aria-busy", "false");
}

function render(value) {
  closePreviews();
  state = value;
  const locale = value.data.locale || document.documentElement.lang;
  document.documentElement.lang = locale;
  labels = strings[locale] || labels;
  const data = value.data;
  const reflect = value.view === "reflect";
  document.documentElement.classList.toggle("qa-evidence", !reflect);
  const pane = element("section");
  const header = element("header", undefined, reflect ? undefined : "qa-toolbar");
  const summary = reflect ? header : element("div", undefined, "qa-summary");
  if (!reflect) header.append(summary);
  summary.append(element("h1", reflect ? data.title : labels.qaResults));
  const meta = [reflect ? data.summary : data.title, data.status, data.round && labels.round + " " + data.round].filter(Boolean);
  if (meta.length) summary.append(element("p", meta.join(" · "), "meta"));
  if (data.coverage) summary.append(element("p", data.coverage, "meta"));
  if (data.limitations) summary.append(element("p", data.limitations, "meta"));
  const rows = element("div", undefined, "rows");
  pane.append(header, rows);
  if (reflect) renderDashboard(pane, data);
  else qaResults(header, rows, data);
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

function applyTheme({ theme, styles } = {}) {
  hostTheme = theme ?? hostTheme;
  const dark = hostTheme ? hostTheme === "dark" : systemColor.matches;
  const root = document.documentElement;
  if (dark !== appliedDark) {
    for (const key of hostColors) root.style.removeProperty(key);
    hostColors.clear();
    appliedDark = dark;
  }
  root.classList.toggle("wa-dark", dark);
  root.classList.toggle("wa-light", !dark);
  if (styles?.variables) {
    applyHostStyleVariables(styles.variables, root);
    for (const key of Object.keys(styles.variables)) {
      if (key.startsWith("--color-")) hostColors.add(key);
    }
  }
}

async function openApp() {
  app.ontoolresult = ({ structuredContent, isError, content }) => {
    if (isError || structuredContent?.view !== "qa-results") {
      showError(content?.find((block) => block.type === "text")?.text);
      return;
    }
    render(structuredContent);
  };
  app.onhostcontextchanged = applyTheme;
  app.onteardown = async () => {
    closePreviews();
    main.replaceChildren();
    return {};
  };
  await app.connect();
  applyTheme(app.getHostContext());
}

document.documentElement.lang = navigator.language.startsWith("uk") ? "uk" : "en";
applyTheme();
systemColor.addEventListener("change", () => applyTheme());
main.append(element("p", labels.loading, "status"));
(inApp ? openApp() : openLocal()).catch((error) => showError(error.message));
