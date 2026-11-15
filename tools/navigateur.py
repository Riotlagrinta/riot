"""Assistance sur TON vrai navigateur Chrome (Playwright via CDP).

Se connecte a un Chrome lance avec --remote-debugging-port (raccourci

"Chrome + Jarvis") pour t'assister pendant que tu surfes : ouvrir un onglet,

lire/resumer la page active, gerer les onglets, agir (clic/scroll/champ).

Distinct de la reservation (Partie A) qui, elle, tourne sur un profil Playwright

SEPARE. Ici c'est ton navigateur de tous les jours.

SECURITE (ton Chrome = toutes tes sessions connectees) :

  - Domaines proteges (banque, impots, sante... dans config.yaml) : LECTURE

    autorisee, mais AUCUNE action (clic/saisie) -> Jarvis te dit de le faire.

  - Jamais de saisie de mot de passe. Achat/paiement detecte -> il te laisse

    valider toi-meme.

  - Fermer des onglets passe par une confirmation vocale (action destructive).

"""

import logging

import os

import time

from datetime import datetime

from pathlib import Path

from urllib.parse import urlparse, quote_plus

from core.config import reglage

from core.registre import outil

LOG = logging.getLogger("jarvis")

_RACINE = Path(__file__).resolve().parent.parent

_DOSSIER_CAPTURES = _RACINE / "_captures"

_DOSSIER_CAPTURES.mkdir(parents=True, exist_ok=True)

_BROWSER = None   # navigateur Chrome connecte via CDP

_MSG_ABSENT = ("Google Chrome n'est pas connecté sur le port 9222. "

               "Demandez-moi 'lance Chrome' ou exécutez 'lancer_chrome_riot.bat'.")

def _capturer_page(page, prefixe: str = "browser") -> str:

    """Capture d'écran JPEG légère de la page active pour rendu immédiat dans le chat."""

    try:

        time.sleep(0.6)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        rnd = os.urandom(2).hex()

        nom_fichier = f"{prefixe}_{ts}_{rnd}.jpg"

        chemin_fichier = _DOSSIER_CAPTURES / nom_fichier

        page.screenshot(path=str(chemin_fichier), type="jpeg", quality=75)

        return f"\n\n![Aperçu de la page](/captures/{nom_fichier})\n"

    except Exception as e:

        LOG.warning(f"Impossible de capturer la page : {e}")

        return ""

_JS_EXTRAIRE_INTERACTIFS = """() => {

    const interactifs = [];

    const elements = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');

    for (const el of elements) {

        const rect = el.getBoundingClientRect();

        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && window.getComputedStyle(el).display !== 'none') {

            const txt = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();

            const tag = el.tagName.toLowerCase();

            if (txt && txt.length < 50 && !interactifs.some(item => item.texte === txt)) {

                interactifs.push({ tag, texte: txt.replace(/\\s+/g, ' ') });

            }

        }

    }

    return interactifs.slice(0, 10);

}"""

def _formater_elements_interactifs(page) -> str:
    """Extrait les boutons et champs interactifs visibles pour guider l'utilisateur."""
    try:
        elements = page.evaluate(_JS_EXTRAIRE_INTERACTIFS)
        if not elements:
            return ""
        lignes = []
        for item in elements:
            tag = item.get("tag", "").upper()
            txt_item = item.get("texte", "")
            if tag in ("BUTTON", "A"):
                lignes.append(f"- [{tag}] « {txt_item} »")
            elif tag in ("INPUT", "TEXTAREA"):
                lignes.append(f"- [CHAMP] « {txt_item} »")
            else:
                lignes.append(f"- [{tag}] « {txt_item} »")
        nl = chr(10)
        titre_bloc = nl + nl + "**Éléments interactifs repérés sur la page :**" + nl
        return titre_bloc + nl.join(lignes)
    except Exception:
        return ""


@outil(
    nom="lancer_navigateur_chrome",

    description="Lance Google Chrome avec le port de débogage 9222 activé pour permettre à RIOT de naviguer, ouvrir des onglets et interagir avec les pages web.",

    parametres={"type": "object", "properties": {}},

    mcp_expose=True,

    affichage="toujours",

)

def lancer_navigateur_chrome() -> str:

    """Démarre Google Chrome avec CDP sur le port 9222."""

    import os

    import subprocess

    import time

    b = _connexion()

    if b is not None:

        return "Google Chrome est déjà ouvert et connecté sur le port 9222 !"

    chemins = [

        r"C:\Program Files\Google\Chrome\Application\chrome.exe",

        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",

        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),

    ]

    exe = next((c for c in chemins if os.path.exists(c)), None)

    if not exe:

        return "Google Chrome est introuvable sur cet ordinateur."

    port = int(reglage("navigateur.cdp_port", 9222))

    profil = os.path.expandvars(r"%LOCALAPPDATA%\Chrome_RIOT")
    # Profil dédié RIOT avec détection anti-bot désactivée pour permettre la connexion Google et les sessions permanentes
    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profil}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized"
    ]

    try:

        subprocess.Popen(cmd)

        for _ in range(8):

            time.sleep(0.5)

            b2 = _connexion()

            if b2:

                break

        if b2:

            return f"Google Chrome a été lancé avec succès (port {port}). RIOT est maintenant connecté à votre navigateur !"

        return f"Google Chrome a été démarré sur le port {port}. Prêt à recevoir vos ordres !"

    except Exception as e:

        return f"Erreur lors du lancement de Chrome : {e}"

MOTS_ACHAT = ["acheter", "commander", "payer", "passer la commande",

              "valider la commande", "proceder au paiement", "checkout",

              "add to cart", "ajouter au panier"]

def _connexion():

    """Retourne le navigateur Chrome connecte, ou None s'il n'est pas joignable."""

    global _BROWSER

    if _BROWSER is not None:

        try:

            _ = _BROWSER.contexts

            return _BROWSER

        except Exception:

            _BROWSER = None

    try:

        from core.playwright_partage import obtenir

        port = int(reglage("navigateur.cdp_port", 9222))

        _BROWSER = obtenir().chromium.connect_over_cdp(f"http://127.0.0.1:{port}",

                                                       timeout=5000)

        return _BROWSER

    except Exception:

        _BROWSER = None

        return None

def _contexte(browser):

    return browser.contexts[0] if browser.contexts else browser.new_context()

def _assurer_sessions_auth(browser, url: str = ""):
    """Injecte silencieusement la session VibeTG si configurée (env ou config.yaml)."""
    if not browser:
        return
    token_vibetg = (os.environ.get("VIBETG_SESSION_TOKEN") or reglage("vibetg.session_token", "") or "").strip()
    if not token_vibetg:
        return
    try:
        ctx = _contexte(browser)
        cookies = ctx.cookies()
        if not any(c.get("name") == "vibetg_session" for c in cookies):
            ctx.add_cookies([{
                "name": "vibetg_session",
                "value": token_vibetg,
                "domain": "kelvix-rewards.vercel.app",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax"
            }])
    except Exception as e:
        LOG.debug(f"Assurance session VibeTG: {e}")

def _pages(browser):

    pages = []

    for ctx in browser.contexts:

        pages.extend(ctx.pages)

    return pages

def _page_active(browser):
    """Meilleur effort : l'onglet visible/au premier plan, priorisant les vraies pages web HTTP/HTTPS."""
    pages = _pages(browser)
    if not pages:
        return None
    # Ne retenir que les vraies pages web valides (ignorer chrome://, chrome-error://, chromewebdata, edge://)
    pages_web = [
        p for p in pages
        if (p.url.startswith("http://") or p.url.startswith("https://"))
        and "chromewebdata" not in p.url
    ]
    pool = pages_web if pages_web else pages
    visibles = []
    for p in pool:
        try:
            if p.evaluate("document.visibilityState") == "visible":
                visibles.append(p)
                if p.evaluate("document.hasFocus()"):
                    return p
        except Exception:
            continue
    return visibles[-1] if visibles else pool[-1]

def _protege(url):

    hote = (urlparse(url).hostname or "").lower()

    for d in (reglage("navigateur.domaines_proteges", []) or []):

        if d.lower() in hote:

            return True

    return False

# ------------------------------------------------------------------- lecture

@outil(

    nom="browser_open",

    description="Ouvre ou bascule vers un onglet dans Google Chrome. Vérifie d'abord si l'onglet est déjà ouvert pour réutiliser la session et éviter les doublons. Capture la vue et liste les boutons/champs interactifs.",

    parametres={

        "type": "object",

        "properties": {

            "url": {"type": "string", "description": "URL complète à ouvrir (https://...)."},

            "recherche": {"type": "string", "description": "Mots-clés à chercher sur le web."},

        },

    },

)

def browser_open(url: str = "", recherche: str = "") -> str:

    browser = _connexion()

    if browser is None:

        lancer_navigateur_chrome()

        browser = _connexion()

        if browser is None:

            return _MSG_ABSENT

    try:

        cible = url.strip()

        if not cible and recherche.strip():

            cible = f"https://www.google.com/search?q={quote_plus(recherche.strip())}"

        if not cible:

            return "Dis-moi quoi ouvrir (une adresse ou une recherche)."

        if "://" not in cible:

            cible = "https://" + cible

        _assurer_sessions_auth(browser, cible)

        from urllib.parse import urlparse

        cible_parsed = urlparse(cible)

        cible_domain = (cible_parsed.netloc or "").lower().replace("www.", "")

        cible_path = (cible_parsed.path or "").rstrip("/")

        onglet_existant = None

        for p in _pages(browser):

            try:

                p_parsed = urlparse(p.url)

                p_domain = (p_parsed.netloc or "").lower().replace("www.", "")

                p_path = (p_parsed.path or "").rstrip("/")

                if cible_domain and cible_domain == p_domain:

                    # Même domaine

                    if not cible_path or cible_path == p_path or p_path in (cible_path, ""):

                        onglet_existant = p

                        break

            except Exception:

                continue

        action_texte = "J'ai ouvert"

        if onglet_existant:

            page = onglet_existant

            try:

                page.bring_to_front()

            except Exception:

                pass

            action_texte = "J'ai basculé sur votre onglet existant"

            if cible_path and cible_path != urlparse(page.url).path.rstrip("/"):

                page.goto(cible, wait_until="domcontentloaded", timeout=15000)

        else:

            page = _contexte(browser).new_page()

            page.goto(cible, wait_until="domcontentloaded", timeout=15000)

            try:

                page.bring_to_front()

            except Exception:

                pass

        apercu = _capturer_page(page, prefixe="browser_nav")

        elements_visibles = _formater_elements_interactifs(page)

        titre = page.title() or cible

        rep = f"{action_texte} : **{titre}** ({page.url}){apercu}"
        if elements_visibles:
            rep += elements_visibles
        rep += "\n\n**Que souhaitez-vous que je fasse ensuite ?**"
        return rep

    except Exception as e:

        LOG.exception("browser_open")

        return f"Je n'ai pas pu ouvrir ca ({e})."

@outil(

    nom="browser_current_page",

    description="Lit l'onglet actif de Chrome (titre, URL, texte, boutons et capture d'écran) pour analyser la page et proposer les actions suivantes.",

    lent=True,

    phrase_attente="Je lis la page.",

)

def browser_current_page() -> str:

    browser = _connexion()

    if browser is None:

        return _MSG_ABSENT

    page = _page_active(browser)

    if page is None:

        return "Aucun onglet ouvert dans Chrome."

    try:

        titre = page.title()

        url = page.url

        try:

            texte = page.inner_text("body")

        except Exception:

            texte = ""

        texte = " ".join(texte.split())[:3000]

        apercu = _capturer_page(page, prefixe="browser_curr")

        elements_visibles = _formater_elements_interactifs(page)

        rep = f"**Titre :** {titre}\n**URL :** {url}{apercu}"
        if elements_visibles:
            rep += elements_visibles
        rep += f"\n\n**Aperçu du texte :**\n{texte}\n\n**Que souhaitez-vous que je fasse ensuite ?**"
        return rep

    except Exception as e:

        LOG.exception("browser_current_page")

        return f"Je n'ai pas pu lire la page ({e})."

@outil(

    nom="browser_tabs",

    description="Liste les onglets ouverts dans Chrome, ou bascule vers un onglet. "

                "Pour 'quels onglets sont ouverts', 'passe sur l'onglet YouTube'. "

                "Pour FERMER des onglets, utilise browser_close_tabs.",

    parametres={

        "type": "object",

        "properties": {

            "action": {"type": "string", "enum": ["lister", "basculer"],

                       "description": "lister (defaut) ou basculer."},

            "filtre": {"type": "string",

                       "description": "Pour basculer : mot present dans le titre ou l'URL."},

        },

    },

)

def browser_tabs(action: str = "lister", filtre: str = "") -> str:

    browser = _connexion()

    if browser is None:

        return _MSG_ABSENT

    pages = _pages(browser)

    if not pages:

        return "Aucun onglet ouvert."

    if action == "basculer" and filtre:

        f = filtre.lower()

        for p in pages:

            try:

                if f in (p.title() or "").lower() or f in p.url.lower():

                    p.bring_to_front()

                    return f"Je suis passe sur : {p.title() or p.url}."

            except Exception:

                continue

        return f"Aucun onglet ne correspond a '{filtre}'."

    lignes = []

    for i, p in enumerate(pages, 1):

        try:

            lignes.append(f"{i}. {p.title() or '(sans titre)'} — {urlparse(p.url).hostname or p.url}")

        except Exception:

            continue

    return f"{len(pages)} onglet(s) :\n" + "\n".join(lignes)

# ------------------------------------------------------------------- actions

def _compter_onglets(filtre):

    browser = _connexion()

    if browser is None:

        return 0

    f = (filtre or "").lower()

    n = 0

    for p in _pages(browser):

        try:

            if not f or f in (p.title() or "").lower() or f in p.url.lower():

                n += 1

        except Exception:

            continue

    return n

def _annonce_fermeture(args):

    filtre = args.get("filtre", "")

    n = _compter_onglets(filtre)

    quoi = f"les {n} onglets" if not filtre else f"{n} onglet(s) '{filtre}'"

    return f"Je ferme {quoi}."

@outil(

    nom="browser_close_tabs",

    description="Ferme des onglets de Chrome. Pour 'ferme cet onglet', 'ferme tous "

                "les onglets YouTube'. Action destructive : confirmation demandee.",

    parametres={

        "type": "object",

        "properties": {

            "filtre": {"type": "string",

                       "description": "Mot present dans le titre/URL des onglets a fermer. "

                                      "Vide = l'onglet actif uniquement."},

        },

    },

    confirmation=True,

    annonce=_annonce_fermeture,

)

def browser_close_tabs(filtre: str = "") -> str:

    browser = _connexion()

    if browser is None:

        return _MSG_ABSENT

    f = (filtre or "").lower()

    fermes = 0

    if not f:

        page = _page_active(browser)

        if page:

            try:

                page.close()

                fermes = 1

            except Exception:

                pass

    else:

        for p in list(_pages(browser)):

            try:

                if f in (p.title() or "").lower() or f in p.url.lower():

                    p.close()

                    fermes += 1

            except Exception:

                continue

    return f"{fermes} onglet(s) ferme(s)."

@outil(

    nom="browser_interact",

    description="Agit sur l'onglet actif de Chrome selon une instruction : 'accepte "

                "les cookies', 'descends aux commentaires', 'mets la video en pause', "

                "'clique sur le premier resultat'. Claude regarde la page et fait UNE "

                "action. Refuse sur les sites proteges et pour les achats/paiements.",

    parametres={

        "type": "object",

        "properties": {

            "instruction": {"type": "string",

                            "description": "Ce qu'il faut faire sur la page active."},

        },

        "required": ["instruction"],

    },

    lent=True,

    phrase_attente="Je regarde la page.",

)

@outil(

    nom="browser_click",

    description="Clique sur un bouton, un lien ou un élément de la page active de Chrome. Indique le texte visible (ex: 'Connexion', 'Documentation', 'Suivant', 'Accepter') ou un sélecteur CSS.",

    parametres={

        "type": "object",

        "properties": {

            "texte_ou_selecteur": {

                "type": "string",

                "description": "Texte visible sur le bouton/lien ou sélecteur de l'élément à cliquer."

            }

        },

        "required": ["texte_ou_selecteur"]

    },

    mcp_expose=True,

    affichage="toujours",

)

def browser_click(texte_ou_selecteur: str) -> str:

    """Clique directement sur un élément textuel ou sélecteur dans Chrome, capture la page et propose la suite."""

    browser = _connexion()

    if browser is None:

        lancer_navigateur_chrome()

        browser = _connexion()

        if browser is None:

            return _MSG_ABSENT

    page = _page_active(browser)

    if not page:

        return "Aucun onglet actif dans Google Chrome."

    if _protege(page.url):

        return "Site protégé (banque/santé/impôts) : action de clic refusée pour votre sécurité."

    cible = texte_ou_selecteur.strip()

    clic_reussi = False


    # Tentative 1 : Direct Playwright get_by_role / get_by_text

    # Ordre optimisé : get_by_text d'abord (match boutons ET liens sans attendre de rôle)
    for attempt in [
        lambda: page.get_by_text(cible, exact=False).first.click(timeout=1500),
        lambda: page.get_by_role("button", name=cible, exact=False).first.click(timeout=1500),
        lambda: page.get_by_role("link", name=cible, exact=False).first.click(timeout=1500),
        lambda: page.click(cible, timeout=1500),
    ]:
        try:
            attempt()
            clic_reussi = True
            break
        except Exception:
            continue

    # Tentative 2 : Recherche via l'index JS

    if not clic_reussi:

        try:

            from tools.reservation import _JS_ELEMENTS

            elements = page.evaluate(_JS_ELEMENTS)

            cible_min = cible.lower()

            for el in elements:

                lbl = (el.get("label") or "").lower()

                if cible_min in lbl or lbl in cible_min:

                    idx = el["index"]

                    page.click(f'[data-jaridx="{idx}"]', timeout=5000)

                    clic_reussi = True

                    break

        except Exception as e:

            LOG.error(f"Erreur recherche element JS : {e}")

    if not clic_reussi:
        apercu_err = _capturer_page(page, prefixe="browser_err")
        elements_visibles = _formater_elements_interactifs(page)
        titre = page.title() or page.url
        rep = f"Impossible de repérer un élément cliquable correspondant à **'{cible}'** sur la page : **{titre}** ({page.url}).{apercu_err}"
        if elements_visibles:
            rep += elements_visibles
        rep += "\n\n**Que souhaitez-vous que je fasse ensuite ?**"
        return rep

    time.sleep(1.2)

    try:

        page.bring_to_front()

    except Exception:

        pass

    apercu = _capturer_page(page, prefixe="browser_click")

    elements_visibles = _formater_elements_interactifs(page)

    titre = page.title() or page.url

    rep = f"Action validée : j'ai cliqué sur **{cible}**.\n\nPage actuelle : **{titre}** ({page.url}){apercu}"
    if elements_visibles:
        rep += elements_visibles
    rep += "\n\n**Que souhaitez-vous que je fasse ensuite ?**"
    return rep

@outil(

    nom="browser_type",

    description="Saisit du texte dans un champ de formulaire ou une barre de recherche de la page active de Chrome.",

    parametres={

        "type": "object",

        "properties": {

            "texte": {"type": "string", "description": "Texte à saisir dans le champ."},

            "champ": {"type": "string", "description": "Label, placeholder ou nom du champ (ex: 'Recherche', 'Email'). Si omis, remplit le premier champ texte actif.", "default": ""}

        },

        "required": ["texte"]

    },

    mcp_expose=True,

    affichage="toujours",

)

def browser_type(texte: str, champ: str = "") -> str:

    """Saisit du texte dans un champ input ou textarea, capture l'écran et propose la suite."""

    browser = _connexion()

    if browser is None:

        lancer_navigateur_chrome()

        browser = _connexion()

        if browser is None:

            return _MSG_ABSENT

    page = _page_active(browser)

    if not page:

        return "Aucun onglet actif dans Google Chrome."

    if _protege(page.url):

        return "Site protégé : saisie de texte refusée pour votre sécurité."

    c = champ.strip()

    saisie_reussie = False

    if c:

        for attempt in [

            lambda: page.get_by_placeholder(c, exact=False).first.fill(texte, timeout=2500),

            lambda: page.get_by_label(c, exact=False).first.fill(texte, timeout=2500),

            lambda: page.fill(c, texte, timeout=2500),

        ]:

            try:

                attempt()

                saisie_reussie = True

                break

            except Exception:

                continue

    if not saisie_reussie:

        # Fallback : premier champ visible

        try:

            inp = page.locator("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]), textarea").first

            if inp:

                inp.fill(texte, timeout=2500)

                saisie_reussie = True

        except Exception as e:

            return f"Erreur lors de la saisie : {e}"

    if not saisie_reussie:

        return f"Impossible de localiser le champ '{c}' sur la page."

    time.sleep(0.8)

    apercu = _capturer_page(page, prefixe="browser_type")

    elements_visibles = _formater_elements_interactifs(page)

    rep = f"Saisie réussie : texte renseigné dans {c or 'le champ actif'}.{apercu}"
    if elements_visibles:
        rep += elements_visibles
    rep += "\n\n**Que souhaitez-vous que je fasse ensuite ?**"
    return rep

@outil(

    nom="browser_scroll",

    description="Fait défiler la page active de Google Chrome vers le bas ou vers le haut.",

    parametres={

        "type": "object",

        "properties": {

            "direction": {"type": "string", "enum": ["bas", "haut"], "default": "bas"}

        }

    },

    mcp_expose=True,

    affichage="toujours",

)

def browser_scroll(direction: str = "bas") -> str:

    """Fait défiler la vue de la page active."""

    browser = _connexion()

    if browser is None:

        return _MSG_ABSENT

    page = _page_active(browser)

    if not page:

        return "Aucun onglet actif dans Google Chrome."

    delta = 800 if direction == "bas" else -800

    try:

        page.mouse.wheel(0, delta)

        return f"Page défilée vers le {direction}."

    except Exception as e:

        return f"Erreur de défilement : {e}"

def browser_interact(instruction: str) -> str:

    browser = _connexion()

    if browser is None:

        return _MSG_ABSENT

    page = _page_active(browser)

    if page is None:

        return "Aucun onglet actif."

    if _protege(page.url):

        return ("On est sur un site protege (banque / impots / sante). Je peux le "

                "lire, mais je n'y fais aucune action : fais-le toi-meme.")

    from tools.reservation import _JS_ELEMENTS, _capture_b64, _client

    client = _client()


    # Si pas de client Anthropic, utiliser le LLM universel configuré (Mistral / Groq / Gemini)

    if client is None:

        try:

            from core.llm import llm

            import json

            provider = llm()

            if not provider or not provider.disponible():

                # Repli automatique sur direct click / type

                inst_lower = instruction.lower()

                if "clique" in inst_lower or "appuie" in inst_lower:

                    m = re.search(r"(?:clique|appuie)\s+(?:sur\s+)?['\"]?([^'\"]+)['\"]?", instruction, re.I)

                    if m:

                        return browser_click(m.group(1).strip())

                elif "tape" in inst_lower or "saisis" in inst_lower:

                    m = re.search(r"(?:tape|saisis)\s+['\"]?([^'\"]+)['\"]?", instruction, re.I)

                    if m:

                        return browser_type(m.group(1).strip())

                elif "descend" in inst_lower or "scroll" in inst_lower:

                    return browser_scroll("bas")

                return "Pas de clé Claude configurée, et instruction trop complexe pour une action directe."


            elements = page.evaluate(_JS_ELEMENTS)

            liste = "\n".join(f"[{e['index']}] {e['tag']} : {e['label']}" for e in elements[:80])

            prompt_sys = (

                "Tu aides à piloter le navigateur Chrome. Analyse les éléments et choisis la meilleure action :\n"

                "- Pour cliquer : réponds uniquement 'CLICK <index>'\n"

                "- Pour taper : réponds uniquement 'TYPE <index> <texte>'\n"

                "- Pour défiler : réponds 'SCROLL down' ou 'SCROLL up'\n"

                "- Si impossible : 'ERROR <raison>'"

            )

            msg_user = f"Instruction utilisateur : {instruction}\n\nÉléments cliquables/saisissables :\n{liste}"

            rep = provider.repondre(prompt_sys, [{"role": "user", "content": msg_user}])

            txt = getattr(rep, "text", str(rep)).strip()


            if txt.startswith("CLICK"):

                idx = int(txt.split()[1])

                page.click(f'[data-jaridx="{idx}"]', timeout=5000)

                return f"J'ai cliqué sur l'élément [{idx}]."

            elif txt.startswith("TYPE"):

                parts = txt.split(maxsplit=2)

                idx = int(parts[1])

                val = parts[2] if len(parts) > 2 else ""

                page.fill(f'[data-jaridx="{idx}"]', val, timeout=5000)

                return f"J'ai saisi '{val}' dans l'élément [{idx}]."

            elif "SCROLL down" in txt:

                page.mouse.wheel(0, 800)

                return "J'ai fait défiler vers le bas."

            elif "SCROLL up" in txt:

                page.mouse.wheel(0, -800)

                return "J'ai fait défiler vers le haut."

        except Exception as ex:

            LOG.error(f"Erreur provider interact : {ex}")

            return f"Action échouée : {ex}"

    schema = {

        "type": "object",

        "properties": {

            "action": {"type": "string",

                       "enum": ["cliquer", "taper", "derouler", "toucheespace",

                                "achat", "fini", "bloque"]},

            "index": {"type": "integer"},

            "texte": {"type": "string"},

            "direction": {"type": "string", "enum": ["bas", "haut"]},

            "raison": {"type": "string"},

        },

        "required": ["action"],

    }

    try:

        elements = page.evaluate(_JS_ELEMENTS)

        liste = "\n".join(

            f"[{e['index']}] {e['tag']}{('/' + e['type']) if e['type'] else ''} : {e['label']}"

            for e in elements[:120])

        sys_prompt = (

            "Tu assistes l'utilisateur sur la page active de son navigateur. Realise "

            "l'instruction en UNE action via l'outil 'agir'. 'toucheespace' met une "

            "video en pause/lecture. Si l'instruction mene a un ACHAT ou un PAIEMENT : "

            "action 'achat' (l'utilisateur validera lui-meme). Ne tape jamais de mot de "

            "passe. Si impossible : 'bloque' avec raison.")

        reponse = client.messages.create(

            model=reglage("reservation.modele", reglage("anthropic.modele", "claude-haiku-4-5")),

            max_tokens=500,

            system=sys_prompt,

            tools=[{"name": "agir", "description": "Une action sur la page.",

                    "input_schema": schema}],

            tool_choice={"type": "tool", "name": "agir"},

            messages=[{"role": "user", "content": [

                {"type": "image", "source": {"type": "base64",

                 "media_type": "image/jpeg", "data": _capture_b64(page)}},

                {"type": "text", "text": f"Instruction : {instruction}\n\nElements :\n{liste}"},

            ]}],

        )

        act = {}

        for bloc in reponse.content:

            if getattr(bloc, "type", None) == "tool_use":

                act = bloc.input

                break

        a = act.get("action")

        if a == "achat":

            return "Ca ressemble a un achat ou un paiement : je te laisse valider toi-meme."

        if a == "bloque":

            return f"Je n'y arrive pas : {act.get('raison', 'raison inconnue')}."

        if a == "fini":

            return "C'est fait."

        idx = act.get("index")

        cible = f'[data-jaridx="{idx}"]' if idx is not None else None

        if a == "cliquer" and cible:

            page.click(cible, timeout=8000)

            return "C'est clique."

        if a == "taper" and cible:

            el = page.query_selector(cible)

            if el and (el.get_attribute("type") or "").lower() == "password":

                return "C'est un champ mot de passe : je ne le remplis pas, fais-le toi-meme."

            page.fill(cible, act.get("texte", ""), timeout=8000)

            return "Saisi."

        if a == "derouler":

            page.mouse.wheel(0, 800 if act.get("direction") != "haut" else -800)

            return "Voila, j'ai defile."

        if a == "toucheespace":

            page.keyboard.press("Space")

            return "C'est fait."

        return "Je n'ai pas su quoi faire ici."

    except Exception as e:

        LOG.exception("browser_interact")

        return f"Souci sur la page ({e})."
