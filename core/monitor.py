"""Routes locales /monitor et /api/monitor/* pour l'observabilite RIOT (Createur uniquement)."""
from pathlib import Path

from core.llm import est_createur
from core.panneau import _local_seulement
from core.telemetry import store_defaut

_RACINE = Path(__file__).resolve().parent.parent
_HTML = _RACINE / "web" / "monitor.html"


def monter_routes(app) -> None:
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse

    def garde(request: Request):
        if not _local_seulement(request):
            return JSONResponse({"ok": False, "erreur": "Monitor accessible en local uniquement."}, status_code=403)
        if not est_createur():
            return JSONResponse({"ok": False, "erreur": "Acces reserve au mode createur (RIOT_ADMIN=1)."}, status_code=403)
        return None

    @app.get("/monitor", response_class=HTMLResponse)
    def route_monitor(request: Request):
        if (r := garde(request)):
            return r
        if not _HTML.exists():
            return HTMLResponse("<h1>RIOT Monitor</h1><p>web/monitor.html manquant.</p>", status_code=404)
        return HTMLResponse(_HTML.read_text(encoding="utf-8"))

    @app.get("/api/monitor/metrics")
    def route_metrics(request: Request, heures: int = 24):
        if (r := garde(request)):
            return r
        return store_defaut().metriques(heures=heures)

    @app.get("/api/monitor/logs")
    def route_logs(request: Request, limit: int = 80, only_errors: bool = False, q: str = ""):
        if (r := garde(request)):
            return r
        return {"ok": True, "logs": store_defaut().lister_logs(limit=limit, only_errors=only_errors, q=q)}
