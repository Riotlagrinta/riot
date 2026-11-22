"""Mode Mentor Antigravity : Coaching pre-tache, audit post-tache et distillation en memoire gouvernee.

Supporte en priorite :
1. Le CLI officiel `agy` (utilise directement la session Antigravity / abonnement Google AI Pro locale, sans cle Gemini separee) ;
2. Le SDK Python `google-antigravity` en repli (si `GEMINI_API_KEY` / `gemini.cle` est configuree).
"""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core import config, memoire
from core.config import reglage

LOG = logging.getLogger("riot.mentor")


class DirectivesMentor(BaseModel):
    plan_etapes: List[str] = Field(default_factory=list, description="Etapes ordonnees et chirurgicales")
    a_faire: List[str] = Field(default_factory=list, description="Obligations techniques a respecter")
    a_eviter: List[str] = Field(default_factory=list, description="Anti-patterns et pieges a ne pas commettre")
    criteres_validation: List[str] = Field(default_factory=list, description="Commandes ou tests prouvant la reussite")


class LeconDistillee(BaseModel):
    titre: str = Field(description="Nom court et actionnable de la regle/recette")
    langage: str = Field(default="dev", description="Langage ou techno (python, nextjs, sql, expo...)")
    scope: str = Field(default="global", description="global | stack:<nom> | project:<nom>")
    probleme: str = Field(description="Symptome ou situation declenchante")
    cause: str = Field(default="", description="Cause racine identifiee")
    solution: str = Field(description="Approche exacte a appliquer")
    interdits: str = Field(default="", description="Ce qu'il ne faut surtout pas faire")
    verification: str = Field(default="", description="Test ou commande de verification")
    tags: str = Field(default="", description="Mots-cles separes par des virgules")


class VerdictMentor(BaseModel):
    verdict: str = Field(description="APPROUVE | CORRIGE | ERREURS")
    resume: str = Field(description="Synthese factuelle de la revue")
    erreurs_trouvees: List[str] = Field(default_factory=list)
    corrections_appliquees: List[str] = Field(default_factory=list)
    lecons: List[LeconDistillee] = Field(default_factory=list)


def _cle_gemini_dispo() -> str:
    cle = str(os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "") or "").strip()
    if cle:
        return cle
    raw = reglage("gemini.cles", []) or reglage("gemini.cle", "")
    if isinstance(raw, list) and raw:
        return str(raw[0]).strip()
    return str(raw or "").strip()


def _trouver_binaire_agy() -> str:
    """Detecte l'executable officiel `agy` (Antigravity CLI) sur la machine locale."""
    for nom in ("agy", "agy.exe"):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    home = Path.home()
    candidats = [
        home / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
        home / ".local" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
    ]
    for c in candidats:
        if c.exists() and c.is_file():
            return str(c)
    return ""


def _sdk_disponible() -> bool:
    try:
        import google.antigravity  # noqa: F401
        return True
    except Exception:
        return False


def statut_mentor() -> Dict[str, Any]:
    agy_bin = _trouver_binaire_agy()
    sdk_ok = _sdk_disponible()
    cle_ok = bool(_cle_gemini_dispo())
    backend = "agy_cli" if agy_bin else ("sdk" if (sdk_ok and cle_ok) else "aucun")
    return {
        "agy_disponible": bool(agy_bin),
        "agy_chemin": agy_bin,
        "sdk_disponible": sdk_ok,
        "auth_disponible": bool(agy_bin) or cle_ok,
        "backend": backend,
        "actif": bool(reglage("mentor.actif", False)),
        "auto_corriger": bool(reglage("mentor.auto_corriger", True)),
        "modele": str(reglage("mentor.modele", "") or ""),
        "memoire": memoire.statistiques_gouvernance_memoire(),
    }


def mentor_est_actif() -> bool:
    st = statut_mentor()
    return bool(st["actif"] and (st["agy_disponible"] or (st["sdk_disponible"] and st["auth_disponible"])))


def _extraire_json_texte(brut: str) -> str:
    txt = (brut or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.IGNORECASE | re.DOTALL).strip()
    m = re.search(r"\{[\s\S]*\}", txt)
    return m.group(0) if m else txt


def _executer_via_agy_cli(
    agy_bin: str,
    system_instructions: str,
    prompt: str,
    dossier_projet: Path,
    response_schema: type[BaseModel],
    enable_edit: bool = False,
    timeout_s: float = 90.0,
) -> Optional[BaseModel]:
    """Execute un agent Antigravity via la CLI officielle `agy` (session Google AI Pro / IDE)."""
    schema_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            tf.write(json.dumps(response_schema.model_json_schema(), ensure_ascii=False))
            schema_path = tf.name

        prompt_final = f"{system_instructions}\n\n{prompt}"
        mode_agy = "accept-edits" if enable_edit else "plan"
        cmd = [
            agy_bin,
            "--mode", mode_agy,
            "--output-format", "json",
            "--json-schema", schema_path,
            "--add-dir", str(dossier_projet.resolve()),
            f"-p={prompt_final}",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(dossier_projet.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            LOG.warning("agy CLI code=%s err=%s", proc.returncode, (proc.stderr or "")[:200])
            return None
        enveloppe = json.loads((proc.stdout or "").strip())
        if not isinstance(enveloppe, dict) or enveloppe.get("status") != "SUCCESS":
            return None
        charge = str(enveloppe.get("response") or "")
        return response_schema.model_validate_json(_extraire_json_texte(charge))
    except Exception as e:
        LOG.warning("Echec execution agy CLI Mentor: %s", e)
        return None
    finally:
        if schema_path:
            try:
                Path(schema_path).unlink(missing_ok=True)
            except Exception:
                pass


def _executer_via_sdk(
    system_instructions: str,
    prompt: str,
    dossier_projet: Path,
    response_schema: type[BaseModel],
    enable_edit: bool = False,
    timeout_s: float = 45.0,
) -> Optional[BaseModel]:
    """Repli via SDK Python `google-antigravity` + GEMINI_API_KEY."""
    try:
        from google.antigravity import Agent, BuiltinTools, CapabilitiesConfig, LocalAgentConfig
    except Exception as e:
        LOG.warning("SDK google-antigravity indisponible: %s", e)
        return None

    outils = [
        BuiltinTools.LIST_DIR,
        BuiltinTools.SEARCH_DIR,
        BuiltinTools.FIND_FILE,
        BuiltinTools.VIEW_FILE,
    ]
    if enable_edit:
        outils.extend([BuiltinTools.EDIT_FILE, BuiltinTools.RUN_COMMAND])

    cle = _cle_gemini_dispo()
    if not cle:
        return None
    kwargs_cfg: Dict[str, Any] = {
        "system_instructions": system_instructions,
        "capabilities": CapabilitiesConfig(
            enable_subagents=False,
            enabled_tools=outils,
        ),
        "workspaces": [str(dossier_projet.resolve())],
        "response_schema": response_schema,
        "api_key": cle,
    }
    modele_cfg = str(reglage("mentor.modele", "") or "").strip()
    if modele_cfg:
        kwargs_cfg["model"] = modele_cfg

    async def _run() -> Optional[BaseModel]:
        cfg = LocalAgentConfig(**kwargs_cfg)
        async with Agent(cfg) as agent:
            rep = await asyncio.wait_for(agent.chat(prompt), timeout=timeout_s)
            chunks: List[str] = []
            async for tok in rep:
                chunks.append(str(tok))
            brut = "".join(chunks).strip()
            if not brut:
                return None
            return response_schema.model_validate_json(_extraire_json_texte(brut))

    try:
        return asyncio.run(_run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as e:
        LOG.warning("Echec execution SDK Mentor Antigravity: %s", e)
        return None


def _executer_agent_mentor(
    system_instructions: str,
    prompt: str,
    dossier_projet: Path,
    response_schema: type[BaseModel],
    enable_edit: bool = False,
    timeout_s: float = 90.0,
) -> Optional[BaseModel]:
    """Orchestre le Mentor Antigravity (CLI `agy` en priorite, sinon SDK + cle Gemini)."""
    agy_bin = _trouver_binaire_agy()
    if agy_bin:
        res = _executer_via_agy_cli(
            agy_bin, system_instructions, prompt, dossier_projet, response_schema, enable_edit, timeout_s
        )
        if res is not None:
            return res
    return _executer_via_sdk(
        system_instructions, prompt, dossier_projet, response_schema, enable_edit, timeout_s
    )


def preparer_directives_mentor(mission: str, dossier_projet: Path, timeout_s: float = 90.0) -> Optional[DirectivesMentor]:
    """Phase 1 (Avant RIOT) : Produit un plan strict + ce qu'il faut faire et ne PAS faire."""
    sys_inst = (
        "Tu es le Mentor Antigravity qui forme l'agent RIOT. "
        "Inspecte brievement les fichiers pertinents du projet puis renvoie UNIQUEMENT du JSON valide "
        "conforme au schema (plan_etapes, a_faire, a_eviter, criteres_validation)."
    )
    prompt = (
        f"Projet : {dossier_projet.name}\n"
        f"Demande utilisateur : {mission}\n\n"
        "Donne a RIOT un cadrage concis mais strict avant qu'il code : quoi faire, quoi NE PAS faire, et comment verifier."
    )
    res = _executer_agent_mentor(sys_inst, prompt, dossier_projet, DirectivesMentor, enable_edit=False, timeout_s=timeout_s)
    return res if isinstance(res, DirectivesMentor) else None


def formater_directives_pour_prompt(d: Optional[DirectivesMentor]) -> str:
    if not d:
        return ""
    lignes = ["\n\n[CADRAGE MENTOR ANTIGRAVITY — OBLIGATOIRE]"]
    if d.plan_etapes:
        lignes.append("Plan à suivre : " + " -> ".join(d.plan_etapes[:6]))
    if d.a_faire:
        lignes.append("À FAIRE IMPÉRATIVEMENT :\n" + "\n".join(f"- {x}" for x in d.a_faire[:6]))
    if d.a_eviter:
        lignes.append("INTERDIT / À ÉVITER :\n" + "\n".join(f"- {x}" for x in d.a_eviter[:6]))
    if d.criteres_validation:
        lignes.append("Critères de validation :\n" + "\n".join(f"- {x}" for x in d.criteres_validation[:4]))
    return "\n".join(lignes) + "\n"


def auditer_et_distiller(
    mission: str,
    dossier_projet: Path,
    resume_riot: str,
    directives: Optional[DirectivesMentor] = None,
    *,
    auto_corriger: Optional[bool] = None,
    timeout_s: float = 110.0,
) -> Optional[VerdictMentor]:
    """Phase 2 (Apres RIOT) : Verifie le travail reel, corrige si besoin et extrait les lecons vers memoire."""
    corriger = bool(reglage("mentor.auto_corriger", True)) if auto_corriger is None else bool(auto_corriger)
    sys_inst = (
        "Tu es l'Auditeur Mentor Antigravity charge d'evaluer le travail de RIOT. "
        "Verifie les fichiers reellement modifies et la coherence avec la demande. "
        + ("Si tu trouves une erreur reelle, corrige-la proprement et documente-la. " if corriger else "Ne modifie pas les fichiers, signale les erreurs. ")
        + "Extrais ensuite 1 a 3 lecons atomiques et generiques (sans secrets ni chemins absolus locaux) et reponds en JSON strict conforme au schema."
    )
    cadrage = formater_directives_pour_prompt(directives)
    prompt = (
        f"Mission : {mission}\n"
        f"{cadrage}\n"
        f"Travail rapporte par RIOT :\n{resume_riot[:4000]}\n\n"
        "Inspecte le workspace, verifie s'il y a des bugs/oublis, corrige si autorise, puis retourne ton verdict JSON et les lecons apprises."
    )
    res = _executer_agent_mentor(sys_inst, prompt, dossier_projet, VerdictMentor, enable_edit=corriger, timeout_s=timeout_s)
    if not isinstance(res, VerdictMentor):
        return None

    for lecon in res.lecons[:5]:
        conf_init = 0.75 if str(res.verdict).upper() == "APPROUVE" else 0.68
        memoire.enregistrer_lecon_mentor(
            titre=lecon.titre,
            probleme=lecon.probleme,
            solution=lecon.solution,
            cause=lecon.cause,
            langage=lecon.langage,
            tags=lecon.tags,
            scope=lecon.scope,
            interdits=lecon.interdits,
            verification=lecon.verification,
            source="antigravity_mentor",
            confiance=conf_init,
        )
    return res


def basculer_mentor(actif: bool, auto_corriger: Optional[bool] = None) -> Dict[str, Any]:
    config.definir("mentor.actif", bool(actif))
    if auto_corriger is not None:
        config.definir("mentor.auto_corriger", bool(auto_corriger))
    return statut_mentor()
