"""Mémoire long terme de RIOT : remember (mémoriser), recall (recherche FTS5), forget (oublier).

Propulsé par SQLite FTS5 pour une recherche instantanée et pertinente.
Intègre également le carnet de recettes de code et résolution de bugs.
"""
from core import memoire
from core.registre import outil
from core.util import sans_accents

_CATEGORIES = {
    "preference": "preferences", "preferences": "preferences", "pref": "preferences",
    "personne": "people", "personnes": "people", "people": "people",
    "proche": "people", "proches": "people", "contact": "people",
    "projet": "projects", "projets": "projects", "project": "projects",
    "fait": "facts", "faits": "facts", "fact": "facts", "info": "facts",
    "regle": "regles_dev", "regles": "regles_dev", "regle_dev": "regles_dev",
}


@outil(
    nom="remember",
    description="Mémorise durablement une information sur l'utilisateur ou ses habitudes. À appeler "
                "automatiquement quand il exprime une préférence, mentionne un projet, une règle de dev ou un fait. "
                "Stocké dans la base SQLite FTS5.",
    parametres={
        "type": "object",
        "properties": {
            "categorie": {
                "type": "string",
                "enum": ["preference", "personne", "projet", "fait", "regle_dev"],
                "description": "Type d'information à mémoriser.",
            },
            "contenu": {
                "type": "string",
                "description": "L'information, formulée clairement. "
                               "Ex : 'Toujours tester les routes API avec TestClient avant de valider'.",
            },
            "cle": {
                "type": "string",
                "description": "Étiquette courte (nom du proche, du projet, ou sujet de la règle). Facultatif.",
            },
        },
        "required": ["categorie", "contenu"],
    },
)
def remember(categorie: str, contenu: str, cle: str = "") -> str:
    """Mémorise une information dans SQLite."""
    contenu = (contenu or "").strip()
    if not contenu:
        return "Rien à retenir."
    cat = _CATEGORIES.get(sans_accents(categorie).strip(), "facts")
    etiquette = cle.strip() or contenu[:40]

    memoire.memoriser_entite(cat, etiquette, contenu)
    return "C'est noté et indexé dans la mémoire RIOT."


@outil(
    nom="recall",
    description="Recherche ultra-rapide dans la mémoire long terme grâce à l'index plein texte FTS5. "
                "Permet de retrouver instantanément les préférences, projets, faits ou règles enregistrées.",
    parametres={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": "Terme ou phrase recherchée (laisser vide pour tout résumer).",
            }
        },
    },
)
def recall(requete: str = "") -> str:
    """Recherche plein texte FTS5 dans la mémoire SQLite."""
    req = requete.strip()
    if req:
        resultats = memoire.rechercher_fts(req, limite=10)
        if not resultats:
            return f"Aucun résultat trouvé dans la mémoire pour '{req}'."
        lignes = [f"Résultats mémoire pour '{req}' :"]
        for r in resultats:
            lignes.append(f"• [{r['categorie'].upper()}] {r['cle']} : {r['contenu']}")
        return "\n".join(lignes)

    # Si aucune requête, on résume la mémoire
    m = memoire.charger()
    trouves = []
    for cat in ("preferences", "people", "projects", "regles_dev"):
        for cle, val in m.get(cat, {}).items():
            trouves.append(f"[{cat.upper()}] {cle} = {val}")
    for fait in m.get("facts", []):
        trouves.append(f"[FAIT] {fait}")

    if not trouves:
        return "Je ne retiens rien pour l'instant dans ma mémoire."
    return "Contenu de la mémoire RIOT :\n" + "\n".join(trouves)


@outil(
    nom="forget",
    description="Supprime de la mémoire SQLite toutes les informations correspondant au sujet donné.",
    parametres={
        "type": "object",
        "properties": {
            "sujet": {"type": "string", "description": "Mot-clé ou sujet à oublier définitivement."}
        },
        "required": ["sujet"],
    },
)
def forget(sujet: str) -> str:
    """Oublie tout ce qui contient ce sujet dans la base SQLite."""
    s = sujet.strip()
    if not s:
        return "Précise ce que tu souhaites oublier."
    n = memoire.oublier_par_motif(s)
    if n == 0:
        return f"Aucune information trouvée contenant '{s}'."
    return f"Oublié : {n} élément(s) supprimé(s) de la mémoire."


@outil(
    nom="enregistrer_recette_dev",
    description="Enregistre une solution technique, un correctif de bug ou un pattern d'architecture dans le carnet de dev.",
    parametres={
        "type": "object",
        "properties": {
            "titre": {"type": "string", "description": "Titre explicite du problème résolu"},
            "probleme": {"type": "string", "description": "Description du bug, de l'erreur ou du besoin"},
            "solution": {"type": "string", "description": "Solution technique détaillée, code ou démarche"},
            "cause": {"type": "string", "description": "Cause racine identifiée (optionnel)"},
            "langage": {"type": "string", "description": "Langage ou framework (ex: python, nextjs, fastapi, react)"},
            "tags": {"type": "string", "description": "Tags séparés par virgules (ex: auth, jwt, pwa)"},
        },
        "required": ["titre", "probleme", "solution"],
    },
)
def enregistrer_recette_dev(
    titre: str,
    probleme: str,
    solution: str,
    cause: str = "",
    langage: str = "",
    tags: str = "",
) -> str:
    """Enregistre une fiche recette dans la base SQLite."""
    recette_id = memoire.ajouter_recette_code(
        titre=titre,
        probleme=probleme,
        solution=solution,
        cause=cause,
        langage=langage,
        tags=tags,
    )
    return f"Recette #{recette_id} '{titre}' enregistrée et indexée dans le carnet de dev."


@outil(
    nom="chercher_recette_dev",
    description="Recherche dans le carnet de recettes techniques et de bugs passés par mots-clés ou description du problème.",
    parametres={
        "type": "object",
        "properties": {
            "requete": {"type": "string", "description": "Mots-clés de l'erreur, du bug ou de la solution recherchée"}
        },
        "required": ["requete"],
    },
)
def chercher_recette_dev(requete: str) -> str:
    """Cherche dans les recettes de dev via FTS5."""
    req = requete.strip()
    if not req:
        return "Précise ta recherche technique."
    trouvees = memoire.rechercher_recettes_code(req, limite=5)
    if not trouvees:
        return f"Aucune recette trouvée correspondant à '{req}'."

    blocs = [f"Recettes trouvées pour '{req}' :"]
    for r in trouvees:
        bloc = (
            f"\n--- [{r['titre']}] ({r.get('langage') or 'general'}) ---\n"
            f"Problème : {r['probleme']}\n"
            f"Cause : {r.get('cause') or 'Non spécifiée'}\n"
            f"Solution : {r['solution']}\n"
            f"Tags : {r.get('tags') or '-'}"
        )
        blocs.append(bloc)
    return "\n".join(blocs)


@outil(
    nom="apprendre_regle",
    description="Enregistre une règle d'ingénierie, de méthodologie ou de dev formulée par l'utilisateur (ex: 'Toujours tester les routes API avec TestClient', 'Utilise le pattern Provider pour les paiements').",
    parametres={
        "type": "object",
        "properties": {
            "cle": {"type": "string", "description": "Identifiant court de la règle (ex: 'validation_api', 'archi_paiements')"},
            "regle": {"type": "string", "description": "La consigne ou règle technique exacte à respecter"},
        },
        "required": ["cle", "regle"],
    },
)
def apprendre_regle(cle: str, regle: str) -> str:
    """Enregistre une règle de dev dans la mémoire persistante SQLite."""
    c = cle.strip()
    r = regle.strip()
    if not c or not r:
        return "Clé et règle requises."
    memoire.ajouter_regle_dev(c, r)
    return f"Règle '{c}' apprise et active dans le système."


@outil(
    nom="lister_regles",
    description="Affiche la liste complète des règles d'ingénierie et de développement actuellement mémorisées.",
    parametres={"type": "object", "properties": {}},
)
def lister_regles() -> str:
    """Liste toutes les règles de dev mémorisées."""
    regles = memoire.lister_regles_dev()
    if not regles:
        return "Aucune règle de développement personnalisée pour le moment."
    lignes = ["Règles d'ingénierie et de dev apprises :"]
    for r in regles:
        lignes.append(f"• [{r['cle']}] : {r['contenu']}")
    return "\n".join(lignes)

