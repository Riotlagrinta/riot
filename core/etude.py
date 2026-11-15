"""Module d'ingestion et de tutorat académique & multimédia RIOT (Dossier etude/).

Permet à l'utilisateur de déposer des cours, manuels, documentations techniques
(PDF, Markdown, TXT, code) ainsi que des formations vidéo longues (jusqu'à 15h : MP4, MKV, MOV, WEBM).
Le moteur fonctionne selon une architecture « Zéro Gaspillage de Quotas » :
- Découpage local en segments digestes (30-45 minutes) via FFmpeg autonome.
- Extraction de Keyframes haute définition (slides, schémas d'architecture, code source à l'écran).
- Extraction et transcription audio locale via Faster-Whisper (optionnelle, sans frais d'API).
- Distillation automatique et instantanée dans :
  * `etude_documents` & `etude_fts` (RAG plein texte avec horodatages et captures associées).
  * `recettes_code` & `recettes_fts` (détection et ajout automatique de fiches de résolution de bugs).
  * `memoire_entites` (`regles_dev` pour les bonnes pratiques et règles strictes énoncées).
"""
import hashlib
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import memoire

LOG = logging.getLogger("riot.etude")
RACINE = Path(__file__).resolve().parent.parent
DOSSIER_ETUDE = RACINE / "etude"
DOSSIER_KEYFRAMES = DOSSIER_ETUDE / "keyframes"
DOSSIER_AUDIO_TEMP = DOSSIER_ETUDE / ".audio_temp"

EXTENSIONS_DOCUMENTS = {".pdf", ".md", ".txt", ".markdown", ".py", ".ts", ".js", ".json", ".sql", ".html", ".css"}
EXTENSIONS_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v"}
EXTENSIONS_SUPPORTEES = EXTENSIONS_DOCUMENTS | EXTENSIONS_VIDEO

# Singleton pour chargement paresseux de Faster-Whisper si demandé
_WHISPER_SINGLETON = None


def get_ffmpeg_exe() -> str:
    """Retourne le chemin vers le binaire FFmpeg local (imageio-ffmpeg ou PATH)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        raise RuntimeError("FFmpeg introuvable. Installe l'extra media : pip install 'riot[media]'")


def initialiser_dossier_etude():
    """Crée l'arborescence etude/ et y dépose le guide complet d'apprentissage."""
    DOSSIER_ETUDE.mkdir(parents=True, exist_ok=True)
    DOSSIER_KEYFRAMES.mkdir(parents=True, exist_ok=True)
    DOSSIER_AUDIO_TEMP.mkdir(parents=True, exist_ok=True)

    fichier_guide = DOSSIER_ETUDE / "LISEZ-MOI.md"
    if not fichier_guide.exists():
        fichier_guide.write_text(
            "# 📚 Centre d'Apprentissage & Tutorat Multimédia RIOT\n\n"
            "Déposez ici vos ressources d'apprentissage, formations et cours :\n"
            "- **Documents & Code** : `.pdf`, `.md`, `.txt`, `.py`, `.sql`, `.json`, etc.\n"
            "- **Formations Vidéo Longues (jusqu'à 15h)** : `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`.\n\n"
            "### Fonctionnalités Automatisées de RIOT :\n"
            "1. **Découpage en segments (30-45 min)** pour un traitement fluide sans saturer la mémoire.\n"
            "2. **Extraction de Keyframes HD** : RIOT capture automatiquement les diapositives, schémas d'architecture et fenêtres de code montrées par le formateur dans `etude/keyframes/`.\n"
            "3. **Distillation dans le Livre de Recettes** : Les solutions de bugs et patterns expliqués dans le cours sont automatiquement indexés dans `recettes_code`.\n"
            "4. **Règles d'Ingénierie Dev** : Les bonnes pratiques fortes sont mémorisées dans les règles dev de RIOT.\n"
            "5. **Recherche RAG SQLite FTS5** : Posez n'importe quelle question technique à RIOT depuis le terminal ou à la voix.\n",
            encoding="utf-8"
        )


def obtenir_duree_video(video_path: Path | str) -> float:
    """Détermine la durée totale d'un fichier vidéo en secondes via FFmpeg."""
    ffmpeg_bin = get_ffmpeg_exe()
    cmd = [ffmpeg_bin, "-i", str(video_path)]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="replace")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def formater_secondes(secondes: float) -> str:
    """Convertit un nombre de secondes en format HH:MM:SS."""
    sec = int(secondes)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def extraire_keyframes(
    video_path: Path | str,
    output_prefix: str,
    start_seconds: float = 0.0,
    duration_seconds: Optional[float] = None,
    interval_seconds: int = 120,
) -> List[str]:
    """Extrait les captures d'écran représentatives (code, schémas, slides) pour un segment vidéo.

    Par défaut extrait 1 image toutes les 2 minutes (120s) pour capturer les graphiques
    sans saturer le disque.
    """
    initialiser_dossier_etude()
    ffmpeg_bin = get_ffmpeg_exe()
    output_pattern = str(DOSSIER_KEYFRAMES / f"{output_prefix}_frame_%03d.jpg")

    effective_interval = interval_seconds
    if duration_seconds is not None and duration_seconds > 0 and duration_seconds < interval_seconds:
        effective_interval = max(1, int(duration_seconds // 2) or 1)

    cmd = [ffmpeg_bin, "-y", "-ss", str(start_seconds)]
    if duration_seconds is not None:
        cmd.extend(["-t", str(duration_seconds)])
    cmd.extend([
        "-i", str(video_path),
        "-vf", f"fps=1/{effective_interval},scale=1280:-1",
        "-pix_fmt", "yuvj420p",
        "-q:v", "3",
        output_pattern,
    ])

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=180,
        )
    except Exception as e:
        LOG.warning("etude: extraction keyframes partielle pour %s : %s", output_prefix, e)

    # Récupérer les images générées
    frames = sorted([
        str(p.relative_to(RACINE)).replace("\\", "/")
        for p in DOSSIER_KEYFRAMES.glob(f"{output_prefix}_frame_*.jpg")
    ])

    # Si aucune frame n'a été produite (ex: segment court), forcer 1 capture nette
    if not frames:
        fallback_img = DOSSIER_KEYFRAMES / f"{output_prefix}_frame_001.jpg"
        cmd_fallback = [
            ffmpeg_bin, "-y",
            "-ss", str(start_seconds),
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "scale=1280:-1",
            "-pix_fmt", "yuvj420p",
            "-q:v", "3",
            str(fallback_img),
        ]
        try:
            subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30)
            if fallback_img.exists():
                frames.append(str(fallback_img.relative_to(RACINE)).replace("\\", "/"))
        except Exception:
            pass

    return frames


def extraire_audio_segment(
    video_path: Path | str,
    output_wav: Path | str,
    start_seconds: float = 0.0,
    duration_seconds: Optional[float] = None,
) -> bool:
    """Extrait la piste audio d'une tranche vidéo en format WAV mono 16 kHz optimisé pour Whisper."""
    ffmpeg_bin = get_ffmpeg_exe()
    cmd = [ffmpeg_bin, "-y", "-ss", str(start_seconds)]
    if duration_seconds is not None:
        cmd.extend(["-t", str(duration_seconds)])
    cmd.extend([
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav),
    ])

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
        return Path(output_wav).exists() and Path(output_wav).stat().st_size > 4096
    except Exception as e:
        LOG.warning("etude: échec extraction audio pour %s : %s", video_path, e)
        return False


def transcrire_audio_segment(audio_wav: Path | str) -> str:
    """Transcrit localement un extrait audio en français avec Faster-Whisper (zéro quota externe)."""
    global _WHISPER_SINGLETON
    wav_path = Path(audio_wav)
    if not wav_path.exists() or wav_path.stat().st_size < 4096:
        return ""

    try:
        if _WHISPER_SINGLETON is None:
            from faster_whisper import WhisperModel
            try:
                _WHISPER_SINGLETON = WhisperModel("base", device="cuda", compute_type="float16")
            except Exception:
                _WHISPER_SINGLETON = WhisperModel("base", device="cpu", compute_type="int8")

        segments, _ = _WHISPER_SINGLETON.transcribe(str(wav_path), language="fr", beam_size=3)
        lignes = [s.text.strip() for s in segments if s.text.strip()]
        return " ".join(lignes)
    except Exception as e:
        LOG.warning("etude: transcription Faster-Whisper non disponible ou erreur : %s", e)
        return ""


def extraire_texte(chemin: Path) -> str:
    """Extrait le texte brut d'un fichier selon son extension (PDF, texte, markdown, code)."""
    ext = chemin.suffix.lower()

    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(chemin))
            pages_texte = []
            for num, page in enumerate(reader.pages, start=1):
                t = page.extract_text() or ""
                if t.strip():
                    pages_texte.append(f"--- Page {num} ---\n{t.strip()}")
            return "\n\n".join(pages_texte)
        except Exception as e:
            LOG.exception("etude: erreur extraction PDF %s : %s", chemin.name, e)
            return ""

    # Fichiers texte brut (md, txt, py, etc.)
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return chemin.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            LOG.warning("etude: erreur lecture %s : %s", chemin.name, e)
            return ""

    return ""


def decouper_en_sections(texte: str, taille_chunk: int = 1000, chevauchement: int = 150) -> List[str]:
    """Découpe un texte long en blocs (chunks) cohérents avec chevauchement contextuel."""
    nettoye = re.sub(r"\r\n", "\n", texte).strip()
    if not nettoye:
        return []

    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", nettoye) if p.strip()]
    chunks = []
    chunk_actuel = []
    taille_actuelle = 0

    for para in paragraphes:
        p_len = len(para)
        if taille_actuelle + p_len > taille_chunk and chunk_actuel:
            texte_chunk = "\n\n".join(chunk_actuel)
            chunks.append(texte_chunk)
            if p_len < taille_chunk:
                chunk_actuel = [para]
                taille_actuelle = p_len
            else:
                chunk_actuel = []
                taille_actuelle = 0
                for i in range(0, p_len, taille_chunk - chevauchement):
                    chunks.append(para[i:i + taille_chunk])
        else:
            chunk_actuel.append(para)
            taille_actuelle += p_len

    if chunk_actuel:
        chunks.append("\n\n".join(chunk_actuel))

    return chunks


def distiller_connaissances_automatiques(texte: str, source_nom: str) -> Dict[str, int]:
    """Analyse le contenu ingéré pour alimenter automatiquement :
    1. Le livre de recettes de résolution de bugs (`recettes_code`)
    2. Les règles de dev et bonnes pratiques d'ingénierie (`regles_dev`)
    """
    if not texte or len(texte.strip()) < 30:
        return {"recettes": 0, "regles": 0}

    recettes_ajoutees = 0
    regles_ajoutees = 0

    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", texte) if len(p.strip()) > 30]

    # Mots-clés pour détection de résolution de bugs et de patterns
    mots_bug = ("erreur", "error", "exception", "bug", "problème", "résolution", "fix", "corriger", "cause", "solution")
    # Mots-clés pour bonnes pratiques et règles strictes
    mots_regle = ("toujours", "ne jamais", "règle", "recommandation", "bonne pratique", "impératif", "convention")

    for para in paragraphes:
        p_lower = para.lower()

        # 1. Détection de fiches recettes de dev
        if any(mb in p_lower for mb in mots_bug) and any(kw in p_lower for kw in ("solution", "fix", "corriger", "pour résoudre")):
            lignes = para.split("\n")
            titre = lignes[0][:75].strip()
            if not titre:
                titre = f"Solution issue de {source_nom}"

            # Détection heuristique du langage
            langage = "general"
            for lang in ("python", "typescript", "javascript", "react", "nextjs", "sql", "postgres", "fastapi", "docker", "node"):
                if lang in p_lower:
                    langage = lang
                    break

            try:
                memoire.ajouter_recette_code(
                    titre=titre,
                    probleme=para[:300],
                    solution=para,
                    cause=f"Extrait automatique du cours {source_nom}",
                    langage=langage,
                    tags=f"cours,auto,{langage}",
                )
                recettes_ajoutees += 1
            except Exception as e:
                LOG.debug("etude: insertion recette ignorée : %s", e)

        # 2. Détection de règles d'ingénierie fortes
        if any(mr in p_lower for mr in mots_regle) and len(para) < 250:
            cle_regle = re.sub(r"[^\w\-_]", "_", source_nom[:20].lower()) + f"_{int(time.time()) % 1000}"
            try:
                memoire.ajouter_regle_dev(cle_regle, para.strip())
                regles_ajoutees += 1
            except Exception as e:
                LOG.debug("etude: insertion règle dev ignorée : %s", e)

    return {"recettes": recettes_ajoutees, "regles": regles_ajoutees}


def ingerer_fichier_video(
    video_path: Path | str,
    titre_cours: str = "",
    chunk_minutes: int = 30,
    transcrire: bool = True,
) -> Dict[str, Any]:
    """Ingère une formation vidéo longue (jusqu'à 15h) en découpant en segments digestes.

    - Extrait des keyframes haute résolution (slides, code à l'écran, schémas).
    - Extrait et transcrit la piste audio localement avec Faster-Whisper.
    - Indexe le tout dans `etude_documents` avec horodatages et captures associées.
    - Distille automatiquement les recettes de code et règles d'ingénierie.
    """
    initialiser_dossier_etude()
    path = Path(video_path).resolve()
    if not path.exists():
        return {"ok": False, "erreur": f"Fichier vidéo introuvable : {path}"}

    titre = titre_cours.strip() or path.stem.replace("_", " ").title()
    nom_rel = path.name
    total_sec = obtenir_duree_video(path)
    chunk_sec = chunk_minutes * 60

    conn = memoire.get_connexion()

    # Nettoyage des anciennes données pour ce fichier
    with memoire._VERROU, conn:
        conn.execute("DELETE FROM etude_documents WHERE fichier = ?;", (nom_rel,))

    segments_crees = 0
    toutes_keyframes = []
    total_recettes = 0
    total_regles = 0

    temps_actuel = 0.0
    num_partie = 1

    while temps_actuel < total_sec or (temps_actuel == 0.0 and total_sec == 0.0):
        duree_segment = min(chunk_sec, total_sec - temps_actuel) if total_sec > 0 else 60.0
        t_debut_str = formater_secondes(temps_actuel)
        t_fin_str = formater_secondes(temps_actuel + duree_segment)
        prefix = f"{path.stem}_part{num_partie:02d}"

        # 1. Extraction des keyframes visuelles (slides, fenêtres de code, graphiques)
        frames = extraire_keyframes(
            path,
            output_prefix=prefix,
            start_seconds=temps_actuel,
            duration_seconds=duree_segment,
            interval_seconds=120,
        )
        toutes_keyframes.extend(frames)

        # 2. Extraction et transcription audio locale
        transcription = ""
        if transcrire:
            audio_temp = DOSSIER_AUDIO_TEMP / f"{prefix}_temp.wav"
            if extraire_audio_segment(path, audio_temp, start_seconds=temps_actuel, duration_seconds=duree_segment):
                transcription = transcrire_audio_segment(audio_temp)
                try:
                    if audio_temp.exists():
                        audio_temp.unlink()
                except Exception:
                    pass

        # 3. Construction du contenu enrichi pour le RAG
        lignes_bloc = [
            f"=== {titre} - Partie {num_partie} [{t_debut_str} -> {t_fin_str}] ===",
            f"Fichier source : {nom_rel}",
            f"Durée du segment : {round(duree_segment / 60, 1)} minutes",
        ]

        if frames:
            lignes_bloc.append("\n[Captures visuelles / Keyframes (slides, schémas, code affiché)] :")
            for f in frames:
                lignes_bloc.append(f"• Capture : {f}")

        if transcription.strip():
            lignes_bloc.append(f"\n[Transcription & Explications orales] :\n{transcription.strip()}")
        else:
            lignes_bloc.append("\n[Notes] : Segment analysé visuellement par keyframes (aucun texte oral transcrit).")

        texte_final = "\n".join(lignes_bloc)

        # 4. Enregistrement dans la base documentaire SQLite FTS5
        with memoire._VERROU, conn:
            titre_partie = f"{titre} (Partie {num_partie} : {t_debut_str} à {t_fin_str})"
            conn.execute("""
                INSERT INTO etude_documents(fichier, titre, section, texte, cree_a)
                VALUES (?, ?, ?, ?, datetime('now'));
            """, (nom_rel, titre_partie, f"Segment {num_partie} [{t_debut_str}]", texte_final))
            segments_crees += 1

        # 5. Distillation des recettes et règles
        if transcription:
            bilan = distiller_connaissances_automatiques(transcription, source_nom=nom_rel)
            total_recettes += bilan["recettes"]
            total_regles += bilan["regles"]

        temps_actuel += duree_segment
        num_partie += 1
        if total_sec == 0.0 or temps_actuel >= total_sec:
            break

    # Nettoyage du dossier temporaire audio
    shutil.rmtree(DOSSIER_AUDIO_TEMP, ignore_errors=True)

    return {
        "ok": True,
        "fichier": nom_rel,
        "titre": titre,
        "duree_totale_minutes": round(total_sec / 60, 1),
        "segments_indexes": segments_crees,
        "keyframes_extraites": len(toutes_keyframes),
        "recettes_dev_ajoutees": total_recettes,
        "regles_dev_ajoutees": total_regles,
    }


def synchroniser_dossier_etude() -> Dict[str, Any]:
    """Scanne le dossier etude/, extrait et indexe les documents ET les vidéos dans SQLite FTS5."""
    initialiser_dossier_etude()
    conn = memoire.get_connexion()

    fichiers_indexes = 0
    chunks_inseres = 0
    videos_traitees = 0
    keyframes_totales = 0
    fichiers_liste = []

    fichiers = [f for f in DOSSIER_ETUDE.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS_SUPPORTEES]

    for f in fichiers:
        # Éviter de réindexer les sous-dossiers de keyframes ou temporaires
        if "keyframes" in f.parts or ".audio_temp" in f.parts:
            continue

        ext = f.suffix.lower()
        nom_rel = str(f.relative_to(DOSSIER_ETUDE))

        if ext in EXTENSIONS_VIDEO:
            # Traitement multimédia pour fichiers vidéo
            res_vid = ingerer_fichier_video(f, titre_cours=f.stem.replace("_", " ").title(), transcrire=True)
            if res_vid.get("ok"):
                videos_traitees += 1
                chunks_inseres += res_vid.get("segments_indexes", 0)
                keyframes_totales += res_vid.get("keyframes_extraites", 0)
                fichiers_indexes += 1
                fichiers_liste.append({
                    "nom": nom_rel,
                    "type": "video",
                    "taille_mo": round(f.stat().st_size / (1024 * 1024), 2),
                    "duree_min": res_vid.get("duree_totale_minutes", 0),
                    "chunks": res_vid.get("segments_indexes", 0),
                    "keyframes": res_vid.get("keyframes_extraites", 0),
                })
        else:
            # Traitement textuel standard (PDF, MD, etc.)
            texte = extraire_texte(f)
            if not texte.strip():
                continue

            chunks = decouper_en_sections(texte)
            if not chunks:
                continue

            with memoire._VERROU, conn:
                conn.execute("DELETE FROM etude_documents WHERE fichier = ?;", (nom_rel,))
                for idx, chunk in enumerate(chunks, start=1):
                    titre = f"{f.stem} (Partie {idx}/{len(chunks)})"
                    conn.execute("""
                        INSERT INTO etude_documents(fichier, titre, section, texte, cree_a)
                        VALUES (?, ?, ?, ?, datetime('now'));
                    """, (nom_rel, titre, f"Section {idx}", chunk))
                    chunks_inseres += 1

            # Distillation recettes et règles
            distiller_connaissances_automatiques(texte, source_nom=nom_rel)

            fichiers_indexes += 1
            fichiers_liste.append({
                "nom": nom_rel,
                "type": "document",
                "taille_ko": round(f.stat().st_size / 1024, 1),
                "chunks": len(chunks),
                "keyframes": 0,
            })

    return {
        "ok": True,
        "fichiers_indexes": fichiers_indexes,
        "videos_traitees": videos_traitees,
        "keyframes_totales": keyframes_totales,
        "chunks_totaux": chunks_inseres,
        "fichiers": fichiers_liste,
    }


def lister_fichiers_etude() -> List[Dict[str, Any]]:
    """Liste tous les cours et documents d'étude présents et leur statut d'indexation."""
    initialiser_dossier_etude()
    conn = memoire.get_connexion()

    with memoire._VERROU:
        cur = conn.execute("""
            SELECT fichier, COUNT(*) as nb_chunks, MAX(cree_a) as indexe_le
            FROM etude_documents
            GROUP BY fichier;
        """)
        indexes = {r["fichier"]: {"nb_chunks": r["nb_chunks"], "indexe_le": r["indexe_le"]} for r in cur.fetchall()}

    fichiers = []
    for f in DOSSIER_ETUDE.rglob("*"):
        if f.is_file() and f.suffix.lower() in EXTENSIONS_SUPPORTEES:
            if "keyframes" in f.parts or ".audio_temp" in f.parts:
                continue
            rel = str(f.relative_to(DOSSIER_ETUDE))
            info = indexes.get(rel, indexes.get(f.name, {"nb_chunks": 0, "indexe_le": None}))
            fichiers.append({
                "fichier": rel,
                "type": "video" if f.suffix.lower() in EXTENSIONS_VIDEO else "document",
                "taille_ko": round(f.stat().st_size / 1024, 1),
                "nb_chunks": info["nb_chunks"],
                "indexe_le": info["indexe_le"],
            })

    return fichiers


def lister_keyframes_etude(filtre_prefixe: str = "") -> List[Dict[str, Any]]:
    """Liste les images clés / keyframes extraites dans `etude/keyframes`."""
    initialiser_dossier_etude()
    resultats = []
    motif = f"*{filtre_prefixe}*.jpg" if filtre_prefixe else "*.jpg"
    for img in sorted(DOSSIER_KEYFRAMES.glob(motif)):
        rel = str(img.relative_to(RACINE)).replace("\\", "/")
        resultats.append({
            "nom": img.name,
            "chemin_relatif": rel,
            "taille_ko": round(img.stat().st_size / 1024, 1),
        })
    return resultats


def recup_contexte_etude(requete: str, limite: int = 4) -> str:
    """Cherche les passages et captures les plus pertinents pour répondre à une question de cours."""
    passages = memoire.rechercher_etude(requete, limite=limite)
    if not passages:
        return ""

    extraits = ["\n[Extraits de cours et formations pertinentes dans etude/] :"]
    for p in passages:
        extraits.append(f"• Fichier : {p['fichier']} ({p['titre']})\n{p['texte']}")
    return "\n".join(extraits) + "\n"
