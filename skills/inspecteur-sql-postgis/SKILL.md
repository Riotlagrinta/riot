---
name: inspecteur-sql-postgis
description: |
  Audit de sécurité, optimisation et inspection des bases de données PostgreSQL, PostGIS et Supabase RLS.
  Utilisez cette compétence dès que l'utilisateur souhaite auditer un schéma SQL, vérifier l'isolation des données sensibles de santé ou d'utilisateurs,
  optimiser des requêtes de proximité géo-spatiales (ST_DWithin, index GIST, pharmacies de garde),
  ou générer des politiques de sécurité Row Level Security (RLS) et des migrations non destructives.
license: Apache-2.0
metadata:
  version: v1
  publisher: riot-studio
---

# Compétence Inspecteur & Optimiseur SQL / PostGIS / Supabase RLS

Cette compétence confère à RIOT Studio une expertise chirurgicale dans la gestion des bases de données relationnelles PostgreSQL, l'extension cartographique PostGIS et les politiques de sécurité Supabase Row Level Security (RLS).

Elle s'applique particulièrement aux projets à forte composante géo-spatiale ou de santé (ex: **MediGo**, **Eco-Atlas**, **TogoDrive**).

---

## 🎯 Capacités Clés

### 1. 🛡️ Audit de Schéma SQL & Détection de Failles (`auditer_schema_sql`)
- **Isolation RLS (Health Data & PII) :** Détecte toute table contenant des données de santé (ordonnances, patients, consultations, antécédents) ou utilisateurs dépourvue de `ENABLE ROW LEVEL SECURITY`.
- **Index Spatiaux GIST :** Repère les colonnes géométrie (`geometry(Point, 4326)`, `geography`) sans index `USING GIST`, prévenant ainsi les Full Table Scans coûteux.
- **Clés Étrangères non Indexées :** Identifie les champs `_id` orphelins d'index pour accélérer les jointures.
- **Calcul de Score de Sécurité :** Rendu d'une note sur 10 avec classification des risques (`CRITIQUE`, `IMPORTANT`, `OPTIMISATION`).
- **Génération Automatique de Remédiation :** Produit un script SQL de migration complet, idempotent (`IF NOT EXISTS`) et non bloquant (`CONCURRENTLY`).

### 2. 🛰️ Optimisation de Requêtes PostGIS (`optimiser_requete_postgis`)
- **Proximité GPS & Rayon :** Remplace les anti-patterns (`ST_Distance <= rayon`) par `ST_DWithin` exploitant les index en mètres sur le type `geography`.
- **Tri K-Nearest Neighbors (KNN) :** Utilisation de l'opérateur spatial `<->` pour un tri de distance instantané.
- **Filtres d'État Hybrides :** Pré-filtrage conditionnel (ex: `est_de_garde = true`) pour alléger les calculs sphériques.
- **Index Partiels Spécialisés :** Définition d'index `WHERE est_de_garde = TRUE` pour des temps de réponse inférieurs à 5 ms.

### 3. 🔐 Générateur de Politiques Supabase RLS (`generer_politiques_rls`)
- Activation stricte `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` et `FORCE ROW LEVEL SECURITY;`.
- Politiques complètes et distinctes pour `SELECT`, `INSERT`, `UPDATE` et `DELETE`.
- Contrôle de propriété basé sur `auth.uid() = user_id` avec bypass sécurisé pour les administrateurs via les claims JWT (`(auth.jwt() ->> 'role') = 'super_admin'`).

---

## ⚠️ Règle de Sécurité Absolue (Non-Destruction)
L'outil agit comme un **conseiller d'audit et générateur de scripts**. Il n'exécute **JAMAIS** de commandes destructrices (`DROP TABLE`, `TRUNCATE`, `DROP DATABASE`) sans accord formel de l'utilisateur.

---

## 🛠️ Utilisation des Outils

Dans [`tools/sql_inspector.py`](file:///e:/PROJETS/Kéranos/keranos-assistant-vocal-main-1/tools/sql_inspector.py) :
- `auditer_schema_sql(schema_sql="CREATE TABLE ...", type_projet="medigo")`
- `optimiser_requete_postgis(requete_sql="SELECT ...", nom_table="pharmacies", colonne_geom="geom")`
- `generer_politiques_rls(nom_table="ordonnances", colonne_proprietaire="patient_id", role_admin="super_admin")`
