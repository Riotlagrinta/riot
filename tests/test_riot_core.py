import os
import pathlib
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_opaque_mode_hides_model_and_protects_source(monkeypatch, tmp_path):
    from core import llm
    from core.cli import _SESSION_CTX
    from tools import code as code_tools

    monkeypatch.delenv("RIOT_ADMIN", raising=False)
    monkeypatch.setattr(llm, "reglage", lambda k, d=None: False if k == "admin_mode" else d)

    pub = llm.identite_publique()
    assert pub["opaque"] is True
    assert pub["admin"] is False
    assert pub["nom"] == "RIOT Engine"
    assert pub["modele"].startswith("RIOT ")

    # Protection du code source interne de RIOT en mode utilisateur
    with pytest.raises(PermissionError):
        code_tools._resoudre_chemin(str(ROOT / "core" / "llm.py"))

    # Isolation vers le projet actif selectionne dans _SESSION_CTX
    prev = _SESSION_CTX.get("projet_actif")
    try:
        _SESSION_CTX["projet_actif"] = tmp_path
        cible = code_tools._resoudre_chemin("app/main.py")
        assert cible == (tmp_path / "app" / "main.py").resolve()
    finally:
        _SESSION_CTX["projet_actif"] = prev


def test_custom_openai_provider_url_normalization(monkeypatch):
    from core.llm import CustomOpenAIProvider, _normaliser_url_chat

    assert _normaliser_url_chat("http://localhost:3001/v1") == "http://localhost:3001/v1/chat/completions"
    assert _normaliser_url_chat("https://api.example.com") == "https://api.example.com/v1/chat/completions"

    monkeypatch.setenv("CUSTOM_BASE_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("CUSTOM_API_KEY", "freellmapi-test")
    prov = CustomOpenAIProvider(modele="auto")
    assert prov.disponible() is True
    assert prov.api_url == "http://localhost:3001/v1/chat/completions"


def test_ide_security_guards_and_patch_lifecycle(monkeypatch, tmp_path):
    from core import ide, serveur
    from core.cli import _SESSION_CTX

    monkeypatch.setenv("RIOT_ADMIN", "1")
    prev = _SESSION_CTX.get("projet_actif")
    _SESSION_CTX["projet_actif"] = tmp_path
    try:
        client = TestClient(serveur.app(), base_url="http://127.0.0.1:8790", client=("127.0.0.1", 50000))

        # Routes critiques en local -> 200
        for p in ("/logo.svg", "/theme.css", "/theme.js", "/api/version", "/ide", "/api/ide/etat", "/api/ide/chemins", "/api/ide/naviguer-dossiers"):
            assert client.get(p).status_code == 200

        # Tunnel simulé -> 403
        assert client.get("/ide", headers={"x-forwarded-for": "8.8.8.8"}).status_code == 403
        assert client.post("/api/update", headers={"x-forwarded-for": "8.8.8.8"}).status_code == 403

        # Traversal hors workspace -> 403/404
        assert client.get("/api/ide/fichier?chemin=../../Windows/win.ini").status_code in (403, 404)

        # Cycle complet patch accept -> revert
        staged = ide._simuler_et_stager_patch(tmp_path, "ecrire_code", {"fichier": "demo.py", "contenu": "x = 1\n"})
        assert staged["ok"] is True
        pid = staged["patch"]["id"]
        assert client.post(f"/api/ide/patch/{pid}/accept").status_code == 200
        assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "x = 1\n"
        assert client.post(f"/api/ide/patch/{pid}/revert").status_code == 200
        assert not (tmp_path / "demo.py").exists()
    finally:
        _SESSION_CTX["projet_actif"] = prev


def test_updater_and_proxy_health(monkeypatch):
    from core import updater
    from proxy.server import _routes_pour_profil, app as proxy_app

    up = updater.etat_mise_a_jour(forcer=False, sans_reseau=True)
    assert up["ok"] is True and up["version_locale"]

    monkeypatch.setenv("GROQ_API_KEY", "gsk_dummy")
    routes = _routes_pour_profil("riot-fast")
    assert len(routes) >= 1 and "api.groq.com" in routes[0]["url"]

    pc = TestClient(proxy_app)
    r = pc.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_spiral_icons_and_creator_monitoring(monkeypatch, tmp_path):
    from core import llm, serveur
    from core.telemetry import TelemetryStore, masquer_secrets

    # 1. Redaction automatique des secrets avant stockage
    s = masquer_secrets("GROQ_API_KEY=gsk_1234567890abcdef12345 et sk-proj-abcdef1234567890abcd")
    assert "gsk_123456" not in s and "sk-proj-abcdef" not in s

    # 2. Enregistrement TelemetryStore + metriques + recherche
    store = TelemetryStore(db_path=tmp_path / "mon.db")
    store.enregistrer(
        source="proxy", client_id="c1", profil="riot-auto",
        provider_reel="Mistral", modele_reel="codestral-latest",
        ok=True, status_code=200, latence_ms=145, tokens_in=20, tokens_out=40,
        prompt="Cree une API FastAPI", reponse="Voici ton endpoint FastAPI.",
    )
    store.enregistrer(
        source="proxy", client_id="c2", profil="riot-fast",
        provider_reel="Groq", modele_reel="llama-3.3",
        ok=False, status_code=429, latence_ms=80,
        prompt="Test erreur quota", erreur="HTTP 429 rate limit",
    )
    met = store.metriques(heures=24)
    assert met["total"] == 2 and met["erreurs"] == 1 and met["taux_succes_pct"] == 50.0
    errs = store.lister_logs(only_errors=True)
    assert len(errs) == 1 and errs[0]["status_code"] == 429

    # 3. Absence de route /monitor dans le package client + icones PWA Spiral
    client = TestClient(serveur.app(), base_url="http://127.0.0.1:8790", client=("127.0.0.1", 50000))
    for asset in ("/logo.svg", "/icon-192.png", "/icon-512.png", "/claude/manifest.json", "/mobile/manifest.json"):
        assert client.get(asset).status_code == 200
    assert client.get("/monitor").status_code == 404

    # 4. Garde /admin + endpoints publics /releases /status/public sur proxy/server.py
    from proxy import server as proxy_srv
    monkeypatch.setattr(proxy_srv, "_STORE", store)
    monkeypatch.setenv("RIOT_ADMIN_TOKEN", "secret_creator_tok")
    pc = TestClient(proxy_srv.app)
    assert pc.get("/status/public").status_code == 200
    assert "prompt" not in pc.get("/status/public").text
    assert pc.get("/releases").status_code == 200
    assert pc.get("/releases/latest").json()["version"] == "0.3.1"
    assert pc.get("/admin/metrics").status_code == 401
    assert pc.get("/admin/metrics", headers={"X-Admin-Token": "secret_creator_tok"}).status_code == 200
    assert pc.get("/admin/logs", headers={"X-Admin-Token": "secret_creator_tok"}).status_code == 200
    r_rel = pc.post(
        "/admin/releases",
        headers={"X-Admin-Token": "secret_creator_tok"},
        json={"version": "0.3.2", "titre": "Test Release", "notes": "- Note 1"},
    )
    assert r_rel.status_code == 200 and pc.get("/releases/latest").json()["version"] == "0.3.2"


def test_proxy_chat_completions_usage_and_opaque_model(monkeypatch, tmp_path):
    from core.telemetry import TelemetryStore
    from proxy import server as proxy_srv

    store = TelemetryStore(db_path=tmp_path / "chat.db")
    monkeypatch.setattr(proxy_srv, "_STORE", store)
    monkeypatch.delenv("RIOT_IDENTITY_DATABASE_URL", raising=False)
    monkeypatch.setenv("RIOT_PROXY_TOKEN", "proxy_tok_test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_dummy")

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "cmp_1",
                "model": "llama-3.3-70b-versatile",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            }

    monkeypatch.setattr(proxy_srv.requests, "post", lambda *a, **kw: _FakeResp())
    pc = TestClient(proxy_srv.app)
    r = pc.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer proxy_tok_test"},
        json={"model": "riot-fast", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "riot-engine"
    logs = store.lister_logs(limit=1)
    assert len(logs) == 1 and logs[0]["tokens_in"] == 11 and logs[0]["tokens_out"] == 4


def test_persistent_memory_user_dir_ide_injection_cloud_sync_and_auto_extract(monkeypatch, tmp_path):
    from core import ide, memoire
    from proxy import server as proxy_srv

    # 1. Emplacement utilisateur persistant (~/.riot/riot_memory.db) hors dossier du code
    assert memoire._DEFAULT_USER_DB_PATH == pathlib.Path.home() / ".riot" / "riot_memory.db"

    prev_db = memoire.DB_PATH
    try:
        # 2. Base PC A isolée + masquage automatique des secrets
        db_pc_a = tmp_path / "pc_a" / "riot_memory.db"
        monkeypatch.setenv("RIOT_MEMORY_SYNC", "0")
        memoire.reinitialiser_connexion(db_pc_a)

        memoire.memoriser_entite("preferences", "stack_pref", "Toujours utiliser FastAPI avec gsk_1234567890abcdef12345", sync_auto=False)
        memoire.ajouter_regle_dev("tests_obligatoires", "Lancer pytest apres chaque edit")
        memoire.ajouter_recette_code(
            titre="Erreur CORS FastAPI",
            langage="python",
            probleme="Requete bloquee CORS depuis localhost:5173",
            cause="CORSMiddleware absent",
            solution="Ajouter CORSMiddleware avec allow_origins explicite",
            tags="fastapi,cors",
            sync_auto=False,
        )

        prompt_ide = ide._construire_prompt_ide("code", tmp_path, None, message="probleme CORS FastAPI")
        assert "Toujours utiliser FastAPI" in prompt_ide
        assert "gsk_123456" not in prompt_ide
        assert "Lancer pytest apres chaque edit" in prompt_ide
        assert "Erreur CORS FastAPI" in prompt_ide

        noms_outils_ide = {s["name"] for s in ide._extraire_outils_ide(lecture_seule=False)}
        assert {"remember", "recall", "forget", "apprendre_regle", "lister_regles", "enregistrer_recette_dev", "chercher_recette_dev"} <= noms_outils_ide

        # 3. Auto-extraction silencieuse type Hermes (filtre trivial + extraction JSON)
        res_trivial = memoire.extraire_et_memoriser_depuis_echange("salut", "bonjour !")
        assert res_trivial == {"entities": 0, "recipes": 0}

        class _FakeMsg:
            def __init__(self, text):
                self.type = "text"
                self.text = text

        class _FakeRep:
            def __init__(self, text):
                self.content = [_FakeMsg(text)]

        class _FakeLLM:
            def disponible(self):
                return True

            def repondre(self, sys_p, msgs, schemas):
                return _FakeRep(
                    '```json\n{"entities": [{"categorie": "projects", "cle": "medigo", '
                    '"contenu": "ERP pharmacie Next.js + PostGIS"}], '
                    '"recipes": [{"titre": "Fix SQLite WAL lock", "langage": "python", '
                    '"probleme": "database is locked", "cause": "threads concurrents", '
                    '"solution": "Activer PRAGMA journal_mode = WAL et RLock", "tags": "sqlite"}]}\n```'
                )

        res_ext = memoire.extraire_et_memoriser_depuis_echange(
            "Je travaille sur mon projet medigo et j'ai corrige le bug database is locked.",
            "Le verrou SQLite WAL est corrige avec PRAGMA journal_mode = WAL et un RLock.",
            surface="ide",
            forcer=True,
            provider=_FakeLLM(),
        )
        assert res_ext == {"entities": 1, "recipes": 1}
        assert memoire.charger()["projects"]["medigo"] == "ERP pharmacie Next.js + PostGIS"

        # 4. Synchro Cloud hybride (PC A -> Proxy MemoryCloudStore -> PC B + propagation tombstone)
        mem_cloud = proxy_srv.MemoryCloudStore(db_path=tmp_path / "cloud_mem.db", pg_url="")
        monkeypatch.setattr(proxy_srv, "_MEMORY_STORE", mem_cloud)
        monkeypatch.delenv("RIOT_IDENTITY_DATABASE_URL", raising=False)
        monkeypatch.setenv("RIOT_PROXY_TOKEN", "tok_mem_test")
        monkeypatch.setenv("RIOT_MEMORY_SYNC", "1")
        monkeypatch.setenv("RIOT_GATEWAY_URL", "http://testserver/v1")
        monkeypatch.setenv("RIOT_GATEWAY_TOKEN", "tok_mem_test")

        pc = TestClient(proxy_srv.app)
        locaux_a = memoire.collecter_items_locaux()
        r_sync_a = pc.post(
            "/v1/memory/sync",
            headers={"Authorization": "Bearer tok_mem_test"},
            json={"items": locaux_a, "since": ""},
        )
        assert r_sync_a.status_code == 200, r_sync_a.text
        assert len(r_sync_a.json()["items"]) >= 4

        # PC B (nouvelle machine vierge) récupère toute la mémoire
        db_pc_b = tmp_path / "pc_b" / "riot_memory.db"
        memoire.reinitialiser_connexion(db_pc_b)
        r_pull_b = pc.get("/v1/memory", headers={"Authorization": "Bearer tok_mem_test"})
        assert r_pull_b.status_code == 200
        appl_b = memoire.appliquer_items_cloud(r_pull_b.json()["items"])
        assert appl_b["appliques"] >= 4
        assert memoire.charger()["projects"]["medigo"] == "ERP pharmacie Next.js + PostGIS"

        # Suppression sur PC A -> tombstone -> propagée vers PC B
        memoire.reinitialiser_connexion(db_pc_a)
        assert memoire.supprimer_entite("projects", "medigo", sync_auto=False) is True
        r_sync_del = pc.post(
            "/v1/memory/sync",
            headers={"Authorization": "Bearer tok_mem_test"},
            json={"items": memoire.collecter_items_locaux(), "since": ""},
        )
        assert r_sync_del.status_code == 200

        memoire.reinitialiser_connexion(db_pc_b)
        r_pull_b2 = pc.get(
            "/v1/memory?since=2000-01-01T00:00:00Z",
            headers={"Authorization": "Bearer tok_mem_test"},
        )
        assert r_pull_b2.status_code == 200
        appl_b2 = memoire.appliquer_items_cloud(r_pull_b2.json()["items"])
        assert appl_b2["supprimes"] >= 1
        assert "medigo" not in memoire.charger()["projects"]
    finally:
        memoire.reinitialiser_connexion(prev_db)



