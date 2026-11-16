"""Verification non-bloquante et execution des mises a jour de RIOT.

Sources surveillees (avec cache local 24h pour ne jamais ralentir le demarrage) :
  - Depot GitHub (pyproject.toml / dernier commit master)
  - Registre npm (@riotlagrinta/riot)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

LOG = logging.getLogger("riot.updater")

_RACINE = Path(__file__).resolve().parent.parent
_CACHE_DIR = Path.home() / ".riot"
_CACHE_FICHIER = _CACHE_DIR / "update_cache.json"
_TTL_SECONDES = 24 * 3600

GITHUB_PYPROJECT_URL = "https://raw.githubusercontent.com/Riotlagrinta/riot/master/pyproject.toml"
GITHUB_API_COMMIT_URL = "https://api.github.com/repos/Riotlagrinta/riot/commits/master"
NPM_REGISTRY_URL = "https://registry.npmjs.org/@riotlagrinta/riot/latest"

_LOCK = threading.Lock()
_ETAT_MEMOIRE: Optional[Dict[str, Any]] = None


def _semver_tuple(v: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))]
    return tuple(nums[:4]) if nums else (0,)


def _est_plus_recent(distant: str, local: str) -> bool:
    if not distant or not local:
        return False
    td = _semver_tuple(distant)
    tl = _semver_tuple(local)
    max_len = max(len(td), len(tl))
    td = td + (0,) * (max_len - len(td))
    tl = tl + (0,) * (max_len - len(tl))
    return td > tl


def version_locale() -> str:
    """Lit la version Python locale depuis pyproject.toml ou importlib.metadata."""
    pyproj = _RACINE / "pyproject.toml"
    if pyproj.exists():
        try:
            txt = pyproj.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', txt)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    try:
        from importlib.metadata import version

        return version("riot")
    except Exception:
        return "0.2.0"


def version_npm_locale() -> str:
    pkg = _RACINE / "npm" / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            return str(data.get("version", "")).strip()
        except Exception:
            pass
    return ""


def _commit_local() -> str:
    if not (_RACINE / ".git").exists():
        return ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=str(_RACINE),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def detecter_mode_installation() -> str:
    if (_RACINE / ".git").exists():
        return "git"
    exe = (sys.executable or "").lower()
    if "uv" in exe or "tools" in exe:
        return "uv"
    return "pip"


def _lire_cache() -> Optional[Dict[str, Any]]:
    try:
        if not _CACHE_FICHIER.exists():
            return None
        data = json.loads(_CACHE_FICHIER.read_text(encoding="utf-8"))
        if time.time() - float(data.get("checked_at", 0)) < _TTL_SECONDES:
            return data
    except Exception:
        pass
    return None


def _ecrire_cache(data: Dict[str, Any]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FICHIER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _interroger_sources() -> Dict[str, Any]:
    import requests

    ver_distante = ""
    commit_distant = ""
    npm_distante = ""

    try:
        r = requests.get(GITHUB_PYPROJECT_URL, timeout=2.5)
        if r.ok:
            m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', r.text)
            if m:
                ver_distante = m.group(1).strip()
    except Exception as e:
        LOG.debug("updater github pyproject: %s", e)

    try:
        r = requests.get(
            GITHUB_API_COMMIT_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=2.5,
        )
        if r.ok:
            sha = str(r.json().get("sha", "")).strip()
            if sha:
                commit_distant = sha[:7]
    except Exception as e:
        LOG.debug("updater github commit: %s", e)

    try:
        r = requests.get(NPM_REGISTRY_URL, timeout=2.5)
        if r.ok:
            npm_distante = str(r.json().get("version", "")).strip()
    except Exception as e:
        LOG.debug("updater npm: %s", e)

    return {
        "checked_at": time.time(),
        "version_distante": ver_distante,
        "commit_distant": commit_distant,
        "npm_distante": npm_distante,
    }


def _assembler_etat(brut: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    v_loc = version_locale()
    npm_loc = version_npm_locale()
    c_loc = _commit_local()
    mode = detecter_mode_installation()

    brut = brut or {}
    v_dist = str(brut.get("version_distante", "") or "")
    c_dist = str(brut.get("commit_distant", "") or "")
    npm_dist = str(brut.get("npm_distante", "") or "")

    maj_version = _est_plus_recent(v_dist, v_loc)
    maj_npm = bool(npm_loc and npm_dist and _est_plus_recent(npm_dist, npm_loc))
    maj_commit = bool(c_loc and c_dist and c_loc != c_dist and mode == "git")
    disponible = maj_version or maj_npm or maj_commit

    if mode == "git":
        cmd = "git pull --ff-only"
    elif mode == "uv":
        cmd = "riot --update-cli"
    else:
        cmd = "npm install -g @riotlagrinta/riot@latest"

    cible = v_dist or (f"commit {c_dist}" if c_dist else npm_dist)
    details = (
        f"Nouvelle version RIOT disponible ({cible}) — commande : {cmd}"
        if disponible
        else f"RIOT est a jour (v{v_loc}{f' · {c_loc}' if c_loc else ''})."
    )

    return {
        "ok": True,
        "version_locale": v_loc,
        "version_distante": v_dist or v_loc,
        "npm_locale": npm_loc,
        "npm_distante": npm_dist,
        "commit_local": c_loc,
        "commit_distant": c_dist,
        "mode_install": mode,
        "disponible": disponible,
        "maj_version": maj_version,
        "maj_npm": maj_npm,
        "maj_commit": maj_commit,
        "commande_maj": cmd,
        "details": details,
        "checked_at": brut.get("checked_at", 0),
    }


def etat_mise_a_jour(forcer: bool = False, sans_reseau: bool = False) -> Dict[str, Any]:
    """Retourne l'etat de mise a jour (utilise le cache 24h sauf si forcer=True)."""
    global _ETAT_MEMOIRE
    if os.environ.get("RIOT_NO_UPDATE_CHECK") == "1":
        return _assembler_etat(None)

    with _LOCK:
        if _ETAT_MEMOIRE and not forcer:
            if time.time() - float(_ETAT_MEMOIRE.get("checked_at", 0)) < _TTL_SECONDES:
                return dict(_ETAT_MEMOIRE)

        cache = None if forcer else _lire_cache()
        if cache is None and not sans_reseau:
            cache = _interroger_sources()
            if cache.get("version_distante") or cache.get("commit_distant") or cache.get("npm_distante"):
                _ecrire_cache(cache)

        etat = _assembler_etat(cache)
        _ETAT_MEMOIRE = etat
        return dict(etat)


def lancer_verification_arriere_plan(callback=None) -> None:
    """Verifie les mises a jour en tache de fond sans bloquer le demarrage."""
    if os.environ.get("RIOT_NO_UPDATE_CHECK") == "1":
        return

    def _job():
        try:
            etat = etat_mise_a_jour(forcer=False, sans_reseau=False)
            if callback and etat.get("disponible"):
                callback(etat)
        except Exception as e:
            LOG.debug("verification maj arriere-plan: %s", e)

    threading.Thread(target=_job, daemon=True, name="riot-update-check").start()


def executer_mise_a_jour() -> Dict[str, Any]:
    """Met a jour RIOT de maniere sure selon le mode d'installation detecte."""
    mode = detecter_mode_installation()
    if mode == "git":
        try:
            st = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(_RACINE),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if st.returncode == 0 and st.stdout.strip():
                return {
                    "ok": False,
                    "mode": "git",
                    "message": (
                        "Modifications locales non commitees detectees dans le depot. "
                        "Fais d'abord un `git stash` ou `git commit` avant de lancer `git pull --ff-only`."
                    ),
                }
            pull = subprocess.run(
                ["git", "pull", "--ff-only", "origin", "master"],
                cwd=str(_RACINE),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pull.returncode == 0:
                etat = etat_mise_a_jour(forcer=True)
                return {
                    "ok": True,
                    "mode": "git",
                    "message": pull.stdout.strip() or "Depot mis a jour (fast-forward).",
                    "etat": etat,
                }
            return {
                "ok": False,
                "mode": "git",
                "message": (pull.stderr or pull.stdout or "Echec git pull").strip(),
            }
        except Exception as e:
            return {"ok": False, "mode": "git", "message": f"Erreur git pull : {e}"}

    if mode == "uv":
        return {
            "ok": True,
            "mode": "uv",
            "redemarrage_requis": True,
            "commande": "riot --update-cli",
            "message": "Pour recharger la derniere version distante sans conflit sur Windows, relance : riot --update-cli",
        }

    return {
        "ok": True,
        "mode": mode,
        "redemarrage_requis": True,
        "commande": "npm install -g @riotlagrinta/riot@latest",
        "message": "Relance dans ton terminal : npm install -g @riotlagrinta/riot@latest",
    }

