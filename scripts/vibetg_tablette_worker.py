"""Worker autonome de visionnage publicitaire VibeTG pour tablette Amazon Fire HD 10.
Synchronisé pour s'arrêter exactement à l'heure cible (13:35).
Gère la persistance de statut dans tablette_pubs_statut.json et les captures d'écran.
"""

import asyncio
import json
import logging
import os
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("vibetg_tablette")

ADB_PATH = r"C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe"
TABLET_IP = "10.94.143.79"
USB_ID = "G001KT0511960C98"
CDP_PORT = 9223
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

BASE_DIR = Path(__file__).resolve().parent.parent
CAPTURES_DIR = BASE_DIR / "_captures"
STATUS_FILE = BASE_DIR / "tablette_pubs_statut.json"

HEURE_FIN = os.environ.get("VIBETG_HEURE_FIN", "08:00")
CIBLE_PUBS = int(os.environ.get("VIBETG_CIBLE_PUBS", "30"))
PAUSE_MIN_S = int(os.environ.get("VIBETG_PAUSE_MIN", "45"))
PAUSE_MAX_S = int(os.environ.get("VIBETG_PAUSE_MAX", "85"))
BRAIN_DIR = Path(r"C:\Users\LENOVO\.gemini\antigravity\brain\f74a4ac9-0ca5-43dd-8b1b-7f5438fd0121")

def check_heure_fin_atteinte(heure_fin_str: str, start_dt: datetime) -> bool:
    """Vérifie si l'heure cible est atteinte, gérant correctement le passage de minuit."""
    if not heure_fin_str or heure_fin_str == "aucun":
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

def save_status(data: dict):
    data["derniere_maj"] = datetime.now().strftime("%H:%M:%S")
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Erreur sauvegarde statut: {e}")

def get_active_device() -> str:
    """Détecte si la tablette est connectée en USB (priorité maximale si branchée) ou en Wi-Fi."""
    try:
        res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, timeout=3)
        if f"{USB_ID}\tdevice" in res.stdout:
            return USB_ID
        subprocess.run([ADB_PATH, "connect", f"{TABLET_IP}:5555"], timeout=2, capture_output=True)
        res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, timeout=3)
        if f"{TABLET_IP}:5555\tdevice" in res.stdout:
            return f"{TABLET_IP}:5555"
        if f"{USB_ID}\tdevice" in res.stdout:
            return USB_ID
    except Exception:
        pass
    return USB_ID

def ensure_adb_forward():
    dev = get_active_device()
    try:
        if dev != USB_ID:
            subprocess.run([ADB_PATH, "connect", f"{TABLET_IP}:5555"], timeout=2, capture_output=True)
        subprocess.run([ADB_PATH, "-s", dev, "shell", "input", "keyevent", "82"], capture_output=True)
        subprocess.run([ADB_PATH, "-s", dev, "shell", "svc", "power", "stayon", "true"], capture_output=True)
        subprocess.run([ADB_PATH, "-s", dev, "shell", "am", "start", "-n", "com.android.chrome/com.google.android.apps.chrome.Main"], capture_output=True)
        time.sleep(2)
        subprocess.run([ADB_PATH, "-s", dev, "forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote"], check=True, capture_output=True)
        logger.info(f"ADB port forward & stayon activés sur {dev}.")
    except Exception as e:
        logger.error(f"Erreur ADB forward ({dev}): {e}")

async def run_worker():
    start_dt = datetime.now()
    status = {
        "actif": True,
        "appareil": "Tablette Amazon Fire HD 10",
        "heure_lancement": start_dt.strftime("%H:%M:%S"),
        "heure_fin_cible": HEURE_FIN,
        "cible_pubs": CIBLE_PUBS,
        "pubs_regardees": 0,
        "total_coins": 0,
        "total_fcfa": 0,
        "etat_courant": "Initialisation...",
        "dernier_message": f"Démarrage session tablette (Objectif: {CIBLE_PUBS} pubs)...",
        "derniere_capture": None
    }
    save_status(status)

    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    ensure_adb_forward()

    while True:
        if check_heure_fin_atteinte(HEURE_FIN, start_dt):
            logger.info(f"Heure cible {HEURE_FIN} atteinte. Fin de session !")
            status["actif"] = False
            status["etat_courant"] = f"Session terminée à {HEURE_FIN}."
            status["dernier_message"] = f"Objectif horaire atteint avec {status['pubs_regardees']} pubs vues (+{status['total_coins']} Coins)."
            save_status(status)
            break

        if status["pubs_regardees"] >= CIBLE_PUBS:
            logger.info(f"Cible de {CIBLE_PUBS} pubs atteinte ! Fin de session.")
            status["actif"] = False
            status["etat_courant"] = f"Session terminée : {CIBLE_PUBS} pubs visionnées avec succès."
            status["dernier_message"] = f"Objectif atteint : {status['pubs_regardees']}/{CIBLE_PUBS} pubs (+{status['total_coins']} Coins)."
            save_status(status)
            break

        try:
            ensure_adb_forward()
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=30000)
                except Exception as e:
                    logger.warning(f"Échec de connexion CDP tablette : {e}. Réessai dans 10s...")
                    status["etat_courant"] = "Reconnexion CDP en cours..."
                    save_status(status)
                    await asyncio.sleep(10)
                    continue

                ctx = browser.contexts[0]
                
                # Trouver le dashboard
                dashboard = None
                for pg in ctx.pages:
                    if "kelvix-rewards" in pg.url or "dashboard" in pg.url:
                        dashboard = pg
                        break
                
                if not dashboard:
                    logger.info("Dashboard non trouvé dans les pages ouvertes, navigation...")
                    dashboard = ctx.pages[0] if ctx.pages else await ctx.new_page()
                    await dashboard.goto("https://kelvix-rewards.vercel.app/dashboard", wait_until="networkidle")

                await dashboard.bring_to_front()

                # Nettoyer les onglets orphelins
                for pg in list(ctx.pages):
                    if pg != dashboard and "chrome://" not in pg.url:
                        try:
                            await pg.close()
                        except Exception:
                            pass

                # Fermer les modals résiduels
                try:
                    close_btn = dashboard.locator("button:has-text('Fermer')").first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                while True:
                    if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                        break
                    if status["pubs_regardees"] >= CIBLE_PUBS:
                        logger.info(f"Cible de {CIBLE_PUBS} pubs atteinte ! Fin de session.")
                        break

                    num_next = status["pubs_regardees"] + 1
                    status["etat_courant"] = f"Préparation pub #{num_next}..."
                    save_status(status)

                    # Vérifier le bouton et le cooldown
                    btn = dashboard.locator("button:has-text('Gagner des Coins')").first
                    btn_busy = dashboard.locator("text=Prochaine pub dans").first

                    # Si cooldown actif sur la page
                    if await btn_busy.count() > 0 and await btn_busy.is_visible():
                        txt_cooldown = await btn_busy.inner_text()
                        status["etat_courant"] = f"Cooldown actif ({txt_cooldown})..."
                        save_status(status)
                        for _ in range(35):
                            if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                                break
                            if await btn.count() > 0 and await btn.is_enabled():
                                break
                            await asyncio.sleep(1)

                    if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                        break

                    if await btn.count() == 0 or not await btn.is_enabled():
                        logger.info("Bouton non disponible, attente 5s...")
                        status["etat_courant"] = "Attente disponibilité bouton..."
                        save_status(status)
                        await asyncio.sleep(5)
                        continue

                    # Simulation de toucher humain / scroll
                    try:
                        await dashboard.mouse.move(random.randint(200, 600), random.randint(300, 700))
                        await asyncio.sleep(random.uniform(0.8, 1.8))
                    except Exception:
                        pass

                    # Clic sur le bouton de pub
                    status["etat_courant"] = f"Lancement pub #{num_next}..."
                    save_status(status)
                    logger.info(f"Clic pub #{num_next} sur la tablette...")
                    # Clic naturel sur le bouton (gestion overlay Popunder)
                    box = await btn.bounding_box()
                    if box:
                        cx = box["x"] + box["width"] / 2 + random.uniform(-10, 10)
                        cy = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
                        await dashboard.mouse.click(cx, cy)
                    else:
                        await btn.click(force=True)

                    await asyncio.sleep(2.5)

                    # Si le premier clic a déclenché le Popunder transparent, re-cliquer directement sur le bouton
                    body_txt = await dashboard.inner_text("body")
                    if "Patientez" not in body_txt and "Attente" not in body_txt and "s)" not in body_txt:
                        btn_again = dashboard.locator("button:has-text('Gagner des Coins')").first
                        if await btn_again.count() > 0 and await btn_again.is_enabled():
                            logger.info("Popunder Adsterra déclenché sur tablette ! 2e clic direct sur le bouton...")
                            await btn_again.click(force=True)
                            await asyncio.sleep(2)

                    # Repérer l'onglet publicitaire externe
                    ad_tab = None
                    for pg in ctx.pages:
                        if pg != dashboard and "chrome://" not in pg.url:
                            ad_tab = pg
                            break

                    if ad_tab:
                        logger.info(f"Onglet pub externe détecté : {ad_tab.url[:50]}...")
                        try:
                            # Scroll léger sur la pub externe
                            await ad_tab.mouse.wheel(0, random.randint(100, 300))
                        except Exception:
                            pass

                    await dashboard.bring_to_front()

                    # Décompte 30 secondes
                    for s in range(28, 0, -5):
                        if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                            break
                        status["etat_courant"] = f"Visionnage pub #{num_next} ({s}s restantes)..."
                        save_status(status)
                        await asyncio.sleep(5)

                    # Attente de la validation et du modal
                    status["etat_courant"] = f"Validation crédit pub #{num_next}..."
                    save_status(status)

                    reward_ok = False
                    coins_gagnes = 10
                    for _ in range(12):
                        txt = await dashboard.inner_text("body")
                        if "Vibe Coins" in txt and ("créditée" in txt or "Félicitations" in txt or "Fermer" in txt):
                            reward_ok = True
                            if "+1000" in txt:
                                coins_gagnes = 1000
                            break
                        await asyncio.sleep(1)

                    # Fermer l'onglet publicitaire
                    if ad_tab:
                        try:
                            await ad_tab.close()
                            logger.info("Onglet pub fermé.")
                        except Exception:
                            pass

                    # Nettoyer d'autres onglets publicitaires qui auraient pu pop
                    for pg in list(ctx.pages):
                        if pg != dashboard and "chrome://" not in pg.url:
                            try:
                                await pg.close()
                            except Exception:
                                pass

                    # Fermer la fenêtre modale de succès
                    try:
                        close_btn = dashboard.locator("button:has-text('Fermer')").first
                        if await close_btn.count() > 0 and await close_btn.is_visible():
                            await close_btn.click()
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                    # Capture de suivi
                    cap_filename = f"tablet_pub_{num_next}_{datetime.now().strftime('%H%M%S')}.jpg"
                    cap_path = CAPTURES_DIR / cap_filename
                    try:
                        await dashboard.screenshot(path=str(cap_path), type="jpeg", quality=75)
                        status["derniere_capture"] = str(cap_path)
                        if BRAIN_DIR.exists():
                            import shutil
                            shutil.copy2(cap_path, BRAIN_DIR / "tablet_latest_pub.jpg")
                    except Exception:
                        pass

                    if reward_ok:
                        status["pubs_regardees"] += 1
                        status["total_coins"] += coins_gagnes
                        status["total_fcfa"] = status["total_coins"] // 10
                        status["dernier_message"] = f"Pub #{status['pubs_regardees']}/{CIBLE_PUBS} validée (+{coins_gagnes} Coins) !"
                        logger.info(f"Succès ! Pub #{status['pubs_regardees']}/{CIBLE_PUBS} validée (+{coins_gagnes} Coins). Total: {status['total_coins']} Coins.")
                    else:
                        status["dernier_message"] = f"Cycle pub #{num_next} terminé (pas de confirmation explicite)."
                        logger.warning(f"Cycle pub #{num_next} terminé sans détection du modal.")

                    save_status(status)

                    if status["pubs_regardees"] >= CIBLE_PUBS:
                        logger.info(f"Cible de {CIBLE_PUBS} pubs atteinte ! Arrêt immédiat de la session.")
                        break

                    # Pause humaine anti-détection
                    if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                        break

                    pause_s = random.randint(PAUSE_MIN_S, PAUSE_MAX_S)
                    logger.info(f"Pause humaine de {pause_s}s...")
                    for rem in range(pause_s, 0, -5):
                        if check_heure_fin_atteinte(HEURE_FIN, start_dt):
                            break
                        min_rem = rem // 60
                        sec_rem = rem % 60
                        txt_rem = f"{min_rem}m {sec_rem}s" if min_rem > 0 else f"{sec_rem}s"
                        status["etat_courant"] = f"Pause humaine anti-détection ({txt_rem})..."
                        save_status(status)
                        await asyncio.sleep(5)

                await browser.close()
                break

        except Exception as e:
            logger.error(f"Erreur dans la boucle principale: {e}")
            await asyncio.sleep(5)

    status["actif"] = False
    if status["pubs_regardees"] >= CIBLE_PUBS:
        status["etat_courant"] = f"Session terminée avec succès ({CIBLE_PUBS} pubs)."
        status["dernier_message"] = f"Objectif atteint : {status['pubs_regardees']} pubs vues (+{status['total_coins']} Coins)."
    else:
        status["etat_courant"] = f"Session terminée à {datetime.now().strftime('%H:%M')}."
    save_status(status)
    logger.info("Session terminée avec succès.")

if __name__ == "__main__":
    asyncio.run(run_worker())
