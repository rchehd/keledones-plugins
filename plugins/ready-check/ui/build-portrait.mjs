import { fileURLToPath } from "node:url";
import { build } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

await build({
  root: fileURLToPath(new URL(".", import.meta.url)),
  configFile: false,
  base: "./",
  publicDir: false,
  plugins: [viteSingleFile()],
  build: {
    outDir: fileURLToPath(new URL("../../gnothi/report/widget", import.meta.url)),
    emptyOutDir: true,
    rollupOptions: { input: fileURLToPath(new URL("portrait.html", import.meta.url)) },
    license: { fileName: "THIRD_PARTY_NOTICES.md" },
  },
});
