import urllib.request
import json

try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3) as response:
        tabs = json.loads(response.read().decode())
        print(f"Connexion CDP RÉUSSIE ! {len(tabs)} onglets trouvés :")
        for t in tabs:
            if t.get("type") == "page":
                print(f"  • {t.get('title')} | URL: {t.get('url')[:60]}")
except Exception as e:
    print(f"PORT_9222_ERREUR: {e}")
