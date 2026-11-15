#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const DEFAULT_GIT_SOURCE =
  "git+https://github.com/Riotlagrinta/riot.git";

/**
 * Locate the `uv` binary in PATH or standard Astral install directories.
 */
function findUvBinary() {
  const isWin = process.platform === "win32";
  const binName = isWin ? "uv.exe" : "uv";

  const check = spawnSync(binName, ["--version"], { stdio: "ignore", shell: false });
  if (check.status === 0) {
    return binName;
  }

  const home = os.homedir();
  const candidates = isWin
    ? [
        path.join(home, ".local", "bin", "uv.exe"),
        path.join(home, ".cargo", "bin", "uv.exe"),
        path.join(process.env.LOCALAPPDATA || "", "uv", "uv.exe"),
      ]
    : [
        path.join(home, ".local", "bin", "uv"),
        path.join(home, ".cargo", "bin", "uv"),
        "/opt/homebrew/bin/uv",
        "/usr/local/bin/uv",
      ];

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * Install `uv` automatically via the official Astral installer when missing.
 */
function ensureUvInstalled() {
  let uvBin = findUvBinary();
  if (uvBin) return uvBin;

  console.log("[RIOT] Outil 'uv' introuvable. Installation automatique de uv (gestionnaire Python léger)...");
  const isWin = process.platform === "win32";

  const installRes = isWin
    ? spawnSync(
        "powershell.exe",
        ["-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"],
        { stdio: "inherit" }
      )
    : spawnSync("sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], { stdio: "inherit" });

  if (installRes.status !== 0) {
    console.error("[RIOT] Échec de l'installation automatique de 'uv'. Installez-le manuellement : https://docs.astral.sh/uv/");
    process.exit(installRes.status || 1);
  }

  uvBin = findUvBinary();
  if (!uvBin) {
    console.error("[RIOT] 'uv' a été installé mais nécessite un rechargement du PATH. Relancez votre terminal puis tapez `riot`.");
    process.exit(1);
  }
  return uvBin;
}

function main() {
  const rawArgs = process.argv.slice(2);
  let upgrade = false;
  const passThroughArgs = [];

  for (const arg of rawArgs) {
    if (arg === "--update-cli" || arg === "--upgrade") {
      upgrade = true;
    } else {
      passThroughArgs.push(arg);
    }
  }

  const uvBin = ensureUvInstalled();

  // Check if running inside a local checkout (e.g. via `npm link` during development)
  const localRepoRoot = path.resolve(__dirname, "..", "..");
  const isLocalCheckout =
    fs.existsSync(path.join(localRepoRoot, "pyproject.toml")) &&
    fs.existsSync(path.join(localRepoRoot, "riot.py"));

  let uvArgs;
  if (isLocalCheckout && !process.env.RIOT_SOURCE) {
    uvArgs = ["run", "--project", localRepoRoot, "riot", ...passThroughArgs];
  } else {
    const baseSource = process.env.RIOT_SOURCE || DEFAULT_GIT_SOURCE;
    const extras = (process.env.RIOT_EXTRAS || "").trim();
    const fromSpec = extras && !baseSource.includes("[") ? `${baseSource}[${extras}]` : baseSource;

    uvArgs = ["tool", "run", "--python", ">=3.12"];
    if (upgrade) {
      uvArgs.push("--refresh");
    }
    uvArgs.push("--from", fromSpec, "riot", ...passThroughArgs);
  }

  const child = spawnSync(uvBin, uvArgs, {
    stdio: "inherit",
    env: process.env,
  });

  if (child.error) {
    console.error(`[RIOT] Erreur de lancement : ${child.error.message}`);
    process.exit(1);
  }

  process.exit(typeof child.status === "number" ? child.status : 0);
}

main();

