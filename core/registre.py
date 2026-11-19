"""Registre d'outils : decorateur @outil, auto-decouverte, confirmation vocale.

Chaque outil est une fonction decoree par @outil dans un fichier de tools/.
Au demarrage, charger_outils() importe tous les modules de tools/ pour peupler
le registre. Le reste de l'assistant n'a plus a connaitre les outils un par un.
"""
import importlib
import logging
import pkgutil

LOG = logging.getLogger("jarvis")
_REGISTRE = {}      # nom -> Outil
_OUTILS_IGNORES = {}  # module -> raison (dependance optionnelle absente)
_EN_ATTENTE = None  # (Outil, args) en attente d'une confirmation vocale


class Outil:
    """Metadonnees + fonction d'un outil."""

    def __init__(self, fonction, nom, description, parametres, confirmation,
                 lent, phrase_attente, annonce, mcp_expose, affichage="auto"):
        self.fonction = fonction
        self.nom = nom
        self.description = description
        self.parametres = parametres
        self.confirmation = confirmation      # demande "tu confirmes ?" avant d'agir
        self.lent = lent                      # accuse de reception pendant l'execution
        self.phrase_attente = phrase_attente  # phrase d'attente si lent
        self.annonce = annonce                # fn(args) -> phrase de confirmation
        self.mcp_expose = mcp_expose          # visible via le serveur MCP externe ?
        self.affichage = affichage            # overlay : "toujours" | "jamais" | "auto"


def outil(nom, description, parametres=None, confirmation=False, lent=False,
          phrase_attente=None, annonce=None, mcp_expose=False, affichage="auto"):
    """Decorateur : enregistre une fonction comme outil de l'assistant.

    mcp_expose : par securite, un outil n'est PAS expose au serveur MCP par
    defaut (un agent externe ne doit voir que ce qu'on autorise explicitement).
    affichage : routage de l'overlay de reponses. "toujours" (musique, stats,
    listes, minuteurs, retours Hermes), "jamais" (acquittement ephemere), ou
    "auto" (defaut : heuristique cote core selon le contenu de la reponse).
    """
    def deco(fonction):
        _REGISTRE[nom] = Outil(
            fonction, nom, description,
            parametres or {"type": "object", "properties": {}},
            confirmation, lent, phrase_attente, annonce, mcp_expose, affichage)
        return fonction
    return deco


def affichage(nom):
    """Hint d'affichage overlay d'un outil : 'toujours' | 'jamais' | 'auto'."""
    o = _REGISTRE.get(nom)
    return getattr(o, "affichage", "auto") if o else "auto"


def charger_outils():
    """Importe tous les modules de tools/ pour remplir le registre.

    Les modules dont une dependance optionnelle est absente sur la machine
    sont ignores proprement pour garantir un demarrage CLI leger partout.
    """
    import tools
    for module in pkgutil.iter_modules(tools.__path__):
        try:
            importlib.import_module(f"tools.{module.name}")
        except (ImportError, OSError) as e:
            _OUTILS_IGNORES[module.name] = str(e)
            LOG.debug("Outil '%s' ignore (dependance absente) : %s", module.name, e)


def outils_ignores():
    """Retourne les modules d'outils ignores faute de dependances optionnelles."""
    return dict(_OUTILS_IGNORES)


def get(nom):
    return _REGISTRE.get(nom)


def tous():
    return list(_REGISTRE.values())


# Outils NON exposes au modele local (mode local) : outils necessitant obligatoirement
# une connexion internet, un service cloud externe ou une capacite de vision multimodale.
# Tous les outils purement locaux (domotique Hue, OBS, gestion PC, audio, overlay, memoire, etc.)
# restent ainsi disponibles meme hors ligne.
_NON_LOCAUX = {
    # Vision d'ecran (necessite un modele multimodal)
    "capture_screen",
    # Mails & Agenda (APIs Google / IMAP)
    "faire_brief", "lire_mails", "lire_mail", "preparer_mail", "envoyer_mail", "mettre_a_la_corbeille",
    "get_events", "create_event", "delete_event", "get_deadlines",
    # Recherche & Automatisation Web
    "chercher_web", "lire_page_web", "recueillir_veille_web", "book_appointment", "confirmer_reservation",
    "browser_open", "browser_current_page", "browser_tabs", "browser_close_tabs", "browser_interact",
    # Telephonie (Twilio)
    "call_with_message", "call_and_book", "cout_appels",
    # Reseaux sociaux & Discord
    "instagram_resume", "rafraichir_instagram",
    "get_mentions_summary", "get_channel_summary",
    # Identification musicale en ligne
    "identifier_musique", "identifier_musique_fichier",
    # Cloud tiers & IA distante
    "lancer_ingestion_youtube", "chercher_inspiration", "generer_idees_contenu", "generer_script",
    "deleguer_a_hermes",
    "alexa_etat", "alexa_annoncer", "alexa_routine", "alexa_appareil", "alexa_media",
    "google_home_etat", "google_home_allumer", "google_home_luminosite",
}


# Packs et routage dynamique des outils (optimisation contextuelle & anti-saturation)
_PACK_REFLEXES = {
    "heure_et_date", "lancer_minuteur", "meteo", "noter", "notes_du_jour",
    "sortir_idee", "mon_budget", "faire_brief", "remember", "recall", "forget", "chercher_web", "lire_page_web", "grill-me"
}

_CATEGORIES_OUTILS = {
    "domotique_audio": {
        "allumer_lumiere", "regler_luminosite", "changer_couleur", "controler_amaran",
        "alexa_etat", "alexa_annoncer", "alexa_routine", "alexa_appareil", "alexa_media",
        "google_home_etat", "google_home_allumer", "google_home_luminosite",
        "sortie_audio", "regler_volume", "controler_media",
        "identifier_musique", "identifier_musique_fichier", "derniere_musique",
        "ajouter_a_playlist", "enchainement_automix"
    },
    "systeme_pc": {
        "launch_app", "ouvrir_application", "ajouter_app",
        "verrouiller_pc", "eteindre_pc", "annuler_extinction",
        "get_system_stats", "inspecter_port", "lister_processus", "tuer_processus",
        "analyser_espace_stockage", "nettoyer_caches_temporaires",
        "capture_screen", "ouvrir_panneau", "detection_presence",
        "changer_personnalite", "controler_gestes", "reglage_overlay",
        "mode_routage", "activer_mode", "afficher_reponse", "afficher_reponses", "mode_silencieux_visuel"
    },
    "code_dev": {
        "explorer_projet", "lire_code", "ecrire_code", "patcher_code", "chercher_dans_code",
        "executer_terminal", "ouvrir_terminal_interactif", "executer_test_ou_commande",
        "lister_dossier", "chercher_fichiers", "supprimer_fichier", "ouvrir_fichier",
        "enregistrer_recette_dev", "chercher_recette_dev", "apprendre_regle", "lister_regles",
        "lister_competences", "charger_competence", "lire_reference", "deleguer_a_hermes"
    },
    "navigateur_web": {
        "lancer_navigateur_chrome", "browser_open", "browser_current_page", "browser_tabs",
        "browser_close_tabs", "browser_interact", "browser_click", "browser_type", "browser_scroll",
        "capturer_page", "capturer_frames"
    },
    "bureautique_documents": {
        "generer_excel", "lire_excel", "generer_powerpoint", "lire_powerpoint",
        "generer_pdf", "extraire_texte_pdf", "fusionner_pdfs",
        "generer_graphique", "generer_diagramme", "creer_produit_digital",
        "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls",
        "generer_composant_mobile", "scaffolder_app_mobile_expo",
        "photoshop_statut", "photoshop_executer_jsx",
        "importer_releve", "corriger_categorie", "detecter_abonnements", "integrer_abonnements_detectes"
    },
    "communication_agenda": {
        "lire_mails", "lire_mail", "preparer_mail", "envoyer_mail", "mettre_a_la_corbeille",
        "get_events", "create_event", "delete_event", "get_deadlines",
        "call_and_book", "call_with_message", "cout_appels", "book_appointment", "confirmer_reservation",
        "instagram_resume", "rafraichir_instagram", "get_mentions_summary", "get_channel_summary"
    },
    "trading_vibetg_marche": {
        "trade_app_statut", "trade_app_prix_crypto", "trade_app_demarrer_service",
        "trading_analyse_technique", "trading_calculateur_risque", "trading_carnet_ordres_express",
        "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille",
        "vibetg_activer_algo_pubs", "vibetg_activer_mode_nuit", "vibetg_statut_algo_pubs", "vibetg_arreter_algo_pubs",
        "vibetg_tablette_statut", "vibetg_tablette_demarrer", "vibetg_tablette_arreter"
    },
    "stream_obs_media": {
        "start_stream", "stop_stream", "start_record", "stop_record", "switch_scene", "save_replay",
        "ingerer_cours_video", "interroger_cours", "lister_keyframes", "synchroniser_cours", "lister_cours",
        "chercher_inspiration", "generer_idees_contenu", "generer_script", "lancer_ingestion_youtube",
        "nouvelle_idee_video", "changer_statut_contenu", "ou_j_en_suis", "etat_contenus"
    }
}

_MOTS_CLES_CATEGORIES = {
    "reflexes": [
        "heure", "date", "minuteur", "timer", "chrono", "meteo", "temps", "noter", "note",
        "idee", "budget", "brief", "rappelle", "souviens", "oublie", "bonjour", "salut", "merci",
        "qui es-tu", "aide", "comment vas"
    ],
    "domotique_audio": [
        "lumiere", "lampe", "hue", "couleur", "salon", "chambre", "musique", "spotify",
        "son", "volume", "morceau", "playlist", "chanson", "alexa", "google home",
        "titre", "shazam", "mix", "dj", "audio", "baffle", "enceinte", "casque", "amaran", "eclairage"
    ],
    "systeme_pc": [
        "lance", "ouvre", "ferme", "app", "application", "jeu", "pc", "ordinateur", "eteins",
        "verrouille", "redemarre", "ecran", "stats", "cpu", "ram", "disque", "processus",
        "port", "tuer", "nettoie", "cache", "panneau", "stockage", "espace"
    ],
    "code_dev": [
        "code", "python", "fichier", "git", "script", "projet", "erreur", "terminal", "bug",
        "fonction", "dossier", "npm", "test", "compiler", "classe", "refactor", "commande",
        "powershell", "bash", "repo", "branche"
    ],
    "navigateur_web": [
        "navigateur", "chrome", "page", "onglet", "clique", "site", "url", "scrolle",
        "visite", "champ", "bouton", "web", "lien", "navigue"
    ],
    "bureautique_documents": [
        "excel", "powerpoint", "pdf", "tableau", "presentation", "slides", "classeur",
        "rapport", "diagramme", "graphique", "chart", "produit digital", "ebook", "sql",
        "postgis", "mobile", "expo", "photoshop", "document", "xlsx", "pptx", "depense",
        "releve", "banque", "abonnement"
    ],
    "communication_agenda": [
        "mail", "email", "message", "agenda", "evenement", "rdv", "rendez-vous", "reunion",
        "rappel", "deadline", "instagram", "discord", "appelle", "telephoner", "appel", "calendrier"
    ],
    "trading_vibetg_marche": [
        "trading", "crypto", "bitcoin", "btc", "eth", "solana", "cours", "prix", "ordre",
        "marche", "veille", "bulletin", "tablette", "pub", "vibetg", "coins", "fire hd", "bourse"
    ],
    "stream_obs_media": [
        "obs", "stream", "streaming", "record", "enregistre", "scene", "twitch", "youtube",
        "cours", "video", "script", "camera", "replay"
    ]
}


def router_outils(requete: str = "") -> set:
    """Sélectionne dynamiquement les outils pertinents pour une requête donnée.

    Réduit le catalogue de 160 outils à un ensemble ciblé de 12 à 35 outils,
    économisant jusqu'à 85% de tokens de prompt et maximisant la précision du LLM.
    """
    if not requete or not isinstance(requete, str):
        return set(_REGISTRE.keys())

    p = requete.lower().strip()
    if not p:
        return set(_REGISTRE.keys())

    sel = set(_PACK_REFLEXES)
    matched_cats = set()

    for cat, mots in _MOTS_CLES_CATEGORIES.items():
        if any(m in p for m in mots):
            matched_cats.add(cat)
            if cat != "reflexes" and cat in _CATEGORIES_OUTILS:
                sel.update(_CATEGORIES_OUTILS[cat])

    # Si aucune catégorie spécifique n'a matché (requête non reconnue ou polyvalente),
    # on fournit le pack réflexes étendu avec système et web
    if not matched_cats:
        sel.update(_CATEGORIES_OUTILS.get("systeme_pc", set()))
        sel.update(_CATEGORIES_OUTILS.get("navigateur_web", set()))

    # Élimine la redondance entre ouvrir_application et launch_app
    if "ouvrir_application" in sel and "launch_app" in sel:
        sel.discard("launch_app")

    return sel


def schemas_api(local_seulement=False, requete=None):
    """Schemas au format Anthropic (name, description, input_schema).

    local_seulement=True : ne renvoie que les outils utilisables par un modele
    local (mode Ollama), en excluant les outils internet/vision (_NON_LOCAUX).
    requete : phrase ou intention utilisateur pour activer le routage dynamique
    d'outils et éviter la saturation du contexte.
    """
    noms_cibles = router_outils(requete) if requete else set(_REGISTRE.keys())

    return [{"name": o.nom, "description": o.description, "input_schema": o.parametres}
            for o in _REGISTRE.values()
            if o.nom in noms_cibles and not (local_seulement and o.nom in _NON_LOCAUX)]


def noms_lents():
    return {o.nom for o in _REGISTRE.values() if o.lent}


def exposes_mcp():
    """Liste des outils autorises a etre exposes via le serveur MCP externe."""
    return [o for o in _REGISTRE.values() if o.mcp_expose]


# ---------------------------------------------------- niveaux de permission (N8)
#
# N1 (sur)      : pas de confirmation -> execute direct, EN LOCAL ET a distance.
# N2 (sensible) : confirmation ; l'utilisateur peut memoriser "toujours autoriser"
#                 (revocable) -> plus de question EN LOCAL ; jamais en auto a distance.
# N3 (critique) : confirmation TOUJOURS ; "toujours" REFUSE ; jamais a distance.
#                 Verrouille ici. (Le pont iPhone refuse deja tout outil a confirmation,
#                 quel que soit le store : le "toujours autoriser" n'ouvre RIEN a distance.)
_N3 = frozenset({
    "envoyer_mail", "mettre_a_la_corbeille",
    "call_with_message", "call_and_book",
    "book_appointment", "confirmer_reservation",
    "delete_event",
    "eteindre_pc",
})


def niveau(nom):
    """Niveau de permission d'un outil : N1 / N2 / N3 (ou '?' si inconnu)."""
    o = _REGISTRE.get(nom)
    if o is None:
        return "?"
    if not o.confirmation:
        return "N1"
    return "N3" if nom in _N3 else "N2"


def est_n3(nom):
    return nom in _N3


def autorisations():
    """Outils N2 memorises 'toujours autoriser' (config securite.toujours)."""
    from core.config import reglage
    return [n for n in (reglage("securite.toujours", []) or []) if niveau(n) == "N2"]


def est_autorise(nom):
    """Vrai si on SAUTE la confirmation EN LOCAL (N2 memorise). Jamais un N3 ni un N1."""
    return niveau(nom) == "N2" and nom in autorisations()


def autoriser_toujours(nom):
    """Memorise 'toujours autoriser' pour un N2. Renvoie True si effectif (N2 uniquement,
    jamais un N3)."""
    if niveau(nom) != "N2":
        return False
    from core.config import reglage, definir
    cur = list(reglage("securite.toujours", []) or [])
    if nom not in cur:
        cur.append(nom)
        definir("securite.toujours", cur)
    return True


def revoquer(nom):
    """Retire un outil du 'toujours autoriser'. Renvoie True si quelque chose a ete retire."""
    from core.config import reglage, definir
    cur = list(reglage("securite.toujours", []) or [])
    if nom in cur:
        cur.remove(nom)
        definir("securite.toujours", cur)
        return True
    return False


def phrase_attente(noms):
    """Phrase d'accuse de reception pour le premier outil lent appele."""
    for o in _REGISTRE.values():
        if o.nom in noms and o.lent and o.phrase_attente:
            return o.phrase_attente
    return "D'accord, je m'en occupe."


# ---------------------------------------------------------------- confirmation

def mettre_en_attente(outil_obj, args):
    """Range une action a confirmer. Renvoie un resultat neutre pour Claude."""
    global _EN_ATTENTE
    _EN_ATTENTE = (outil_obj, args)
    return "En attente de la confirmation vocale de l'utilisateur."


def annonce_en_attente():
    """Phrase a prononcer pour demander l'accord, ou None si rien en attente."""
    if _EN_ATTENTE is None:
        return None
    outil_obj, args = _EN_ATTENTE
    if outil_obj.annonce:
        try:
            return outil_obj.annonce(args)
        except Exception:
            pass
    return f"Je vais executer {outil_obj.nom}."


def nom_en_attente():
    """Nom de l'outil en attente de confirmation (ou None)."""
    return _EN_ATTENTE[0].nom if _EN_ATTENTE else None


def executer_confirme(memoriser=False):
    """Execute l'action en attente et renvoie son resultat.

    memoriser=True (l'utilisateur a dit "oui, toujours") : si l'outil est N2, on
    l'ajoute au 'toujours autoriser' (revocable) ; un N3 REFUSE la memorisation et
    on le lui dit, mais l'action de ce tour est quand meme executee.
    """
    global _EN_ATTENTE
    if _EN_ATTENTE is None:
        return ""
    outil_obj, args = _EN_ATTENTE
    _EN_ATTENTE = None
    suffixe = ""
    if memoriser:
        if autoriser_toujours(outil_obj.nom):
            suffixe = " Je ne te le redemanderai plus pour cette action."
        else:
            suffixe = " Mais c'est une action critique : je te demanderai toujours confirmation."
    try:
        res = outil_obj.fonction(**args)
    except Exception:
        return "Desole, je n'ai pas reussi a faire ca."
    return (str(res) + suffixe) if suffixe else res


def annuler_confirme():
    global _EN_ATTENTE
    _EN_ATTENTE = None
