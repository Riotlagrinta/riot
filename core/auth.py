"""Authentification de RIOT : PIN haché, sessions révocables, anti-force brute.

- Le PIN n'est JAMAIS stocké en clair : hachage scrypt + sel aléatoire.
- Le client reçoit un jeton de session aléatoire (jamais le PIN).
  Seule l'empreinte SHA-256 du jeton est conservée sur disque.
- Verrouillage après trop d'échecs (par IP + verrou global, utile derrière un tunnel
  où toutes les requêtes semblent venir de 127.0.0.1).
- Sans PIN configuré, TOUT accès distant est refusé (fail-closed).

Le PIN se définit uniquement en local : `python scripts/definir_pin.py`.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

_RACINE = Path(__file__).resolve().parent.parent
FICHIER = _RACINE / "securite.json"          # ignoré par git
AUDIT = _RACINE / "logs" / "audit.log"

PIN_MIN = 6
PIN_MAX = 64
DUREE_SESSION = 30 * 86400                   # 30 jours
MAX_ECHECS_IP = 5
MAX_ECHECS_GLOBAL = 15
DUREE_BLOCAGE = 15 * 60                      # 15 minutes

_VERROU = threading.Lock()
_echecs: dict[str, list[float]] = {}         # cle (ip ou "*") -> horodatages d'échecs
_bloque_jusqua: dict[str, float] = {}


# ------------------------------------------------------------------ stockage

def _lire() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ecrire(data: dict) -> None:
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(FICHIER)


def audit(evenement: str, ip: str = "-", detail: str = "") -> None:
    """Trace les événements sensibles (connexions, commandes, échecs)."""
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        ligne = f"{datetime.now().isoformat(timespec='seconds')}\t{ip}\t{evenement}\t{detail[:500]}\n"
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(ligne)
    except Exception:
        pass


# ------------------------------------------------------------------ PIN

def _hacher(pin: str, sel: bytes) -> str:
    return hashlib.scrypt(pin.encode("utf-8"), salt=sel, n=2 ** 14, r=8, p=1, dklen=32).hex()


def pin_configure() -> bool:
    return bool(_lire().get("pin_hash"))


def valider_format_pin(pin: str) -> str | None:
    """Retourne un message d'erreur, ou None si le PIN est acceptable."""
    if len(pin) < PIN_MIN:
        return f"Le PIN doit faire au moins {PIN_MIN} caractères."
    if len(pin) > PIN_MAX:
        return f"Le PIN doit faire au plus {PIN_MAX} caractères."
    if len(set(pin)) == 1:
        return "Le PIN ne peut pas être un seul caractère répété."
    if pin in "01234567890123456789" or pin in "98765432109876543210":
        return "Le PIN ne peut pas être une suite (123456, 987654...)."
    return None


def definir_pin(pin: str) -> None:
    """Enregistre un nouveau PIN (haché) et révoque toutes les sessions existantes."""
    erreur = valider_format_pin(pin)
    if erreur:
        raise ValueError(erreur)
    sel = secrets.token_bytes(16)
    with _VERROU:
        _ecrire({"pin_sel": sel.hex(), "pin_hash": _hacher(pin, sel), "sessions": {}})
    audit("PIN_DEFINI", "local")


def verifier_pin(pin: str) -> bool:
    data = _lire()
    if not data.get("pin_hash"):
        return False
    calcule = _hacher(pin, bytes.fromhex(data["pin_sel"]))
    return hmac.compare_digest(calcule, data["pin_hash"])


# ------------------------------------------------------------------ anti-force brute

def _purger(cle: str, maintenant: float) -> list[float]:
    liste = [t for t in _echecs.get(cle, []) if maintenant - t < DUREE_BLOCAGE]
    _echecs[cle] = liste
    return liste


def secondes_blocage(ip: str) -> int:
    """Secondes restantes de blocage pour cette IP (ou globalement), 0 sinon."""
    maintenant = time.time()
    with _VERROU:
        restant = max(_bloque_jusqua.get(ip, 0), _bloque_jusqua.get("*", 0)) - maintenant
    return max(0, int(restant))


def _noter_echec(ip: str) -> None:
    maintenant = time.time()
    with _VERROU:
        for cle, maxi in ((ip, MAX_ECHECS_IP), ("*", MAX_ECHECS_GLOBAL)):
            liste = _purger(cle, maintenant)
            liste.append(maintenant)
            if len(liste) >= maxi:
                _bloque_jusqua[cle] = maintenant + DUREE_BLOCAGE
                _echecs[cle] = []
                audit("BLOCAGE", ip, f"cle={cle}")


def _reinitialiser(ip: str) -> None:
    with _VERROU:
        _echecs.pop(ip, None)


# ------------------------------------------------------------------ sessions

def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def creer_session(ip: str = "-") -> str:
    jeton = secrets.token_urlsafe(32)
    maintenant = time.time()
    with _VERROU:
        data = _lire()
        sessions = {k: v for k, v in data.get("sessions", {}).items() if v.get("expire", 0) > maintenant}
        sessions[_empreinte(jeton)] = {"expire": maintenant + DUREE_SESSION, "ip": ip,
                                        "cree": datetime.now().isoformat(timespec="seconds")}
        data["sessions"] = sessions
        _ecrire(data)
    return jeton


def session_valide(jeton: str) -> bool:
    if not jeton or not pin_configure():
        return False
    s = _lire().get("sessions", {}).get(_empreinte(jeton))
    return bool(s) and s.get("expire", 0) > time.time()


def revoquer_session(jeton: str) -> None:
    with _VERROU:
        data = _lire()
        data.get("sessions", {}).pop(_empreinte(jeton), None)
        _ecrire(data)


def revoquer_tout() -> int:
    with _VERROU:
        data = _lire()
        n = len(data.get("sessions", {}))
        data["sessions"] = {}
        _ecrire(data)
    audit("SESSIONS_REVOQUEES", "local", f"n={n}")
    return n


def connexion(pin: str, ip: str) -> tuple[bool, str, int]:
    """Tente une connexion. Retourne (ok, jeton_ou_message, code_http)."""
    if not pin_configure():
        return False, "Aucun PIN configuré. Sur le PC : python scripts/definir_pin.py", 503
    attente = secondes_blocage(ip)
    if attente:
        return False, f"Trop d'essais. Réessaie dans {attente // 60 + 1} min.", 429
    if verifier_pin(pin):
        _reinitialiser(ip)
        audit("CONNEXION_OK", ip)
        return True, creer_session(ip), 200
    _noter_echec(ip)
    audit("CONNEXION_ECHEC", ip)
    return False, "Code PIN incorrect.", 401
