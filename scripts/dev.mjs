/**
 * Cross-platform dev startup script.
 *
 * Starts the backend (uvicorn) and frontend (electron-vite) in parallel,
 * prefixing their output so you can tell them apart in one terminal.
 *
 * Works on macOS, Linux and Windows (Node >= 14).
 */

import { spawn } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

function run(label, cmd, args, cwd) {
  const child = spawn(cmd, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    shell: true,
  });

  const prefix = `[${label}]`;

  child.stdout.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      if (line) process.stdout.write(`${prefix} ${line}\n`);
    }
  });

  child.stderr.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      if (line) process.stderr.write(`${prefix} ${line}\n`);
    }
  });

  child.on("close", (code) => {
    console.log(`${prefix} exited with code ${code}`);
  });

  return child;
}

// Detect python command (prefer venv if present)
const isWin = process.platform === "win32";
const venvPython = isWin
  ? resolve(root, "backend", ".venv", "Scripts", "python.exe")
  : resolve(root, "backend", ".venv", "bin", "python");

// Use venv python if it exists, otherwise fall back to system python
import { existsSync } from "node:fs";
const pythonCmd = existsSync(venvPython) ? venvPython : "python3";

const backend = run(
  "backend",
  pythonCmd,
  ["main.py"],
  resolve(root, "backend")
);

const frontend = run(
  "frontend",
  "npm",
  ["run", "dev"],
  resolve(root, "frontend")
);

// Forward SIGINT / SIGTERM to children
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    backend.kill(sig);
    frontend.kill(sig);
  });
}
