import { renderDashboard } from "./dashboard.js";
import "./portrait.css";

const main = document.querySelector("main");
const local = JSON.parse(document.getElementById("portrait-data").textContent);

function render(data) {
  document.documentElement.lang = data.locale;
  document.title = data.title;
  const heading = document.createElement("h1");
  heading.textContent = data.title;
  const summary = document.createElement("p");
  summary.textContent = data.summary;
  summary.className = "intro";
  main.replaceChildren(heading, summary);
  renderDashboard(main, data);
  main.setAttribute("aria-busy", "false");
}

if (local) render(local);
else main.removeAttribute("aria-busy");
