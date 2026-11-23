import { App } from "@modelcontextprotocol/ext-apps";
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

async function connect() {
  const app = new App({ name: "Gnothi", version: "1.0.0" });
  const theme = (context) => {
    document.documentElement.style.colorScheme = context?.theme || "";
  };
  app.onhostcontextchanged = theme;
  app.ontoolresult = ({ structuredContent }) => {
    if (structuredContent?.metrics) render(structuredContent);
  };
  await app.connect();
  theme(app.getHostContext());
}

if (local) render(local);
else if (window.parent !== window) {
  connect().catch(() => {
    main.textContent = "The Gnothi widget could not be opened. Use the local HTML report.";
    main.setAttribute("aria-busy", "false");
  });
}
