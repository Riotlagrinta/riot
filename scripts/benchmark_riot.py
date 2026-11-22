"""Benchmark objectif de RIOT Engine, IDE et profils LLM actifs.

Mesure les performances locales reelles (demarrage, memoire FTS5, patcher_code,
routes IDE/Studio) ainsi que la latence et la precision sur micro-taches des
profils/modeles configures sur la machine (sans inventer de score).
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def bench_moteur_local() -> dict:
    res = {}

    t0 = time.perf_counter()
    from core import llm as core_llm, memoire, model_router, registre, serveur  # noqa: F401
    res["import_core_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    if len(registre.tous()) < 20:
        registre.charger_outils()
    res["nb_outils"] = len(registre.tous())
    res["chargement_outils_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # Test API TestClient IDE/Studio sans reseau externe
    from fastapi.testclient import TestClient
    t0 = time.perf_counter()
    client = TestClient(serveur.app(), base_url="http://127.0.0.1:8790", client=("127.0.0.1", 50000))
    res["init_fastapi_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    r_etat = client.get("/api/ide/etat")
    res["ide_etat_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    res["ide_etat_ok"] = r_etat.status_code == 200

    # Benchmark patcher_code tolerant (espaces / indentation)
    from tools import code as code_tools
    from core.cli import _SESSION_CTX
    prev_proj = _SESSION_CTX.get("projet_actif")
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            f = p / "sample.py"
            f.write_text("def calc(x):   \n    return x * 2\n", encoding="utf-8")
            _SESSION_CTX["projet_actif"] = p
            t0 = time.perf_counter()
            out_patch = code_tools.patcher_code(
                "sample.py",
                "def calc(x):\n    return x * 2",
                "def calc(x):\n    return x * 3",
            )
            res["patch_tolerant_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            res["patch_tolerant_ok"] = "Patch appliqué" in out_patch or "x * 3" in f.read_text(encoding="utf-8")
    finally:
        _SESSION_CTX["projet_actif"] = prev_proj

    # Benchmark memoire SQLite FTS5
    t0 = time.perf_counter()
    memoire.memoriser_entite("benchmark_perf", "fts5_probe", "test latence memoire fts5 riot", sync_auto=False)
    trouve = memoire.rechercher_fts("fts5 riot", categorie="benchmark_perf", limite=3)
    res["memoire_fts5_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    res["memoire_fts5_ok"] = any("fts5" in str(x).lower() for x in trouve)
    memoire.supprimer_entite("benchmark_perf", "fts5_probe", sync_auto=False)

    return res


def bench_llm_live() -> list:
    from core.llm import identite_publique, llm

    prov = llm()
    pub = identite_publique(prov)
    taches = [
        ("fast", "Reponds exactement par le nombre entier : 17 * 24 ?", "408"),
        ("code", "Ecris uniquement une fonction Python `def est_pair(n: int) -> bool:` sans markdown ni texte autour.", "def est_pair"),
        ("deep", "Dans `a = [1, 2]; print(a[2])`, quel nom d'exception Python exact est leve ? Reponds en 1 mot.", "IndexError"),
    ]
    resultats = []
    if not prov.disponible():
        return [{
            "tache": "all",
            "ok": False,
            "raison": f"Provider {pub['nom']} indisponible/non configure sur ce poste",
        }]

    for hint, prompt, attendu in taches:
        t0 = time.perf_counter()
        try:
            rep = prov.repondre(
                "Tu es un assistant technique precis et concis.",
                [{"role": "user", "content": prompt}],
                [],
                tache_hint=hint,
            )
            dt_ms = round((time.perf_counter() - t0) * 1000, 1)
            textes = [b.text for b in rep.content if getattr(b, "type", None) == "text" and b.text]
            txt = "\n".join(textes).strip()
            ok = attendu.lower() in txt.lower()
            resultats.append({
                "tache": hint,
                "provider": pub["nom"],
                "modele_config": pub["modele"],
                "latence_ms": dt_ms,
                "ok": ok,
                "extrait": txt[:90].replace("\n", " "),
            })
        except Exception as e:
            resultats.append({
                "tache": hint,
                "provider": pub["nom"],
                "latence_ms": round((time.perf_counter() - t0) * 1000, 1),
                "ok": False,
                "erreur": str(e)[:120],
            })
    return resultats


def main():
    parser = argparse.ArgumentParser(description="Benchmark local et LLM pour RIOT")
    parser.add_argument("--live", action="store_true", help="Inclure les appels LLM live")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute")
    args = parser.parse_args()

    rapport = {"local": bench_moteur_local()}
    if args.live:
        rapport["llm_live"] = bench_llm_live()

    if args.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        return

    print("=== BENCHMARK RIOT (MESURES REELLES) ===")
    loc = rapport["local"]
    for k, v in loc.items():
        print(f"  {k:<24}: {v}")
    if "llm_live" in rapport:
        print("\n=== PROFILS LLM LIVE ===")
        for item in rapport["llm_live"]:
            print(" ", item)


if __name__ == "__main__":
    main()
