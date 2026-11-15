import psutil

found = False
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    if p.info['name'] and 'chrome' in p.info['name'].lower():
        cmd = p.info['cmdline'] or []
        cmd_str = " ".join(cmd)
        if "remote-debugging-port" in cmd_str:
            print(f"Trouvé Chrome avec port de debug (PID {p.info['pid']})")
            found = True
            break

if not found:
    print("AUCUN Chrome n'a le drapeau --remote-debugging-port actif.")
    print("Raison : Chrome n'était pas complètement fermé avant de lancer le .bat (il restait des processus Chrome d'arrière-plan).")
