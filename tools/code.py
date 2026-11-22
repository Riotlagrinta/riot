"""Outils spécialisés pour le Sous-Agent Coder de RIOT.

Permet d'explorer, lire, écrire, patcher, chercher et tester du code sur n'importe
quel projet ou disque de la machine avec robustesse et zéro erreur d'encodage.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List

from core.registre import outil

# Dossiers et fichiers bruités à ignorer systématiquement lors de l'exploration et de la recherche
DOSSIERS_IGNORE = {
    ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".next", ".nuxt", "dist", "build", "coverage", ".turbo",
    ".idea", ".vscode", "target", "bin", "obj"
}

EXTENSIONS_CODE = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".md", ".env.example",
    ".sh", ".bat", ".ps1", ".rs", ".go", ".c", ".cpp", ".h"
}

from core.config import dossier_projets

DOSSIER_PROJETS_DEFAUT = dossier_projets()


_RACINE_RIOT = Path(__file__).resolve().parent.parent


def _projet_actif_courant() -> Optional[Path]:
    """Retourne le projet actif selectionne dans le CLI ou RIOT IDE."""
    try:
        from core.cli import _SESSION_CTX
        p = _SESSION_CTX.get("projet_actif")
        if isinstance(p, Path) and p.exists() and p.is_dir():
            return p.resolve()
    except Exception:
        pass
    return None


def definir_projet_actif(chemin_dossier: Path) -> Optional[Path]:
    """Ancre le dossier de travail courant dans _SESSION_CTX (sans pointer sur RIOT interne)."""
    try:
        res = Path(chemin_dossier).resolve()
        if not res.exists() or not res.is_dir():
            return None
        try:
            res.relative_to(_RACINE_RIOT.resolve())
            from core.llm import est_createur
            if not est_createur():
                return None
        except ValueError:
            pass
        from core.cli import _SESSION_CTX
        _SESSION_CTX["projet_actif"] = res
        return res
    except Exception:
        return None


def extraire_et_ancrer_dossier_texte(texte: str) -> Optional[Path]:
    """Detecte un chemin de dossier existant mentionne par l'utilisateur et l'ancre."""
    if not texte:
        return None
    motifs = [
        r"""["']([A-Za-z]:\\[^"'\r\n]+|/(?:home|Users|var|opt|srv|mnt|projects)[^"'\r\n]+)["']""",
        r"""\b([A-Za-z]:\\[^\s,;'"`<>|*?]+(?:[\\/][^\s,;'"`<>|*?]+)*)""",
    ]
    for pat in motifs:
        for m in re.finditer(pat, texte):
            brut = m.group(1).strip().rstrip(".,;:!?")
            try:
                cand = Path(brut)
                if cand.exists() and cand.is_dir():
                    return definir_projet_actif(cand)
                if cand.exists() and cand.is_file():
                    return definir_projet_actif(cand.parent)
            except Exception:
                continue
    return None


def _verifier_acces_source_interne(cible: Path) -> None:
    """Empeche la lecture ou modification du code source de RIOT sans autorisation createur."""
    try:
        from core.llm import est_createur
        if est_createur():
            return
    except Exception:
        pass
    try:
        cible.resolve().relative_to(_RACINE_RIOT.resolve())
        raise PermissionError("Acces refuse : le code source interne de RIOT est protege (mode createur requis).")
    except ValueError:
        return


def _resoudre_chemin(chemin: str, dossier_base: Optional[str] = None) -> Path:
    """Resout un chemin absolu ou relatif en priorisant le projet actif courant."""
    p_str = chemin.strip().strip('"').strip("'")
    p = Path(p_str)
    if not p.is_absolute():
        actif = _projet_actif_courant()
        if dossier_base and os.path.isdir(dossier_base):
            p = Path(dossier_base) / p
        elif actif is not None:
            p = actif / p
        elif (DOSSIER_PROJETS_DEFAUT / p).exists():
            p = DOSSIER_PROJETS_DEFAUT / p
        else:
            p = Path.cwd() / p
    res = p.resolve()
    _verifier_acces_source_interne(res)
    return res


@outil(
    nom="explorer_projet",
    description="Explore et affiche l'arborescence propre d'un projet ou dossier de code. "
                "Filtre automatiquement le bruit (node_modules, .venv, .git, __pycache__). "
                "Ex: explorer_projet('E:\\PROJETS\\Trade App', profondeur=2)",
    parametres={
        "type": "object",
        "properties": {
            "dossier": {
                "type": "string",
                "description": "Chemin du projet ou nom du sous-dossier (ex: 'Trade App', 'E:\\PROJETS\\Trade App')",
            },
            "profondeur": {
                "type": "integer",
                "default": 2,
                "description": "Profondeur d'exploration (1 à 4, défaut 2)",
            },
        },
        "required": ["dossier"],
    },
)
def explorer_projet(dossier: str, profondeur: int = 2) -> str:
    """Génère une arborescence lisible avec distinction dossiers/fichiers et tailles."""
    racine = _resoudre_chemin(dossier)
    if not racine.exists() or not racine.is_dir():
        # Essai de recherche souple dans E:\PROJETS
        if DOSSIER_PROJETS_DEFAUT.exists():
            candidats = [d for d in DOSSIER_PROJETS_DEFAUT.iterdir() if d.is_dir() and dossier.lower() in d.name.lower()]
            if candidats:
                racine = candidats[0]
            else:
                return f"[ERREUR] Le dossier '{dossier}' n'existe pas dans {DOSSIER_PROJETS_DEFAUT} ni en chemin absolu."
        else:
            return f"[ERREUR] Le dossier '{dossier}' est introuvable."

    definir_projet_actif(racine)
    max_prof = min(max(1, profondeur), 4)
    lignes = [f"📁 [PROJET] {racine.name} ({racine})"]
    nb_fichiers = 0
    nb_dossiers = 0

    def scanner(rep: Path, niveau: int, prefixe: str = ""):
        nonlocal nb_fichiers, nb_dossiers
        if niveau > max_prof:
            return

        try:
            entrees = sorted(list(rep.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            lignes.append(f"{prefixe}└── [Accès refusé]")
            return

        # Filtrage du bruit
        visibles = [e for e in entrees if e.name not in DOSSIERS_IGNORE and not e.name.startswith(".git")]
        total = len(visibles)

        for i, entree in enumerate(visibles):
            est_dernier = (i == total - 1)
            symbole = "└── " if est_dernier else "├── "
            nouveau_prefixe = prefixe + ("    " if est_dernier else "│   ")

            if entree.is_dir():
                nb_dossiers += 1
                lignes.append(f"{prefixe}{symbole}📁 {entree.name}/")
                scanner(entree, niveau + 1, nouveau_prefixe)
            else:
                nb_fichiers += 1
                taille_ko = round(entree.stat().st_size / 1024, 1)
                taille_str = f"{taille_ko} Ko" if taille_ko > 0 else f"{entree.stat().st_size} octets"
                lignes.append(f"{prefixe}{symbole}📄 {entree.name} ({taille_str})")

    scanner(racine, 1)
    lignes.append(f"\nTotal : {nb_dossiers} dossiers, {nb_fichiers} fichiers visibles.")

    # Detection rapide de stack pour accelerer l'analyse de l'agent
    stack_infos = []
    pkg_json = racine / "package.json"
    if pkg_json.is_file():
        try:
            import json as _json
            pdata = _json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            scripts = list((pdata.get("scripts") or {}).keys())[:6]
            deps = list({**(pdata.get("dependencies") or {}), **(pdata.get("devDependencies") or {})}.keys())
            majeurs = [d for d in deps if d in ("next", "react", "remotion", "@remotion/cli", "vite", "express", "tailwindcss", "typescript", "jest", "vitest", "prisma")]
            stack_infos.append(f"Node/JS ({', '.join(majeurs) or 'package.json'}) | scripts: {', '.join(scripts) or '-'}")
        except Exception:
            stack_infos.append("Node/JS (package.json)")
    if (racine / "pyproject.toml").is_file() or (racine / "requirements.txt").is_file():
        stack_infos.append("Python (" + ("pyproject.toml" if (racine / "pyproject.toml").is_file() else "requirements.txt") + ")")
    if (racine / ".git").exists():
        stack_infos.append("Dépôt Git actif")
    if stack_infos:
        lignes.append("[STACK DÉTECTÉE] " + " · ".join(stack_infos))

    return "\n".join(lignes)


@outil(
    nom="lire_code",
    description="Lit le contenu d'un fichier source avec numéros de lignes précis. "
                "Supporte les plages de lignes pour inspecter des gros modules sans saturer le contexte. "
                "Ex: lire_code('backend/app/main.py', debut=1, fin=100)",
    parametres={
        "type": "object",
        "properties": {
            "fichier": {
                "type": "string",
                "description": "Chemin absolu ou relatif vers le fichier de code",
            },
            "debut": {
                "type": "integer",
                "default": 1,
                "description": "Numéro de ligne de début (1-indexé, défaut 1)",
            },
            "fin": {
                "type": "integer",
                "default": 150,
                "description": "Numéro de ligne de fin (défaut 150, max 300 lignes par appel)",
            },
        },
        "required": ["fichier"],
    },
)
def lire_code(fichier: str, debut: int = 1, fin: int = 150) -> str:
    """Lit un fichier avec affichage clair façon IDE."""
    chemin = _resoudre_chemin(fichier)
    if not chemin.exists():
        return f"[ERREUR] Le fichier '{chemin}' n'existe pas."
    if not chemin.is_file():
        return f"[ERREUR] '{chemin}' est un dossier, pas un fichier."

    contenu = ""
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(chemin, "r", encoding=enc) as f:
                contenu = f.read()
            break
        except (UnicodeDecodeError, Exception):
            continue

    if not contenu and chemin.stat().st_size > 0:
        return f"[ERREUR] Impossible de décoder le fichier '{chemin}' en texte UTF-8/ANSI."

    lignes = contenu.splitlines()
    total_lignes = len(lignes)

    deb = max(1, debut)
    arr = min(max(deb, fin), total_lignes, deb + 300)

    lignes_extrait = []
    lignes_extrait.append(f"┌─ 📄 {chemin.name} ({chemin}) [Lignes {deb}-{arr}/{total_lignes}] ─┐")
    for i in range(deb, arr + 1):
        num = str(i).rjust(4)
        ligne_texte = lignes[i - 1]
        lignes_extrait.append(f"│ {num} │ {ligne_texte}")
    lignes_extrait.append(f"└{'─' * (len(lignes_extrait[0]) - 2)}┘")

    return "\n".join(lignes_extrait)


def _verifier_syntaxe_et_qualite(chemin: Path) -> str:
    """Vérifie automatiquement la syntaxe et la validité du fichier modifié (Pilier 4)."""
    suf = chemin.suffix.lower()
    if suf == ".py":
        import py_compile
        try:
            py_compile.compile(str(chemin), doraise=True)
            return " [Syntaxe Python: Valide ✓]"
        except py_compile.PyCompileError as e:
            return f"\n⚠️ [ALERTE SYNTAXE PYTHON DÉTECTÉE]\n{e.msg} (Ligne {e.lineno}). Veuillez corriger immédiatement."
    elif suf in (".json",):
        import json
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                json.load(f)
            return " [Syntaxe JSON: Valide ✓]"
        except Exception as e:
            return f"\n⚠️ [ALERTE SYNTAXE JSON DÉTECTÉE]\n{e}. Veuillez corriger le JSON."
    return ""


@outil(
    nom="ecrire_code",
    description="Écrit ou remplace intégralement le contenu d'un fichier source. "
                "Crée les dossiers parents automatiquement si nécessaire. Encodage UTF-8 garanti. "
                "Ex: ecrire_code('backend/app/services/trading.py', contenu='...')",
    parametres={
        "type": "object",
        "properties": {
            "fichier": {
                "type": "string",
                "description": "Chemin du fichier à créer ou modifier",
            },
            "contenu": {
                "type": "string",
                "description": "Le code source complet à écrire dans le fichier",
            },
        },
        "required": ["fichier", "contenu"],
    },
)
def ecrire_code(fichier: str, contenu: str) -> str:
    """Écrit le fichier sur le disque avec sauvegarde automatique en cas d'écrasement."""
    chemin = _resoudre_chemin(fichier)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    action = "modifié" if chemin.exists() else "créé"
    ancien_nb_lignes = 0
    if chemin.exists():
        try:
            with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                ancien_nb_lignes = len(f.readlines())
        except Exception:
            pass

    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)

    nouv_lignes = len(contenu.splitlines())
    taille_ko = round(chemin.stat().st_size / 1024, 2)
    verif = _verifier_syntaxe_et_qualite(chemin)
    return f"✓ Fichier {action} avec succès : {chemin} ({nouv_lignes} lignes, {taille_ko} Ko, avant: {ancien_nb_lignes} lignes).{verif}"


@outil(
    nom="patcher_code",
    description="Remplace chirurgicalement un bloc de code précis par un nouveau dans un fichier existant. "
                "Très recommandé pour modifier une fonction ou corriger un bug sans réécrire tout le fichier. "
                "Ex: patcher_code('frontend/src/App.tsx', ancien_bloc='const x = 1;', nouveau_bloc='const x = 2;')",
    parametres={
        "type": "object",
        "properties": {
            "fichier": {
                "type": "string",
                "description": "Chemin du fichier à modifier",
            },
            "ancien_bloc": {
                "type": "string",
                "description": "Le bloc exact de code existant à remplacer (doit être unique dans le fichier)",
            },
            "nouveau_bloc": {
                "type": "string",
                "description": "Le nouveau bloc de code qui vient remplacer l'ancien",
            },
        },
        "required": ["fichier", "ancien_bloc", "nouveau_bloc"],
    },
)
def patcher_code(fichier: str, ancien_bloc: str, nouveau_bloc: str) -> str:
    """Applique un patch chirurgical sur un fichier texte avec vérification automatique."""
    chemin = _resoudre_chemin(fichier)
    if not chemin.exists():
        return f"[ERREUR] Le fichier '{chemin}' n'existe pas."

    contenu = ""
    enc_choisi = "utf-8"
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(chemin, "r", encoding=enc) as f:
                contenu = f.read()
            enc_choisi = enc
            break
        except Exception:
            continue

    # Normalisation des retours à la ligne pour comparaison fiable
    ancien_norm = ancien_bloc.replace("\r\n", "\n")
    contenu_norm = contenu.replace("\r\n", "\n")
    nouveau_norm = nouveau_bloc.replace("\r\n", "\n")

    nb_occurrences = contenu_norm.count(ancien_norm)
    if nb_occurrences == 0:
        # Fallback tolerant : correspondance ligne par ligne en ignorant les espaces de fin de ligne
        lignes_fic = contenu_norm.splitlines()
        lignes_cible = ancien_norm.splitlines()
        if lignes_cible:
            cible_rstrip = [l.rstrip() for l in lignes_cible]
            n_c = len(cible_rstrip)
            hits = [
                idx for idx in range(len(lignes_fic) - n_c + 1)
                if [l.rstrip() for l in lignes_fic[idx:idx + n_c]] == cible_rstrip
            ]
            if len(hits) == 1:
                idx = hits[0]
                nouvelles_lignes = lignes_fic[:idx] + nouveau_norm.splitlines() + lignes_fic[idx + n_c:]
                contenu_modifie = "\n".join(nouvelles_lignes) + ("\n" if contenu_norm.endswith("\n") else "")
                with open(chemin, "w", encoding=enc_choisi, newline="\n") as f:
                    f.write(contenu_modifie)
                diff_lignes = len(nouveau_norm.splitlines()) - n_c
                signe = f"+{diff_lignes}" if diff_lignes >= 0 else str(diff_lignes)
                verif = _verifier_syntaxe_et_qualite(chemin)
                return f"✓ Patch appliqué avec succès sur {chemin.name} ({signe} lignes, correspondance souple ligne {idx + 1}).{verif}"
            if len(hits) > 1:
                return (
                    f"[ERREUR] Le bloc cible apparaît {len(hits)} fois dans '{chemin.name}'. "
                    "Ajoutez 2-3 lignes de contexte autour pour le rendre unique."
                )

        # Indice utile avec la premiere ligne non vide trouvee dans le fichier
        indice = ""
        prem = next((l.strip() for l in ancien_norm.splitlines() if l.strip()), "")
        if prem:
            proches = [f"L{i + 1}: {l.strip()[:70]}" for i, l in enumerate(lignes_fic) if prem[:20] in l][:3]
            if proches:
                indice = " Lignes proches : " + " | ".join(proches)
        return (
            f"[ERREUR] Le bloc cible est introuvable dans '{chemin.name}'. "
            f"Vérifiez avec 'lire_code' avant de réessayer.{indice}"
        )
    if nb_occurrences > 1:
        return (
            f"[ERREUR] Le bloc cible apparaît {nb_occurrences} fois dans '{chemin.name}'. "
            "Fournissez un bloc plus large avec quelques lignes de contexte pour garantir l'unicité du remplacement."
        )

    contenu_modifie = contenu_norm.replace(ancien_norm, nouveau_norm, 1)

    with open(chemin, "w", encoding=enc_choisi, newline="\n") as f:
        f.write(contenu_modifie)

    diff_lignes = len(nouveau_norm.splitlines()) - len(ancien_norm.splitlines())
    signe = f"+{diff_lignes}" if diff_lignes >= 0 else str(diff_lignes)
    verif = _verifier_syntaxe_et_qualite(chemin)
    return f"✓ Patch appliqué avec succès sur {chemin.name} ({signe} lignes, remplacement unique effectué).{verif}"


@outil(
    nom="chercher_dans_code",
    description="Effectue une recherche textuelle ou regex ultra-rapide (façon ripgrep/grep) "
                "dans les fichiers de code d'un projet. Renvoie les fichiers et les numéros de ligne correspondants.",
    parametres={
        "type": "object",
        "properties": {
            "terme": {
                "type": "string",
                "description": "Le texte ou regex à rechercher (ex: 'create_order', 'TRADE_APP_DATABASE_URL')",
            },
            "dossier": {
                "type": "string",
                "default": "",
                "description": "Dossier où effectuer la recherche (défaut: dossier des projets ou courant)",
            },
            "extensions": {
                "type": "string",
                "default": ".py,.ts,.tsx,.js,.json,.sql",
                "description": "Extensions de fichiers ciblées séparées par virgule",
            },
            "max_resultats": {
                "type": "integer",
                "default": 25,
                "description": "Nombre maximal d'occurrences à retourner (défaut 25)",
            },
        },
        "required": ["terme"],
    },
)
def chercher_dans_code(terme: str, dossier: str = "", extensions: str = ".py,.ts,.tsx,.js,.json,.sql", max_resultats: int = 25) -> str:
    """Recherche rapide et ciblée dans le code source."""
    racine = _resoudre_chemin(dossier or str(DOSSIER_PROJETS_DEFAUT))
    if not racine.exists():
        return f"[ERREUR] Le dossier '{racine}' n'existe pas."

    exts_valides = {e.strip().lower() for e in extensions.split(",") if e.strip()}
    resultats = []
    regex = re.compile(terme, re.IGNORECASE)

    for courant, sous_dossiers, fichiers in os.walk(racine):
        # Filtrage en place des dossiers ignorés pour éviter de descendre dans node_modules/.venv
        sous_dossiers[:] = [d for d in sous_dossiers if d not in DOSSIERS_IGNORE and not d.startswith(".git")]

        for nom in fichiers:
            chemin_f = Path(courant) / nom
            if chemin_f.suffix.lower() not in exts_valides:
                continue

            try:
                with open(chemin_f, "r", encoding="utf-8", errors="replace") as f:
                    for num_l, ligne in enumerate(f, start=1):
                        if regex.search(ligne):
                            rel_p = os.path.relpath(chemin_f, racine)
                            resultats.append(f"{rel_p}:{num_l}: {ligne.strip()[:120]}")
                            if len(resultats) >= max_resultats:
                                break
            except Exception:
                continue
            if len(resultats) >= max_resultats:
                break
        if len(resultats) >= max_resultats:
            break

    if not resultats:
        return f"Aucune occurrence de '{terme}' trouvée dans {racine.name} (extensions: {extensions})."

    lignes_res = [f"🔍 Résultats pour '{terme}' dans {racine.name} ({len(resultats)} occurrences) :"]
    lignes_res.extend(resultats)
    if len(resultats) >= max_resultats:
        lignes_res.append(f"... (limite de {max_resultats} résultats atteinte)")
    return "\n".join(lignes_res)


@outil(
    nom="executer_test_ou_commande",
    description="Exécute une commande de test, de lint ou de build (pytest, npm test, git diff, ruff, alembic) "
                "dans le répertoire d'un projet et retourne la sortie avec le code d'erreur.",
    parametres={
        "type": "object",
        "properties": {
            "commande": {
                "type": "string",
                "description": "La commande à exécuter (ex: 'pytest backend/tests', 'git status', 'npm run lint')",
            },
            "dossier": {
                "type": "string",
                "default": "",
                "description": "Le dossier de travail où exécuter la commande (défaut: dossier projets ou courant)",
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "description": "Délai maximal en secondes (défaut 60s, max 180s)",
            },
        },
        "required": ["commande"],
    },
)
def executer_test_ou_commande(commande: str, dossier: str = "", timeout: int = 60) -> str:
    """Exécute une commande système avec capture exacte des codes de retour (multiplateforme)."""
    base = dossier or str(_projet_actif_courant() or DOSSIER_PROJETS_DEFAUT)
    racine = _resoudre_chemin(base)
    if not racine.exists():
        return f"[ERREUR] Le dossier de travail '{racine}' est introuvable."

    limite = min(max(5, timeout), 180)
    if sys.platform == "win32":
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", commande]
    else:
        args = ["/bin/sh", "-c", commande]

    try:
        proc = subprocess.run(
            args,
            cwd=str(racine),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=limite,
        )
        sortie = (proc.stdout or "").strip()
        erreurs = (proc.stderr or "").strip()
        code = proc.returncode

        parties = [f"[Dossier: {racine.name}] [Code retour: {code}]"]
        if sortie:
            parties.append(f"[STDOUT]\n{sortie}")
        if erreurs:
            parties.append(f"[STDERR]\n{erreurs}")
        if not sortie and not erreurs:
            parties.append("(Exécution terminée sans affichage texte)")

        res = "\n".join(parties)
        if len(res) > 3500:
            res = res[:3300] + f"\n... [tronqué, total {len(res)} caractères]"
        return res

    except subprocess.TimeoutExpired:
        return f"[ERREUR] La commande a dépassé le délai de {limite} secondes."
    except Exception as e:
        return f"[ERREUR] Échec de l'exécution : {e}"
