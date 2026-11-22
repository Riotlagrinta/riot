"""Outils fichiers medias : chercher, lister et ouvrir tes photos/videos/musiques/
documents en local (N1, lecture + ouverture via l'appli par defaut, aucun acces internet)."""
import os
from pathlib import Path

from core.config import reglage
from core.config import dossier_projets
from core.registre import outil

EXTENSIONS = {
    "musique": {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
    "photo": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"},
    "document": {".pdf", ".docx", ".doc", ".txt", ".pptx", ".xlsx"},
}

ALIAS_DOSSIERS = {
    "photos": "Pictures", "images": "Pictures", "photo": "Pictures",
    "videos": "Videos", "video": "Videos",
    "musique": "Music", "musiques": "Music", "audio": "Music",
    "documents": "Documents", "document": "Documents",
    "telechargements": "Downloads", "téléchargements": "Downloads",
}

PROFONDEUR_MAX = int(reglage("fichiers.profondeur_max", 4))


def _dossiers_racine():
    """Dossiers medias par defaut (Images/Videos/Musique/Documents/Telechargements),
    plus d'eventuels dossiers additionnels definis dans config.yaml (fichiers.dossiers)."""
    accueil = Path.home()
    racines = [
        accueil / "Pictures",
        accueil / "Videos",
        accueil / "Music",
        accueil / "Documents",
        accueil / "Downloads",
    ]
    extra = reglage("fichiers.dossiers", []) or []
    racines += [Path(d) for d in extra]
    return [r for r in racines if r.exists()]


def _toutes_extensions(type_media=None):
    if not type_media:
        s = set()
        for e in EXTENSIONS.values():
            s |= e
        return s
    return EXTENSIONS.get(type_media.lower().strip(), set())


def _marcher(racine, profondeur_max):
    """Parcourt un dossier avec une profondeur limitee (evite de scanner des
    arborescences enormes sur une machine peu puissante)."""
    racine_profondeur = str(racine).count(os.sep)
    for courant, sous_dossiers, fichiers in os.walk(racine):
        profondeur = str(courant).count(os.sep) - racine_profondeur
        if profondeur >= profondeur_max:
            sous_dossiers[:] = []
        for nom in fichiers:
            yield Path(courant) / nom


def _recherche(mot_cle, type_media=None, limite=10):
    mot_cle = (mot_cle or "").lower().strip()
    exts = _toutes_extensions(type_media)
    resultats = []
    for racine in _dossiers_racine():
        try:
            for chemin in _marcher(racine, PROFONDEUR_MAX):
                if exts and chemin.suffix.lower() not in exts:
                    continue
                if mot_cle and mot_cle not in chemin.stem.lower():
                    continue
                resultats.append(chemin)
                if len(resultats) >= limite:
                    return resultats
        except Exception:
            continue
    return resultats


@outil(
    nom="chercher_fichiers",
    mcp_expose=True,
    description="Cherche des fichiers medias (photos, videos, musique, documents) sur "
                "l'ordinateur par mot-cle, dans les dossiers personnels (Images, Videos, "
                "Musique, Documents, Telechargements). Utilise pour 'trouve mes photos de...', "
                "'cherche la video...', 'ai-je un fichier...'.",
    parametres={
        "type": "object",
        "properties": {
            "mot_cle": {
                "type": "string",
                "description": "Mot ou partie du nom de fichier a chercher",
            },
            "type_media": {
                "type": "string",
                "enum": ["musique", "video", "photo", "document"],
                "description": "Filtrer par type de fichier (optionnel, tous types si omis)",
            },
        },
        "required": ["mot_cle"],
    },
)
def chercher_fichiers(mot_cle: str, type_media: str = "") -> str:
    """Cherche des fichiers par mot-cle, optionnellement filtres par type."""
    resultats = _recherche(mot_cle, type_media or None, limite=8)
    if not resultats:
        return f"Je n'ai trouve aucun fichier correspondant a {mot_cle}."
    noms = [c.name for c in resultats]
    if len(noms) == 1:
        return f"J'ai trouve un fichier : {noms[0]}."
    return f"J'ai trouve {len(noms)} fichiers : " + ", ".join(noms) + "."


@outil(
    nom="lister_dossier",
    mcp_expose=True,
    description="Liste le contenu d'un dossier quelconque sur le PC (disques C:, E:, dossiers personnels ou projets). "
                "Affiche les dossiers et les fichiers avec leur taille réelle.",
    parametres={
        "type": "object",
        "properties": {
            "dossier": {
                "type": "string",
                "description": "Chemin du dossier (ex: 'E:\\', 'E:\\PROJETS', 'telechargements', 'documents')",
            },
        },
        "required": ["dossier"],
    },
)
def lister_dossier(dossier: str) -> str:
    """Liste les dossiers et fichiers présents dans n'importe quel répertoire."""
    d_clean = dossier.strip().strip('"').strip("'")
    cle = d_clean.lower()
    
    # 1. Vérifier si c'est un alias personnel
    if cle in ALIAS_DOSSIERS:
        chemin = Path.home() / ALIAS_DOSSIERS[cle]
    else:
        chemin = Path(d_clean)
        if not chemin.is_absolute():
            # Si relatif, tester dans home puis dans E:\PROJETS
            if (Path.home() / d_clean).exists():
                chemin = Path.home() / d_clean
            elif (dossier_projets() / d_clean).exists():
                chemin = dossier_projets() / d_clean
            else:
                chemin = Path.cwd() / d_clean

    if not chemin.exists():
        return f"[ERREUR] Le dossier '{chemin}' n'existe pas."
    if not chemin.is_dir():
        return f"[ERREUR] '{chemin}' est un fichier, pas un dossier."

    # Ancre automatiquement le dossier s'il s'agit d'un vrai repertoire projet (hors racine utilisateur)
    try:
        if chemin.resolve() != Path.home().resolve() and len(chemin.resolve().parts) > 2:
            from tools.code import definir_projet_actif
            definir_projet_actif(chemin)
    except Exception:
        pass

    try:
        entrees = sorted(list(chemin.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return f"[ERREUR] Accès refusé à '{chemin}'."

    dossiers = []
    fichiers = []
    for e in entrees:
        if e.is_dir():
            dossiers.append(f"📁 {e.name}/")
        else:
            taille_mo = round(e.stat().st_size / (1024 * 1024), 2)
            if taille_mo >= 1.0:
                fichiers.append(f"📄 {e.name} ({taille_mo} Mo)")
            else:
                taille_ko = round(e.stat().st_size / 1024, 1)
                fichiers.append(f"📄 {e.name} ({taille_ko} Ko)")

    res = [f"Contenu de '{chemin}' :"]
    if dossiers:
        res.append(f"• Dossiers ({len(dossiers)}) : " + ", ".join(dossiers[:25]) + ("..." if len(dossiers) > 25 else ""))
    if fichiers:
        res.append(f"• Fichiers ({len(fichiers)}) : " + ", ".join(fichiers[:30]) + ("..." if len(fichiers) > 30 else ""))
    if not dossiers and not fichiers:
        res.append("(Dossier vide)")

    return "\n".join(res)


@outil(
    nom="supprimer_fichier",
    description="Supprime un fichier spécifique sur le disque avec confirmation de sécurité. "
                "Gère parfaitement les chemins contenant des crochets [ ], espaces et caractères spéciaux.",
    parametres={
        "type": "object",
        "properties": {
            "fichier": {
                "type": "string",
                "description": "Chemin absolu ou nom exact du fichier à supprimer",
            },
        },
        "required": ["fichier"],
    },
)
def supprimer_fichier(fichier: str) -> str:
    """Supprime un fichier en toute sécurité."""
    f_clean = fichier.strip().strip('"').strip("'")
    chemin = Path(f_clean)
    if not chemin.is_absolute():
        if (Path.home() / f_clean).exists():
            chemin = Path.home() / f_clean
        elif (dossier_projets() / f_clean).exists():
            chemin = dossier_projets() / f_clean
        elif Path("E:\\").exists() and (Path("E:\\") / f_clean).exists():
            chemin = Path("E:\\") / f_clean
        else:
            chemin = Path.cwd() / f_clean

    if not chemin.exists():
        return f"[ERREUR] Le fichier '{chemin}' est introuvable."
    if chemin.is_dir():
        return f"[ERREUR] '{chemin}' est un dossier. Pour supprimer un dossier, utilisez rmdir dans le terminal."

    try:
        taille_mo = round(chemin.stat().st_size / (1024 * 1024), 2)
        nom = chemin.name
        chemin.unlink()
        return f"✓ Fichier '{nom}' supprimé avec succès ({taille_mo} Mo libérés sur le disque)."
    except Exception as e:
        return f"[ERREUR] Impossible de supprimer '{chemin}' : {e}"


@outil(
    nom="ouvrir_fichier",
    description="Cherche un fichier media (photo, video, musique, document) par son nom "
                "ou une partie du nom, et l'ouvre avec l'application par defaut de "
                "Windows. Utilise pour 'ouvre le fichier...', 'lance la video...', "
                "'joue la musique...'.",
    parametres={
        "type": "object",
        "properties": {
            "nom": {
                "type": "string",
                "description": "Nom ou partie du nom du fichier a ouvrir",
            },
        },
        "required": ["nom"],
    },
)
def ouvrir_fichier(nom: str) -> str:
    """Cherche un fichier par nom (partiel) et l'ouvre avec l'application par defaut."""
    resultats = _recherche(nom, None, limite=1)
    if not resultats:
        return f"Je n'ai trouve aucun fichier correspondant a {nom}."
    chemin = resultats[0]
    try:
        os.startfile(str(chemin))   # gere .exe, fichiers, et protocoles (steam://, spotify:)
        return f"J'ouvre {chemin.name}."
    except Exception as e:
        return f"Je n'ai pas pu ouvrir {chemin.name} ({e})."
