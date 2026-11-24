import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const inputs = ["index.html", "ui.js", "ui.css", "dashboard.js", "dashboard.css", "vite.config.mjs", "package.json", "package-lock.json"];

function revisionTag() {
  return {
    name: "ready-check-ui-revision",
    transformIndexHtml() {
      const digest = createHash("sha256");
      for (const name of inputs) {
        const source = readFileSync(new URL(name, import.meta.url), "utf8").replaceAll("\r\n", "\n");
        digest.update(name).update("\0").update(source).update("\0");
      }
      return [{ tag: "meta", attrs: { name: "ready-check-ui-revision", content: digest.digest("hex") } }];
    },
  };
}

function localSystemIcons() {
  let patched = false;
  return {
    name: "ready-check-local-system-icons",
    transform(source, id) {
      if (!id.includes("/@awesome.me/webawesome/dist/") || !source.includes("// src/components/icon/icon.ts")) return;
      const original = 'fileData = await fetch(url, { mode: "cors" });';
      if (!source.includes(original)) this.error("Review the Web Awesome icon loader after updating the dependency.");
      patched = true;
      return source.replace(original, `
        const prefix = "data:image/svg+xml,";
        fileData = url.startsWith(prefix)
          ? new Response(decodeURIComponent(url.slice(prefix.length)))
          : await fetch(url, { mode: "cors" });
      `);
    },
    generateBundle() {
      if (!patched) this.error("Web Awesome's local system icon loader was not applied.");
    },
  };
}

export default defineConfig({
  base: "./",
  publicDir: false,
  css: {
    postcss: {
      plugins: [{
        postcssPlugin: "ready-check-local-assets",
        AtRule: {
          import(rule) {
            if (/^(?:url\(\s*)?["']?(?:https?:)?\/\//i.test(rule.params)) rule.remove();
          },
        },
      }],
    },
  },
  plugins: [localSystemIcons(), viteSingleFile(), revisionTag()],
  build: { license: { fileName: "THIRD_PARTY_NOTICES.md" } },
});
