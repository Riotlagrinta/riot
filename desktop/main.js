const { app, BrowserWindow, WebContentsView, Tray, Menu, globalShortcut, ipcMain, dialog, shell, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");
const os = require("os");
const http = require("http");
const { spawn, execFile } = require("child_process");

const PORT = Number(process.env.RIOT_PORT || 8790);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const SHELL_HEIGHT = 40;
const TAB_ROUTES = {
  ide: "/ide",
  studio: "/studio",
  mobile: "/mobile",
  panneau: "/panneau",
};

let mainWindow = null;
let contentView = null;
let tray = null;
let backendProc = null;
let startedByUs = false;
let isQuitting = false;
let activeTab = "ide";
let currentStatus = { state: "starting", label: "Démarrage du moteur...", activeTab: "ide" };

function iconPath(name) {
  return path.join(__dirname, "assets", name);
}

function broadcastStatus(patch) {
  currentStatus = { ...currentStatus, ...patch, activeTab };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("riot:status", currentStatus);
  }
  if (contentView && contentView.webContents && !contentView.webContents.isDestroyed()) {
    contentView.webContents.send("riot:status", currentStatus);
  }
}

function layoutContentView() {
  if (!mainWindow || mainWindow.isDestroyed() || !contentView) return;
  const [w, h] = mainWindow.getContentSize();
  contentView.setBounds({
    x: 0,
    y: SHELL_HEIGHT,
    width: Math.max(320, w),
    height: Math.max(200, h - SHELL_HEIGHT),
  });
}

function showAndFocusWindow(tab) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (tab && TAB_ROUTES[tab]) switchTab(tab);
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function switchTab(tab) {
  if (!TAB_ROUTES[tab]) return;
  activeTab = tab;
  if (currentStatus.state === "ready" && contentView && !contentView.webContents.isDestroyed()) {
    contentView.webContents.loadURL(`${BASE_URL}${TAB_ROUTES[tab]}`);
  }
  broadcastStatus({ activeTab });
}

function pingBackend() {
  return new Promise((resolve) => {
    const req = http.get(`${BASE_URL}/api/version`, { timeout: 1200 }, (res) => {
      let body = "";
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => {
        if (res.statusCode >= 200 && res.statusCode < 400) {
          try {
            const parsed = JSON.parse(body || "{}");
            resolve({ ok: true, version: parsed.version || parsed.local || "" });
            return;
          } catch (_) {
            resolve({ ok: true, version: "" });
            return;
          }
        }
        resolve({ ok: false });
      });
    });
    req.on("error", () => resolve({ ok: false }));
    req.on("timeout", () => { req.destroy(); resolve({ ok: false }); });
  });
}

function resolveBackendCommand() {
  const envHome = (process.env.RIOT_HOME || "").trim();
  const devRoot = path.resolve(__dirname, "..");
  const candidateRoots = [envHome, devRoot].filter(Boolean);

  for (const root of candidateRoots) {
    const riotPy = path.join(root, "riot.py");
    const venvPy = path.join(root, ".venv", "Scripts", "python.exe");
    if (fs.existsSync(riotPy) && fs.existsSync(venvPy)) {
      return { cmd: venvPy, args: [riotPy, "--server"], cwd: root, shell: false };
    }
  }

  const userVenvPy = path.join(os.homedir(), ".riot", "venv", "Scripts", "python.exe");
  if (fs.existsSync(userVenvPy)) {
    return { cmd: userVenvPy, args: ["-m", "riot", "--server"], cwd: os.homedir(), shell: false };
  }

  const npmRiotCmd = path.join(process.env.APPDATA || "", "npm", "riot.cmd");
  if (process.env.APPDATA && fs.existsSync(npmRiotCmd)) {
    return { cmd: npmRiotCmd, args: ["--server"], cwd: os.homedir(), shell: true };
  }

  return { cmd: "riot", args: ["--server"], cwd: os.homedir(), shell: true };
}

function stopOwnedBackend() {
  if (!backendProc || !startedByUs) return;
  const pid = backendProc.pid;
  backendProc = null;
  startedByUs = false;
  if (!pid) return;
  if (process.platform === "win32") {
    execFile("taskkill", ["/pid", String(pid), "/T", "/F"], () => {});
  } else {
    try { process.kill(pid, "SIGTERM"); } catch (_) {}
  }
}

async function ensureBackendReady() {
  const already = await pingBackend();
  if (already.ok) {
    const label = already.version ? `En ligne · v${already.version}` : "En ligne";
    broadcastStatus({ state: "ready", label });
    if (contentView && !contentView.webContents.isDestroyed()) {
      contentView.webContents.loadURL(`${BASE_URL}${TAB_ROUTES[activeTab]}`);
    }
    return true;
  }

  broadcastStatus({ state: "starting", label: "Lancement serveur RIOT..." });
  const spec = resolveBackendCommand();
  try {
    backendProc = spawn(spec.cmd, spec.args, {
      cwd: spec.cwd,
      shell: spec.shell,
      windowsHide: true,
      stdio: "ignore",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    startedByUs = true;
    backendProc.on("exit", () => {
      if (!isQuitting && startedByUs) {
        startedByUs = false;
      }
    });
  } catch (err) {
    broadcastStatus({
      state: "error",
      label: "Moteur introuvable",
      detail: `Impossible de lancer RIOT (${err.message}). Exécutez : npm install -g @riotlagrinta/riot`,
    });
    return false;
  }

  const deadline = Date.now() + 25000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 400));
    const st = await pingBackend();
    if (st.ok) {
      const label = st.version ? `En ligne · v${st.version}` : "En ligne";
      broadcastStatus({ state: "ready", label });
      if (contentView && !contentView.webContents.isDestroyed()) {
        contentView.webContents.loadURL(`${BASE_URL}${TAB_ROUTES[activeTab]}`);
      }
      return true;
    }
  }

  broadcastStatus({
    state: "error",
    label: "Délai dépassé",
    detail: "Le serveur local http://127.0.0.1:8790 ne répond pas. Vérifiez votre installation RIOT.",
  });
  return false;
}

function runBackendUpdate() {
  return new Promise((resolve) => {
    const spec = resolveBackendCommand();
    const updateArgs = spec.args.map((a) => (a === "--server" ? "/update" : a));
    const proc = spawn(spec.cmd, updateArgs, {
      cwd: spec.cwd,
      shell: spec.shell,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let errText = "";
    if (proc.stderr) proc.stderr.on("data", (d) => { errText += d.toString(); });
    proc.on("close", async (code) => {
      if (code === 0) {
        stopOwnedBackend();
        await ensureBackendReady();
        resolve({ ok: true });
      } else {
        resolve({ ok: false, error: (errText || `Code ${code}`).slice(0, 120) });
      }
    });
    proc.on("error", (e) => resolve({ ok: false, error: e.message }));
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1420,
    height: 900,
    minWidth: 960,
    minHeight: 620,
    frame: false,
    backgroundColor: "#0B0C0E",
    icon: iconPath("icon.ico"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "shell.html"));

  contentView = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.contentView.addChildView(contentView);
  layoutContentView();
  contentView.webContents.loadFile(path.join(__dirname, "splash.html"));

  contentView.webContents.setWindowOpenHandler(({ url }) => {
    if (url && !url.startsWith(BASE_URL)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    layoutContentView();
  });

  mainWindow.on("resize", layoutContentView);
  mainWindow.on("maximize", layoutContentView);
  mainWindow.on("unmaximize", layoutContentView);

  mainWindow.on("close", (ev) => {
    if (!isQuitting && tray) {
      ev.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const img = nativeImage.createFromPath(iconPath("tray.png"));
  tray = new Tray(img.isEmpty() ? iconPath("icon.ico") : img);
  tray.setToolTip("RIOT Desktop — IDE & Studio");
  const menu = Menu.buildFromTemplate([
    { label: "Ouvrir RIOT IDE", click: () => showAndFocusWindow("ide") },
    { label: "Ouvrir RIOT Studio", click: () => showAndFocusWindow("studio") },
    { label: "Cockpit Mobile", click: () => showAndFocusWindow("mobile") },
    { label: "Réglages", click: () => showAndFocusWindow("panneau") },
    { type: "separator" },
    {
      label: "Mettre à jour le moteur RIOT",
      click: async () => {
        showAndFocusWindow();
        await runBackendUpdate();
      },
    },
    { type: "separator" },
    {
      label: "Quitter RIOT",
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", () => {
    if (mainWindow && mainWindow.isVisible()) mainWindow.focus();
    else showAndFocusWindow();
  });
}

const singleLock = app.requestSingleInstanceLock();
if (!singleLock) {
  app.quit();
} else {
  app.on("second-instance", () => showAndFocusWindow());

  app.whenReady().then(() => {
    createWindow();
    createTray();
    try {
      globalShortcut.register("CommandOrControl+Alt+R", () => {
        if (!mainWindow || mainWindow.isDestroyed()) return;
        if (mainWindow.isVisible() && mainWindow.isFocused()) {
          mainWindow.hide();
        } else {
          showAndFocusWindow();
        }
      });
    } catch (_) {}
    void ensureBackendReady();
  });

  app.on("before-quit", () => {
    isQuitting = true;
    globalShortcut.unregisterAll();
    stopOwnedBackend();
  });
}

ipcMain.on("riot:switch-tab", (_ev, tab) => switchTab(tab));

ipcMain.on("riot:window-action", (_ev, action) => {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (action === "minimize") mainWindow.minimize();
  else if (action === "maximize") {
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
  } else if (action === "close") {
    if (tray) mainWindow.hide();
    else app.quit();
  }
});

ipcMain.handle("riot:get-status", () => currentStatus);

ipcMain.handle("riot:pick-folder", async (_ev, defaultPath) => {
  const opts = {
    title: "Ouvrir un dossier projet — RIOT IDE",
    properties: ["openDirectory", "createDirectory"],
  };
  if (defaultPath && fs.existsSync(defaultPath)) {
    opts.defaultPath = defaultPath;
  }
  const res = await dialog.showOpenDialog(mainWindow, opts);
  if (res.canceled || !res.filePaths || res.filePaths.length === 0) return null;
  return res.filePaths[0];
});

ipcMain.handle("riot:update-backend", () => runBackendUpdate());

ipcMain.handle("riot:restart-backend", async () => {
  if (contentView && !contentView.webContents.isDestroyed()) {
    contentView.webContents.loadFile(path.join(__dirname, "splash.html"));
  }
  stopOwnedBackend();
  return ensureBackendReady();
});

ipcMain.on("riot:open-external", (_ev, url) => {
  if (url && /^https?:\/\//i.test(url)) {
    shell.openExternal(url);
  }
});
