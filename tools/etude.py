"""Outils de tutorat et d'étude multimédia RIOT (Dossier etude/).

Permet à RIOT de :
- Ingérer des formations vidéo longues (jusqu'à 15h) avec extraction de graphiques/code et transcription locale.
- Interroger les cours (PDF, Markdown, code, vidéos) avec références visuelles et horodatages via SQLite FTS5.
- Déclencher la synchronisation et l'indexation de nouveaux documents et cours vidéo déposés.
- Lister les documents d'étude et les keyframes (captures visuelles de slides/code).
"""
from pathlib import Path
from core import etude
from core.registre import outil


@outil(
    nom="ingerer_cours_video",
    description="Ingère une formation ou un cours vidéo long (jusqu'à 15h : MP4, MKV, MOV, WEBM) "
                "dans l'esprit zéro quota : découpe en tranches digestes, extrait les captures d'écran "
                "des schémas et du code affiché, transcrit l'audio et distille les recettes de dev dans RIOT.",
    parametres={
        "type": "object",
        "properties": {
            "chemin_video": {
                "type": "string",
                "description": "Chemin absolu ou relatif vers le fichier vidéo (ex: 'E:/Formations/Docker_Masterclass.mp4')",
            },
            "titre": {
                "type": "string",
                "description": "Titre du cours ou de la formation (facultatif, déduit du nom de fichier si omis)",
            },
            "chunk_minutes": {
                "type": "integer",
                "description": "Durée de chaque tranche en minutes (défaut : 30 minutes)",
            },
            "transcrire_audio": {
                "type": "boolean",
                "description": "True pour transcrire la parole en local via Faster-Whisper, False pour analyse visuelle seule",
            },
        },
        "required": ["chemin_video"],
    },
    lent=True,
    phrase_attente="J'analyse la vidéo, j'extrais les graphiques et je distille les connaissances...",
)
def ingerer_cours_video(
    chemin_video: str,
    titre: str = "",
    chunk_minutes: int = 30,
    transcrire_audio: bool = True,
) -> str:
    """Ingère une formation vidéo complète avec extraction de keyframes et recettes."""
    p = Path(chemin_video).strip() if isinstance(chemin_video, str) else chemin_video
    p = Path(str(p).strip("'\""))

    if not p.is_absolute():
        # Vérifier si dans dossier etude/
        p_etude = etude.DOSSIER_ETUDE / p
        if p_etude.exists():
            p = p_etude

    if not p.exists():
        return f"Erreur : le fichier vidéo '{p}' est introuvable."

    res = etude.ingerer_fichier_video(
        video_path=p,
        titre_cours=titre,
        chunk_minutes=chunk_minutes or 30,
        transcrire=transcrire_audio,
    )

    if not res.get("ok"):
        return f"Échec de l'ingestion vidéo : {res.get('erreur')}"

    return (
        f"Formation '{res['titre']}' ingérée avec succès !\n"
        f"- Durée totale : {res['duree_totale_minutes']} minutes\n"
        f"- Segments indexés dans FTS5 : {res['segments_indexes']}\n"
        f"- Keyframes visuelles extraites (code & graphiques) : {res['keyframes_extraites']}\n"
        f"- Fiches recettes de dev générées : {res['recettes_dev_ajoutees']}\n"
        f"- Règles d'ingénierie apprises : {res['regles_dev_ajoutees']}"
    )


@outil(
    nom="interroger_cours",
    description="Recherche dans les cours et formations déposés dans etude/ (vidéos, PDF, Markdown, manuels) "
                "pour répondre à une question technique, réviser un concept ou résoudre un exercice d'examen.",
    parametres={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "La question de cours, le concept ou le problème à rechercher",
            }
        },
        "required": ["question"],
    },
)
def interroger_cours(question: str) -> str:
    """Interroge les cours ingérés via FTS5."""
    q = question.strip()
    if not q:
        return "Précise ta question de cours."
    contexte = etude.recup_contexte_etude(q, limite=4)
    if not contexte:
        return f"Aucun extrait de cours trouvé dans le dossier etude/ pour '{q}'."
    return contexte


@outil(
    nom="lister_keyframes",
    description="Affiche les captures d'écran visuelles (slides, fenêtres de code, schémas) "
                "extraites lors de l'ingestion de formations vidéo.",
    parametres={
        "type": "object",
        "properties": {
            "filtre": {
                "type": "string",
                "description": "Filtre optionnel sur le nom de la formation ou du fichier",
            }
        },
    },
)
def lister_keyframes(filtre: str = "") -> str:
    """Liste les keyframes enregistrées dans etude/keyframes/."""
    frames = etude.lister_keyframes_etude(filtre_prefixe=filtre.strip())
    if not frames:
        return "Aucune capture visuelle (keyframe) disponible pour l'instant."
    lignes = [f"Keyframes visuelles disponibles ({len(frames)} captures) :"]
    for f in frames[:20]:
        lignes.append(f"- {f['nom']} ({f['taille_ko']} Ko) -> {f['chemin_relatif']}")
    if len(frames) > 20:
        lignes.append(f"... et {len(frames) - 20} autres captures.")
    return "\n".join(lignes)


@outil(
    nom="synchroniser_cours",
    description="Scanne le dossier etude/ pour indexer tous les nouveaux documents (PDF, MD, TXT, code) "
                "et formations vidéo (MP4, MKV, MOV, WEBM) dans SQLite FTS5.",
    parametres={"type": "object", "properties": {}},
    lent=True,
    phrase_attente="Synchronisation des cours et vidéos du dossier etude en cours...",
)
def synchroniser_cours() -> str:
    """Synchronise et découpe les fichiers et vidéos du dossier etude/."""
    res = etude.synchroniser_dossier_etude()
    nb_fichiers = res.get("fichiers_indexes", 0)
    nb_videos = res.get("videos_traitees", 0)
    nb_chunks = res.get("chunks_totaux", 0)
    nb_kf = res.get("keyframes_totales", 0)
    return (
        f"Synchronisation terminée :\n"
        f"- {nb_fichiers} ressource(s) traitée(s) (dont {nb_videos} vidéo(s))\n"
        f"- {nb_chunks} sections indexées dans la base de cours RIOT\n"
        f"- {nb_kf} keyframes visuelles prêtes pour la consultation"
    )


@outil(
    nom="lister_cours",
    description="Affiche la liste des cours, manuels et formations vidéo actuellement présents dans le dossier etude/.",
    parametres={"type": "object", "properties": {}},
)
def lister_cours() -> str:
    """Liste tous les cours présents."""
    fichiers = etude.lister_fichiers_etude()
    if not fichiers:
        return "Aucun cours déposé pour l'instant dans le dossier etude/."
    lignes = ["Documents et formations d'étude disponibles :"]
    for f in fichiers:
        type_icone = "Video" if f.get("type") == "video" else "Doc"
        lignes.append(f"- [{type_icone}] {f['fichier']} ({f['taille_ko']} Ko) -- {f['nb_chunks']} sections indexées")
    return "\n".join(lignes)
