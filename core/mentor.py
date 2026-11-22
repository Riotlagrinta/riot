"""Mode Mentor Antigravity : Coaching pre-tache, audit post-tache et distillation en memoire gouvernee.

Concu strictement pour l'usage labo/entrainement local du createur afin de faire
monter en puissance le Playbook public de RIOT sans exposer de session privee.
"""
import asyncio
import logging
import os
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


def statut_mentor() -> Dict[str, Any]:
    sdk_ok = False
    try:
        import google.antigravity  # noqa: F401
        sdk_ok = True
    except Exception:
        sdk_ok = False
    return {
        "sdk_disponible": sdk_ok,
        "auth_disponible": bool(_cle_gemini_dispo()),
        "actif": bool(reglage("mentor.actif", False)),
        "auto_corriger": bool(reglage("mentor.auto_corriger", True)),
        "modele": str(reglage("mentor.modele", "") or ""),
        "memoire": memoire.statistiques_gouvernance_memoire(),
    }


def mentor_est_actif() -> bool:
    st = statut_mentor()
    return bool(st["sdk_disponible"] and st["actif"])


def _executer_agent_mentor(
    system_instructions: str,
    prompt: str,
    dossier_projet: Path,
    response_schema: type[BaseModel],
    enable_edit: bool = False,
    timeout_s: float = 45.0,
) -> Optional[BaseModel]:
    """Lance une session Antigravity bornee et retourne le modele Pydantic structure."""
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
    kwargs_cfg: Dict[str, Any] = {
        "system_instructions": system_instructions,
        "capabilities": CapabilitiesConfig(
            enable_subagents=False,
            enabled_tools=outils,
        ),
        "workspaces": [str(dossier_projet.resolve())],
        "response_schema": response_schema,
    }
    if cle:
        kwargs_cfg["api_key"] = cle
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
            return response_schema.model_validate_json(brut)

    try:
        return asyncio.run(_run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as e:
        LOG.warning("Echec execution agent Mentor Antigravity: %s", e)
        return None


def preparer_directives_mentor(mission: str, dossier_projet: Path, timeout_s: float = 40.0) -> Optional[DirectivesMentor]:
    """Phase 1 (Avant RIOT) : Produit un plan strict + ce qu'il faut faire et ne PAS faire."""
    sys_inst = (
        "Tu es le Mentor Antigravity qui forme l'agent RIOT. "
        "Inspecte brievement les fichiers pertinents du projet puis renvoie UNIQUEMENT des directives "
        "structurees (plan, obligations, interdits explicites, verification attendue)."
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
    timeout_s: float = 65.0,
) -> Optional[VerdictMentor]:
    """Phase 2 (Apres RIOT) : Verifie le travail reel, corrige si besoin et extrait les lecons vers memoire."""
    corriger = bool(reglage("mentor.auto_corriger", True)) if auto_corriger is None else bool(auto_corriger)
    sys_inst = (
        "Tu es l'Auditeur Mentor Antigravity charge d'evaluer le travail de RIOT. "
        "Verifie les fichiers reellement modifies et la coherence avec la demande. "
        + ("Si tu trouves une erreur reelle, corrige-la proprement avec edit_file et documente-la. " if corriger else "Ne modifie pas les fichiers, signale les erreurs. ")
        + "Extrais ensuite 1 a 3 lecons atomiques et generiques (sans secrets ni chemins absolus locaux) pour le Playbook de RIOT."
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
