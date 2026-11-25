import { App, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import "@awesome.me/webawesome/dist/styles/webawesome.css";
import "@awesome.me/webawesome/dist/styles/themes/awesome.css";
import "@awesome.me/webawesome/dist/components/badge/badge.js";
import "@awesome.me/webawesome/dist/components/button/button.js";
import "@awesome.me/webawesome/dist/components/card/card.js";
import "@awesome.me/webawesome/dist/components/dialog/dialog.js";
import "@awesome.me/webawesome/dist/translations/ru.js";
import "@awesome.me/webawesome/dist/translations/uk.js";
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
    scenarioKinds: { browser: "Browser", mobile: "Mobile", desktop: "Desktop", api: "API", cli: "CLI", ci: "CI" },
    scenarioCategories: {
      accessibility: "Accessibility", "user-flow": "User flow", "access-control": "Access control",
      "error-handling": "Error handling",
    },
    loading: "Opening Ready Check…", unavailable: "The view could not be loaded.",
    artifact: "View evidence", play: "Play", localReport: "Open local report", noMedia: "No media evidence.",
    openInBrowser: "View in browser", browserRequested: "Asked the client to open the QA report.",
    openReportRequest: "Open this Ready Check QA report in a visible tab using the current client's browser tool. If it cannot open the local page, give me the link.",
    compareScreenshots: "Compare screenshots", screenshot: "Screenshot",
    copyEvidenceUrl: "Copy this local address to open the evidence in your browser.",
    requestLocalReport: "Ask the agent for the local QA report link.",
    staleEvidence: "The evidence could not be loaded. Reopen the current QA round.",
    videoFallback: "This client could not play the video. Open the local report to watch it.",
  },
  uk: {
    qaResults: "Результати QA", round: "Раунд", expected: "Очікувано", actual: "Фактично",
    scenarioKinds: { browser: "Браузер", mobile: "Мобільний", desktop: "Десктоп", api: "API", cli: "CLI", ci: "CI" },
    scenarioCategories: {
      accessibility: "Доступність", "user-flow": "Користувацький сценарій", "access-control": "Права доступу",
      "error-handling": "Обробка помилок",
    },
    statuses: {
      PASS: "Пройдено",
      FAIL: "Не пройдено",
      BLOCKED: "Заблоковано",
      INCOMPLETE: "Не завершено",
      NOT_RUN: "Не запускали",
      "N/A": "Не застосовується",
    },
    loading: "Відкриваємо Ready Check…", unavailable: "Не вдалося відкрити звіт.",
    artifact: "Переглянути доказ", play: "Відтворити", localReport: "Відкрити локальний звіт",
    openInBrowser: "Переглянути у браузері", browserRequested: "Запит на відкриття звіту надіслано.",
    openReportRequest: "Відкрий цей QA-звіт Ready Check у видимій вкладці через браузер поточного клієнта. Якщо він не може відкрити локальну сторінку, дай мені посилання.",
    compareScreenshots: "Порівняти скріншоти", screenshot: "Скріншот",
    noMedia: "Медіадоказів немає.",
    copyEvidenceUrl: "Скопіюй цю локальну адресу, щоб відкрити докази у браузері.",
    requestLocalReport: "Попроси агента дати посилання на локальний звіт QA.",
    staleEvidence: "Не вдалося завантажити доказ. Відкрий поточний раунд QA ще раз.",
    videoFallback: "Клієнт не зміг відтворити відео. Відкрий локальний звіт, щоб його переглянути.",
  },
  ru: {
    qaResults: "Результаты QA", round: "Раунд", expected: "Ожидалось", actual: "Фактически",
    scenarioKinds: { browser: "Браузер", mobile: "Мобильный", desktop: "Десктоп", api: "API", cli: "CLI", ci: "CI" },
    scenarioCategories: {
      accessibility: "Доступность", "user-flow": "Пользовательский сценарий", "access-control": "Права доступа",
      "error-handling": "Обработка ошибок",
    },
    statuses: {
      PASS: "Пройдено",
      FAIL: "Не пройдено",
      BLOCKED: "Заблокировано",
      INCOMPLETE: "Не завершено",
      NOT_RUN: "Не запускали",
      "N/A": "Неприменимо",
    },
    loading: "Открываем Ready Check…", unavailable: "Не удалось открыть отчёт.",
    artifact: "Посмотреть материалы", play: "Воспроизвести", localReport: "Открыть локальный отчёт",
    openInBrowser: "Открыть в браузере", browserRequested: "Запрос на открытие отчёта отправлен.",
    openReportRequest: "Открой этот QA-отчёт Ready Check на видимой вкладке браузера текущего клиента. Если клиент не может открыть локальную страницу, дай мне ссылку.",
    compareScreenshots: "Сравнить скриншоты", screenshot: "Скриншот",
    noMedia: "Скриншотов и видео нет.",
    copyEvidenceUrl: "Скопируй этот локальный адрес, чтобы посмотреть материалы в браузере.",
    requestLocalReport: "Попроси агента дать ссылку на локальный QA-отчёт.",
    staleEvidence: "Не удалось загрузить материалы. Открой текущий раунд QA заново.",
    videoFallback: "Клиент не смог воспроизвести видео. Открой локальный отчёт, чтобы его посмотреть.",
  },
};

function displayLocale(locale) {
  const language = typeof locale === "string" ? locale.toLowerCase().split("-")[0] : "";
  return Object.hasOwn(strings, language) ? language : "en";
}

let labels = strings[displayLocale(navigator.language)];
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
    if (typeof url !== "string" || !/^http:\/\/127\.0\.0\.1:\d+\/#[-\w]+$/.test(url)) {
      message(labels.requestLocalReport, true);
      return;
    }
    address.textContent = url;
    address.hidden = false;
    if (capabilities?.message) {
      const sent = await app.sendMessage({
        role: "user",
        content: [{ type: "text", text: labels.openReportRequest + "\n" + url }],
      }).catch(() => null);
      if (state !== snapshot) return;
      if (sent && !sent.isError) {
        message(labels.browserRequested);
        return;
      }
    }
    if (capabilities?.openLinks) {
      const opened = await app.openLink({ url }).catch(() => null);
      if (state !== snapshot || (opened && !opened.isError)) return;
    }
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

function cachedPreviewUrl(asset) {
  const preview = state.previews[asset.path];
  return preview ? "data:" + preview.mimeType + ";base64," + preview.data : null;
}

async function previewUrl(asset) {
  const cached = cachedPreviewUrl(asset);
  if (cached || !app.getHostCapabilities()?.serverTools) return cached;
  const preview = await appTool("preview_media", { path: asset.path });
  if (preview.open_local || (isRecording(asset) && !document.createElement("video").canPlayType(preview.mimeType))) {
    return null;
  }
  return "data:" + preview.mimeType + ";base64," + preview.data;
}

function mediaButton(text, assets, address, show) {
  const snapshot = state;
  const canPreview = app.getHostCapabilities()?.serverTools || assets.some((asset) => state.previews[asset.path]);
  const caption = assets.length === 1 ? assets[0].title || labels.artifact : text;
  const control = button(canPreview ? text : labels.openInBrowser + " · " + caption, async () => {
    control.disabled = true;
    address.hidden = true;
    message("");
    try {
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
  if (assets.length === 1 && isRecording(assets[0])) {
    const icon = element("span", "▶", "play-icon");
    icon.slot = "start";
    icon.setAttribute("aria-hidden", "true");
    control.prepend(icon);
  }
  return control;
}

function screenshotButton(url, title, address) {
  const control = element("button", undefined, address ? "screenshot-preview screenshot-thumbnail" : "screenshot-preview");
  control.type = "button";
  const image = element("img");
  image.alt = title;
  image.loading = inApp ? "eager" : "lazy";
  image.addEventListener("error", () => {
    if (address) {
      control.replaceWith(button(labels.openInBrowser, () => openLocalReport(address)));
    } else {
      message(labels.staleEvidence, true);
    }
  }, { once: true });
  image.src = url;
  control.append(image);
  control.addEventListener("click", () => openImage(url, title));
  return control;
}

function reportAddress() {
  const address = element("p", undefined, "meta qa-address");
  address.hidden = true;
  return address;
}

function screenshotFigure(title, view) {
  const figure = element("figure", undefined, "screenshot-figure");
  figure.append(element("figcaption", title), view);
  return figure;
}

function screenshotPair(card, assets) {
  const row = element("div", undefined, "evidence");
  const address = reportAddress();
  card.append(row);
  function show(urls, focus = false) {
    const pair = element("div", undefined, inApp ? "screenshot-pair thumbnail-pair" : "screenshot-pair");
    for (const [index, url] of urls.entries()) {
      const title = assets[index].title || labels.screenshot + " " + (index + 1);
      let view;
      if (url) {
        view = screenshotButton(url, title, inApp ? address : undefined);
      } else if (!focus && app?.getHostCapabilities()?.serverTools) {
        view = mediaButton(labels.artifact, [assets[index]], address, ([src]) => {
          const thumbnail = screenshotButton(src, title, address);
          view.replaceWith(thumbnail);
          thumbnail.focus();
        });
      } else {
        view = button(labels.openInBrowser, () => openLocalReport(address));
      }
      pair.append(screenshotFigure(title, view));
    }
    row.replaceChildren(pair);
    if (inApp) row.append(address);
    if (focus) pair.querySelector("button, wa-button")?.focus();
  }
  const urls = assets.map(inApp ? cachedPreviewUrl : localAssetUrl);
  if (urls.some(Boolean)) show(urls);
  else row.append(mediaButton(labels.compareScreenshots, assets, address, (urls) => show(urls, true)), address);
}

function artifact(card, asset, thumbnail) {
  const row = element("div", undefined, "evidence");
  const title = asset.title || labels.artifact;
  const isImage = isScreenshot(asset);
  const isVideo = isRecording(asset);
  if (inApp) {
    if (!isImage && !isVideo) return false;
    const address = reportAddress();
    const cached = thumbnail ? cachedPreviewUrl(asset) : null;
    const view = cached
      ? screenshotFigure(title, screenshotButton(cached, title, address))
      : mediaButton(isVideo ? labels.play + " · " + title : title, [asset], address, ([url]) => {
        if (isImage) {
          openImage(url, title);
          return;
        }
        const player = addVideo(row, asset, url, title, labels.videoFallback);
        player.focus();
        player.play().catch(() => {});
      });
    row.append(view, address);
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
  if (inApp) {
    const address = reportAddress();
    const report = button(labels.localReport, () => openLocalReport(address));
    report.className = "qa-report";
    header.append(report, address);
  }
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
    const thumbnails = screenshots.slice(0, 2);
    if (hasPair) screenshotPair(card, screenshots);
    let hasMedia = hasPair;
    for (const asset of hasPair ? assets.filter((asset) => !isScreenshot(asset)) : assets) {
      if (artifact(card, asset, thumbnails.includes(asset))) hasMedia = true;
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

function render(value, previews = {}) {
  closePreviews();
  state = { ...value, previews: previews ?? {} };
  const locale = displayLocale(value.data.locale || navigator.language);
  document.documentElement.lang = locale;
  labels = strings[locale];
  const data = value.data;
  const reflect = value.view === "reflect";
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
  app.ontoolresult = ({ structuredContent, isError, content, _meta }) => {
    if (isError || structuredContent?.view !== "qa-results") {
      showError(content?.find((block) => block.type === "text")?.text);
      return;
    }
    render(structuredContent, _meta?.readyCheckPreviews);
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

document.documentElement.lang = displayLocale(navigator.language);
applyTheme();
systemColor.addEventListener("change", () => applyTheme());
main.append(element("p", labels.loading, "status"));
(inApp ? openApp() : openLocal()).catch((error) => showError(error.message));
