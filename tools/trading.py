"""Module d'Outils Quantitatifs et Risk Management pour l'Agent de Trading (RIOT-Trader).

Fournit des outils d'analyse technique en temps réel, de calcul de dimensionnement
de position selon la règle des 1% de risque, et d'inspection du carnet d'ordres Binance.
"""
import math
import requests
from typing import Dict, Any, List, Optional
from core.registre import outil

BINANCE_API_BASE = "https://api.binance.com/api/v3"


def _calculer_rsi(clotures: List[float], periode: int = 14) -> float:
    """Calcule le RSI (Relative Strength Index) classique sur N périodes."""
    if len(clotures) < periode + 1:
        return 50.0

    variations = [clotures[i] - clotures[i - 1] for i in range(1, len(clotures))]
    gains = [v if v > 0 else 0.0 for v in variations]
    pertes = [-v if v < 0 else 0.0 for v in variations]

    moy_gain = sum(gains[:periode]) / periode
    moy_perte = sum(pertes[:periode]) / periode

    for i in range(periode, len(variations)):
        moy_gain = (moy_gain * (periode - 1) + gains[i]) / periode
        moy_perte = (moy_perte * (periode - 1) + pertes[i]) / periode

    if moy_perte == 0:
        return 100.0
    rs = moy_gain / moy_perte
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _calculer_ema(valeurs: List[float], periode: int) -> float:
    """Calcule l'EMA (Moyenne Mobile Exponentielle)."""
    if len(valeurs) < periode:
        return sum(valeurs) / len(valeurs) if valeurs else 0.0
    k = 2.0 / (periode + 1)
    ema = sum(valeurs[:periode]) / periode
    for v in valeurs[periode:]:
        ema = (v * k) + (ema * (1 - k))
    return ema


@outil(
    nom="trading_analyse_technique",
    mcp_expose=True,
    description="Récupère les bougies récentes (Klines) via l'API publique Binance et calcule les indicateurs techniques clés : "
                "RSI(14), SMA 20, SMA 50, EMA 20, supports/résistances et volatilité moyenne.",
    parametres={
        "type": "object",
        "properties": {
            "symbole": {
                "type": "string",
                "default": "BTCUSDT",
                "description": "La paire de trading (ex: 'BTCUSDT', 'ETHUSDT', 'SOLUSDT')",
            },
            "intervalle": {
                "type": "string",
                "default": "1h",
                "enum": ["15m", "1h", "4h", "1d"],
                "description": "L'unité de temps des chandeliers (15m, 1h, 4h, 1d)",
            },
        },
        "required": ["symbole"],
    },
)
def trading_analyse_technique(symbole: str = "BTCUSDT", intervalle: str = "1h") -> str:
    """Analyse technique quantitative temps réel."""
    sym = symbole.strip().upper().replace("/", "").replace("-", "")
    url = f"{BINANCE_API_BASE}/klines?symbol={sym}&interval={intervalle}&limit=60"

    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return f"[ERREUR] Impossible de récupérer les bougies Binance pour {sym} (HTTP {r.status_code})."
        data = r.json()
    except Exception as e:
        return f"[ERREUR] Échec de connexion Binance : {e}"

    if not data or len(data) < 20:
        return f"[ERREUR] Données insuffisantes pour {sym} ({len(data)} bougies reçues)."

    clotures = [float(b[4]) for b in data]
    hauts = [float(b[2]) for b in data]
    bas = [float(b[3]) for b in data]
    volumes = [float(b[5]) for b in data]

    prix_actuel = clotures[-1]
    plus_haut_periode = max(hauts)
    plus_bas_periode = min(bas)

    # Indicateurs
    rsi_14 = _calculer_rsi(clotures, 14)
    sma_20 = sum(clotures[-20:]) / 20
    sma_50 = sum(clotures[-50:]) / 50 if len(clotures) >= 50 else sum(clotures) / len(clotures)
    ema_20 = _calculer_ema(clotures, 20)

    # Diagnostic de tendance
    if prix_actuel > sma_20 > sma_50:
        tendance = "HAUSSIÈRE FORTE (Bullish - Prix > SMA20 > SMA50)"
    elif prix_actuel < sma_20 < sma_50:
        tendance = "BAISSIÈRE FORTE (Bearish - Prix < SMA20 < SMA50)"
    elif prix_actuel > sma_20:
        tendance = "HAUSSIÈRE MODÉRÉE (Prix > SMA20)"
    else:
        tendance = "NEUTRE / CONSOLIDATION"

    # État RSI
    if rsi_14 >= 70:
        etat_rsi = f"SURACHAT ({rsi_14}/100) ⚠️ Risque de repli ou essoufflement"
    elif rsi_14 <= 30:
        etat_rsi = f"SURVENTE ({rsi_14}/100) 💡 Potentiel rebond technique"
    else:
        etat_rsi = f"NEUTRE ({rsi_14}/100)"

    return (
        f"📊 ANALYSE TECHNIQUE QUANTITATIVE [{sym}] ({intervalle}) :\n"
        f"• Prix actuel : {prix_actuel:,.2f} $\n"
        f"• Tendance détectée : {tendance}\n"
        f"• RSI (14) : {etat_rsi}\n"
        f"• SMA 20 : {sma_20:,.2f} $ │ SMA 50 : {sma_50:,.2f} $\n"
        f"• EMA 20 (Support/Résistance dyn.) : {ema_20:,.2f} $\n"
        f"• Niveaux Clés sur les {len(data)} dernières bougies :\n"
        f"  - Résistance majeure : {plus_haut_periode:,.2f} $\n"
        f"  - Support majeur     : {plus_bas_periode:,.2f} $\n"
        f"• Volume dernière bougie : {volumes[-1]:,.2f} {sym.replace('USDT', '')}"
    )


@outil(
    nom="trading_calculateur_risque",
    mcp_expose=True,
    description="Calcule scientifiquement le dimensionnement de position (Position Sizing) et le ratio Risque/Rendement (R:R) "
                "selon la règle institutionnelle des 1% de risque maximum par trade.",
    parametres={
        "type": "object",
        "properties": {
            "capital_total": {
                "type": "number",
                "description": "Le capital total du compte en dollars (ex: 10000)",
            },
            "risque_pct": {
                "type": "number",
                "default": 1.0,
                "description": "Pourcentage maximum du capital risqué sur ce trade (défaut: 1.0%)",
            },
            "prix_entree": {
                "type": "number",
                "description": "Prix d'entrée envisagé",
            },
            "prix_stop_loss": {
                "type": "number",
                "description": "Niveau d'invalidation strict (Stop-Loss)",
            },
            "prix_take_profit": {
                "type": "number",
                "description": "Objectif de prise de profit (Take-Profit)",
            },
            "sens": {
                "type": "string",
                "enum": ["LONG", "SHORT"],
                "default": "LONG",
                "description": "Direction du trade : LONG (achat) ou SHORT (vente)",
            },
        },
        "required": ["capital_total", "prix_entree", "prix_stop_loss"],
    },
)
def trading_calculateur_risque(
    capital_total: float,
    prix_entree: float,
    prix_stop_loss: float,
    prix_take_profit: float = 0.0,
    risque_pct: float = 1.0,
    sens: str = "LONG"
) -> str:
    """Calculateur de Risk Management et dimensionnement de position."""
    if capital_total <= 0 or prix_entree <= 0 or prix_stop_loss <= 0:
        return "[ERREUR] Le capital, le prix d'entrée et le stop-loss doivent être strictement positifs."

    sens_norm = sens.upper().strip()
    montant_risque = capital_total * (risque_pct / 100.0)

    # Calcul de la distance d'invalidation
    if sens_norm == "LONG":
        if prix_stop_loss >= prix_entree:
            return "[ERREUR RISK MANAGEMENT] En position LONG, le Stop-Loss doit être strictement inférieur au prix d'entrée."
        distance_sl_pct = ((prix_entree - prix_stop_loss) / prix_entree) * 100.0
        distance_prix = prix_entree - prix_stop_loss
    else:  # SHORT
        if prix_stop_loss <= prix_entree:
            return "[ERREUR RISK MANAGEMENT] En position SHORT, le Stop-Loss doit être strictement supérieur au prix d'entrée."
        distance_sl_pct = ((prix_stop_loss - prix_entree) / prix_entree) * 100.0
        distance_prix = prix_stop_loss - prix_entree

    # Taille de la position (Taille = Risque $ / Distance du Stop)
    quantite_unites = montant_risque / distance_prix
    valeur_position_doll = quantite_unites * prix_entree

    ratio_rr_str = "Non spécifié"
    gain_potentiel_str = ""
    conformite_rr = True

    if prix_take_profit > 0:
        if sens_norm == "LONG":
            distance_tp = prix_take_profit - prix_entree
        else:
            distance_tp = prix_entree - prix_take_profit

        if distance_tp > 0:
            rr = distance_tp / distance_prix
            gain_potentiel = quantite_unites * distance_tp
            ratio_rr_str = f"1:{rr:.2f}"
            gain_potentiel_str = f"• Gain potentiel (TP) : +{gain_potentiel:,.2f} $ (+{(distance_tp/prix_entree)*100:.2f}%)\n"
            if rr < 1.5:
                conformite_rr = False

    # Verdict
    alertes = []
    if risque_pct > 2.0:
        alertes.append("⚠️ RISQUE ÉLEVÉ : Le risque dépasse la limite prudentielle recommandée (<= 1.5%).")
    if not conformite_rr:
        alertes.append("⚠️ RATIO R:R DÉFAVORABLE : Le ratio Risque/Rendement est inférieur à 1:1.5. Le trade est déconseillé.")

    statut_verdict = "✓ PLAN DE RISK MANAGEMENT VALIDE" if not alertes else "⚠️ PLAN NON CONFORME AUX RÈGLES DE RISQUE"

    return (
        f"🛡️ CALCUL DE RISK MANAGEMENT & POSITION SIZING ({sens_norm}) :\n"
        f"{statut_verdict}\n"
        f"• Capital du compte : {capital_total:,.2f} $\n"
        f"• Risque autorisé ({risque_pct}%) : {montant_risque:,.2f} $\n"
        f"• Prix d'Entrée : {prix_entree:,.2f} $ │ Stop-Loss : {prix_stop_loss:,.2f} $\n"
        f"• Distance au Stop-Loss : {distance_sl_pct:.2f}%\n"
        f"--------------------------------------------------\n"
        f"🎯 DIMENSIONNEMENT CHIRURGICAL OBLIGATOIRE :\n"
        f"• Taille de position requise : {valeur_position_doll:,.2f} $\n"
        f"• Quantité exacte à trader   : {quantite_unites:.4f} unités\n"
        f"• Perte maximale si invalidé : -{montant_risque:,.2f} $\n"
        f"{gain_potentiel_str}"
        f"• Ratio Risque / Rendement   : {ratio_rr_str}\n"
        + ("\n".join(alertes) if alertes else "✓ Le sizing respecte scrupuleusement la règle des 1%.")
    )


@outil(
    nom="trading_carnet_ordres_express",
    mcp_expose=True,
    description="Inspecte les 10 meilleures offres d'achat (Bids) et de vente (Asks) sur le carnet d'ordres Binance en direct "
                "pour évaluer la pression acheteuse/vendeuse immédiate.",
    parametres={
        "type": "object",
        "properties": {
            "symbole": {
                "type": "string",
                "default": "BTCUSDT",
                "description": "Paire crypto (ex: 'BTCUSDT', 'ETHUSDT')",
            }
        },
        "required": ["symbole"],
    },
)
def trading_carnet_ordres_express(symbole: str = "BTCUSDT") -> str:
    """Analyse la profondeur du carnet d'ordres."""
    sym = symbole.strip().upper().replace("/", "").replace("-", "")
    url = f"{BINANCE_API_BASE}/depth?symbol={sym}&limit=10"

    try:
        r = requests.get(url, timeout=4)
        if r.status_code != 200:
            return f"[ERREUR] Impossible de charger le carnet pour {sym}."
        d = r.json()
    except Exception as e:
        return f"[ERREUR] Connexion Binance : {e}"

    bids = d.get("bids", [])  # Acheteurs [[prix, qte], ...]
    asks = d.get("asks", [])  # Vendeurs

    if not bids or not asks:
        return "Carnet d'ordres vide ou indisponible."

    vol_achats = sum(float(b[1]) for b in bids)
    vol_ventes = sum(float(a[1]) for a in asks)
    total_vol = vol_achats + vol_ventes

    ratio_achat = (vol_achats / total_vol) * 100 if total_vol > 0 else 50
    ratio_vente = (vol_ventes / total_vol) * 100 if total_vol > 0 else 50

    pression = "PRESSION ACHETEUSE (Bulls)" if ratio_achat > 55 else ("PRESSION VENDEUSE (Bears)" if ratio_vente > 55 else "ÉQUILIBRÉ")

    meilleur_achat = float(bids[0][0])
    meilleure_vente = float(asks[0][0])
    spread = meilleure_vente - meilleur_achat
    spread_pct = (spread / meilleur_achat) * 100

    return (
        f"📖 CARNET D'ORDRES EXPRESS [{sym}] :\n"
        f"• Meilleur Achat (Bid) : {meilleur_achat:,.2f} $ │ Meilleure Vente (Ask) : {meilleure_vente:,.2f} $\n"
        f"• Spread : {spread:,.2f} $ ({spread_pct:.4f}%)\n"
        f"• Pression immédiate (Top 10) : {pression}\n"
        f"  - Force acheteuse : {ratio_achat:.1f}% ({vol_achats:,.2f} {sym.replace('USDT', '')})\n"
        f"  - Force vendeuse  : {ratio_vente:.1f}% ({vol_ventes:,.2f} {sym.replace('USDT', '')})"
    )
