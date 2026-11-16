(function () {
  var THEMES = {
    obsidian: { label: "Obsidian", dot: "#E8A838", bg: "#0B0C0E" },
    paper: { label: "Encre", dot: "#059669", bg: "#F6F5F0" },
    tactical: { label: "Tactical", dot: "#4ADE80", bg: "#090B0D" }
  };

  function normalize(name) {
    if (!name) return "obsidian";
    var k = String(name).trim().toLowerCase();
    if (k === "ambre" || k === "amber" || k === "dark") return "obsidian";
    if (k === "encre" || k === "emeraude" || k === "light" || k === "clair") return "paper";
    if (k === "ops" || k === "tactical_ops") return "tactical";
    return THEMES[k] ? k : "obsidian";
  }

  function initialTheme() {
    try {
      var params = new URLSearchParams(window.location.search);
      var fromUrl = params.get("theme");
      if (fromUrl) return normalize(fromUrl);
      var fromStorage = localStorage.getItem("riot_theme");
      if (fromStorage) return normalize(fromStorage);
    } catch (_) {}
    return "obsidian";
  }

  function apply(name, persistServer) {
    var t = normalize(name);
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("riot_theme", t); } catch (_) {}

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta && THEMES[t]) meta.setAttribute("content", THEMES[t].bg);

    document.querySelectorAll(".riot-theme-btn[data-theme-choice]").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-theme-choice") === t);
    });

    if (typeof window.mermaid !== "undefined" && window.mermaid && window.mermaid.initialize) {
      try {
        window.mermaid.initialize({ startOnLoad: false, theme: t === "paper" ? "default" : "dark" });
      } catch (_) {}
    }

    if (persistServer) {
      try {
        fetch("/api/theme", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ theme: t })
        }).catch(function () {});
      } catch (_) {}
    }

    try {
      window.dispatchEvent(new CustomEvent("riot:theme-change", { detail: { theme: t } }));
    } catch (_) {}
    return t;
  }

  function mountSwitchers() {
    var current = document.documentElement.getAttribute("data-theme") || initialTheme();
    document.querySelectorAll("[data-riot-theme-switcher]").forEach(function (host) {
      if (host.dataset.mounted === "1") return;
      host.dataset.mounted = "1";
      host.classList.add("riot-theme-switcher");
      Object.keys(THEMES).forEach(function (id) {
        var cfg = THEMES[id];
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "riot-theme-btn" + (id === current ? " active" : "");
        btn.setAttribute("data-theme-choice", id);
        btn.title = "Theme " + cfg.label;
        btn.innerHTML =
          '<span class="riot-theme-dot" style="background:' + cfg.dot + '"></span>' +
          '<span class="riot-theme-label">' + cfg.label + '</span>';
        btn.addEventListener("click", function () {
          apply(id, true);
        });
        host.appendChild(btn);
      });
    });
  }

  // Appliquer immediatement pour eviter le flash au chargement
  apply(initialTheme(), false);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountSwitchers();
      // Synchroniser si aucun choix local explicite n'etait encore stocke
      try {
        if (!localStorage.getItem("riot_theme")) {
          fetch("/api/theme").then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
            if (d && d.theme) apply(d.theme, false);
          }).catch(function () {});
        }
      } catch (_) {}
    });
  } else {
    mountSwitchers();
  }

  window.RiotTheme = {
    get: function () { return document.documentElement.getAttribute("data-theme") || "obsidian"; },
    set: function (name) { return apply(name, true); },
    mount: mountSwitchers,
    themes: THEMES
  };
})();

