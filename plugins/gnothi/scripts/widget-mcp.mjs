import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const entry = fileURLToPath(new URL("widget-mcp.py", import.meta.url));

function launch(candidates) {
  const [[command, ...prefix], ...rest] = candidates;
  const child = spawn(command, [...prefix, entry], { stdio: "inherit" });
  child.once("error", (error) => {
    if (error.code === "ENOENT" && rest.length) launch(rest);
    else {
      console.error("Cannot start Gnothi MCP: " + error.message);
      process.exitCode = 2;
    }
  });
  child.once("exit", (code) => {
    if (code === 9009 && rest.length) launch(rest);
    else process.exitCode = code ?? 2;
  });
}

launch([["python3"], ["python"], ["py", "-3"]]);
