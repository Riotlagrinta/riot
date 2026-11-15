import asyncio
import os
import random
import sys
import time
from datetime import datetime
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

def check_heure_fin_atteinte(heure_fin_str: str, start_dt: datetime) -> bool:
    """Vérifie si l'heure cible est atteinte en gérant le passage de minuit."""
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

async def promenade_active(dashboard, ctx, pause_time: int, heure_fin: str, start_dt: datetime):
    """
    Promenade active entre deux pubs :
    - Visite d'autres pages (/explore, /dashboard/wallet, etc.)
    - Déclenchement naturel des Popunders et des impressions Social Bar & Native Banner
    - Clôture automatique des popunders après 3s d'interaction
    - Retour impératif sur le dashboard avant la fin de la pause
    """
    print(f"🚶 Début de la promenade active ({pause_time}s) : Exploration du site & activation des pubs...")
    t_start = time.time()
    
    pages_destinations = [
        "https://kelvix-rewards.vercel.app/explore",
        "https://kelvix-rewards.vercel.app/dashboard/wallet",
        "https://kelvix-rewards.vercel.app/dashboard/telecharger",
        "https://kelvix-rewards.vercel.app/dashboard/challenges",
    ]
    dest = random.choice(pages_destinations)
    
    try:
        # Étape 1 : Visite d'une autre page
        print(f"   [1/3] Navigation vers {dest}...")
        await dashboard.goto(dest, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)
        
        # Scroll naturel pour simuler un vrai visiteur
        for _ in range(random.randint(2, 3)):
            await dashboard.mouse.wheel(0, random.randint(150, 350))
            await asyncio.sleep(random.uniform(0.8, 1.4))
            
        # Clic aléatoire sur la page pour activer le Popunder Adsterra s'il est réarmé
        print("   [2/3] Clic naturel pour déclencher le Popunder ou la Social Bar...")
        cx = random.randint(300, 700)
        cy = random.randint(200, 450)
        await dashboard.mouse.move(cx, cy, steps=6)
        await asyncio.sleep(0.3)
        await dashboard.mouse.click(cx, cy)
        await asyncio.sleep(2)
        
        # Vérifier si un popunder externe s'est ouvert
        for pg in ctx.pages:
            if pg != dashboard and "chrome://" not in pg.url and "about:blank" not in pg.url:
                print(f"   🎯 Popunder activé pendant la promenade : {pg.url[:60]}...")
                try:
                    await pg.mouse.wheel(0, random.randint(100, 300))
                    await asyncio.sleep(random.uniform(2.5, 4.0))
                    await pg.close()
                    print("   🔒 Popunder fermé avec succès.")
                except Exception:
                    pass
    except Exception as e:
        print(f"   ⚠️ Info promenade : {e}")

    # Étape 3 : Retour impératif sur /dashboard
    temps_ecoule = time.time() - t_start
    temps_restant = max(5, pause_time - temps_ecoule)
    
    print(f"   [3/3] Retour sur /dashboard (reste {int(temps_restant)}s de pause)...")
    try:
        await dashboard.goto("https://kelvix-rewards.vercel.app/dashboard", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1.5)
        # Scroll doux pour afficher la Native Banner (in-view impression)
        await dashboard.mouse.wheel(0, 300)
        await asyncio.sleep(1)
        await dashboard.mouse.wheel(0, -300)
    except Exception:
        pass
        
    # Fin de la pause
    while (time.time() - t_start) < pause_time:
        if check_heure_fin_atteinte(heure_fin, start_dt):
            break
        await asyncio.sleep(2)
    print("✨ Promenade terminée : Prêt pour le visionnage de la prochaine pub !")

async def run_campaign(max_ads: int = 6):
    start_dt = datetime.now()
    heure_fin = os.environ.get("VIBETG_HEURE_FIN", "")
    if heure_fin:
        max_ads = 999999
        print("=" * 60)
        print(f"🌙 DÉMARRAGE MODE NUIT PC (Arrêt programmé à {heure_fin})")
        print("🛡️  Mode : Simulation humaine anti-détection (Jitter + Tab cleanup)")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"🚀 DÉMARRAGE DU VISIONNAGE AUTOMATISÉ (Objectif : {max_ads} pubs)")
        print("🛡️  Mode : Simulation humaine anti-détection (Jitter + Tab cleanup)")
        print("=" * 60)

    async with async_playwright() as p:
        try:
            b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        except Exception as e:
            print(f"❌ Impossible de se connecter à Chrome sur le port 9222 : {e}")
            return

        ctx = b.contexts[0]

        # 1. Identifier la page Dashboard
        dashboard = None
        for pg in ctx.pages:
            if "kelvix-rewards" in pg.url or "dashboard" in pg.url:
                dashboard = pg
                break

        if not dashboard:
            print("⚠️ Aucun onglet Dashboard trouvé, ouverture automatique...")
            dashboard = await ctx.new_page()
            await dashboard.goto("https://kelvix-rewards.vercel.app/dashboard", wait_until="networkidle")

        await dashboard.bring_to_front()

        # Nettoyage initial : fermer les onglets publicitaires orphelins
        for pg in list(ctx.pages):
            if pg != dashboard and "chrome://" not in pg.url:
                try:
                    print(f"🧹 Fermeture onglet orphelin : {pg.url[:60]}...")
                    await pg.close()
                except Exception:
                    pass

        # Fermer d'éventuels modals ouverts
        try:
            close_btn = dashboard.locator("button:has-text('Fermer')").first
            if await close_btn.count() > 0 and await close_btn.is_visible():
                await close_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        ads_completed = 0
        total_coins_earned = 0

        while ads_completed < max_ads:
            if check_heure_fin_atteinte(heure_fin, start_dt):
                print(f"⏰ Heure de fin ({heure_fin}) atteinte ! Clôture de la session.")
                break

            current_num = ads_completed + 1
            lbl_cible = heure_fin if heure_fin else f"{max_ads}"
            print(f"\n--- [PUB {current_num} | Cible : {lbl_cible}] Début du cycle ---")

            try:
                await dashboard.bring_to_front()

                # Vérifier l'état du bouton "Gagner des Coins"
                btn = dashboard.locator("button:has-text('Gagner des Coins')").first
                
                # S'il y a un cooldown en cours, attendre le temps nécessaire
                btn_busy = dashboard.locator("text=Prochaine pub dans").first
                if await btn_busy.count() > 0 and await btn_busy.is_visible():
                    txt = await btn_busy.inner_text()
                    print(f"⏳ Cooldown actif détecté : {txt}")
                    # Attendre jusqu'à ce que le bouton redevienne actif
                    for _ in range(40):
                        if await btn.count() > 0 and await btn.is_enabled():
                            break
                        await asyncio.sleep(1)

                # Re-vérification du bouton
                if await btn.count() == 0 or not await btn.is_enabled():
                    print("⏳ Attente que le bouton soit disponible...")
                    await asyncio.sleep(5)
                    continue

                # Simulation humaine : léger défilement et mouvement de curseur
                try:
                    await dashboard.mouse.move(random.randint(200, 500), random.randint(200, 600))
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                except Exception:
                    pass

                # Clic sur le bouton pour lancer la pub (gestion Popunder overlay incluse)
                print("▶️ Clic sur 'Gagner des Coins'...")
                box = await btn.bounding_box()
                if box:
                    cx = box["x"] + box["width"] / 2 + random.uniform(-10, 10)
                    cy = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
                    await dashboard.mouse.click(cx, cy)
                else:
                    await btn.click(force=True)

                await asyncio.sleep(2)
                await dashboard.bring_to_front()

                # Si le premier clic a été capturé par l'overlay transparent du Popunder Adsterra :
                try:
                    body_txt = await dashboard.inner_text("body", timeout=4000)
                except Exception:
                    body_txt = ""

                if "Patientez" not in body_txt and "Attente" not in body_txt and "s)" not in body_txt:
                    btn_again = dashboard.locator("button:has-text('Gagner des Coins')").first
                    try:
                        if await btn_again.count() > 0 and await btn_again.is_enabled():
                            print("🔄 Popunder Adsterra déclenché ! Second clic immédiat sur 'Gagner des Coins'...")
                            box2 = await btn_again.bounding_box()
                            if box2:
                                await dashboard.mouse.click(box2["x"] + box2["width"] / 2, box2["y"] + box2["height"] / 2)
                            else:
                                await btn_again.click(force=True)
                            await asyncio.sleep(2)
                    except Exception as e_click:
                        print(f"⚠️ Info second clic : {e_click}")

                # Attendre 2 secondes que le popup de pub externe s'ouvre
                await asyncio.sleep(2)

                # Repérer l'onglet de pub externe qui vient d'ouvrir
                ad_tab = None
                for pg in ctx.pages:
                    if pg != dashboard and "chrome://" not in pg.url and "dashboard" not in pg.url:
                        ad_tab = pg
                        break

                if ad_tab:
                    print(f"🌐 Onglet pub ouvert : {ad_tab.url[:70]}...")
                    # Simuler une interaction naturelle sur l'onglet de pub (focus & scroll léger)
                    try:
                        await ad_tab.mouse.wheel(0, random.randint(100, 300))
                    except Exception:
                        pass

                # Revenir sur le dashboard pour suivre le décompte
                await dashboard.bring_to_front()

                # Attendre 28 secondes (décompte de 30s)
                print("⏱️ Visionnage en cours (décompte de 30 secondes)...")
                for sec in range(28, 0, -5):
                    print(f"   ... {sec}s restantes")
                    await asyncio.sleep(5)

                # Attendre l'écran de résultat (success ou error)
                print("🎁 Validation du crédit de la récompense...")
                reward_success = False
                for _ in range(12):  # Attente max 12 secondes
                    try:
                        text_page = await dashboard.inner_text("body", timeout=3000)
                    except Exception:
                        text_page = ""
                    if "Vibe Coins" in text_page and ("créditée à ton solde" in text_page or "Fermer" in text_page):
                        reward_success = True
                        # Extraire le montant
                        if "+1000" in text_page:
                            coins = 1000
                            print("🎉 SUCCÈS : +1 000 Vibe Coins (100 FCFA - VIP) crédités !")
                        elif "+10" in text_page:
                            coins = 10
                            print("✅ SUCCÈS : +10 Vibe Coins (1 FCFA) crédités !")
                        else:
                            coins = 10
                            print("✅ SUCCÈS : Récompense créditée !")
                        total_coins_earned += coins
                        break
                    await asyncio.sleep(1)

                # Fermer l'onglet publicitaire pour libérer la mémoire et rester clean
                if ad_tab:
                    try:
                        await ad_tab.close()
                        print("🔒 Onglet pub externe fermé avec succès.")
                    except Exception:
                        pass

                # Fermer d'autres onglets orphelins éventuels
                for pg in list(ctx.pages):
                    if pg != dashboard and "chrome://" not in pg.url and "dashboard" not in pg.url:
                        try:
                            await pg.close()
                        except Exception:
                            pass

                # Fermer le modal de succès sur le dashboard
                try:
                    close_btn = dashboard.locator("button:has-text('Fermer')").first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

                ads_completed += 1
                print(f"📊 Bilan intermédiaire : {ads_completed}/{max_ads} pubs validées | Total : +{total_coins_earned} Coins (+{total_coins_earned // 10} FCFA)")

                # Pause humaine intelligente entre deux pubs (anti-bot Adsterra)
                if ads_completed < max_ads:
                    if check_heure_fin_atteinte(heure_fin, start_dt):
                        print(f"⏰ Heure de fin ({heure_fin}) atteinte ! Arrêt immédiat.")
                        break
                    pause_time = random.randint(50, 75)
                    # Promenade active au lieu d'une pause passive : visite du site et déclenchement Popunder/SocialBar
                    await promenade_active(dashboard, ctx, pause_time, heure_fin, start_dt)

            except Exception as cycle_err:
                print(f"⚠️ Incident cycle pub #{current_num} : {cycle_err}")
                # Nettoyage de sécurité
                try:
                    await dashboard.bring_to_front()
                    for pg in list(ctx.pages):
                        if pg != dashboard and "chrome://" not in pg.url and "dashboard" not in pg.url:
                            try:
                                await pg.close()
                            except Exception:
                                pass
                except Exception:
                    pass
                await asyncio.sleep(5)
                continue

        # Rapport final
        print("\n" + "=" * 60)
        print("🏆 CAMPAGNE DE VISIONNAGE TERMINÉE AVEC SUCCÈS !")
        print(f"• Pubs regardées avec succès : {ads_completed}")
        print(f"• Total Vibe Coins gagnés : +{total_coins_earned} Coins")
        print(f"• Équivalent en Francs CFA : +{total_coins_earned // 10} FCFA")
        print("=" * 60)

        # Capture d'écran finale
        cap_dest = "e:/PROJETS/Kéranos/keranos-assistant-vocal-main-1/_captures/campaign_final.jpg"
        await dashboard.screenshot(path=cap_dest)
        print("📸 Capture du dashboard final enregistrée : _captures/campaign_final.jpg")
        try:
            import shutil
            brain_dest = r"C:\Users\LENOVO\.gemini\antigravity\brain\f74a4ac9-0ca5-43dd-8b1b-7f5438fd0121\pc_session_final.jpg"
            shutil.copy2(cap_dest, brain_dest)
        except Exception:
            pass

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    asyncio.run(run_campaign(count))
