"""Abstraction du modele de langage : le reste du code ignore quel provider tourne.

Trois implementations, choisies par config.yaml (mode: groq | cloud/hybride | local) :
  - GroqProvider    : API Groq (ultra-rapide, Llama 3.3 / GPT-OSS, rotation auto).
  - ClaudeProvider  : API Anthropic (cloud, defaut).
  - OllamaProvider  : Ollama en local (http://localhost:11434), 100% offline.

Tous exposent la meme methode `repondre(systeme, historique, outils)` et
renvoient un objet a la forme d'une reponse Anthropic (.stop_reason + .content,
chaque bloc ayant .type / .text / .name / .input / .id). Ainsi la boucle de
dialogue de Kéranos ne change pas selon le provider.

L'historique reste au format "content blocks" d'Anthropic ; GroqProvider et
OllamaProvider le traduisent vers/depuis leur format respectif de facon interne.
"""
import json
import logging

# Magasin de certificats Windows (Malwarebytes intercepte le TLS : sans ca, les
# appels a l'API Anthropic echouent en "certificate verify failed").
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

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
                    for item in (contenu or []):
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "tool_result":
                            c = item.get("content")
                            if isinstance(c, list):
                                c = "[image capturee — format non supporte]"
                            messages.append({
                                "role": "tool",
                                "tool_call_id": item.get("tool_use_id", "call_0"),
                                "content": str(c),
                            })
                        elif item.get("type") == "image":
                            messages.append({"role": "user", "content": "[image]"})
                        elif item.get("type") == "text":
                            messages.append({"role": "user", "content": item.get("text", "")})
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

    def _chat(self, messages, tools):
        import requests

        derniere_erreur = None
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in self.rotation:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("groq.temperature", 0.3)),
                    "max_tokens": int(reglage("groq.max_tokens", 1024)),
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
            return self._parser(self._chat(messages, tools))
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
                    "max_tokens": int(reglage("openrouter.max_tokens", 2048)),
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
        cles_a_tester = self.cles or [self.cle]
        for cle_courante in cles_a_tester:
            for modele_courant in self.rotation:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("mistral.temperature", 0.2)),
                    "max_tokens": int(reglage("mistral.max_tokens", 2048)),
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
        return "http://localhost:3001/v1/chat/completions"
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1") or u.endswith("/openai"):
        return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions" if "/v1/" not in u else u


class CustomOpenAIProvider(ProviderLLM):
    """Provider generique compatible OpenAI (/v1/chat/completions) : FreeLLMAPI, LiteLLM, LM Studio, DeepSeek..."""

    nom = "Custom"

    def __init__(self, modele=None):
        import os

        cles_brutes = reglage("custom.cles", []) or reglage("custom.cle", "")
        self.cles = _recuperer_liste_cles(cles_brutes, "CUSTOM_API_KEY")
        if not self.cles:
            self.cles = _recuperer_liste_cles("", "FREELLMAPI_KEY")
        self.cle = self.cles[0] if self.cles else ""

        base_cfg = (
            reglage("custom.base_url", "")
            or reglage("custom.url", "")
            or os.environ.get("CUSTOM_BASE_URL", "")
            or os.environ.get("FREELLMAPI_BASE_URL", "")
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

    def _chat(self, messages, tools):
        import requests

        derniere_erreur = None
        cles_a_tester = self.cles or ["no-key-required"]
        for cle_courante in cles_a_tester:
            for modele_courant in self.rotation:
                payload = {
                    "model": modele_courant,
                    "messages": messages,
                    "temperature": float(reglage("custom.temperature", 0.3)),
                    "max_tokens": int(reglage("custom.max_tokens", 2048)),
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {cle_courante}",
                    "Content-Type": "application/json",
                }
                try:
                    r = requests.post(self.api_url, headers=headers, json=payload, timeout=35)
                    if r.status_code == 400 and tools and "tool" in r.text.lower():
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                        r = requests.post(self.api_url, headers=headers, json=payload, timeout=35)
                    if r.status_code == 429 or r.status_code == 503 or r.status_code >= 500:
                        LOG.warning("custom (%s): modele %s statut %s, bascule...", self.api_url, modele_courant, r.status_code)
                        derniere_erreur = f"HTTP {r.status_code}: {r.text}"
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
                    continue

        raise RuntimeError(f"Echec du fournisseur compatible OpenAI ({self.api_url}). Derniere erreur : {derniere_erreur}")

    def repondre(self, systeme, historique, outils, visites=None, **kwargs):
        if visites is None:
            visites = set()
        visites.add(self.nom)
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("custom: echec (%s), declenchement cascade failover...", e)
            return cascade_failover(systeme, historique, outils, visites, **kwargs)


# --------------------------------------------------------------- Claude (cloud)

class ClaudeProvider(ProviderLLM):
    nom = "Claude"

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
            max_tokens=1024,
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
                    "Claude (Jarvis)", self.modele,
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

def cascade_failover(systeme, historique, outils, visites: set, **kwargs):
    """Bascule vers le prochain fournisseur IA disponible sans jamais entrer en boucle récursive."""
    if visites is None:
        visites = set()

    # Ordre de secours intelligent :
    # 1. Mistral (champion code/français, accepte les 105 outils sans limite TPM)
    # 2. OpenRouter (agrégateur multi-modèles avec accès gratuit)
    # 3. Groq (ultra-rapide pour texte et outils légers)
    # 4. Gemini (Google AI Studio)
    # 5. Claude (Anthropic si configuré)
    candidats = [
        ("Mistral", MistralProvider),
        ("OpenRouter", OpenRouterProvider),
        ("Groq", GroqProvider),
        ("Gemini", GeminiProvider),
        ("Custom", CustomOpenAIProvider),
        ("Claude", ClaudeProvider),
    ]
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
            continue

    LOG.error("Cascade Failover: tous les fournisseurs disponibles ont echoue.")
    return Reponse("end", [Bloc("text", text="Tous les fournisseurs IA ont échoué ou sont temporairement indisponibles.")])


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
            _LLM = CustomOpenAIProvider(modele=f"riot-{reglage('riot.profil', 'auto')}")
            _LLM.api_url = _normaliser_url_chat(gw_url)
            _LLM.cles = [gw_tok] if gw_tok else []
            _LLM.cle = gw_tok
            _LLM.base_url_configuree = False
            _LLM.nom = "RIOT Engine"
            _LLM.nom_affiche = "RIOT Engine"
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
            _LLM = ClaudeProvider(reglage("anthropic.modele_qualite",
                                          "claude-sonnet-4-5"))
        else:                                    # hybride (defaut)
            # Priorité aux clés configurées (Groq -> Mistral -> Gemini -> OpenRouter -> Custom -> Claude)
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
                _LLM = ClaudeProvider(reglage("anthropic.modele", "claude-haiku-4-5"))

        LOG.info("provider LLM : %s (mode %s, modele %s)",
                 _LLM.nom, m, getattr(_LLM, "modele", "-"))
    return _LLM


def reinitialiser():
    """Force la reconstruction du provider au prochain llm() (apres un switch de mode)."""
    global _LLM
    _LLM = None
