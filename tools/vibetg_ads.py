"""Module d'automatisation intelligente de visionnage des publicités VibeTG.

Intègre :
- Exécution en arrière-plan non-bloquante avec contrôle d'arrêt.
- Mode Nuit sécurisé (arrêt automatique à heure fixe, ex: 09:00, avec pauses de 5 à 7 min).
- Simulation humaine avancée (mouvements de curseur, scrolls, délais variables anti-détection).
- Suivi en temps réel des métriques (pubs vues, Vibe Coins gagnés, équivalent FCFA, statut).
- Nettoyage automatique des onglets publicitaires tiers (anti-fuite mémoire).
"""

import asyncio
import logging
import random
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

from core.registre import outil

LOG = logging.getLogger("jarvis.vibetg")

def _empecher_veille():
    """Empêche Windows de mettre le système en veille pendant le visionnage."""
    try:
        import ctypes
        # ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass


def _autoriser_veille():
    """Rétablit la mise en veille normale de Windows."""
    try:
        import ctypes
        # ES_CONTINUOUS (0x80000000)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


def check_heure_fin_atteinte(heure_fin_str: Optional[str], start_dt: Optional[datetime]) -> bool:
    """Vérifie si l'heure cible est atteinte en gérant le passage de minuit."""
    if not heure_fin_str or not start_dt:
        return False
    try:
        now = datetime.now()
        fin_h, fin_m = map(int, heure_fin_str.split(":"))
        target = start_dt.replace(hour=fin_h, minute=fin_m, second=0, microsecond=0)
        if target <= start_dt:
            from datetime import timedelta
            target += timedelta(days=1)
        return now >= target
    except Exception:
        return False


class MoteurPubsVibeTG:
    """Gestionnaire singleton de l'algorithme de visionnage publicitaire VibeTG."""

    def __init__(self):
        self._lock = threading.Lock()
        self.actif: bool = False
        self.arreter_demande: bool = False
        self.cible_pubs: int = 7
        self.pubs_regardees: int = 0
        self.pubs_vip: int = 0
        self.pubs_standards: int = 0
        self.total_coins: int = 0
        self.date_lancement: Optional[str] = None
        self.date_lancement_dt: Optional[datetime] = None
        self.etat_courant: str = "Inactif"
        self.dernier_message: str = "Aucune session en cours."
        self.derniere_capture: Optional[str] = None
        self.mode_nuit: bool = False
        self.heure_fin: Optional[str] = None
        self.pause_min_s: int = 35
        self.pause_max_s: int = 55
        self._thread: Optional[threading.Thread] = None

    def statut_dict(self) -> Dict[str, Any]:
        """Retourne l'état complet en dictionnaire pour API et inspection."""
        with self._lock:
            return {
                "actif": self.actif,
                "arreter_demande": self.arreter_demande,
                "cible_pubs": self.cible_pubs,
                "pubs_regardees": self.pubs_regardees,
                "pubs_vip": self.pubs_vip,
                "pubs_standards": self.pubs_standards,
                "total_coins": self.total_coins,
                "total_fcfa": self.total_coins // 10,
                "etat_courant": self.etat_courant,
                "dernier_message": self.dernier_message,
                "date_lancement": self.date_lancement,
                "derniere_capture": self.derniere_capture,
                "mode_nuit": self.mode_nuit,
                "heure_fin": self.heure_fin,
            }

    def demarrer(self, nombre_pubs: int = 7) -> str:
        """Lance l'algorithme en arrière-plan."""
        with self._lock:
            if self.actif:
                return (
                    f"⚠️ L'algorithme des pubs est déjà en cours d'exécution !\n\n"
                    f"**Progression actuelle :** {self.pubs_regardees}/{self.cible_pubs} pubs regardées.\n"
                    f"**Gains :** +{self.total_coins} Coins (+{self.total_coins // 10} FCFA)\n"
                    f"**Statut :** {self.etat_courant}\n\n"
                    f"Pour l'interrompre, dites simplement : *« Arrête l'algorithme des pubs »*."
                )

            self.actif = True
            self.arreter_demande = False
            self.mode_nuit = False
            self.heure_fin = None
            self.pause_min_s = 35
            self.pause_max_s = 55
            self.cible_pubs = max(1, nombre_pubs)
            self.pubs_regardees = 0
            self.pubs_vip = 0
            self.pubs_standards = 0
            self.total_coins = 0
            self.date_lancement_dt = datetime.now()
            self.date_lancement = self.date_lancement_dt.strftime("%H:%M:%S")
            self.etat_courant = "Démarrage en cours..."
            self.dernier_message = f"Session lancée pour {self.cible_pubs} pubs."

            self._thread = threading.Thread(
                target=self._run_async_loop,
                daemon=True,
                name="VibeTG-Ad-Worker"
            )
            self._thread.start()

        return (
            f"🚀 **Algorithme des publicités VibeTG activé !**\n\n"
            f"• **Objectif :** {self.cible_pubs} publicités\n"
            f"• **Mode anti-détection :** Mouvements de souris naturels, interactions sur la pub, nettoyage des onglets et pauses humaines aléatoires (35 à 60s).\n"
            f"• **Suivi :** Vous pouvez demander à tout moment *« Combien de pubs as-tu regardé ? »* ou *« Statut des pubs »* pour voir l'avancement en direct.\n"
            f"• **Arrêt :** Dites *« Arrête l'algorithme des pubs »* dès que vous souhaitez stopper."
        )

    def configurer_mode_nuit(self, heure_fin: str = "09:00", pause_min_min: int = 5, pause_max_min: int = 7) -> str:
        """Active ou transitionne vers le mode nuit sécurisé jusqu'à l'heure cible."""
        with self._lock:
            self.mode_nuit = True
            self.heure_fin = heure_fin
            self.pause_min_s = int(pause_min_min * 60)
            self.pause_max_s = int(pause_max_min * 60)

            if self.actif:
                self.cible_pubs = 999999
                self.dernier_message = f"Transition vers le Mode Nuit active jusqu'à {heure_fin} (pauses de {pause_min_min}-{pause_max_min} min)."
                msg = (
                    f"🌙 **Mode Nuit activé en direct !**\n\n"
                    f"• **Heure de fin :** {heure_fin} (arrêt automatique programmé)\n"
                    f"• **Cadence nocturne :** 1 publicité toutes les {pause_min_min} à {pause_max_min} minutes\n"
                    f"• **Sécurité :** Simulation d'écoute nocturne, zéro alerte pour la régie Adsterra.\n"
                    f"• **Session en cours :** La boucle actuelle s'étend jusqu'à {heure_fin} en douceur."
                )
            else:
                self.actif = True
                self.arreter_demande = False
                self.cible_pubs = 999999
                self.pubs_regardees = 0
                self.pubs_vip = 0
                self.pubs_standards = 0
                self.total_coins = 0
                self.date_lancement_dt = datetime.now()
                self.date_lancement = self.date_lancement_dt.strftime("%H:%M:%S")
                self.etat_courant = f"Mode Nuit en cours (jusqu'à {heure_fin})..."
                self.dernier_message = f"Session nocturne lancée jusqu'à {heure_fin}."
                self._thread = threading.Thread(
                    target=self._run_async_loop,
                    daemon=True,
                    name="VibeTG-Night-Worker"
                )
                self._thread.start()
                msg = (
                    f"🌙 **Mode Nuit démarré !**\n\n"
                    f"• **Heure de fin :** {heure_fin} (arrêt automatique programmé)\n"
                    f"• **Cadence nocturne :** 1 publicité toutes les {pause_min_min} à {pause_max_min} minutes\n"
                    f"• **Sécurité :** Simulation d'écoute nocturne sans risque de ban Adsterra."
                )
        return msg

    def arreter(self) -> str:
        """Arrête immédiatement l'algorithme."""
        with self._lock:
            if not self.actif:
                return "ℹ️ L'algorithme des pubs n'est pas actif actuellement."

            self.arreter_demande = True
            self.etat_courant = "Arrêt demandé par l'utilisateur..."
            self.dernier_message = "Interruption en cours du visionnage..."

        return (
            f"🛑 **Demande d'arrêt envoyée à l'algorithme des pubs.**\n\n"
            f"Le processus finalise l'action en cours, ferme les onglets ouverts et s'interrompt en toute sécurité.\n"
            f"**Bilan de la session :** {self.pubs_regardees} pubs regardées, +{self.total_coins} Coins (+{self.total_coins // 10} FCFA)."
        )

    def _run_async_loop(self):
        """Point d'entrée du thread d'arrière-plan."""
        _empecher_veille()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._boucle_principale())
        except Exception as e:
            LOG.exception("Erreur dans la boucle de visionnage VibeTG : %s", e)
            with self._lock:
                self.etat_courant = f"Erreur : {e}"
        finally:
            with self._lock:
                self.actif = False
            _autoriser_veille()
            loop.close()

    async def _boucle_principale(self):
        """Boucle asynchrone orchestrant Playwright CDP et le visionnage."""
        from playwright.async_api import async_playwright
        from tools.navigateur import _DOSSIER_CAPTURES

        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5000)
            except Exception as e:
                with self._lock:
                    self.etat_courant = f"Erreur de connexion CDP (port 9222) : {e}"
                    self.actif = False
                return

            ctx = browser.contexts[0]

            # 1. Identifier ou ouvrir le Dashboard
            dashboard = None
            for pg in ctx.pages:
                if "kelvix-rewards" in pg.url or "dashboard" in pg.url:
                    dashboard = pg
                    break

            if not dashboard:
                with self._lock:
                    self.etat_courant = "Ouverture du Dashboard VibeTG..."
                dashboard = await ctx.new_page()
                await dashboard.goto("https://kelvix-rewards.vercel.app/dashboard", wait_until="networkidle")

            await dashboard.bring_to_front()

            # Nettoyage initial : fermer les onglets de pub orphelins
            for pg in list(ctx.pages):
                if pg != dashboard and "chrome://" not in pg.url:
                    try:
                        await pg.close()
                    except Exception:
                        pass

            # Fermer tout modal résiduel
            try:
                close_btn = dashboard.locator("button:has-text('Fermer')").first
                if await close_btn.count() > 0 and await close_btn.is_visible():
                    await close_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            while True:
                with self._lock:
                    # Arrêt horaire automatique en Mode Nuit
                    if self.heure_fin and check_heure_fin_atteinte(self.heure_fin, self.date_lancement_dt) and self.pubs_regardees > 0:
                        self.etat_courant = f"Mode Nuit terminé à {self.heure_fin} (Objectif atteint)."
                        break

                    if self.arreter_demande or self.pubs_regardees >= self.cible_pubs:
                        break
                    num_actuel = self.pubs_regardees + 1
                    cible_lbl = f"{self.cible_pubs}" if self.cible_pubs < 900000 else f"Nuit ({self.heure_fin})"

                with self._lock:
                    self.etat_courant = f"Préparation de la pub {num_actuel}/{cible_lbl}..."

                # Vérifier si un cooldown est en cours sur le bouton
                btn = dashboard.locator("button:has-text('Gagner des Coins')").first
                btn_busy = dashboard.locator("text=Prochaine pub dans").first
                if await btn_busy.count() > 0 and await btn_busy.is_visible():
                    txt_cooldown = await btn_busy.inner_text()
                    with self._lock:
                        self.etat_courant = f"Cooldown anti-spam en cours ({txt_cooldown})..."

                    for _ in range(40):
                        if self.arreter_demande:
                            break
                        if await btn.count() > 0 and await btn.is_enabled():
                            break
                        await asyncio.sleep(1)

                if self.arreter_demande:
                    break

                if await btn.count() == 0 or not await btn.is_enabled():
                    with self._lock:
                        self.etat_courant = "Attente d'activation du bouton..."
                    await asyncio.sleep(4)
                    continue

                # Simulation humaine : légers mouvements aléatoires de souris
                try:
                    await dashboard.mouse.move(random.randint(150, 450), random.randint(180, 500))
                    await asyncio.sleep(random.uniform(0.6, 1.4))
                except Exception:
                    pass

                # Clic pour lancer la pub
                with self._lock:
                    self.etat_courant = f"Lancement de la pub {num_actuel}/{cible_lbl}..."
                await btn.click()
                await asyncio.sleep(3)

                # Repérer l'onglet de pub externe ouvert
                ad_tab = None
                for pg in ctx.pages:
                    if pg != dashboard and "chrome://" not in pg.url:
                        ad_tab = pg
                        break

                if ad_tab:
                    # Simuler un léger scroll humain sur la page de pub
                    try:
                        await ad_tab.mouse.wheel(0, random.randint(120, 280))
                    except Exception:
                        pass

                await dashboard.bring_to_front()

                # Décompte de visionnage de 30 secondes
                for s in range(28, 0, -5):
                    if self.arreter_demande:
                        break
                    with self._lock:
                        self.etat_courant = f"Visionnage pub {num_actuel}/{cible_lbl} ({s}s restantes)..."
                    await asyncio.sleep(5)

                if self.arreter_demande:
                    if ad_tab:
                        try:
                            await ad_tab.close()
                        except Exception:
                            pass
                    break

                # Validation du crédit
                with self._lock:
                    self.etat_courant = f"Validation du crédit pub {num_actuel}/{cible_lbl}..."

                reward_validee = False
                coins_ajoutes = 0
                for _ in range(12):
                    if self.arreter_demande:
                        break
                    txt_body = await dashboard.inner_text("body")
                    if "Vibe Coins" in txt_body and ("créditée à ton solde" in txt_body or "Fermer" in txt_body):
                        reward_validee = True
                        if "+1000" in txt_body:
                            coins_ajoutes = 1000
                            with self._lock:
                                self.pubs_vip += 1
                        else:
                            coins_ajoutes = 10
                            with self._lock:
                                self.pubs_standards += 1
                        break
                    await asyncio.sleep(1)

                # Fermer l'onglet publicitaire externe
                if ad_tab:
                    try:
                        await ad_tab.close()
                    except Exception:
                        pass

                # Fermer la fenêtre modale
                try:
                    close_btn = dashboard.locator("button:has-text('Fermer')").first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                # Prendre une capture de suivi
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                nom_img = f"vibetg_loop_{ts}.jpg"
                img_path = _DOSSIER_CAPTURES / nom_img
                try:
                    await dashboard.screenshot(path=str(img_path), type="jpeg", quality=75)
                    with self._lock:
                        self.derniere_capture = f"/captures/{nom_img}"
                except Exception:
                    pass

                with self._lock:
                    if reward_validee:
                        self.pubs_regardees += 1
                        self.total_coins += coins_ajoutes
                        self.dernier_message = f"Pub {self.pubs_regardees} validée (+{coins_ajoutes} Coins)."
                    else:
                        self.dernier_message = f"Cycle pub {num_actuel} terminé sans modal."

                # Pause humaine anti-détection (standard ou Mode Nuit)
                with self._lock:
                    if self.heure_fin and check_heure_fin_atteinte(self.heure_fin, self.date_lancement_dt):
                        break
                    reste = self.pubs_regardees < self.cible_pubs and not self.arreter_demande

                if reste:
                    pause_s = random.randint(int(self.pause_min_s), int(self.pause_max_s))
                    for remaining in range(pause_s, 0, -5):
                        if self.arreter_demande:
                            break
                        with self._lock:
                            if self.heure_fin and check_heure_fin_atteinte(self.heure_fin, self.date_lancement_dt):
                                break
                            txt_p = f"{remaining // 60}m {remaining % 60}s" if remaining >= 60 else f"{remaining}s"
                            label_mode = "Mode Nuit" if self.mode_nuit else "anti-détection"
                            self.etat_courant = f"Pause humaine {label_mode} ({txt_p})..."
                        await asyncio.sleep(5)

            # Fin de la boucle
            with self._lock:
                if self.arreter_demande:
                    self.etat_courant = "Arrêté par l'utilisateur."
                elif self.heure_fin and check_heure_fin_atteinte(self.heure_fin, self.date_lancement_dt):
                    self.etat_courant = f"Mode Nuit terminé à {self.heure_fin} (Objectif atteint)."
                else:
                    self.etat_courant = "Terminé (Objectif atteint)."
                self.actif = False


# Instance unique partagée
MOTEUR_PUBS = MoteurPubsVibeTG()


# -----------------------------------------------------------------------------
# Déclaration des Outils de l'Assistant
# -----------------------------------------------------------------------------

@outil(
    nom="vibetg_activer_algo_pubs",
    description="Active l'algorithme automatisé de visionnage des publicités VibeTG en arrière-plan avec pauses humaines et anti-détection. Permet d'accumuler des Vibe Coins (FCFA).",
    parametres={
        "type": "object",
        "properties": {
            "nombre_pubs": {
                "type": "integer",
                "description": "Nombre de publicités à regarder (par défaut 7 pour maximiser le quota VIP).",
                "default": 7
            }
        }
    },
    mcp_expose=True,
    affichage="toujours"
)
def vibetg_activer_algo_pubs(nombre_pubs: int = 7) -> str:
    """Démarre l'algorithme des publicités en tâche de fond."""
    return MOTEUR_PUBS.demarrer(nombre_pubs=nombre_pubs)


@outil(
    nom="vibetg_activer_mode_nuit",
    description="Active le Mode Nuit sécurisé : visionnage avec cadence humaine espacée (5 à 7 min) et arrêt automatique à 09:00 du matin.",
    parametres={
        "type": "object",
        "properties": {
            "heure_fin": {
                "type": "string",
                "description": "Heure d'arrêt automatique au format HH:MM (par défaut '09:00').",
                "default": "09:00"
            }
        }
    },
    mcp_expose=True,
    affichage="toujours"
)
def vibetg_activer_mode_nuit(heure_fin: str = "09:00") -> str:
    """Configure et démarre le mode nuit sécurisé."""
    return MOTEUR_PUBS.configurer_mode_nuit(heure_fin=heure_fin)


@outil(
    nom="vibetg_statut_algo_pubs",
    description="Consulte en temps réel le statut de l'algorithme des publicités VibeTG : nombre de pubs regardées, gains en Vibe Coins et FCFA, état en direct.",
    parametres={"type": "object", "properties": {}},
    mcp_expose=True,
    affichage="toujours"
)
def vibetg_statut_algo_pubs() -> str:
    """Retourne un rapport d'avancement détaillé en direct."""
    info = MOTEUR_PUBS.statut_dict()
    actif = info["actif"]
    etat = "🟢 **EN COURS**" if actif else "⚪ **ARRÊTÉ / INACTIF**"

    rep = (
        f"### 📊 Statut de l'Algorithme des Publicités VibeTG\n\n"
        f"• **État actuel :** {etat} — *{info['etat_courant']}*\n"
        f"• **Progression :** **{info['pubs_regardees']} / {info['cible_pubs'] if info['cible_pubs'] < 900000 else 'Mode Nuit (09:00)'}** publicités\n"
        f"• **Répartition :** {info['pubs_vip']} VIP (100 FCFA) • {info['pubs_standards']} Standard (1 FCFA)\n"
        f"• **Total accumulé :** **+{info['total_coins']} Vibe Coins** (soit **+{info['total_fcfa']} FCFA**)\n"
        f"• **Dernière activité :** {info['dernier_message']}\n"
    )

    if info.get("mode_nuit"):
        rep += f"• **Mode Nuit actif :** Arrêt programmé à **{info.get('heure_fin', '09:00')}** (cadence 5-7 min)\n"

    if info["date_lancement"]:
        rep += f"• **Heure de début :** {info['date_lancement']}\n"

    if info["derniere_capture"]:
        rep += f"\n![Aperçu direct du visionnage]({info['derniere_capture']})\n"

    if actif:
        rep += "\n💡 *Pour stopper à tout moment, dites : « Arrête l'algorithme des pubs ».*"
    else:
        rep += "\n💡 *Pour démarrer une session, dites : « Active l'algorithme des pubs ».*"

    return rep


@outil(
    nom="vibetg_arreter_algo_pubs",
    description="Arrête immédiatement l'algorithme automatisé de visionnage des publicités VibeTG.",
    parametres={"type": "object", "properties": {}},
    mcp_expose=True,
    affichage="toujours"
)
def vibetg_arreter_algo_pubs() -> str:
    """Arrête immédiatement l'exécution de l'algorithme."""
    return MOTEUR_PUBS.arreter()
