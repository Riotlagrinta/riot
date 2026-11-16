(function () {
  var state = {
    tabs: [], // { path, name, content, savedContent, dirty, diff }
    activePath: null,
    agentMode: "code",
    history: [],
    treeNodes: []
  };

  var els = {};
  function q(id) { return document.getElementById(id); }

  function bindEls() {
    [
      "ide-project-select", "ide-branch-pill", "ide-btn-model", "ide-model-label",
      "ide-tree", "ide-tree-filter", "ide-btn-newfile", "ide-btn-refresh",
      "ide-search-form", "ide-search-input", "ide-search-results",
      "ide-tabs", "ide-breadcrumb", "ide-empty-state", "ide-code-wrap",
      "ide-gutter", "ide-editor", "ide-diff-wrap", "ide-diff-pre",
      "ide-diff-close", "ide-btn-diff", "ide-btn-save", "ide-btn-term-toggle",
      "ide-terminal-panel", "ide-term-cwd", "ide-term-output", "ide-term-form",
      "ide-term-input", "ide-term-clear", "ide-agent-feed", "ide-agent-form",
      "ide-agent-input", "ide-agent-send", "ide-attach-active", "ide-active-file-chip",
      "ide-model-modal", "ide-modal-close", "ide-model-form",
      "ide-cfg-mode", "ide-cfg-baseurl-wrap", "ide-cfg-baseurl", "ide-cfg-model", "ide-cfg-key"
    ].forEach(function (id) { els[id] = q(id); });
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function updateGutter() {
    var txt = els["ide-editor"].value || "";
    var count = txt.split("\n").length;
    var nums = [];
    for (var i = 1; i <= count; i++) nums.push(i);
    els["ide-gutter"].textContent = nums.join("\n");
  }

  function currentTab() {
    return state.tabs.find(function (t) { return t.path === state.activePath; }) || null;
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
        if (ev.target.classList.contains("ide-tab-close")) {
          closeTab(tab.path);
        } else {
          selectTab(tab.path);
        }
      });
      box.appendChild(el);
    });

    var act = currentTab();
    if (!act) {
      els["ide-empty-state"].classList.remove("hidden");
      els["ide-code-wrap"].classList.add("hidden");
      els["ide-breadcrumb"].textContent = "Sélectionnez un fichier à gauche ou demandez à l'agent RIOT.";
      els["ide-active-file-chip"].textContent = "Joindre onglet actif (aucun)";
    } else {
      els["ide-empty-state"].classList.add("hidden");
      els["ide-code-wrap"].classList.remove("hidden");
      els["ide-editor"].value = act.content;
      updateGutter();
      els["ide-breadcrumb"].textContent = act.path + " · " + act.content.split("\n").length + " lignes" + (act.dirty ? " (modifié)" : "");
      els["ide-active-file-chip"].textContent = "Joindre " + act.path;
    }
  }

  function selectTab(path) {
    state.activePath = path;
    els["ide-diff-wrap"].classList.add("hidden");
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
        existing.dirty = false;
      } else {
        state.tabs.push({
          path: d.chemin,
          name: d.nom,
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
    try {
      var r = await fetch("/api/ide/fichier", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chemin: tab.path, contenu: tab.content, creer: false })
      });
      var d = await r.json();
      if (!d.ok) {
        appendAgentMsg("system", "Echec sauvegarde : " + (d.erreur || ""));
        return;
      }
      tab.savedContent = tab.content;
      tab.dirty = false;
      tab.diff = d.diff || "(aucune différence)";
      renderTabs();
      loadTree();
    } catch (e) {
      appendAgentMsg("system", "Erreur sauvegarde : " + e.message);
    }
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
        if (filter && childBox.children.length === 0 && n.nom.toLowerCase().indexOf(filter) === -1) {
          return;
        }
        var row = document.createElement("div");
        row.className = "ide-tree-row";
        row.style.paddingLeft = (6 + depth * 12) + "px";
        row.innerHTML = '<span>▸ ' + escapeHtml(n.nom) + '</span>';
        var open = Boolean(filter) || depth === 0;
        childBox.classList.toggle("hidden", !open);
        row.addEventListener("click", function () {
          childBox.classList.toggle("hidden");
        });
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
    (d.projets || []).forEach(function (p) {
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
      els["ide-cfg-mode"].value = d.fournisseur.mode || "mistral";
      els["ide-cfg-baseurl-wrap"].classList.toggle("hidden", els["ide-cfg-mode"].value !== "custom");
    }
    if (d.custom_base_url) {
      els["ide-cfg-baseurl"].value = d.custom_base_url;
    }
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
      var finalAnswer = "";

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
          } else if (ev.type === "tool") {
            if (ev.statut === "running") {
              appendAgentMsg("tool", "▸ " + ev.nom + "(" + JSON.stringify(ev.args || {}).slice(0, 120) + ")");
            } else {
              appendAgentMsg("tool", "✓ " + ev.nom + " -> " + (ev.extrait || "").slice(0, 180));
            }
          } else if (ev.type === "file_changed" && ev.chemin) {
            loadTree();
            var opened = state.tabs.find(function (t) { return t.path === ev.chemin; });
            if (opened) openFile(ev.chemin, true);
          } else if (ev.type === "artifact" && ev.kind === "image" && ev.detail) {
            var m = ev.detail.match(/(\/captures\/[^\s`]+)/);
            if (m) {
              appendAgentMsg("system", "Maquette générée :", '<img class="ide-msg-img" src="' + escapeHtml(m[1]) + '" alt="Apercu" />');
            }
          } else if (ev.type === "done") {
            finalAnswer = ev.texte || "";
            statusEl.remove();
            appendAgentMsg("system", finalAnswer);
            state.history.push({ role: "user", content: prompt }, { role: "assistant", content: finalAnswer });
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
      if (d.ok) {
        await loadTree();
        await openFile(d.chemin, true);
      } else {
        window.alert(d.erreur || "Impossible de créer le fichier");
      }
    });

    els["ide-project-select"].addEventListener("change", async function () {
      await fetch("/api/ide/projet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chemin: els["ide-project-select"].value })
      });
      state.tabs = [];
      state.activePath = null;
      renderTabs();
      await loadState();
    });

    els["ide-editor"].addEventListener("input", function () {
      var tab = currentTab();
      if (!tab) return;
      tab.content = els["ide-editor"].value;
      tab.dirty = tab.content !== tab.savedContent;
      updateGutter();
      els["ide-breadcrumb"].textContent = tab.path + " · " + tab.content.split("\n").length + " lignes" + (tab.dirty ? " (modifié)" : "");
    });

    els["ide-editor"].addEventListener("scroll", function () {
      els["ide-gutter"].scrollTop = els["ide-editor"].scrollTop;
    });

    els["ide-btn-save"].addEventListener("click", saveActiveFile);
    els["ide-btn-diff"].addEventListener("click", function () {
      var tab = currentTab();
      els["ide-diff-pre"].textContent = (tab && tab.diff) ? tab.diff : "Enregistrez d'abord une modification pour afficher le diff.";
      els["ide-diff-wrap"].classList.toggle("hidden");
    });
    els["ide-diff-close"].addEventListener("click", function () {
      els["ide-diff-wrap"].classList.add("hidden");
    });

    els["ide-btn-term-toggle"].addEventListener("click", function () {
      els["ide-terminal-panel"].classList.toggle("hidden");
    });
    els["ide-term-clear"].addEventListener("click", function () {
      els["ide-term-output"].textContent = "";
    });
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

    els["ide-btn-model"].addEventListener("click", function () {
      els["ide-model-modal"].classList.remove("hidden");
    });
    els["ide-modal-close"].addEventListener("click", function () {
      els["ide-model-modal"].classList.add("hidden");
    });
    els["ide-cfg-mode"].addEventListener("change", function () {
      els["ide-cfg-baseurl-wrap"].classList.toggle("hidden", els["ide-cfg-mode"].value !== "custom");
    });
    els["ide-model-form"].addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var r = await fetch("/api/ide/modele", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: els["ide-cfg-mode"].value,
          base_url: els["ide-cfg-baseurl"].value,
          modele: els["ide-cfg-model"].value,
          cle: els["ide-cfg-key"].value
        })
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
      } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "`") {
        ev.preventDefault();
        els["ide-terminal-panel"].classList.toggle("hidden");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindEls();
    wireEvents();
    loadState();
  });
})();

