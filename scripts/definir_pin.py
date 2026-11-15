"""Définir (ou changer) le PIN de RIOT — à lancer UNIQUEMENT sur le PC.

    .venv\\Scripts\\python scripts\\definir_pin.py            # définir / changer le PIN
    .venv\\Scripts\\python scripts\\definir_pin.py --revoquer # déconnecter tous les appareils

Le PIN est saisi masqué, haché (scrypt) et jamais affiché ni écrit en clair.
Changer le PIN déconnecte automatiquement tous les appareils.
"""
import getpass
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_RACINE = Path(__file__).resolve().parent.parent
if str(_RACINE) not in sys.path:
    sys.path.insert(0, str(_RACINE))

from core import auth  # noqa: E402


_GETPASS_ORIGINAL = getpass.getpass


def _saisie(invite: str) -> str:
    """Saisie masquée affichant une étoile par caractère (Windows), getpass sinon."""
    try:
        import msvcrt
    except ImportError:
        return _GETPASS_ORIGINAL(invite)
    # Vide les touches parasites déjà en attente (ex. injection du terminal VS Code)
    while msvcrt.kbhit():
        msvcrt.getwch()
    print(invite, end="", flush=True)
    chars: list[str] = []
    while True:
        c = msvcrt.getwch()
        if c in ("\r", "\n"):
            print()
            return "".join(chars)
        if c == "\x03":
            print()
            raise KeyboardInterrupt
        if c == "\x08":
            if chars:
                chars.pop()
                print("\b \b", end="", flush=True)
            continue
        if c in ("\x00", "\xe0"):      # touches spéciales (flèches...) : on ignore
            msvcrt.getwch()
            continue
        if c.isprintable():
            chars.append(c)
            print("*", end="", flush=True)


getpass.getpass = _saisie  # utilisé partout dans main()


def main() -> int:
    if "--revoquer" in sys.argv:
        n = auth.revoquer_tout()
        print(f"[OK] {n} session(s) révoquée(s). Tous les appareils devront ressaisir le PIN.")
        return 0

    print("=== RIOT : définition du PIN ===")
    print(f"Minimum {auth.PIN_MIN} caractères (chiffres, lettres ou phrase). La saisie est masquée.\n")

    if auth.pin_configure():
        actuel = getpass.getpass("PIN actuel : ")
        if not auth.verifier_pin(actuel):
            print("[ERREUR] PIN actuel incorrect.")
            return 1

    for _ in range(3):
        pin = getpass.getpass("Nouveau PIN : ").strip()
        erreur = auth.valider_format_pin(pin)
        if erreur:
            print(f"[REFUSÉ] {erreur}")
            continue
        if getpass.getpass("Confirme le PIN : ").strip() != pin:
            print("[REFUSÉ] Les deux saisies ne correspondent pas.")
            continue
        auth.definir_pin(pin)
        print("\n[OK] PIN enregistré (haché). Tous les anciens appareils ont été déconnectés.")
        return 0

    print("[ABANDON] Trop de tentatives.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ANNULÉ] Aucun changement effectué. Relance la commande pour réessayer.")
        sys.exit(1)
