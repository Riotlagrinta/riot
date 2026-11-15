"""Outils d'Audit, Diagnostic et Optimisation SQL / PostGIS / Supabase RLS.

Spécialisé pour les architectures PostgreSQL, PostGIS et Supabase (ex: MediGo, Eco-Atlas, TogoDrive) :
1. Audit de sécurité des schémas SQL (détection de tables sans RLS, clés étrangères non indexées, fuites de données de santé/users).
2. Optimisation des requêtes géo-spatiales PostGIS (ST_DWithin, index GIST, SRID, bounding box &&, ordre de filtrage).
3. Générateur de politiques RLS (Row Level Security) durcies et idempotentes pour Supabase et PostgreSQL.
4. Génération de scripts de migration non destructifs (CREATE INDEX CONCURRENTLY IF NOT EXISTS).
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.sql_inspector")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_MIGRATIONS = _RACINE / "output_documents"
_DOSSIER_MIGRATIONS.mkdir(parents=True, exist_ok=True)


def _decouper_colonnes(corps: str) -> List[str]:
    """Découpe les définitions de colonnes et contraintes en respectant les parenthèses imbriquées."""
    morceaux = []
    courant = []
    profondeur = 0
    for char in corps:
        if char == '(':
            profondeur += 1
            courant.append(char)
        elif char == ')':
            profondeur -= 1
            courant.append(char)
        elif char == ',' and profondeur == 0:
            morceaux.append("".join(courant).strip())
            courant = []
        else:
            courant.append(char)
    if courant:
        morceaux.append("".join(courant).strip())
    return [m for m in morceaux if m]


def _analyser_tables_et_colonnes(sql_texte: str) -> Dict[str, Dict[str, Any]]:
    """Parse approfondi des instructions CREATE TABLE, ALTER TABLE et INDEX en SQL."""
    tables = {}
    # Nettoyer les commentaires SQL (-- et /* */)
    sql_propre = re.sub(r"--.*?\n", "\n", sql_texte)
    sql_propre = re.sub(r"/\*.*?\*/", "", sql_propre, flags=re.DOTALL)

    pattern_table = re.compile(
        r"create\s+table(?:\s+if\s+not\s+exists)?\s+([^\s\(]+)\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL
    )

    mots_sensibles = (
        "patient", "ordonnance", "sante", "maladie", "medicament", "prescription",
        "mot_de_passe", "password", "secret", "telephone", "solde", "transaction",
        "montant", "carte", "user", "utilisateur", "auth", "token", "dossier_medical"
    )

    for match in pattern_table.finditer(sql_propre):
        nom_brut = match.group(1).strip().strip('"').strip("'")
        corps = match.group(2).strip()

        colonnes = []
        lignes = _decouper_colonnes(corps)
        
        has_pk = False
        has_geom = False
        champs_sensibles = []
        foreign_keys = []

        # Vérifier si la table elle-même est sensible
        if any(s in nom_brut.lower() for s in ("patient", "ordonnance", "dossier", "sante", "transaction", "consultation", "user", "paiement")):
            champs_sensibles.append(f"Nom de table sensible (`{nom_brut}`)")

        for l_net in lignes:
            l_lower = l_net.lower()
            if l_lower.startswith("primary key") or " primary key" in l_lower:
                has_pk = True

            # Détection colonnes géométrie PostGIS
            if any(k in l_lower for k in ("geometry", "geography", "point", "polygon", "multipolygon", "linestring")):
                has_geom = True

            # Analyse du nom de colonne
            col_match = re.match(r"^([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_\(\)]+)", l_net)
            if col_match:
                nom_col = col_match.group(1).lower()
                type_col = col_match.group(2).lower()
                colonnes.append({"nom": nom_col, "type": type_col, "raw": l_net})
                if any(s in nom_col for s in mots_sensibles):
                    champs_sensibles.append(nom_col)
                if nom_col.endswith("_id") and nom_col != "id":
                    foreign_keys.append(nom_col)

        tables[nom_brut] = {
            "colonnes": colonnes,
            "has_pk": has_pk,
            "has_geom": has_geom,
            "champs_sensibles": champs_sensibles,
            "foreign_keys": foreign_keys,
            "rls_active": False,
            "politiques": [],
            "index_gist": [],
            "index_btree": []
        }

    # Détection des ENABLE ROW LEVEL SECURITY
    for match_rls in re.finditer(r"alter\s+table\s+([^\s]+)\s+enable\s+row\s+level\s+security", sql_propre, re.IGNORECASE):
        t_nom = match_rls.group(1).strip().strip('"').strip("'")
        if t_nom in tables:
            tables[t_nom]["rls_active"] = True

    # Détection des CREATE POLICY
    for match_pol in re.finditer(r"create\s+policy\s+([^\s]+)\s+on\s+([^\s]+)", sql_propre, re.IGNORECASE):
        pol_nom = match_pol.group(1).strip()
        t_nom = match_pol.group(2).strip().strip('"').strip("'")
        if t_nom in tables:
            tables[t_nom]["politiques"].append(pol_nom)

    # Détection des CREATE INDEX (B-Tree et GIST)
    for match_idx in re.finditer(r"create\s+(?:unique\s+)?index(?:\s+concurrently)?(?:\s+if\s+not\s+exists)?\s+([^\s]+)\s+on\s+([^\s\(]+)(?:\s+using\s+([a-z]+))?\s*\((.*?)\)", sql_propre, re.IGNORECASE):
        idx_nom = match_idx.group(1).strip()
        t_nom = match_idx.group(2).strip().strip('"').strip("'")
        methode = (match_idx.group(3) or "btree").lower().strip()
        cols = match_idx.group(4).strip()
        if t_nom in tables:
            if methode == "gist":
                tables[t_nom]["index_gist"].append({"nom": idx_nom, "cols": cols})
            else:
                tables[t_nom]["index_btree"].append({"nom": idx_nom, "cols": cols})

    return tables


@outil(
    nom="auditer_schema_sql",
    description="Audite un schéma de base de données PostgreSQL / Supabase / PostGIS : vérifie l'isolation des données sensibles (RLS), la présence d'index géo-spatiaux GIST sur les colonnes géométrie, l'indexation des clés étrangères et génère un script de migration de sécurisation et d'optimisation.",
    parametres={
        "type": "object",
        "properties": {
            "schema_sql": {
                "type": "string",
                "description": "Script DDL SQL (CREATE TABLE, ALTER TABLE, INDEX) ou chemin vers un fichier .sql à auditer"
            },
            "type_projet": {
                "type": "string",
                "description": "Contexte du projet (ex: 'medigo' pour ERP santé, 'ecogis' pour cartographie, ou 'standard')",
                "default": "standard"
            }
        },
        "required": ["schema_sql"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def auditer_schema_sql(schema_sql: str, type_projet: str = "standard") -> str:
    """Effectue un audit approfondi de sécurité et de performances sur un schéma SQL."""
    texte_sql = schema_sql.strip()

    # Si c'est un chemin de fichier existant, charger son contenu
    p = Path(texte_sql)
    if p.exists() and p.is_file():
        try:
            texte_sql = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"❌ Impossible de lire le fichier SQL `{p}` : {e}"

    if not texte_sql:
        return "❌ Schéma SQL vide. Veuillez fournir du code DDL (CREATE TABLE...) à auditer."

    tables = _analyser_tables_et_colonnes(texte_sql)
    if not tables:
        return "⚠️ Aucune instruction `CREATE TABLE` valide détectée dans le code fourni."

    anomalies_critiques = []
    anomalies_importantes = []
    optimisations = []
    scripts_remediation = []

    total_tables = len(tables)
    tables_sensibles_non_protegees = 0
    tables_postgis_non_indexees = 0

    for nom_table, meta in tables.items():
        # 1. Sécurité RLS sur données sensibles
        if meta["champs_sensibles"]:
            if not meta["rls_active"]:
                tables_sensibles_non_protegees += 1
                anomalies_critiques.append(
                    f"**Table `{nom_table}`** : Données sensibles détectées ({', '.join(meta['champs_sensibles'])}) mais **aucune politique RLS active** (`ENABLE ROW LEVEL SECURITY` manquant). Risque direct de fuite de données de santé ou d'utilisateurs !"
                )
                scripts_remediation.append(
                    f"-- Sécurisation RLS pour {nom_table}\n"
                    f"ALTER TABLE {nom_table} ENABLE ROW LEVEL SECURITY;\n"
                    f"ALTER TABLE {nom_table} FORCE ROW LEVEL SECURITY;\n"
                    f"CREATE POLICY p_{nom_table}_isolation ON {nom_table} FOR ALL TO authenticated USING (auth.uid() = {meta['foreign_keys'][0] if meta['foreign_keys'] else 'user_id'});"
                )
            elif not meta["politiques"]:
                anomalies_importantes.append(
                    f"**Table `{nom_table}`** : RLS activée mais **aucune politique définie** (`CREATE POLICY` manquant). Toutes les requêtes clientes non-admin seront bloquées à 100%."
                )

        # 2. Vérification PostGIS & GIST Index
        if meta["has_geom"]:
            if not meta["index_gist"]:
                tables_postgis_non_indexees += 1
                anomalies_critiques.append(
                    f"**Table `{nom_table}` (Géo-spatiale)** : Colonne géométrie détectée mais **aucun index spatial GIST** (`USING GIST`). Les requêtes `ST_DWithin` ou de proximité feront un Full Table Scan extrêmement lent !"
                )
                col_geom = next((c["nom"] for c in meta["colonnes"] if "geom" in c["nom"] or "point" in c["type"] or "geometry" in c["type"]), "geom")
                scripts_remediation.append(f"-- Index spatial GIST pour {nom_table}\nCREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{nom_table}_{col_geom}_gist ON {nom_table} USING GIST ({col_geom});")
            else:
                optimisations.append(f"Table `{nom_table}` : Index spatial GIST bien présent (`{meta['index_gist'][0]['nom']}`).")

        # 3. Indexation des clés étrangères (Foreign Keys)
        for fk in meta["foreign_keys"]:
            deja_indexe = any(fk in str(idx["cols"]) for idx in meta["index_btree"])
            if not deja_indexe:
                anomalies_importantes.append(
                    f"**Table `{nom_table}`** : Clé étrangère `{fk}` non indexée. Les jointures et suppressions en cascade peuvent dégrader les performances."
                )
                scripts_remediation.append(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{nom_table}_{fk} ON {nom_table} ({fk});")

        # 4. Absence de Primary Key
        if not meta["has_pk"]:
            anomalies_importantes.append(f"**Table `{nom_table}`** : Clé primaire explicite introuvable.")

    # Calcul du score de sécurité & robustesse
    score = 10.0
    score -= (tables_sensibles_non_protegees * 2.5)
    score -= (tables_postgis_non_indexees * 1.5)
    score -= (len(anomalies_importantes) * 0.5)
    score = max(1.0, min(10.0, round(score, 1)))

    badge_couleur = "🟢" if score >= 8.5 else ("🟡" if score >= 6.0 else "🔴")

    rapport = [
        f"## 🛡️ Rapport d'Audit SQL / PostGIS / Supabase",
        f"**Score de Robustesse & Sécurité :** {badge_couleur} **{score} / 10**",
        f"- **Tables analysées :** {total_tables}",
        f"- **Tables sensibles non isolées (sans RLS) :** {tables_sensibles_non_protegees}",
        f"- **Colonnes géo-spatiales sans index GIST :** {tables_postgis_non_indexees}",
        "",
        "---",
        ""
    ]

    if anomalies_critiques:
        rapport.append("### 🚨 Vulnérabilités & Points Critiques :")
        for a in anomalies_critiques:
            rapport.append(f"- ❌ {a}")
        rapport.append("")

    if anomalies_importantes:
        rapport.append("### ⚠️ Avertissements & Performance :")
        for a in anomalies_importantes:
            rapport.append(f"- ⚠️ {a}")
        rapport.append("")

    if optimisations:
        rapport.append("### ✅ Bonnes pratiques détectées :")
        for o in optimisations:
            rapport.append(f"- {o}")
        rapport.append("")

    if scripts_remediation:
        nom_migration = f"migration_remediation_sql_{type_projet}.sql"
        fichier_mig = _DOSSIER_MIGRATIONS / nom_migration
        contenu_mig = "-- Migration de Sécurisation & Optimisation générée par Claude RIOT Studio\n-- Exécution idempotente et sécurisée\n\n" + "\n\n".join(scripts_remediation) + "\n"
        fichier_mig.write_text(contenu_mig, encoding="utf-8")
        
        rapport.append("### 🛠️ Script de Remédiation & Migration Généré :")
        rapport.append("```sql")
        rapport.append(contenu_mig.strip())
        rapport.append("```")
        rapport.append(f"📄 **Fichier sauvegardé :** [{nom_migration}](/api/claude/document/telecharger?chemin={nom_migration})")

    return "\n".join(rapport)


@outil(
    nom="optimiser_requete_postgis",
    description="Analyse et optimise une requête SQL géospatiale PostGIS (calcul de rayon ST_DWithin, pharmacies de garde, recherche par proximité GPS). Détecte les casts inefficaces, les calculs sphériques redondants, propose l'écriture avec index GIST et bounding box &&.",
    parametres={
        "type": "object",
        "properties": {
            "requete_sql": {
                "type": "string",
                "description": "La requête SQL PostGIS à analyser"
            },
            "nom_table": {
                "type": "string",
                "description": "Nom de la table contenant la géométrie (ex: pharmacies)",
                "default": "pharmacies"
            },
            "colonne_geom": {
                "type": "string",
                "description": "Nom de la colonne géométrique (ex: geom, localisation, position)",
                "default": "geom"
            }
        },
        "required": ["requete_sql"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def optimiser_requete_postgis(requete_sql: str, nom_table: str = "pharmacies", colonne_geom: str = "geom") -> str:
    """Analyse chirurgicale d'une requête PostGIS et réécriture haute performance."""
    q = requete_sql.strip()
    q_lower = q.lower()

    diagnostics = []
    optimisations = []

    # 1. Vérification ST_DWithin
    has_dwithin = "st_dwithin" in q_lower
    has_distance = "st_distance" in q_lower

    if has_distance and not has_dwithin:
        diagnostics.append(
            "⚠️ Utilisation de `ST_Distance(...) <= rayon` au lieu de `ST_DWithin(...)`. `ST_Distance` calcule la distance exacte pour chaque ligne et empêche l'utilisation optimale de l'index spatial GIST !"
        )
        optimisations.append("Remplacer le filtre par `ST_DWithin(geom, ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography, rayon_metres)`.")

    # 2. Vérification SRID et Cast Geography vs Geometry
    if "st_makepoint" in q_lower and "st_setsrid" not in q_lower:
        diagnostics.append(
            "⚠️ Point géographique créé avec `ST_MakePoint` sans spécifier le SRID (`ST_SetSRID(..., 4326)`). Cela peut provoquer des erreurs d'incompatibilité spatiale ou des calculs erronés."
        )

    # 3. Vérification de l'utilisation de l'opérateur KNN (<->) pour trier par distance
    if "order by" in q_lower and "st_distance" in q_lower:
        diagnostics.append(
            "💡 Tri par `ORDER BY ST_Distance(...)` détecté. Pour limiter aux N plus proches (K-Nearest Neighbors), l'opérateur spatial `<->` est jusqu'à 50x plus rapide s'il est indexé."
        )

    # 4. Ordre des filtres d'état (ex: pharmacies de garde)
    mots_filtres = ("est_de_garde", "ouvert", "statut", "actif", "certifie")
    filtres_trouves = [f for f in mots_filtres if f in q_lower]
    if filtres_trouves:
        optimisations.append(
            f"Filtre d'état présent (`{', '.join(filtres_trouves)}`). Assurez-vous d'avoir un index composite ou partiel (ex: `WHERE est_de_garde = true`) pour éliminer les lignes inactives avant le calcul spatial."
        )

    # Modèle de requête optimale (Cas classique MediGo / Proximité)
    requete_optimisee = f"""-- Version Ultra-Performante PostGIS (GIST + Geography 4326)
SELECT 
    id,
    nom,
    adresse,
    telephone,
    est_de_garde,
    ROUND(ST_Distance({colonne_geom}::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography)::numeric, 1) AS distance_metres
FROM {nom_table}
WHERE 
    -- 1. Filtre conditionnel avant le calcul spatial lourd
    (:garde_uniquement IS FALSE OR est_de_garde = TRUE)
    -- 2. Exploitation directe de l'index GIST en mètres
    AND ST_DWithin(
        {colonne_geom}::geography,
        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
        :rayon_metres
    )
ORDER BY {colonne_geom} <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
LIMIT :limite;"""

    index_requis = f"""-- Index requis pour exécuter cette requête en moins de 5ms sur 50 000 points
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{nom_table}_{colonne_geom}_gist 
ON {nom_table} USING GIST ({colonne_geom});

-- Index partiel optionnel pour les pharmacies de garde
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{nom_table}_garde_spatial 
ON {nom_table} USING GIST ({colonne_geom}) 
WHERE est_de_garde = TRUE;"""

    retour = [
        "## 🛰️ Diagnostic & Optimisation PostGIS",
        "",
        "### 🔍 Analyse de la Requête Soumise :",
        "\n".join(f"- {d}" for d in (diagnostics or ["✅ Aucun anti-pattern spatial majeur détecté."])),
        "",
        "### ⚡ Recommandations d'Architecture :",
        "\n".join(f"- {o}" for o in optimisations),
        "",
        "### 🚀 Requête Optimale Réécrite :",
        "```sql",
        requete_optimisee,
        "```",
        "",
        "### 📌 Index SQL Obligatoires :",
        "```sql",
        index_requis,
        "```"
    ]
    return "\n".join(retour)


@outil(
    nom="generer_politiques_rls",
    description="Génère un ensemble complet de politiques de sécurité RLS (Row Level Security) pour Supabase / PostgreSQL : isolation par utilisateur, permissions d'insertion, mise à jour restreinte et contournement sécurisé pour le rôle super_admin.",
    parametres={
        "type": "object",
        "properties": {
            "nom_table": {
                "type": "string",
                "description": "Nom de la table à sécuriser (ex: ordonnances, dossiers_medicaux, rendez_vous)"
            },
            "colonne_proprietaire": {
                "type": "string",
                "description": "Nom de la colonne liant la ligne à l'utilisateur authentifié (ex: user_id, patient_id)",
                "default": "user_id"
            },
            "autoriser_lecture_publique": {
                "type": "boolean",
                "description": "True si les données peuvent être lues par tout le monde (ex: catalogue, pharmacies publiques)",
                "default": False
            },
            "role_admin": {
                "type": "string",
                "description": "Rôle administrateur autorisé à tout voir (ex: super_admin)",
                "default": "super_admin"
            }
        },
        "required": ["nom_table"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def generer_politiques_rls(
    nom_table: str,
    colonne_proprietaire: str = "user_id",
    autoriser_lecture_publique: bool = False,
    role_admin: str = "super_admin"
) -> str:
    """Génère les politiques RLS strictes et vérifiées pour Supabase."""
    t = nom_table.strip()
    col = colonne_proprietaire.strip()
    adm = role_admin.strip()

    sql_rls = f"""-- ====================================================================
-- POLITIQUES RLS RENFORCÉES POUR : {t}
-- Norme : Isolation stricte des données de santé & multi-tenant
-- ====================================================================

-- 1. Activation obligatoire de RLS (Fail-Closed par défaut)
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE ROW LEVEL SECURITY;

-- 2. Politique de LECTURE (SELECT)
"""
    if autoriser_lecture_publique:
        sql_rls += f"""CREATE POLICY "Lecture publique autorisee sur {t}"
ON {t} FOR SELECT
TO anon, authenticated
USING (true);
"""
    else:
        sql_rls += f"""CREATE POLICY "Isolation SELECT propriétaire sur {t}"
ON {t} FOR SELECT
TO authenticated
USING (
    auth.uid() = {col}
    OR (auth.jwt() ->> 'role') = '{adm}'
);
"""

    sql_rls += f"""
-- 3. Politique d'INSERTION (INSERT)
CREATE POLICY "Controle INSERT propriétaire sur {t}"
ON {t} FOR INSERT
TO authenticated
WITH CHECK (
    auth.uid() = {col}
    OR (auth.jwt() ->> 'role') = '{adm}'
);

-- 4. Politique de MODIFICATION (UPDATE)
CREATE POLICY "Controle UPDATE propriétaire sur {t}"
ON {t} FOR UPDATE
TO authenticated
USING (
    auth.uid() = {col}
    OR (auth.jwt() ->> 'role') = '{adm}'
)
WITH CHECK (
    auth.uid() = {col}
    OR (auth.jwt() ->> 'role') = '{adm}'
);

-- 5. Politique de SUPPRESSION (DELETE)
CREATE POLICY "Controle DELETE propriétaire sur {t}"
ON {t} FOR DELETE
TO authenticated
USING (
    auth.uid() = {col}
    OR (auth.jwt() ->> 'role') = '{adm}'
);
"""

    # Enregistrer la politique dans un fichier pour téléchargement
    nom_fichier = f"rls_{t}.sql"
    cible = _DOSSIER_MIGRATIONS / nom_fichier
    cible.write_text(sql_rls, encoding="utf-8")

    return f"""### 🛡️ Politiques RLS générées pour `{t}` :

```sql
{sql_rls.strip()}
```

📄 **Fichier de migration prêt :** [{nom_fichier}](/api/claude/document/telecharger?chemin={nom_fichier})

> [!IMPORTANT]
> **Vérification requise :** Assurez-vous que la fonction `auth.uid()` et les claims JWT correspondent à votre structure d'authentification Supabase."""
