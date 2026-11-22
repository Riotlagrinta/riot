import urllib.request
import json
import time
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

print("Watchdog activé : attente de la fin de la 30ème pub...")

while True:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8790/api/studio/vibetg/pubs/statut", timeout=4) as res:
            data = json.loads(res.read().decode())
            prog = data.get("pubs_regardees", 0)
            actif = data.get("actif", True)
            print(f"Progression : {prog}/30 (Actif: {actif})")
            if prog >= 30 or not actif:
                print("Session de 30 pubs terminée ! Transition vers le Mode Nuit...")
                break
    except Exception as e:
        print(f"Erreur vérification: {e}")
    time.sleep(10)

time.sleep(3)

print("Redémarrage de FastAPI avec le Mode Nuit...")
subprocess.run(["powershell", "-Command", "Get-Process python | Where-Object { $_.CommandLine -like '*uvicorn*' } | Stop-Process -Force"], capture_output=True)
time.sleep(2)

proc = subprocess.Popen([
    r"e:\PROJETS\Kéranos\keranos-assistant-vocal-main-1\.venv\Scripts\python.exe",
    "-c",
    "import uvicorn; from core import serveur; uvicorn.run(serveur.app(), host='0.0.0.0', port=8790, log_level='info')"
], cwd=r"e:\PROJETS\Kéranos\keranos-assistant-vocal-main-1")

time.sleep(5)

print("Activation du Mode Nuit (arrêt 09:00)...")
req = urllib.request.Request(
    "http://127.0.0.1:8790/api/studio/vibetg/pubs/mode_nuit",
    data=json.dumps({"heure_fin": "09:00"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=5) as res:
        print("Réponse activation :", res.read().decode())
    print("MODE NUIT OFFICIELLEMENT LANCÉ JUSQU'À 09:00 !")
except Exception as e:
    print(f"Erreur lors de l'appel d'activation: {e}")
