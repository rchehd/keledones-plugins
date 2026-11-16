import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const entry = join(dirname(fileURLToPath(import.meta.url)), "ready-check.py");
const args = [entry, "mcp", ...process.argv.slice(2)];

// 9009 is the Windows "command not found" exit, also returned by the Store python3 stub.
function run(candidates) {
  const [[python, ...prefix], ...rest] = candidates;
  const child = spawn(python, [...prefix, ...args], { stdio: "inherit" });
  let failed = false;
  child.on("error", (error) => {
    failed = true;
    if (error.code === "ENOENT" && rest.length) {
      run(rest);
      return;
    }
    console.error(`Cannot start Ready Check Playwright MCP: ${error.message}`);
    process.exit(2);
  });
  child.on("exit", (code, signal) => {
    if (failed) {
      return;
    }
    if (code === 9009 && rest.length) {
      run(rest);
      return;
    }
    process.exit(signal ? 1 : code ?? 1);
  });
}

run([["python3"], ["python"], ["py", "-3"]]);
