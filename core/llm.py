"""Abstraction du modele de langage : le reste du code ignore quel provider tourne.

Trois implementations, choisies par config.yaml (mode: groq | cloud/hybride | local) :
  - GroqProvider      : API Groq (ultra-rapide, Llama 3.3 / GPT-OSS, rotation auto).
  - AnthropicProvider : API Anthropic (cloud, defaut).
  - OllamaProvider    : Ollama en local (http://localhost:11434), 100% offline.

Tous exposent la meme methode `repondre(systeme, historique, outils)` et
renvoient un objet a la forme d'une reponse Anthropic (.stop_reason + .content,
chaque bloc ayant .type / .text / .name / .input / .id). Ainsi la boucle de
dialogue de Kéranos ne change pas selon le provider.

L'historique reste au format "content blocks" d'Anthropic ; GroqProvider et
OllamaProvider le traduisent vers/depuis leur format respectif de facon interne.
"""
import json
import logging
from typing import Optional

# Magasin de certificats Windows (Malwarebytes intercepte le TLS : sans ca, les
# appels a l'API Anthropic echouent en "certificate verify failed").
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage
from core.model_router import classifier_tache_requete, profil_vers_tache

LOG = logging.getLogger("jarvis")


class Bloc:
    """Imite un bloc de contenu Anthropic (text ou tool_use)."""

    def __init__(self, type, text=None, id=None, name=None, input=None):
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class Reponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


# --------------------------------------------------------------- interface

class ProviderLLM:
    nom = "?"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        orig = cls.__dict__.get("repondre")
        if orig and not getattr(orig, "_riot_monitored", False):
            def _wrapped(self, systeme, historique, outils, visites=None, **kw):
                import os, time as _t
                if visites is not None or os.environ.get("RIOT_DISABLE_TELEMETRY") == "1":
                    return orig(self, systeme, historique, outils, visites=visites, **kw)
                t0 = _t.time()
                prompt_txt = _extraire_prompt_historique(historique)
                try:
                    rep = orig(self, systeme, historique, outils, visites=visites, **kw)
                    rep_txt = _resumer_reponse_llm(rep)
                    echec = "tous les fournisseurs ia ont" in rep_txt.lower()
                    _journaliser_telemetrie(
                        provider=self,
                        ok=not echec,
                        latence_ms=int((_t.time() - t0) * 1000),
                        prompt=prompt_txt,
                        reponse=rep_txt,
                        erreur=rep_txt if echec else "",
                    )
                    return rep
                except Exception as exc:
                    _journaliser_telemetrie(
                        provider=self,
                        ok=False,
                        latence_ms=int((_t.time() - t0) * 1000),
                        prompt=prompt_txt,
                        erreur=str(exc),
                    )
                    raise
            _wrapped._riot_monitored = True
            cls.repondre = _wrapped

    def disponible(self):
        return True

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        raise NotImplementedError


def _extraire_prompt_historique(historique) -> str:
    for m in reversed(historique or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                partes = [str(x.get("text", "")) for x in c if isinstance(x, dict) and x.get("text")]
                if partes:
                    return " ".join(partes)
    return ""


def _resumer_reponse_llm(rep) -> str:
    blocs = getattr(rep, "content", None) or []
    textes = [b.text for b in blocs if getattr(b, "type", None) == "text" and getattr(b, "text", None)]
    outils = [b.name for b in blocs if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None)]
    morceaux = []
    if textes:
        morceaux.append("\n".join(textes))
    if outils:
        morceaux.append(f"[tools: {', '.join(outils)}]")
    return "\n".join(morceaux).strip()


def _journaliser_telemetrie(provider, ok: bool, latence_ms: int, prompt: str = "", reponse: str = "", erreur: str = "") -> None:
    try:
        from core.telemetry import envoyer_alerte_webhook, store_defaut
        store_defaut().enregistrer(
            source="local",
            profil=str(reglage("riot.profil", "auto") or "auto"),
            provider_reel=getattr(provider, "nom", "-"),
            modele_reel=getattr(provider, "modele", "-"),
            ok=ok,
            status_code=200 if ok else 500,
            latence_ms=latence_ms,
            prompt=prompt,
            reponse=reponse,
            erreur=erreur,
        )
        if not ok and erreur:
            wh = str(reglage("telemetry.webhook_url", "") or "")
            envoyer_alerte_webhook(
                f"Erreur IA ({getattr(provider, 'nom', '?')})",
                erreur,
                cle_cooldown=f"llm_err_{getattr(provider, 'nom', 'x')}",
                webhook_url=wh or None,
            )
    except Exception:
        pass


# --------------------------------------------------------------- Groq (cloud rapide)

def _recuperer_liste_cles(val_config, env_nom=""):
    """Normalise une chaîne, liste ou variable d'environnement en une liste propre de clés API."""
    import os
    cles = []
    if isinstance(val_config, list):
        cles.extend(str(c).strip() for c in val_config if str(c).strip())
    elif isinstance(val_config, str) and val_config.strip():
        for chunk in val_config.replace(";", ",").split(","):
            if chunk.strip():
                cles.append(chunk.strip())
    if not cles and env_nom:
        env_val = os.environ.get(env_nom, "")
        if env_val.strip():
            for chunk in env_val.replace(";", ",").split(","):
                if chunk.strip():
                    cles.append(chunk.strip())
    return cles


_PROFILS_PUBLICS = {
    "auto": ("RIOT Auto", "mistral"),
    "fast": ("RIOT Fast", "groq"),
    "code": ("RIOT Code", "mistral"),
    "deep": ("RIOT Deep", "openrouter"),
}


def est_createur() -> bool:
    """Retourne True uniquement pour les createurs (RIOT_ADMIN=1 ou admin_mode: true)."""
    import os
    return os.environ.get("RIOT_ADMIN", "").strip() == "1" or bool(reglage("admin_mode", False))


def identite_publique(provider=None) -> dict:
    """Masque le vrai modele/fournisseur pour les utilisateurs finaux (mode boite noire)."""
    if provider is None:
        provider = llm()
    if est_createur():
        return {
            "nom": getattr(provider, "nom", "-"),
            "modele": getattr(provider, "modele", "-"),
            "profil": str(reglage("riot.profil", "auto") or "auto"),
            "opaque": False,
            "admin": True,
        }
    profil = str(reglage("riot.profil", "auto") or "auto").lower().strip()
    label = _PROFILS_PUBLICS.get(profil, ("RIOT Auto", "mistral"))[0]
    return {
        "nom": "RIOT Engine",
        "modele": label,
        "profil": profil if profil in _PROFILS_PUBLICS else "auto",
        "opaque": True,
        "admin": False,
    }


def definir_profil_public(profil: str) -> dict:
    """Permet a un utilisateur de choisir un profil opaque (auto/fast/code/deep) sans voir le fournisseur."""
    import os
    from core import config
    p = (profil or "auto").lower().strip()
    if p not in _PROFILS_PUBLICS:
        p = "auto"
    config.definir("riot.profil", p)
    if not (os.environ.get("RIOT_GATEWAY_URL") or reglage("gateway.url", "")):
        config.definir("mode", _PROFILS_PUBLICS[p][1])
    reinitialiser()
    return identite_publique()


# --------------------------------------------------------------- Groq (cloud rapide)

class GroqProvider(ProviderLLM):
    nom = "Groq"

    def __init__(self, modele=None):
        cles_brutes = reglage("groq.cles", []) or reglage("groq.cle", "")
        self.cles = _recuperer_liste_cles(cles_brutes, "GROQ_API_KEY")
        self.cle = self.cles[0] if self.cles else ""
        self.modele = modele or reglage("groq.modele", "openai/gpt-oss-120b")
        rotation = reglage("groq.modeles_rotation", [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "llama-3.3-70b-versatile",
        ])
        if not isinstance(rotation, list):
            rotation = [rotation]
        self.rotation = [self.modele] + [m for m in rotation if m != self.modele]
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def disponible(self):
        return bool(self.cles)

    def _traduire(self, systeme, historique):
        messages = [{"role": "system", "content": systeme}]
        for m in historique:
            role, contenu = m.get("role"), m.get("content")
            if role == "user":
                if isinstance(contenu, str):
                    messages.append({"role": "user", "content": contenu})
                else:
                    blocs_multimodaux = []
                    for item in (contenu or []):
                        if not isinstance(item, dict):
                            continue
                        itype = item.get("type")
                        if itype == "tool_result":
                            if blocs_multimodaux:
                                messages.append({"role": "user", "content": blocs_multimodaux})
                                blocs_multimodaux = []
                            c = item.get("content")
                            if isinstance(c, list):
                                textes_tr = [str(x.get("text", "")) for x in c if isinstance(x, dict) and x.get("type") == "text"]
                                c = " ".join(textes_tr).strip() or "[image capturee]"
                            messages.append({
                                "role": "tool",
                                "tool_call_id": item.get("tool_use_id", "call_0"),
                                "content": str(c),
                            })
                        elif itype == "image":
                            src = item.get("source") or {}
                            b64 = str(src.get("data") or "").strip()
                            mtype = str(src.get("media_type") or "image/jpeg").strip()
                            if b64:
                                blocs_multimodaux.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mtype};base64,{b64}"},
                                })
                        elif itype == "image_url":
                            blocs_multimodaux.append(item)
                        elif itype == "text":
                            txt_val = str(item.get("text", ""))
                            if txt_val:
                                blocs_multimodaux.append({"type": "text", "text": txt_val})
                    if blocs_multimodaux:
                        if len(blocs_multimodaux) == 1 and blocs_multimodaux[0].get("type") == "text":
                            messages.append({"role": "user", "content": blocs_multimodaux[0]["text"]})
                        else:
                            messages.append({"role": "user", "content": blocs_multimodaux})
            else:  # assistant
                if isinstance(contenu, str):
                    messages.append({"role": "assistant", "content": contenu})
                else:
                    texte = " ".join(b.text for b in (contenu or [])
                                     if getattr(b, "type", None) == "text" and b.text)
                    appels = [b for b in (contenu or []) if getattr(b, "type", None) == "tool_use"]
                    msg = {"role": "assistant"}
                    if texte:
                        msg["content"] = texte
                    if appels:
                        msg["tool_calls"] = [
                            {
                                "id": getattr(b, "id", None) or f"call_{i}",
                                "type": "function",
                                "function": {
                                    "name": b.name,
                                    "arguments": json.dumps(b.input or {}) if isinstance(b.input, dict) else str(b.input or "{}")
                                }
                            }
                            for i, b in enumerate(appels)
                        ]
                    if not texte and not appels:
                        msg["content"] = ""
                    messages.append(msg)
        return messages

    def _outils(self, outils):
        tools = []
        for o in (outils or []):
            tools.append({
                "type": "function",
                "function": {
                    "name": o["name"],
                    "description": o.get("description", ""),
                    "parameters": o.get("input_schema", {"type": "object", "properties": {}})
                }
            })
        return tools

    def _chat(self, messages, tools, tache_hint: str = ""):
        import requests

        derniere_erreur = None
        tache = tache_hint or classifier_tache_requete(messages=messages, tools=tools)
        rotation_eff = list(self.rotation)
        if tache == "fast" and "openai/gpt-oss-20b" in rotation_eff:
            rotation_eff = ["openai/gpt-oss-20b"] + [m for m in rotation_eff if m != "openai/gpt-oss-20b"]
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in rotation_eff:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("groq.temperature", 0.3)),
                    "max_tokens": int(reglage("groq.max_tokens", 4096)),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                }

                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=25)
                    try:
                        from core.key_quota import capturer_reponse
                        capturer_reponse(self.nom, cle_courante, modele_courant, r.status_code, dict(r.headers))
                    except Exception:
                        pass
                    if r.status_code == 413:
                        LOG.warning("groq: payload/outils trop volumineux (HTTP 413 TPM limite atteinte)")
                        raise RuntimeError("Groq TPM limite atteinte (413): outils trop volumineux pour le tier gratuit")
                    if r.status_code == 429 or r.status_code >= 500:
                        LOG.warning("groq: cle %s... modele %s statut %s, bascule...",
                                    cle_courante[:8], modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text}"
                        continue
                    r.raise_for_status()
                    data = r.json()

                    # Enregistrement consommation budget
                    try:
                        usage = data.get("usage", {})
                        if usage:
                            from core import budget
                            budget.enregistrer(
                                "Groq (Jarvis)", modele_courant,
                                usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0)
                    except Exception:
                        pass

                    return data
                except Exception as e:
                    if "413" in str(e):
                        raise
                    LOG.warning("groq: echec sur cle %s... / modele %s (%s)", cle_courante[:8], modele_courant, e)
                    derniere_erreur = e
                    continue

        raise RuntimeError(f"Toutes les cles et modeles Groq ont echoue. Derniere erreur : {derniere_erreur}")

    def _parser(self, rep):
        choices = rep.get("choices", [])
        if not choices:
            return Reponse("end", [Bloc("text", text="")])
        msg = choices[0].get("message", {}) or {}
        blocs = []
        texte = (msg.get("content") or "").strip()
        if texte:
            blocs.append(Bloc("text", text=texte))
        for i, tc in enumerate(msg.get("tool_calls") or []):
            call_id = tc.get("id") or f"call_{i}"
            fn = tc.get("function", {}) or {}
            nom = fn.get("name")
            args_raw = fn.get("arguments", {})
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except Exception:
                    args = {}
            else:
                args = args_raw or {}
            blocs.append(Bloc("tool_use", id=call_id, name=nom, input=args))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end"
        return Reponse(stop, blocs)

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools, tache_hint=str(kwargs.get("tache_hint", "") or "")))
        except Exception as e:
            LOG.warning("groq: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, **kwargs)


# --------------------------------------------------------------- Gemini (Google AI Studio)

class GeminiProvider(ProviderLLM):
    nom = "Gemini"

    def __init__(self, modele=None):
        cles_brutes = reglage("gemini.cles", []) or reglage("gemini.cle", "")
        self.cles = _recuperer_liste_cles(cles_brutes, "GEMINI_API_KEY")
        self.cle = self.cles[0] if self.cles else ""
        self.modele = modele or reglage("gemini.modele", "gemini-flash-latest")
        rotation = reglage("gemini.modeles_rotation", [
            "gemini-flash-latest",
            "gemini-3.8-flash",
            "gemini-pro-latest",
            "gemini-flash-lite-latest",
        ])
        if not isinstance(rotation, list):
            rotation = [rotation]
        self.rotation = [self.modele] + [m for m in rotation if m != self.modele]
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def disponible(self):
        return bool(self.cles)

    _traduire = GroqProvider._traduire
    _outils = GroqProvider._outils
    _parser = GroqProvider._parser

    def _chat(self, messages, tools):
        import requests
        derniere_erreur = None
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in self.rotation:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("gemini.temperature", 0.3)),
                    "max_tokens": int(reglage("gemini.max_tokens", 2048)),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                }

                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=25)
                    try:
                        from core.key_quota import capturer_reponse
                        capturer_reponse(self.nom, cle_courante, modele_courant, r.status_code, dict(r.headers))
                    except Exception:
                        pass
                    if r.status_code == 429 or r.status_code == 503 or r.status_code >= 500:
                        LOG.warning("gemini: cle %s... modele %s statut %s, bascule...",
                                    cle_courante[:8], modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text}"
                        if "RESOURCE_EXHAUSTED" in r.text or "quota" in r.text.lower():
                            break
                        continue
                    r.raise_for_status()
                    data = r.json()

                    try:
                        usage = data.get("usage", {})
                        if usage:
                            from core import budget
                            budget.enregistrer(
                                "Gemini (RIOT)", modele_courant,
                                usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0)
                    except Exception:
                        pass

                    return data
                except Exception as e:
                    LOG.warning("gemini: echec sur cle %s... / modele %s (%s)", cle_courante[:8], modele_courant, e)
                    derniere_erreur = e
                    continue

        raise RuntimeError(f"Toutes les cles et modeles Gemini ont echoue. Derniere erreur : {derniere_erreur}")

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("gemini: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, **kwargs)


# --------------------------------------------------------------- OpenRouter

class OpenRouterProvider(ProviderLLM):
    nom = "OpenRouter"

    def __init__(self, modele=None):
        cles_brutes = reglage("openrouter.cles", []) or reglage("openrouter.cle", "")
        self.cles = _recuperer_liste_cles(cles_brutes, "OPENROUTER_API_KEY")
        self.cle = self.cles[0] if self.cles else ""
        self.modele = modele or reglage("openrouter.modele", "openrouter/free")
        rotation = reglage("openrouter.modeles_rotation", [
            "openrouter/free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3.5-lightning:free",
            "cohere/north-mini-code:free",
        ])
        if not isinstance(rotation, list):
            rotation = [rotation]
        self.rotation = [self.modele] + [m for m in rotation if m != self.modele]
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    def disponible(self):
        return bool(self.cles)

    _traduire = GroqProvider._traduire
    _outils = GroqProvider._outils
    _parser = GroqProvider._parser

    def _chat(self, messages, tools):
        import requests
        derniere_erreur = None
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in self.rotation:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("openrouter.temperature", 0.3)),
                    "max_tokens": int(reglage("openrouter.max_tokens", 4096)),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://riot.local",
                    "X-Title": "RIOT Copilot",
                }

                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=25)
                    try:
                        from core.key_quota import capturer_reponse
                        capturer_reponse(self.nom, cle_courante, modele_courant, r.status_code, dict(r.headers))
                    except Exception:
                        pass
                    if r.status_code == 429 or r.status_code == 503 or r.status_code >= 500:
                        LOG.warning("openrouter: cle %s... modele %s statut %s, bascule...",
                                    cle_courante[:8], modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text}"
                        continue
                    r.raise_for_status()
                    data = r.json()

                    try:
                        usage = data.get("usage", {})
                        if usage:
                            from core import budget
                            budget.enregistrer(
                                "OpenRouter (RIOT)", modele_courant,
                                usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0)
                    except Exception:
                        pass

                    return data
                except Exception as e:
                    LOG.warning("openrouter: echec sur cle %s... / modele %s (%s)", cle_courante[:8], modele_courant, e)
                    derniere_erreur = e
                    continue

        raise RuntimeError(f"Toutes les cles et modeles OpenRouter ont echoue. Derniere erreur : {derniere_erreur}")

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("openrouter: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, **kwargs)


# --------------------------------------------------------------- Mistral AI

class MistralProvider(ProviderLLM):
    nom = "Mistral"

    def __init__(self, modele=None):
        cles_brutes = reglage("mistral.cles", []) or reglage("mistral.cle", "")
        self.cles = _recuperer_liste_cles(cles_brutes, "MISTRAL_API_KEY")
        self.cle = self.cles[0] if self.cles else ""
        self.modele = modele or reglage("mistral.modele", "codestral-latest")
        rotation = reglage("mistral.modeles_rotation", [
            "codestral-latest",
            "mistral-small-latest",
            "open-mistral-nemo",
            "pixtral-12b",
        ])
        if not isinstance(rotation, list):
            rotation = [rotation]
        self.rotation = [self.modele] + [m for m in rotation if m != self.modele]
        self.api_url = "https://api.mistral.ai/v1/chat/completions"

    def disponible(self):
        return bool(self.cles)

    _traduire = GroqProvider._traduire
    _outils = GroqProvider._outils
    _parser = GroqProvider._parser

    def _chat(self, messages, tools):
        import requests
        derniere_erreur = None
        tache = classifier_tache_requete(messages=messages, tools=tools)
        rotation_eff = list(self.rotation)
        if tache != "code" and "mistral-small-latest" in rotation_eff:
            rotation_eff = ["mistral-small-latest"] + [m for m in rotation_eff if m != "mistral-small-latest"]
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in rotation_eff:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("mistral.temperature", 0.2)),
                    "max_tokens": int(reglage("mistral.max_tokens", 4096)),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                }

                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=25)
                    try:
                        from core.key_quota import capturer_reponse
                        capturer_reponse(self.nom, cle_courante, modele_courant, r.status_code, dict(r.headers))
                    except Exception:
                        pass
                    if r.status_code == 429 or r.status_code == 503 or r.status_code >= 500:
                        LOG.warning("mistral: cle %s... modele %s statut %s, bascule...",
                                    cle_courante[:8], modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text}"
                        continue
                    r.raise_for_status()
                    data = r.json()

                    try:
                        usage = data.get("usage", {})
                        if usage:
                            from core import budget
                            budget.enregistrer(
                                "Mistral (RIOT)", modele_courant,
                                usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0)
                    except Exception:
                        pass

                    return data
                except Exception as e:
                    LOG.warning("mistral: echec sur cle %s... / modele %s (%s)", cle_courante[:8], modele_courant, e)
                    derniere_erreur = e
                    continue

        raise RuntimeError(f"Toutes les cles et modeles Mistral ont echoue. Derniere erreur : {derniere_erreur}")

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("mistral: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, **kwargs)


# --------------------------------------------------------------- Custom / OpenAI-Compatible (FreeLLMAPI, LiteLLM, LM Studio...)

def _normaliser_url_chat(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://127.0.0.1:31415/v1/chat/completions"
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1") or u.endswith("/openai"):
        return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions" if "/v1/" not in u else u


_ROTATION_FREELLMAPI_PAR_TACHE = {
    "code": ["claude-sonnet-4-5", "gpt-oss-120b", "nemotron-3-ultra-550b", "llama-3.3-70b", "qwen3.6-27b", "kilo-auto", "auto"],
    "deep": ["claude-sonnet-4-5", "nemotron-3-ultra-550b", "nemotron-3.5-lightning", "gpt-oss-120b", "llama-3.3-70b", "kilo-auto", "auto"],
    "agent": ["gpt-oss-120b", "qwen3.6-27b", "llama-3.3-70b", "claude-sonnet-4-5", "free-router", "auto"],
    "fast": ["auto", "claude-haiku-4-5", "free-router", "gpt-oss-120b", "qwen3.5-9b", "gpt-oss-20b"],
}


class CustomOpenAIProvider(ProviderLLM):
    """Provider generique compatible OpenAI (/v1/chat/completions) : FreeLLMAPI, LiteLLM, LM Studio, DeepSeek..."""

    nom = "Custom"

    def __init__(self, modele=None):
        import os

        cles_brutes = (
            reglage("custom.cles", [])
            or reglage("custom.cle", "")
            or reglage("freellmapi.cles", [])
            or reglage("freellmapi.cle", "")
        )
        self.cles = _recuperer_liste_cles(cles_brutes, "CUSTOM_API_KEY")
        if not self.cles:
            self.cles = _recuperer_liste_cles("", "FREELLMAPI_KEY")
        self.cle = self.cles[0] if self.cles else ""

        base_cfg = (
            os.environ.get("CUSTOM_BASE_URL", "")
            or os.environ.get("FREELLMAPI_BASE_URL", "")
            or reglage("custom.base_url", "")
            or reglage("custom.url", "")
            or reglage("freellmapi.base_url", "")
            or reglage("freellmapi.url", "")
        )
        self.base_url_configuree = bool(str(base_cfg).strip())
        self.api_url = _normaliser_url_chat(str(base_cfg))
        self.nom_affiche = str(reglage("custom.nom_affiche", "Custom / FreeLLMAPI") or "Custom / FreeLLMAPI")
        self.nom = self.nom_affiche
        self.modele = modele or reglage("custom.modele", "auto")
        rotation = reglage("custom.modeles_rotation", [])
        if not isinstance(rotation, list):
            rotation = [rotation] if rotation else []
        self.rotation = [self.modele] + [m for m in rotation if m and m != self.modele]

    def disponible(self):
        return bool(self.cles or self.base_url_configuree)

    _traduire = GroqProvider._traduire
    _outils = GroqProvider._outils
    _parser = GroqProvider._parser

    def _rotation_adaptative(self, messages, tools, tache_hint: str = ""):
        # Sur RIOT Engine (passerelle Render), le proxy gere deja le routage opaque
        if str(self.nom).startswith("RIOT Engine"):
            return list(self.rotation)
        est_freellmapi = (
            "31415" in self.api_url
            or "freellmapi" in self.api_url.lower()
            or "freellmapi" in str(self.nom).lower()
            or any(str(c).startswith("freellmapi-") for c in self.cles)
        )
        if not est_freellmapi or str(self.modele).lower() != "auto":
            return list(self.rotation)

        has_images = any(
            isinstance(m, dict)
            and isinstance(m.get("content"), list)
            and any(isinstance(b, dict) and b.get("type") in ("image_url", "image") for b in m["content"])
            for m in (messages or [])
        )
        if has_images:
            ordre = ["qwen2.5-vl-72b", "auto", "claude-sonnet-4-5", "free-router"]
            for m in self.rotation:
                if m not in ordre:
                    ordre.append(m)
            return ordre
        tache = tache_hint or classifier_tache_requete(messages=messages, tools=tools)
        taille_chars = sum(len(str(m.get("content", ""))) for m in (messages or []) if isinstance(m, dict))
        if taille_chars > 25000:
            ordre = ["nemotron-3.5-lightning", "nemotron-3-ultra-550b", "claude-sonnet-4-5", "kilo-auto", "auto"]
        else:
            ordre = list(_ROTATION_FREELLMAPI_PAR_TACHE.get(tache, _ROTATION_FREELLMAPI_PAR_TACHE["agent"]))
        for m in self.rotation:
            if m not in ordre:
                ordre.append(m)
        return ordre

    def _chat(self, messages, tools, tache_hint: str = ""):
        import requests

        derniere_erreur = None
        cles_a_tester = self.cles or ["no-key-required"]
        rotation_eff = self._rotation_adaptative(messages, tools, tache_hint=tache_hint)
        tache_eff = tache_hint or classifier_tache_requete(messages=messages, tools=tools)
        base_max_tok = int(reglage("custom.max_tokens", 4096))
        max_tok_eff = max(8192, base_max_tok) if (tache_eff in ("code", "deep") and not str(self.nom).startswith("RIOT Engine")) else base_max_tok
        for cle_courante in cles_a_tester:
            for modele_courant in rotation_eff:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("custom.temperature", 0.3)),
                    "max_tokens": max_tok_eff,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                }
                if tache_hint:
                    headers["X-Riot-Task"] = tache_hint
                timeout_req = 65 if str(self.nom).startswith("RIOT Engine") else 35
                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=timeout_req)
                    if r.status_code == 400 and tools and "tool" in r.text.lower():
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                        r = requests.post(self.api_url, headers=headers, json=payload, timeout=timeout_req)
                    if r.status_code in (401, 403):
                        raise RuntimeError(f"HTTP {r.status_code} (auth): {r.text[:240]}")
                    if r.status_code in (400, 404, 413, 429, 503) or r.status_code >= 500:
                        LOG.warning("custom (%s): modele %s statut %s, bascule...", self.api_url, modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text[:240]}"
                        continue
                    r.raise_for_status()
                    data = r.json()
                    try:
                        usage = data.get("usage", {})
                        if usage:
                            from core import budget
                            budget.enregistrer(
                                self.nom_affiche,
                                modele_courant,
                                usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0,
                            )
                    except Exception:
                        pass
                    return data
                except Exception as e:
                    LOG.warning("custom: echec sur %s / modele %s (%s)", self.api_url, modele_courant, e)
                    derniere_erreur = e
                    if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                        break
                    continue

        raise RuntimeError(f"Echec du fournisseur compatible OpenAI ({self.api_url}). Derniere erreur : {derniere_erreur}")

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        tache_hint = str(kwargs.get("tache_hint", "") or "").strip().lower() or profil_vers_tache(
            self.modele, messages=messages, tools=tools, systeme=systeme
        )
        try:
            return self._parser(self._chat(messages, tools, tache_hint=tache_hint))
        except Exception as e:
            LOG.warning("custom: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, erreur_precedente=str(e), **kwargs)


# --------------------------------------------------------------- Anthropic (cloud)

class AnthropicProvider(ProviderLLM):
    nom = "Anthropic"

    def __init__(self, modele=None):
        import anthropic
        cle = reglage("anthropic.cle", "")
        self.modele = modele or reglage("anthropic.modele", "claude-haiku-4-5")
        self.client = anthropic.Anthropic(api_key=cle) if cle else None

    def disponible(self):
        return self.client is not None

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        # La reponse native Anthropic a deja la bonne forme (.stop_reason/.content).
        rep = self.client.messages.create(
            model=self.modele,
            max_tokens=4096,
            system=[{"type": "text", "text": systeme,
                     "cache_control": {"type": "ephemeral"}}],
            messages=historique,
            tools=outils,
        )
        # Comptabilite (N9) : tokens + cout estime, par jour, cote Jarvis.
        try:
            u = getattr(rep, "usage", None)
            if u is not None:
                from core import budget
                budget.enregistrer(
                    "Anthropic (RIOT)", self.modele,
                    getattr(u, "input_tokens", 0) or 0,
                    getattr(u, "output_tokens", 0) or 0,
                    cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
                    cache_creation=getattr(u, "cache_creation_input_tokens", 0) or 0)
        except Exception:
            pass
        return rep


# --------------------------------------------------------------- Ollama (local)

class OllamaProvider(ProviderLLM):
    nom = "Ollama"

    def __init__(self, modele=None):
        self.hote = reglage("ollama.hote", "http://localhost:11434").rstrip("/")
        self.modele = modele or reglage("ollama.modele", "dolphin-phi:latest")

    def disponible(self):
        try:
            import requests
            requests.get(f"{self.hote}/api/version", timeout=3)
            return True
        except Exception:
            return False

    # -- traduction historique Anthropic -> messages Ollama --
    def _traduire(self, systeme, historique):
        messages = [{"role": "system", "content": systeme}]
        for m in historique:
            role, contenu = m.get("role"), m.get("content")
            if role == "user":
                if isinstance(contenu, str):
                    messages.append({"role": "user", "content": contenu})
                else:
                    for item in contenu or []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "tool_result":
                            c = item.get("content")
                            if isinstance(c, list):   # bloc image
                                c = "[image capturee — la vision n'est pas disponible en mode local]"
                            messages.append({"role": "tool", "content": str(c)})
                        elif item.get("type") == "image":
                            messages.append({"role": "user",
                                             "content": "[image — vision indisponible en local]"})
            else:  # assistant
                if isinstance(contenu, str):
                    messages.append({"role": "assistant", "content": contenu})
                else:
                    texte = " ".join(b.text for b in (contenu or [])
                                     if getattr(b, "type", None) == "text" and b.text)
                    appels = [b for b in (contenu or []) if getattr(b, "type", None) == "tool_use"]
                    msg = {"role": "assistant", "content": texte}
                    if appels:
                        msg["tool_calls"] = [
                            {"function": {"name": b.name, "arguments": b.input or {}}}
                            for b in appels]
                    messages.append(msg)
        return messages

    def _outils(self, outils):
        return [{"type": "function", "function": {
            "name": o["name"], "description": o["description"],
            "parameters": o.get("input_schema", {"type": "object", "properties": {}})}}
            for o in outils]

    def _chat(self, messages, tools, nudge=None):
        import requests
        if nudge:
            messages = messages + [{"role": "user", "content": nudge}]
        est_modele_brut = any(k in self.modele.lower() for k in ("dolphin", "abliterated", "uncensored"))
        payload = {
            "model": self.modele,
            "messages": messages,
            "stream": False,
            "think": bool(reglage("ollama.think", False)),
            "options": {
                "temperature": 0.15 if est_modele_brut else 0.25,
                "top_p": 0.9,
                "repeat_penalty": 1.20 if est_modele_brut else 1.15,
                "num_ctx": 4096,
                "num_predict": int(reglage("ollama.max_tokens", 768)),
            },
        }
        if tools and not est_modele_brut:
            payload["tools"] = tools

        r = requests.post(f"{self.hote}/api/chat", timeout=300, json=payload)
        if r.status_code == 400 and "does not support tools" in r.text:
            payload.pop("tools", None)
            r = requests.post(f"{self.hote}/api/chat", timeout=300, json=payload)
        r.raise_for_status()
        return r.json()

    def _parser(self, rep):
        msg = rep.get("message", {}) or {}
        blocs = []
        texte = (msg.get("content") or "").strip()
        if texte:
            blocs.append(Bloc("text", text=texte))
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)   # peut lever -> gere par le retry
            blocs.append(Bloc("tool_use", id=f"call_{i}", name=fn.get("name"), input=args or {}))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end"
        return Reponse(stop, blocs)

    def repondre(self, systeme, historique, outils, visites=None, prefill=None, **kwargs):
        messages = self._traduire(systeme, historique)
        if prefill:
            # Prefill de l'assistant pour court-circuiter tout refus ou préambule
            messages.append({"role": "assistant", "content": prefill})
        tools = self._outils(outils)
        try:
            rep = self._parser(self._chat(messages, tools))
            if prefill and rep.content:
                for b in rep.content:
                    if getattr(b, "type", None) == "text" and b.text:
                        if not b.text.startswith(prefill):
                            b.text = f"{prefill} {b.text}".strip()
                        break
            return rep
        except Exception as e:
            LOG.warning("ollama: 1er essai en echec (%s), retry plus directif", e)
            # Retry unique, avec une consigne plus stricte sur l'appel d'outil.
            nudge = ("Rappel : pour agir, appelle l'outil approprie via un tool call "
                     "avec des arguments JSON valides ; sinon reponds simplement en texte.")
            try:
                rep = self._parser(self._chat(messages, tools, nudge=nudge))
                if prefill and rep.content:
                    for b in rep.content:
                        if getattr(b, "type", None) == "text" and b.text:
                            if not b.text.startswith(prefill):
                                b.text = f"{prefill} {b.text}".strip()
                            break
                return rep
            except Exception:
                LOG.exception("ollama: echec apres retry")
                return Reponse("end", [Bloc("text", text=(
                    "Desole, le modele local n'a pas reussi a traiter la demande "
                    "correctement. Reessaie en reformulant, ou repasse en mode cloud."))])


# --------------------------------------------------------------- cascade de secours automatique

def _diagnostiquer_echec_cascade(erreur_precedente: str) -> str:
    msg = (erreur_precedente or "").strip()
    if not msg:
        return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles."
    low = msg.lower()
    if "401" in low or "403" in low or "jeton" in low or "connexion riot requise" in low:
        return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles.\nCause probable : session RIOT non connectée ou expirée — lance `riot login` dans le terminal."
    if "429" in low or "quota" in low or "rate limit" in low or "tpm" in low:
        return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles.\nCause probable : limite de requêtes/tokens momentanément atteinte (429/TPM). Réessaie dans 30s ou évite le mode Swarm sur de très gros prompts."
    if "timeout" in low or "timed out" in low or "readtimeout" in low:
        return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles.\nCause probable : délai dépassé sur la passerelle cloud (réveil serveur ou requête trop lourde). Réessaie dans un instant."
    if "502" in low or "503" in low:
        return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles.\nCause probable : surcharge passagère des fournisseurs cloud sur la passerelle (HTTP 502/503). Réessaie ou passe en mode Coder (Mono)."
    return "Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles."


def _construire_gateway_provider(gw_url: str = "", gw_tok: str = "") -> "CustomOpenAIProvider":
    """Construit le provider passerelle RIOT Engine (Render)."""
    import os
    url_eff = (
        gw_url
        or os.environ.get("RIOT_GATEWAY_URL", "")
        or str(reglage("gateway.url", "") or "")
        or DEFAULT_GATEWAY_URL
    ).strip()
    tok_eff = (gw_tok or os.environ.get("RIOT_GATEWAY_TOKEN", "") or str(reglage("gateway.token", "") or "")).strip()
    prov = CustomOpenAIProvider(modele=f"riot-{reglage('riot.profil', 'auto')}")
    prov.api_url = _normaliser_url_chat(url_eff)
    prov.cles = [tok_eff] if tok_eff else []
    prov.cle = tok_eff
    prov.base_url_configuree = False
    prov.nom = "RIOT Engine"
    prov.nom_affiche = "RIOT Engine"
    return prov


def _detecter_freellmapi_local(timeout_s: float = 0.35) -> Optional["CustomOpenAIProvider"]:
    """Detecte automatiquement FreeLLMAPI local (127.0.0.1:31415) si present et pret (sinon None en <350ms)."""
    import os
    if os.environ.get("RIOT_DISABLE_LOCAL_FREELLMAPI", "").strip() == "1":
        return None
    if reglage("freellmapi.auto_detect", True) is False:
        return None
    base_url = (
        os.environ.get("FREELLMAPI_BASE_URL", "")
        or str(reglage("freellmapi.base_url", "") or "")
        or str(reglage("freellmapi.url", "") or "")
        or "http://127.0.0.1:31415/v1"
    ).strip().rstrip("/")
    cles = _recuperer_liste_cles(
        reglage("freellmapi.cles", []) or reglage("freellmapi.cle", "") or reglage("custom.cles", []) or reglage("custom.cle", ""),
        "FREELLMAPI_KEY",
    ) or _recuperer_liste_cles("", "CUSTOM_API_KEY")
    if not cles:
        return None
    try:
        import requests
        models_url = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
        r = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {cles[0]}"},
            timeout=timeout_s,
        )
        if r.status_code != 200:
            return None
        prov = CustomOpenAIProvider(modele="auto")
        prov.api_url = _normaliser_url_chat(base_url)
        prov.cles = cles
        prov.cle = cles[0]
        prov.base_url_configuree = True
        prov.nom = "FreeLLMAPI"
        prov.nom_affiche = "FreeLLMAPI (Local)"
        return prov
    except Exception:
        return None


def cascade_failover(systeme, historique, outils, visites: set, **kwargs):
    """Bascule vers le prochain fournisseur IA disponible sans jamais entrer en boucle récursive."""
    if visites is None:
        visites = set()
    erreur_prec = str(kwargs.pop("erreur_precedente", "") or "")

    # Ordre de secours adaptatif selon le type de requete
    tache = str(kwargs.get("tache_hint", "") or "").strip().lower() or classifier_tache_requete(
        messages=historique, tools=outils, systeme=systeme
    )
    if tache == "code":
        candidats = [
            ("Mistral", MistralProvider),
            ("Groq", GroqProvider),
            ("Gemini", GeminiProvider),
            ("OpenRouter", OpenRouterProvider),
            ("Custom", CustomOpenAIProvider),
            ("Anthropic", AnthropicProvider),
        ]
    else:
        candidats = [
            ("Groq", GroqProvider),
            ("Gemini", GeminiProvider),
            ("Mistral", MistralProvider),
            ("OpenRouter", OpenRouterProvider),
            ("Custom", CustomOpenAIProvider),
            ("Anthropic", AnthropicProvider),
        ]
    if "RIOT Engine" not in visites:
        candidats.append(("RIOT Engine", _construire_gateway_provider))
    for nom, cls_prov in candidats:
        if nom in visites:
            continue
        try:
            prov = cls_prov()
            if prov.disponible():
                LOG.warning("Cascade Failover RIOT : secours automatique vers %s...", nom)
                return prov.repondre(systeme, historique, outils, visites=visites, **kwargs)
        except Exception as e:
            LOG.warning("Cascade Failover: echec sur %s (%s)", nom, e)
            if not erreur_prec:
                erreur_prec = str(e)
            continue

    LOG.error("Cascade Failover: tous les fournisseurs disponibles ont echoue.")
    return Reponse("end", [Bloc("text", text=_diagnostiquer_echec_cascade(erreur_prec))])


# --------------------------------------------------------------- fabrique

_LLM = None
DEFAULT_GATEWAY_URL = "https://riot-engine-proxy.onrender.com/v1"


def llm():
    """Provider LLM courant selon le mode (gateway | groq | mistral | gemini | openrouter | custom | local | hybride | qualite)."""
    global _LLM
    if _LLM is None:
        import os
        from core.routage import mode_actuel
        gw_url = (
            os.environ.get("RIOT_GATEWAY_URL", "")
            or str(reglage("gateway.url", "") or "")
            or DEFAULT_GATEWAY_URL
        ).strip()
        gw_tok = (os.environ.get("RIOT_GATEWAY_TOKEN", "") or str(reglage("gateway.token", "") or "")).strip()
        m = mode_actuel()
        fournisseur = (reglage("llm.fournisseur", "") or "").lower()

        if not est_createur() and m != "local" and fournisseur != "ollama":
            local_free = None if m == "gateway" else _detecter_freellmapi_local()
            _LLM = local_free if local_free is not None else _construire_gateway_provider(gw_url, gw_tok)
        elif m == "groq" or fournisseur == "groq":
            _LLM = GroqProvider()
        elif m == "mistral" or fournisseur == "mistral":
            _LLM = MistralProvider()
        elif m == "gemini" or fournisseur == "gemini":
            _LLM = GeminiProvider()
        elif m == "openrouter" or fournisseur == "openrouter":
            _LLM = OpenRouterProvider()
        elif m in ("custom", "freellmapi", "openai", "litellm") or fournisseur in ("custom", "freellmapi", "openai", "litellm"):
            _LLM = CustomOpenAIProvider()
        elif m == "local" or fournisseur == "ollama":
            _LLM = OllamaProvider()
        elif m == "qualite":
            _LLM = AnthropicProvider(reglage("anthropic.modele_qualite",
                                          "claude-sonnet-4-5"))
        else:                                    # hybride (defaut)
            # Priorité aux clés configurées (Groq -> Mistral -> Gemini -> OpenRouter -> Custom -> Anthropic)
            if reglage("groq.cles", []) or reglage("groq.cle", ""):
                _LLM = GroqProvider()
            elif reglage("mistral.cles", []) or reglage("mistral.cle", ""):
                _LLM = MistralProvider()
            elif reglage("gemini.cles", []) or reglage("gemini.cle", ""):
                _LLM = GeminiProvider()
            elif reglage("openrouter.cles", []) or reglage("openrouter.cle", ""):
                _LLM = OpenRouterProvider()
            elif reglage("custom.base_url", "") or reglage("custom.cles", []) or reglage("custom.cle", ""):
                _LLM = CustomOpenAIProvider()
            else:
                _LLM = AnthropicProvider(reglage("anthropic.modele", "claude-haiku-4-5"))

        LOG.info("provider LLM : %s (mode %s, modele %s)",
                 _LLM.nom, m, getattr(_LLM, "modele", "-"))
    return _LLM


def reinitialiser():
    """Force la reconstruction du provider au prochain llm() (apres un switch de mode)."""
    global _LLM
    _LLM = None
