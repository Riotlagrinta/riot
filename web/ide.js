(function () {
  var state = {
    tabs: [], // { path, name, ext, content, savedContent, dirty, diff }
    activePath: null,
    agentMode: "code",
    history: [],
    treeNodes: [],
    pendingPatches: [],
    activePatchId: null,
    lastAcceptedPatch: null, // { id, chemin }
    allPaths: []
  };

  var cm = null;
  var suppressCmChange = false;
  var els = {};
  function q(id) { return document.getElementById(id); }

  function bindEls() {
    [
      "ide-sidebar", "ide-agent", "ide-resizer-left", "ide-resizer-right", "ide-resizer-term",
      "ide-project-select", "ide-btn-openfolder", "ide-branch-pill", "ide-btn-quickopen", "ide-btn-model", "ide-model-label",
      "ide-tree", "ide-tree-filter", "ide-btn-newfile", "ide-btn-refresh",
      "ide-search-form", "ide-search-input", "ide-search-results",
      "ide-tabs", "ide-breadcrumb", "ide-empty-state", "ide-code-wrap",
      "ide-cm-host", "ide-fallback-host", "ide-gutter", "ide-editor",
      "ide-preview-wrap", "ide-diff-wrap", "ide-diff-title", "ide-diff-body",
      "ide-diff-close", "ide-btn-revert", "ide-btn-preview", "ide-btn-diff", "ide-btn-save", "ide-btn-term-toggle",
      "ide-patch-bar", "ide-patch-file", "ide-patch-stats", "ide-patch-accept", "ide-patch-reject",
      "ide-terminal-panel", "ide-term-cwd", "ide-term-output", "ide-term-form",
      "ide-term-input", "ide-term-clear", "ide-agent-feed", "ide-agent-form",
      "ide-agent-input", "ide-agent-send", "ide-attach-active", "ide-active-file-chip",
      "ide-review-mode", "ide-pending-count",
      "ide-quickopen-modal", "ide-quickopen-input", "ide-quickopen-list",
      "ide-folder-modal", "ide-folder-close", "ide-folder-cancel", "ide-folder-roots",
      "ide-folder-up", "ide-folder-path", "ide-folder-go", "ide-folder-os",
      "ide-folder-list", "ide-folder-open",
      "ide-btn-mcp", "ide-mcp-modal", "ide-mcp-close", "ide-mcp-reload", "ide-mcp-summary", "ide-mcp-list",
      "ide-model-modal", "ide-modal-close", "ide-model-form",
      "ide-cfg-profil-wrap", "ide-cfg-profil", "ide-admin-model-fields",
      "ide-cfg-mode", "ide-cfg-baseurl-wrap", "ide-cfg-baseurl", "ide-cfg-model", "ide-cfg-key"
    ].forEach(function (id) { els[id] = q(id); });
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function cmModeForExt(ext) {
    var e = (ext || "").toLowerCase();
    if (e === "py") return "python";
    if (e === "js" || e === "ts" || e === "tsx" || e === "jsx" || e === "json") return "javascript";
    if (e === "css" || e === "scss") return "css";
    if (e === "html" || e === "htm" || e === "svg" || e === "xml") return "htmlmixed";
    if (e === "md" || e === "markdown") return "markdown";
    if (e === "yaml" || e === "yml") return "yaml";
    return "text/plain";
  }

  function ensureCodeMirror() {
    if (cm || typeof window.CodeMirror === "undefined") return cm;
    els["ide-cm-host"].classList.remove("hidden");
    els["ide-fallback-host"].classList.add("hidden");
    cm = window.CodeMirror(els["ide-cm-host"], {
      value: "",
      lineNumbers: true,
      tabSize: 4,
      indentUnit: 4,
      mode: "python"
    });
    cm.on("change", function () {
      if (suppressCmChange) return;
      var tab = currentTab();
      if (!tab) return;
      tab.content = cm.getValue();
      tab.dirty = tab.content !== tab.savedContent;
      updateBreadcrumb(tab);
    });
    return cm;
  }

  function setEditorContent(text, ext) {
    var instance = ensureCodeMirror();
    if (instance) {
      suppressCmChange = true;
      instance.setOption("mode", cmModeForExt(ext));
      instance.setValue(text || "");
      instance.clearHistory();
      suppressCmChange = false;
      setTimeout(function () { instance.refresh(); }, 10);
    } else {
      els["ide-editor"].value = text || "";
      updateGutter();
    }
  }

  function updateGutter() {
    var txt = els["ide-editor"].value || "";
    var count = txt.split("\n").length;
    var nums = [];
    for (var i = 1; i <= count; i++) nums.push(i);
    els["ide-gutter"].textContent = nums.join("\n");
  }

  function updateBreadcrumb(tab) {
    if (!tab) return;
    els["ide-breadcrumb"].textContent = tab.path + " · " + tab.content.split("\n").length + " lignes" + (tab.dirty ? " (modifié)" : "");
  }

  function currentTab() {
    return state.tabs.find(function (t) { return t.path === state.activePath; }) || null;
  }

  function renderDiffLines(diffText, title) {
    els["ide-diff-title"].textContent = title || "Inspecteur de Diff";
    var box = els["ide-diff-body"];
    box.innerHTML = "";
    var lines = String(diffText || "Aucune différence enregistrée.").split("\n");
    lines.forEach(function (ln) {
      var div = document.createElement("div");
      if (ln.startsWith("+") && !ln.startsWith("+++")) div.className = "ide-dline ide-dline-add";
      else if (ln.startsWith("-") && !ln.startsWith("---")) div.className = "ide-dline ide-dline-del";
      else if (ln.startsWith("@@") || ln.startsWith("---") || ln.startsWith("+++")) div.className = "ide-dline ide-dline-hunk";
      else div.className = "ide-dline ide-dline-ctx";
      div.textContent = ln;
      box.appendChild(div);
    });
  }

  function renderPendingPatches() {
    var n = state.pendingPatches.length;
    els["ide-pending-count"].textContent = n + (n > 1 ? " patches" : " patch");
    els["ide-pending-count"].classList.toggle("hidden", n === 0);

    var p = state.pendingPatches.find(function (x) { return x.id === state.activePatchId; }) || state.pendingPatches[0];
    if (!p) {
      els["ide-patch-bar"].classList.add("hidden");
      state.activePatchId = null;
      return;
    }
    state.activePatchId = p.id;
    els["ide-patch-bar"].classList.remove("hidden");
    els["ide-patch-file"].textContent = p.chemin;
    els["ide-patch-stats"].textContent = "+" + p.plus + " / -" + p.moins + " lignes (" + p.outil + ")";
    renderDiffLines(p.diff, "Revue avant écriture : " + p.chemin);
    els["ide-empty-state"].classList.add("hidden");
    els["ide-diff-wrap"].classList.remove("hidden");
    els["ide-preview-wrap"].classList.add("hidden");
  }

  function renderTabs() {
    var box = els["ide-tabs"];
    box.innerHTML = "";
    state.tabs.forEach(function (tab) {
      var el = document.createElement("div");
      el.className = "ide-tab" + (tab.path === state.activePath ? " active" : "");
      el.innerHTML =
        '<span>' + escapeHtml(tab.name) + (tab.dirty ? " •" : "") + '</span>' +
        '<button type="button" class="ide-tab-close" title="Fermer">×</button>';
      el.addEventListener("click", function (ev) {
        if (ev.target.classList.contains("ide-tab-close")) closeTab(tab.path);
        else selectTab(tab.path);
      });
      box.appendChild(el);
    });

    var act = currentTab();
    if (!act) {
      els["ide-empty-state"].classList.remove("hidden");
      els["ide-code-wrap"].classList.add("hidden");
      els["ide-preview-wrap"].classList.add("hidden");
      els["ide-breadcrumb"].textContent = "Sélectionnez un fichier à gauche, appuyez sur Ctrl+P ou pilotez l'agent RIOT.";
      els["ide-active-file-chip"].textContent = "Joindre onglet actif (aucun)";
    } else {
      els["ide-empty-state"].classList.add("hidden");
      els["ide-code-wrap"].classList.remove("hidden");
      els["ide-preview-wrap"].classList.add("hidden");
      setEditorContent(act.content, act.ext);
      updateBreadcrumb(act);
      els["ide-active-file-chip"].textContent = "Joindre " + act.path;
    }
  }

  function selectTab(path) {
    state.activePath = path;
    els["ide-diff-wrap"].classList.add("hidden");
    els["ide-preview-wrap"].classList.add("hidden");
    renderTabs();
    highlightActiveTree();
  }

  function closeTab(path) {
    var idx = state.tabs.findIndex(function (t) { return t.path === path; });
    if (idx === -1) return;
    state.tabs.splice(idx, 1);
    if (state.activePath === path) {
      state.activePath = state.tabs.length ? state.tabs[Math.max(0, idx - 1)].path : null;
    }
    renderTabs();
  }

  async function openFile(relPath, forceReload) {
    var existing = state.tabs.find(function (t) { return t.path === relPath; });
    if (existing && !forceReload) {
      selectTab(relPath);
      return;
    }
    try {
      var r = await fetch("/api/ide/fichier?chemin=" + encodeURIComponent(relPath));
      var d = await r.json();
      if (!d.ok) {
        appendAgentMsg("system", "Impossible d'ouvrir `" + relPath + "` : " + (d.erreur || "erreur"));
        return;
      }
      if (existing) {
        existing.content = d.contenu;
        existing.savedContent = d.contenu;
        existing.ext = d.ext;
        existing.dirty = false;
      } else {
        state.tabs.push({
          path: d.chemin,
          name: d.nom,
          ext: d.ext,
          content: d.contenu,
          savedContent: d.contenu,
          dirty: false,
          diff: ""
        });
      }
      selectTab(d.chemin);
    } catch (e) {
      appendAgentMsg("system", "Erreur lecture : " + e.message);
    }
  }

  async function saveActiveFile() {
    var tab = currentTab();
    if (!tab) return;
    var r = await fetch("/api/ide/fichier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chemin: tab.path, contenu: tab.content, creer: false })
    });
    var d = await r.json();
    if (!d.ok) {
      appendAgentMsg("system", "Échec sauvegarde : " + (d.erreur || ""));
      return;
    }
    tab.savedContent = tab.content;
    tab.dirty = false;
    tab.diff = d.diff || "(aucune différence)";
    renderTabs();
    loadTree();
  }

  function highlightActiveTree() {
    els["ide-tree"].querySelectorAll(".ide-tree-row").forEach(function (row) {
      row.classList.toggle("active", row.dataset.path === state.activePath);
    });
  }

  function renderTreeNodes(nodes, container, depth, filter) {
    nodes.forEach(function (n) {
      if (n.type === "dir") {
        var wrapper = document.createElement("div");
        var childBox = document.createElement("div");
        renderTreeNodes(n.enfants || [], childBox, depth + 1, filter);
        if (filter && childBox.children.length === 0 && n.nom.toLowerCase().indexOf(filter) === -1) return;
        var row = document.createElement("div");
        row.className = "ide-tree-row";
        row.style.paddingLeft = (6 + depth * 12) + "px";
        row.innerHTML = '<span>▸ ' + escapeHtml(n.nom) + '</span>';
        var open = Boolean(filter) || depth === 0;
        childBox.classList.toggle("hidden", !open);
        row.addEventListener("click", function () { childBox.classList.toggle("hidden"); });
        wrapper.appendChild(row);
        wrapper.appendChild(childBox);
        container.appendChild(wrapper);
      } else {
        if (filter && n.chemin.toLowerCase().indexOf(filter) === -1) return;
        var frow = document.createElement("div");
        frow.className = "ide-tree-row" + (n.chemin === state.activePath ? " active" : "");
        frow.dataset.path = n.chemin;
        frow.style.paddingLeft = (14 + depth * 12) + "px";
        frow.innerHTML =
          '<span>' + escapeHtml(n.nom) + '</span>' +
          (n.git ? '<span class="ide-git-badge">' + escapeHtml(n.git) + '</span>' : '');
        frow.addEventListener("click", function () { openFile(n.chemin, false); });
        container.appendChild(frow);
      }
    });
  }

  async function loadTree() {
    var r = await fetch("/api/ide/arborescence");
    var d = await r.json();
    if (d.ok) {
      state.treeNodes = d.noeuds || [];
      var box = els["ide-tree"];
      box.innerHTML = "";
      renderTreeNodes(state.treeNodes, box, 0, (els["ide-tree-filter"].value || "").trim().toLowerCase());
    }
  }

  async function loadState() {
    var r = await fetch("/api/ide/etat");
    var d = await r.json();
    if (!d.ok) return;
    var sel = els["ide-project-select"];
    sel.innerHTML = "";
    var listProj = (d.projets || []).slice();
    if (d.projet && !listProj.some(function (p) { return p.chemin === d.projet.chemin; })) {
      listProj.unshift({ nom: d.projet.nom, chemin: d.projet.chemin });
    }
    listProj.forEach(function (p) {
      var opt = document.createElement("option");
      opt.value = p.chemin;
      opt.textContent = p.nom;
      if (d.projet && p.chemin === d.projet.chemin) opt.selected = true;
      sel.appendChild(opt);
    });
    if (d.projet) {
      els["ide-branch-pill"].textContent = d.projet.branche || "no-git";
      els["ide-term-cwd"].textContent = d.projet.nom || ".";
    }
    if (d.fournisseur) {
      els["ide-model-label"].textContent = d.fournisseur.nom + " · " + d.fournisseur.modele;
      state.isAdmin = Boolean(d.fournisseur.admin);
      els["ide-cfg-profil"].value = d.fournisseur.profil || "auto";
      els["ide-cfg-profil-wrap"].classList.toggle("hidden", state.isAdmin);
      els["ide-admin-model-fields"].classList.toggle("hidden", !state.isAdmin);
      if (state.isAdmin) {
        els["ide-cfg-mode"].value = d.fournisseur.mode || "mistral";
        els["ide-cfg-baseurl-wrap"].classList.toggle("hidden", els["ide-cfg-mode"].value !== "custom");
      }
    }
    if (d.custom_base_url) els["ide-cfg-baseurl"].value = d.custom_base_url;
    await loadTree();
  }

  function appendAgentMsg(role, text, extraHtml) {
    var el = document.createElement("div");
    el.className = "ide-msg " + (role === "user" ? "ide-msg-user" : role === "tool" ? "ide-msg-tool" : "ide-msg-sys");
    el.textContent = text;
    if (extraHtml) {
      var extra = document.createElement("div");
      extra.innerHTML = extraHtml;
      el.appendChild(extra);
    }
    els["ide-agent-feed"].appendChild(el);
    els["ide-agent-feed"].scrollTop = els["ide-agent-feed"].scrollHeight;
    return el;
  }

  async function runAgentChat(prompt) {
    appendAgentMsg("user", "[" + state.agentMode.toUpperCase() + "] " + prompt);
    els["ide-agent-send"].disabled = true;
    var tab = currentTab();
    var payload = {
      message: prompt,
      mode: state.agentMode,
      review_mode: els["ide-review-mode"].checked,
      historique: state.history.slice(-8),
      fichier_actif: els["ide-attach-active"].checked && tab ? { chemin: tab.path, contenu: tab.content } : null
    };

    var statusEl = appendAgentMsg("tool", "Démarrage de l'agent RIOT...");
    try {
      var r = await fetch("/api/ide/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        var parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].trim();
          if (!line.startsWith("data:")) continue;
          var ev = JSON.parse(line.slice(5).trim());
          if (ev.type === "step") {
            statusEl.textContent = "⟳ " + ev.label;
          } else if (ev.type === "pending_patch" && ev.patch) {
            state.pendingPatches.push(ev.patch);
            state.activePatchId = ev.patch.id;
            renderPendingPatches();
            appendAgentMsg("tool", "⧗ Patch #" + ev.patch.id + " en attente sur " + ev.patch.chemin + " (+" + ev.patch.plus + "/-" + ev.patch.moins + ")");
          } else if (ev.type === "tool") {
            appendAgentMsg("tool", (ev.statut === "running" ? "▸ " : "✓ ") + ev.nom + (ev.extrait ? " -> " + ev.extrait.slice(0, 160) : ""));
          } else if (ev.type === "file_changed" && ev.chemin) {
            loadTree();
            if (state.tabs.some(function (t) { return t.path === ev.chemin; })) openFile(ev.chemin, true);
          } else if (ev.type === "artifact" && ev.kind === "image" && ev.detail) {
            var m = ev.detail.match(/(\/captures\/[^\s`]+)/);
            if (m) appendAgentMsg("system", "Maquette générée :", '<img class="ide-msg-img" src="' + escapeHtml(m[1]) + '" alt="Apercu" />');
          } else if (ev.type === "done") {
            statusEl.remove();
            appendAgentMsg("system", ev.texte || "");
            state.history.push({ role: "user", content: prompt }, { role: "assistant", content: ev.texte || "" });
          } else if (ev.type === "error") {
            statusEl.remove();
            appendAgentMsg("system", "Erreur agent : " + ev.erreur);
          }
        }
      }
    } catch (e) {
      appendAgentMsg("system", "Erreur connexion agent : " + e.message);
    } finally {
      els["ide-agent-send"].disabled = false;
    }
  }

  function setupResizers() {
    function persistWidths() {
      try {
        localStorage.setItem("riot_ide_layout", JSON.stringify({
          left: els["ide-sidebar"].style.width,
          right: els["ide-agent"].style.width,
          term: els["ide-terminal-panel"].style.height
        }));
      } catch (_) {}
    }
    try {
      var saved = JSON.parse(localStorage.getItem("riot_ide_layout") || "{}");
      if (saved.left) els["ide-sidebar"].style.width = saved.left;
      if (saved.right) els["ide-agent"].style.width = saved.right;
      if (saved.term) els["ide-terminal-panel"].style.height = saved.term;
    } catch (_) {}

    function dragX(handle, target, invert) {
      handle.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        handle.classList.add("active");
        var startX = ev.clientX;
        var startW = target.getBoundingClientRect().width;
        function onMove(m) {
          var dx = invert ? (startX - m.clientX) : (m.clientX - startX);
          target.style.width = Math.max(180, Math.min(560, startW + dx)) + "px";
        }
        function onUp() {
          handle.classList.remove("active");
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          persistWidths();
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    }
    dragX(els["ide-resizer-left"], els["ide-sidebar"], false);
    dragX(els["ide-resizer-right"], els["ide-agent"], true);

    els["ide-resizer-term"].addEventListener("mousedown", function (ev) {
      ev.preventDefault();
      els["ide-resizer-term"].classList.add("active");
      var startY = ev.clientY;
      var startH = els["ide-terminal-panel"].getBoundingClientRect().height;
      function onMove(m) {
        els["ide-terminal-panel"].style.height = Math.max(90, Math.min(440, startH + (startY - m.clientY))) + "px";
      }
      function onUp() {
        els["ide-resizer-term"].classList.remove("active");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        persistWidths();
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  async function openQuickOpen() {
    els["ide-quickopen-modal"].classList.remove("hidden");
    els["ide-quickopen-input"].value = "";
    els["ide-quickopen-input"].focus();
    var r = await fetch("/api/ide/chemins");
    var d = await r.json();
    state.allPaths = (d && d.chemins) ? d.chemins : [];
    renderQuickOpen("");
  }

  function renderQuickOpen(filter) {
    var f = (filter || "").trim().toLowerCase();
    var list = els["ide-quickopen-list"];
    list.innerHTML = "";
    state.allPaths.filter(function (p) { return !f || p.toLowerCase().indexOf(f) !== -1; }).slice(0, 40).forEach(function (p) {
      var item = document.createElement("div");
      item.className = "ide-qo-item";
      item.textContent = p;
      item.addEventListener("click", function () {
        els["ide-quickopen-modal"].classList.add("hidden");
        openFile(p, false);
      });
      list.appendChild(item);
    });
  }

  function wireEvents() {
    document.querySelectorAll(".ide-stab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".ide-stab").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        var target = btn.getAttribute("data-stab");
        q("ide-pane-explorer").classList.toggle("active", target === "explorer");
        q("ide-pane-search").classList.toggle("active", target === "search");
      });
    });

    document.querySelectorAll(".ide-mpill").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".ide-mpill").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.agentMode = btn.getAttribute("data-mode");
      });
    });

    els["ide-tree-filter"].addEventListener("input", function () {
      var box = els["ide-tree"];
      box.innerHTML = "";
      renderTreeNodes(state.treeNodes, box, 0, (els["ide-tree-filter"].value || "").trim().toLowerCase());
    });

    els["ide-btn-refresh"].addEventListener("click", loadTree);
    els["ide-btn-newfile"].addEventListener("click", async function () {
      var rel = window.prompt("Chemin du nouveau fichier (ex: src/nouveau.py) :");
      if (!rel) return;
      var r = await fetch("/api/ide/fichier", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chemin: rel, contenu: "", creer: true })
      });
      var d = await r.json();
      if (d.ok) { await loadTree(); await openFile(d.chemin, true); }
      else window.alert(d.erreur || "Impossible de créer le fichier");
    });

    var folderParent = "";
    async function activateProjectFolder(chemin) {
      var r = await fetch("/api/ide/projet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chemin: chemin })
      });
      var d = await r.json();
      if (!r.ok || !d.ok) {
        window.alert(d.erreur || "Impossible d'ouvrir ce dossier.");
        return false;
      }
      state.tabs = [];
      state.activePath = null;
      renderTabs();
      await loadState();
      return true;
    }

    async function browseFolder(chemin) {
      var qs = chemin ? ("?chemin=" + encodeURIComponent(chemin)) : "";
      var r = await fetch("/api/ide/naviguer-dossiers" + qs);
      var d = await r.json();
      if (!r.ok || !d.ok) {
        window.alert(d.erreur || "Dossier inaccessible.");
        return;
      }
      els["ide-folder-path"].value = d.courant || "";
      folderParent = d.parent || "";
      els["ide-folder-up"].disabled = !folderParent;

      var rootsEl = els["ide-folder-roots"];
      rootsEl.innerHTML = "";
      (d.racines || []).forEach(function (rt) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "ide-pill ide-pill-btn";
        b.textContent = rt.nom;
        b.addEventListener("click", function () { void browseFolder(rt.chemin); });
        rootsEl.appendChild(b);
      });

      var listEl = els["ide-folder-list"];
      listEl.innerHTML = "";
      var subs = d.dossiers || [];
      if (subs.length === 0) {
        var empty = document.createElement("div");
        empty.className = "ide-hint";
        empty.style.padding = "10px";
        empty.textContent = "Aucun sous-dossier ici. Cliquez sur « Ouvrir ce dossier » pour sélectionner le dossier courant.";
        listEl.appendChild(empty);
      } else {
        subs.forEach(function (sub) {
          var row = document.createElement("div");
          row.className = "ide-folder-row";
          row.textContent = "📁 " + sub.nom;
          row.addEventListener("click", function () { void browseFolder(sub.chemin); });
          listEl.appendChild(row);
        });
      }
    }

    function openFolderModal() {
      els["ide-folder-modal"].classList.remove("hidden");
      void browseFolder(els["ide-project-select"].value || "");
    }

    els["ide-btn-openfolder"].addEventListener("click", openFolderModal);
    els["ide-folder-close"].addEventListener("click", function () { els["ide-folder-modal"].classList.add("hidden"); });
    els["ide-folder-cancel"].addEventListener("click", function () { els["ide-folder-modal"].classList.add("hidden"); });
    els["ide-folder-modal"].addEventListener("click", function (ev) {
      if (ev.target === els["ide-folder-modal"]) els["ide-folder-modal"].classList.add("hidden");
    });
    els["ide-folder-up"].addEventListener("click", function () {
      if (folderParent) void browseFolder(folderParent);
    });
    els["ide-folder-go"].addEventListener("click", function () {
      void browseFolder(els["ide-folder-path"].value.trim());
    });
    els["ide-folder-path"].addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        void browseFolder(els["ide-folder-path"].value.trim());
      }
    });
    els["ide-folder-open"].addEventListener("click", async function () {
      var target = els["ide-folder-path"].value.trim();
      if (!target) return;
      if (await activateProjectFolder(target)) {
        els["ide-folder-modal"].classList.add("hidden");
      }
    });
    els["ide-folder-os"].addEventListener("click", async function () {
      var r = await fetch("/api/ide/choisir-dossier-os", { method: "POST" });
      var d = await r.json();
      if (d.ok && d.chemin) {
        if (await activateProjectFolder(d.chemin)) {
          els["ide-folder-modal"].classList.add("hidden");
        }
      } else if (!d.annule) {
        window.alert(d.erreur || "Sélecteur système indisponible.");
      }
    });

    els["ide-project-select"].addEventListener("change", async function () {
      await activateProjectFolder(els["ide-project-select"].value);
    });

    els["ide-editor"].addEventListener("input", function () {
      var tab = currentTab();
      if (!tab) return;
      tab.content = els["ide-editor"].value;
      tab.dirty = tab.content !== tab.savedContent;
      updateGutter();
      updateBreadcrumb(tab);
    });
    els["ide-editor"].addEventListener("scroll", function () {
      els["ide-gutter"].scrollTop = els["ide-editor"].scrollTop;
    });

    els["ide-btn-save"].addEventListener("click", saveActiveFile);
    els["ide-btn-diff"].addEventListener("click", function () {
      var tab = currentTab();
      renderDiffLines((tab && tab.diff) ? tab.diff : "Enregistrez d'abord une modification pour afficher le diff.", tab ? "Diff : " + tab.path : "Inspecteur de Diff");
      var opening = els["ide-diff-wrap"].classList.contains("hidden");
      els["ide-diff-wrap"].classList.toggle("hidden");
      if (opening) els["ide-empty-state"].classList.add("hidden");
      else if (!tab) els["ide-empty-state"].classList.remove("hidden");
    });
    els["ide-diff-close"].addEventListener("click", function () {
      els["ide-diff-wrap"].classList.add("hidden");
      if (!currentTab() && els["ide-preview-wrap"].classList.contains("hidden")) {
        els["ide-empty-state"].classList.remove("hidden");
      }
    });

    els["ide-btn-preview"].addEventListener("click", function () {
      var tab = currentTab();
      if (!tab) return;
      els["ide-preview-wrap"].classList.toggle("hidden");
      if (!els["ide-preview-wrap"].classList.contains("hidden")) {
        els["ide-empty-state"].classList.add("hidden");
        els["ide-preview-wrap"].innerHTML = (typeof window.marked !== "undefined")
          ? window.marked.parse(tab.content)
          : "<pre>" + escapeHtml(tab.content) + "</pre>";
      }
    });

    els["ide-patch-accept"].addEventListener("click", async function () {
      if (!state.activePatchId) return;
      var pid = state.activePatchId;
      var r = await fetch("/api/ide/patch/" + pid + "/accept", { method: "POST" });
      var d = await r.json();
      state.pendingPatches = state.pendingPatches.filter(function (x) { return x.id !== pid; });
      if (d.ok) {
        state.lastAcceptedPatch = { id: pid, chemin: d.chemin };
        els["ide-btn-revert"].classList.remove("hidden");
        els["ide-diff-wrap"].classList.add("hidden");
        await loadTree();
        await openFile(d.chemin, true);
        appendAgentMsg("system", "✓ Patch #" + pid + " appliqué sur " + d.chemin + ".");
      }
      renderPendingPatches();
    });

    els["ide-btn-revert"].addEventListener("click", async function () {
      if (!state.lastAcceptedPatch) return;
      var pid = state.lastAcceptedPatch.id;
      var r = await fetch("/api/ide/patch/" + pid + "/revert", { method: "POST" });
      var d = await r.json();
      if (d.ok) {
        appendAgentMsg("system", "↶ Patch #" + pid + " annulé sur " + d.chemin + ".");
        state.lastAcceptedPatch = null;
        els["ide-btn-revert"].classList.add("hidden");
        await loadTree();
        if (!d.supprime) await openFile(d.chemin, true);
      }
    });

    els["ide-patch-reject"].addEventListener("click", async function () {
      if (!state.activePatchId) return;
      var pid = state.activePatchId;
      await fetch("/api/ide/patch/" + pid + "/reject", { method: "POST" });
      state.pendingPatches = state.pendingPatches.filter(function (x) { return x.id !== pid; });
      els["ide-diff-wrap"].classList.add("hidden");
      appendAgentMsg("system", "✕ Patch #" + pid + " rejeté.");
      renderPendingPatches();
    });

    els["ide-pending-count"].addEventListener("click", renderPendingPatches);
    els["ide-btn-term-toggle"].addEventListener("click", function () { els["ide-terminal-panel"].classList.toggle("hidden"); });
    els["ide-term-clear"].addEventListener("click", function () { els["ide-term-output"].textContent = ""; });
    els["ide-term-form"].addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var cmd = (els["ide-term-input"].value || "").trim();
      if (!cmd) return;
      els["ide-term-input"].value = "";
      els["ide-term-output"].textContent += "\n$ " + cmd + "\n";
      var r = await fetch("/api/ide/terminal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commande: cmd })
      });
      var d = await r.json();
      els["ide-term-output"].textContent += (d.stdout || "") + (d.stderr ? "\n[stderr]\n" + d.stderr : "") + "\n(exit " + (d.returncode ?? "?") + " · " + (d.duree_ms || 0) + " ms)\n";
      els["ide-term-output"].scrollTop = els["ide-term-output"].scrollHeight;
    });

    els["ide-search-form"].addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var r = await fetch("/api/ide/recherche", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requete: els["ide-search-input"].value })
      });
      var d = await r.json();
      var box = els["ide-search-results"];
      box.innerHTML = "";
      (d.resultats || []).forEach(function (hit) {
        var item = document.createElement("div");
        item.className = "ide-search-hit";
        item.innerHTML = '<div class="ide-search-path">' + escapeHtml(hit.chemin) + ":" + hit.ligne + '</div><div class="ide-search-line">' + escapeHtml(hit.extrait) + '</div>';
        item.addEventListener("click", function () { openFile(hit.chemin, false); });
        box.appendChild(item);
      });
    });

    els["ide-agent-form"].addEventListener("submit", function (ev) {
      ev.preventDefault();
      var msg = (els["ide-agent-input"].value || "").trim();
      if (!msg) return;
      els["ide-agent-input"].value = "";
      runAgentChat(msg);
    });
    els["ide-agent-input"].addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
        ev.preventDefault();
        els["ide-agent-form"].requestSubmit();
      }
    });

    els["ide-btn-quickopen"].addEventListener("click", openQuickOpen);
    els["ide-quickopen-input"].addEventListener("input", function () { renderQuickOpen(els["ide-quickopen-input"].value); });
    els["ide-quickopen-modal"].addEventListener("click", function (ev) {
      if (ev.target === els["ide-quickopen-modal"]) els["ide-quickopen-modal"].classList.add("hidden");
    });

    async function loadMcpConnectors() {
      if (!els["ide-mcp-list"]) return;
      els["ide-mcp-summary"].textContent = "Chargement du catalogue MCP...";
      var r = await fetch("/api/ide/mcp");
      var d = await r.json();
      if (!r.ok || !d.ok) {
        els["ide-mcp-summary"].textContent = d.erreur || "Erreur chargement MCP.";
        return;
      }
      var st = d.statut || {};
      var srvs = st.serveurs || {};
      els["ide-mcp-summary"].textContent = (st.total_outils_mcp || 0) + " outil(s) MCP actif(s) · Config : " + (d.config_path || "~/.riot/mcp_servers.json");
      var box = els["ide-mcp-list"];
      box.innerHTML = "";
      (d.catalogue || []).forEach(function (c) {
        var live = srvs[c.slug] || {};
        var statutTxt = live.statut || (c.actif ? "actif" : (c.installe ? "désactivé" : "disponible"));
        var row = document.createElement("div");
        row.className = "ide-folder-row";
        row.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:10px;cursor:default;";
        var info = document.createElement("div");
        info.style.cssText = "display:flex;flex-direction:column;gap:2px;";
        info.innerHTML =
          "<strong>" + escapeHtml(c.slug) + " <span style='opacity:.65;font-weight:400;'>[" + escapeHtml(c.categorie) + " · " + escapeHtml(statutTxt) + "]</span></strong>" +
          "<span style='font-size:12px;opacity:.8;'>" + escapeHtml(c.description) + "</span>" +
          (live.erreur ? "<span style='font-size:11px;color:#f87171;'>" + escapeHtml(live.erreur) + "</span>" : "");
        var actions = document.createElement("div");
        actions.style.cssText = "display:flex;gap:6px;flex-shrink:0;";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = c.actif ? "ide-btn-sm" : "ide-btn-sm ide-btn-accent";
        btn.textContent = c.actif ? "Désactiver" : (c.installe ? "Activer" : "Installer");
        btn.addEventListener("click", async function () {
          btn.disabled = true;
          if (!c.installe) {
            var cred = "";
            if (c.env_requis && c.env_requis.length > 0) {
              cred = window.prompt("Clé / URL pour " + c.slug + " (" + c.env_requis.join(", ") + ") — laissez vide si déjà en variable d'env :", "") || "";
            }
            await fetch("/api/ide/mcp/add", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ slug: c.slug, credential: cred })
            });
          } else {
            await fetch("/api/ide/mcp/toggle", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ nom: c.slug, enabled: !c.actif })
            });
          }
          await loadMcpConnectors();
        });
        actions.appendChild(btn);
        row.appendChild(info);
        row.appendChild(actions);
        box.appendChild(row);
      });
    }

    if (els["ide-btn-mcp"]) {
      els["ide-btn-mcp"].addEventListener("click", function () {
        els["ide-mcp-modal"].classList.remove("hidden");
        void loadMcpConnectors();
      });
      els["ide-mcp-close"].addEventListener("click", function () { els["ide-mcp-modal"].classList.add("hidden"); });
      els["ide-mcp-modal"].addEventListener("click", function (ev) {
        if (ev.target === els["ide-mcp-modal"]) els["ide-mcp-modal"].classList.add("hidden");
      });
      els["ide-mcp-reload"].addEventListener("click", async function () {
        els["ide-mcp-reload"].disabled = true;
        await fetch("/api/ide/mcp/reload", { method: "POST" });
        els["ide-mcp-reload"].disabled = false;
        await loadMcpConnectors();
      });
    }

    els["ide-btn-model"].addEventListener("click", function () { els["ide-model-modal"].classList.remove("hidden"); });
    els["ide-modal-close"].addEventListener("click", function () { els["ide-model-modal"].classList.add("hidden"); });
    els["ide-cfg-mode"].addEventListener("change", function () {
      els["ide-cfg-baseurl-wrap"].classList.toggle("hidden", els["ide-cfg-mode"].value !== "custom");
    });
    els["ide-model-form"].addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var payload = state.isAdmin ? {
        mode: els["ide-cfg-mode"].value,
        base_url: els["ide-cfg-baseurl"].value,
        modele: els["ide-cfg-model"].value,
        cle: els["ide-cfg-key"].value
      } : {
        profil: els["ide-cfg-profil"].value
      };
      var r = await fetch("/api/ide/modele", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      var d = await r.json();
      if (d.ok) {
        els["ide-model-label"].textContent = d.nom + " · " + d.modele;
        els["ide-model-modal"].classList.add("hidden");
      }
    });

    document.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") {
        ev.preventDefault();
        saveActiveFile();
      } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "o") {
        ev.preventDefault();
        openFolderModal();
      } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "p") {
        ev.preventDefault();
        openQuickOpen();
      } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "`") {
        ev.preventDefault();
        els["ide-terminal-panel"].classList.toggle("hidden");
      } else if (ev.key === "Escape") {
        els["ide-quickopen-modal"].classList.add("hidden");
        els["ide-folder-modal"].classList.add("hidden");
        if (els["ide-mcp-modal"]) els["ide-mcp-modal"].classList.add("hidden");
        els["ide-model-modal"].classList.add("hidden");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindEls();
    setupResizers();
    wireEvents();
    loadState();
  });
})();
