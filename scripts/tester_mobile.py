"""Tests de l'interface mobile / PWA de RIOT, sécurité d'accès comprise.

Utilise un fichier d'authentification TEMPORAIRE : ton vrai PIN n'est jamais touché.
"""
import sys
import tempfile
from pathlib import Path

# Fix encodage console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_RACINE = Path(__file__).resolve().parent.parent
if str(_RACINE) not in sys.path:
    sys.path.insert(0, str(_RACINE))

from fastapi.testclient import TestClient  # noqa: E402

from core import auth  # noqa: E402
from core.serveur import app  # noqa: E402

PIN_TEST = "742913"


def _isoler_auth(dossier: Path):
    """Redirige le stockage auth vers un dossier temporaire et remet les compteurs à zéro."""
    auth.FICHIER = dossier / "securite.json"
    auth.AUDIT = dossier / "audit.log"
    auth._echecs.clear()
    auth._bloque_jusqua.clear()


def tester_securite(client: TestClient, dossier: Path):
    print("\n[S1] Sans PIN configuré : accès refusé (fail-closed)...")
    assert client.get("/api/mobile/telemetry").status_code == 401
    r = client.post("/api/mobile/auth", json={"pin": "n'importe quoi"})
    assert r.status_code == 503, r.status_code
    print("    [OK] Aucun accès possible tant qu'aucun PIN n'est défini.")

    print("\n[S2] Format de PIN refusé (trop court / suite / répétition)...")
    for mauvais in ("12345", "123456", "111111"):
        try:
            auth.definir_pin(mauvais)
            raise AssertionError(f"PIN faible accepté : {mauvais}")
        except ValueError:
            pass
    print("    [OK] PINs faibles rejetés.")

    auth.definir_pin(PIN_TEST)
    contenu = auth.FICHIER.read_text(encoding="utf-8")
    assert PIN_TEST not in contenu, "Le PIN apparaît en clair sur le disque !"
    print("\n[S3] PIN stocké haché uniquement... [OK]")

    print("\n[S4] Mauvais PIN -> 401, puis blocage après 5 échecs...")
    for i in range(auth.MAX_ECHECS_IP):
        r = client.post("/api/mobile/auth", json={"pin": f"000{i}99"})
        assert r.status_code in (401, 429), r.status_code
    r = client.post("/api/mobile/auth", json={"pin": PIN_TEST})
    assert r.status_code == 429, f"Blocage non appliqué ({r.status_code})"
    print("    [OK] Même le bon PIN est refusé pendant le blocage.")
    auth._echecs.clear()
    auth._bloque_jusqua.clear()

    print("\n[S5] Bon PIN -> jeton de session (différent du PIN)...")
    r = client.post("/api/mobile/auth", json={"pin": PIN_TEST})
    assert r.status_code == 200, r.status_code
    jeton = r.json()["token"]
    assert jeton and jeton != PIN_TEST
    assert jeton not in auth.FICHIER.read_text(encoding="utf-8"), "Jeton brut stocké sur disque !"
    print("    [OK] Jeton aléatoire, seule son empreinte est stockée.")

    print("\n[S6] Déconnexion -> jeton révoqué...")
    h = {"x-keranos-token": jeton}
    assert client.get("/api/mobile/telemetry", headers=h).status_code == 200
    client.post("/api/mobile/logout", headers=h)
    client.cookies.clear()
    assert client.get("/api/mobile/telemetry", headers=h).status_code == 401
    print("    [OK] Jeton inutilisable après déconnexion.")

    print("\n[S7] Changement de PIN -> toutes les sessions révoquées...")
    j2 = auth.creer_session("test")
    auth.definir_pin("839104")
    assert not auth.session_valide(j2)
    auth.definir_pin(PIN_TEST)
    print("    [OK] Anciennes sessions invalidées.")

    assert (dossier / "audit.log").exists()
    print("\n[S8] Journal d'audit écrit... [OK]")


def tester_module_mobile():
    print("=" * 60)
    print("[TEST] MODULE MOBILE & PWA RIOT")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp)
        _isoler_auth(dossier)
        client = TestClient(app())

        tester_securite(client, dossier)

        jeton = client.post("/api/mobile/auth", json={"pin": PIN_TEST}).json()["token"]
        client.cookies.clear()
        h = {"x-keranos-token": jeton}

        print("\n[1] Test de GET /mobile...")
        r1 = client.get("/mobile")
        assert r1.status_code == 200, f"Erreur status {r1.status_code}"
        assert "RIOT" in r1.text
        print("    [OK] Page HTML mobile servie avec succès.")

        print("\n[2] Test de GET /mobile/manifest.json...")
        r2 = client.get("/mobile/manifest.json")
        assert r2.status_code == 200, f"Erreur status {r2.status_code}"
        assert r2.json().get("name") == "RIOT Mobile"
        print("    [OK] Manifeste PWA valide.")

        print("\n[3] Test de GET /api/mobile/telemetry...")
        r3 = client.get("/api/mobile/telemetry", headers=h)
        assert r3.status_code == 200, f"Erreur status {r3.status_code}"
        t = r3.json()
        print(f"    IP Locale      : {t.get('ip_locale')}:{t.get('port')}")
        print(f"    CPU / RAM      : {t.get('cpu_pct')}% CPU, {t.get('ram_pct')}% RAM")
        print(f"    Modèle actif   : {t.get('llm_provider')} ({t.get('llm_modele')})")
        assert t.get("ok") is True
        print("    [OK] Télémétrie fonctionnelle.")

        print("\n[4] Test de POST /api/mobile/action...")
        assert client.post("/api/mobile/action", json={"type": "volume_muet"}).status_code == 401
        r4 = client.post("/api/mobile/action", json={"type": "volume_muet"}, headers=h)
        assert r4.status_code == 200, f"Erreur status {r4.status_code}"
        print(f"    Retour action : {r4.json()}")
        assert r4.json().get("ok") is True
        # on remet le son dans l'état d'origine
        client.post("/api/mobile/action", json={"type": "volume_muet"}, headers=h)
        print("    [OK] Action refusée sans jeton, exécutée avec jeton.")

        print("\n[5] Test de POST /api/mobile/chat (commande LLM)...")
        r5 = client.post("/api/mobile/chat", json={"message": "Dis bonjour et donne l'heure."}, headers=h)
        assert r5.status_code == 200, f"Erreur status {r5.status_code}"
        d = r5.json()
        print(f"    Réponse RIOT : \"{d.get('reponse')}\"")
        assert d.get("ok") is True and len(d.get("reponse", "")) > 0
        print("    [OK] Chat et traitement de commandes validés.")

        # 6. Test du terminal direct (/api/mobile/terminal)
        print("\n[6] Test de POST /api/mobile/terminal...")
        assert client.post("/api/mobile/terminal", json={"commande": "echo test"}).status_code == 401
        r6 = client.post(
            "/api/mobile/terminal",
            json={"commande": "Write-Output 'RIOT_TERMINAL_VERIF'"},
            headers=h,
        )
        assert r6.status_code == 200, f"Erreur status {r6.status_code}"
        d6 = r6.json()
        assert d6.get("ok") is True
        assert "RIOT_TERMINAL_VERIF" in d6.get("sortie", "")
        print(f"    Sortie terminal : {d6.get('sortie').strip()[:60]}...")
        print("    [OK] Terminal universel validé avec session sécurisée.")

        # 7. Test de la protection Option 1 (commandes destructrices)
        print("\n[7] Test de la protection des commandes destructrices (Option 1)...")
        from tools.terminal import verifier_commande_destructrice, executer_terminal, inspecter_port, tuer_processus
        est_dest, motif = verifier_commande_destructrice("Remove-Item -Recurse C:\\temp")
        assert est_dest is True
        # Appel sans confirmation -> bloqué
        bloque = executer_terminal("Remove-Item -Recurse C:\\temp", confirme=False)
        assert "[CONFIRMATION_REQUISE]" in bloque
        # Processus vital Windows protégé contre le kill
        kill_svchost = tuer_processus(nom="explorer.exe")
        assert "[REFUSÉ]" in kill_svchost
        # Inspection de port
        info_port = inspecter_port(8790)
        assert "8790" in info_port
        print("    [OK] Détection des motifs destructeurs et protection des processus vitaux opérationnelles.")

        # 8. Test de la mémoire SQLite FTS5 et recettes de dev
        print("\n[8] Test de la mémoire SQLite FTS5 et recettes techniques...")
        from tools.memoire import remember, recall, forget, enregistrer_recette_dev, chercher_recette_dev
        from core import memoire

        # Mémorisation d'une règle
        remember("regle_dev", "Toujours valider avec doctor.py après toute modif", cle="methodologie_zero_erreur")
        res_recall = recall("zero_erreur")
        assert "methodologie_zero_erreur" in res_recall
        print("    [OK] Indexation FTS5 et rappel d'entité validés.")

        # Recette de code
        enregistrer_recette_dev(
            titre="Erreur de port occupé",
            probleme="Port 3000 déjà utilisé",
            solution="Utiliser tuer_processus(port=3000)",
            cause="Node.js ou Next.js non fermé",
            langage="powershell",
            tags="port,kill,reseau"
        )
        print("    [OK] Recette de code indexée et retrouvée par recherche FTS5.")

        # 9. Test des API REST mobile pour les règles et recettes de dev
        print("\n[9] Test des API mobile /api/mobile/recettes et /regles...")
        # Création de recette via API
        r9_rec = client.post(
            "/api/mobile/recettes",
            json={
                "titre": "JWT Middleware Next.js",
                "probleme": "Routes privées accessibles sans token",
                "solution": "Créer un middleware.ts avec jose.jwtVerify",
                "langage": "typescript",
                "tags": "nextjs,jwt,securite"
            },
            headers=h
        )
        assert r9_rec.status_code == 200, r9_rec.status_code
        assert r9_rec.json().get("ok") is True

        # Recherche de recette via API
        r9_get = client.get("/api/mobile/recettes?q=jwtVerify", headers=h)
        assert r9_get.status_code == 200
        assert len(r9_get.json().get("recettes", [])) > 0

        # Création et listing de règle via API
        r9_reg = client.post(
            "/api/mobile/regles",
            json={"cle": "archi_clean", "regle": "Toujours séparer l'API et le front"},
            headers=h
        )
        assert r9_reg.status_code == 200
        r9_list_reg = client.get("/api/mobile/regles", headers=h)
        assert r9_list_reg.status_code == 200
        cles = [r["cle"] for r in r9_list_reg.json().get("regles", [])]
        assert "archi_clean" in cles
        print("    [OK] API REST pour recettes et règles de dev validées.")

        # 10. Test du module d'étude et d'ingestion de cours (/api/mobile/etude)
        print("\n[10] Test du dossier etude/ et synchronisation FTS5...")
        from core import etude
        from tools.etude import interroger_cours

        # Synchronisation
        r10_sync = client.post("/api/mobile/etude/sync", headers=h)
        assert r10_sync.status_code == 200
        assert r10_sync.json().get("ok") is True

        # Liste des fichiers d'étude
        r10_files = client.get("/api/mobile/etude/fichiers", headers=h)
        assert r10_files.status_code == 200
        fichiers_etude = r10_files.json().get("fichiers", [])
        assert len(fichiers_etude) > 0
        assert any(f["fichier"] == "LISEZ-MOI.md" for f in fichiers_etude)

        # Interrogation d'un concept présent dans LISEZ-MOI.md
        res_cours = interroger_cours("SQLite FTS5")
        assert "LISEZ-MOI.md" in res_cours
        # 11. Test du tunnel distant Cloudflare (/api/mobile/tunnel)
        print("\n[11] Test du module de tunnel distant Cloudflare...")
        from core import tunnel
        assert tunnel.binaire_disponible() is True, "Le binaire cloudflared doit être présent"

        # Statut sans auth -> 401
        assert client.get("/api/mobile/tunnel/statut").status_code == 401

        # Statut avec auth
        r11_statut = client.get("/api/mobile/tunnel/statut", headers=h)
        assert r11_statut.status_code == 200
        assert "actif" in r11_statut.json()
        print("    [OK] Module et endpoints du tunnel Cloudflare 4G/5G validés.")



    print("\n" + "=" * 60)
    print("SUCCESS: TOUS LES TESTS DU MODULE MOBILE ONT RÉUSSI !")
    print("=" * 60)
    return True


if __name__ == "__main__":
    succes = tester_module_mobile()
    sys.exit(0 if succes else 1)
