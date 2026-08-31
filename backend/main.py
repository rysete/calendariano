from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import uuid
import logging
import json
import sys
from datetime import datetime, timezone
try:
    from .bridge import EscalaBridge
    from . import google_calendar
except ImportError:
    from bridge import EscalaBridge
    import google_calendar

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Escala Web Editor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

def get_writable_dir(env_var: str, default_subfolder: str) -> str:
    env_val = os.getenv(env_var)
    if env_val:
        os.makedirs(env_val, exist_ok=True)
        return env_val
    # Tenta criar no BASE_DIR se for gravável
    local_path = os.path.join(BASE_DIR, default_subfolder)
    try:
        os.makedirs(local_path, exist_ok=True)
        # Testar escrita
        test_file = os.path.join(local_path, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return local_path
    except (OSError, PermissionError):
        pass

    # Se for Flatpak ou read-only (/app/share), usar XDG_DATA_HOME ou /tmp
    data_home = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    user_path = os.path.join(data_home, "escala-web-editor", default_subfolder)
    try:
        os.makedirs(user_path, exist_ok=True)
        return user_path
    except (OSError, PermissionError):
        tmp_path = os.path.join("/tmp/escala-web-editor", default_subfolder)
        os.makedirs(tmp_path, exist_ok=True)
        return tmp_path

UPLOAD_DIR = get_writable_dir("UPLOAD_DIR", "uploads")
CALENDAR_DIR = get_writable_dir("CALENDAR_DIR", "calendars")

sessions = {}

class EscalaItem(BaseModel):
    date: str
    day: int
    weekday: str
    status: str
    start_time: str
    end_time: str

class EscalaUpdate(BaseModel):
    name: str
    turno: str
    month_name: str
    escala: List[EscalaItem]

class GoogleSyncRequest(BaseModel):
    calendar_id: str = "primary"
    escala: EscalaUpdate

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), col_nome: int = 0):
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        bridge = EscalaBridge(file_path, col_nome=col_nome)
        sessions[file_id] = bridge
        return {"file_id": file_id, "months": bridge.get_months()}
    except Exception as e:
        logger.error(f"Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/months")
async def get_months():
    return EscalaBridge().get_months()

@app.get("/api/turnos")
async def get_turnos():
    return EscalaBridge().get_turnos()

@app.get("/api/employees/{file_id}/{month_id}")
async def get_employees(file_id: str, month_id: str):
    if file_id not in sessions: raise HTTPException(status_code=404)
    return sessions[file_id].get_employees(month_id)

@app.get("/api/escala/{file_id}/{month_id}/{employee_id}")
async def get_escala(file_id: str, month_id: str, employee_id: int):
    if file_id not in sessions: raise HTTPException(status_code=404)
    return sessions[file_id].get_escala(month_id, employee_id)

@app.post("/api/export/csv")
async def export_csv(data: EscalaUpdate):
    return Response(content=EscalaBridge().generate_csv_content(data.dict()), media_type="text/csv")

@app.post("/api/escala/save-link")
async def save_escala_link(data: EscalaUpdate, request: Request):
    safe_name = "".join([c if c.isalnum() else "_" for c in data.name.lower()]).strip("_")
    file_path = os.path.join(CALENDAR_DIR, f"{safe_name}.json")
    
    with open(file_path, "w") as f:
        json.dump(data.dict(), f)
    
    # DETECÇÃO DINÂMICA DA URL:
    # Se você acessa via tunnel, o link gerado usa o domínio do tunnel.
    base_url = str(request.base_url).rstrip('/')
    calendar_url = f"{base_url}/api/calendar/{safe_name}.ics"
    
    logger.info(f"Escala salva. Link gerado: {calendar_url}")
    return {"link_id": safe_name, "url": calendar_url}

@app.get("/api/calendar/{link_id}.ics")
async def get_calendar_ics(link_id: str):
    safe_id = link_id.replace(".ics", "")
    file_path = os.path.join(CALENDAR_DIR, f"{safe_id}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404)
    
    with open(file_path, "r") as f:
        data = json.load(f)
    
    mtime = os.path.getmtime(file_path)
    last_modified = datetime.fromtimestamp(mtime, timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    return Response(
        content=EscalaBridge().generate_ics_content(data), 
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": f'W/"{int(mtime)}"',
            "Last-Modified": last_modified,
            "X-WR-CALNAME": f"Escala {data.get('name')}"
        }
    )

@app.get("/api/google/status")
async def google_status(request: Request):
    return google_calendar.status(request)

@app.post("/api/google/credentials")
async def upload_google_credentials(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Envie o arquivo OAuth client JSON do Google.")

    content = await file.read()
    try:
        parsed = json.loads(content.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalido: {exc}") from exc

    if "web" not in parsed and "installed" not in parsed:
        raise HTTPException(status_code=400, detail="O JSON precisa conter a chave 'web' ou 'installed'.")

    google_calendar.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    google_calendar.CREDENTIALS_FILE.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(google_calendar.CREDENTIALS_FILE)}

@app.get("/api/google/auth-url")
async def google_auth_url(request: Request):
    try:
        return google_calendar.auth_url(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(f"<h1>Google Calendar</h1><p>Autorizacao cancelada: {error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h1>Google Calendar</h1><p>Codigo OAuth ausente.</p>", status_code=400)

    try:
        google_calendar.finish_oauth(request, code, state)
    except Exception as exc:
        return HTMLResponse(f"<h1>Google Calendar</h1><p>Erro ao conectar: {exc}</p>", status_code=400)

    return HTMLResponse(
        """
        <h1>Google Calendar conectado</h1>
        <p>Voce ja pode voltar ao Escala Web Editor e sincronizar a escala.</p>
        <script>setTimeout(() => window.close(), 1200)</script>
        """
    )

@app.get("/api/google/calendars")
async def google_calendars():
    try:
        return google_calendar.list_calendars()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/google/sync")
async def google_sync(data: GoogleSyncRequest):
    try:
        return google_calendar.sync_escala(data.escala.dict(), calendar_id=data.calendar_id or "primary")
    except Exception as exc:
        logger.exception("Erro ao sincronizar com Google Calendar")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# --- SERVIR FRONTEND ---
frontend_dist = os.getenv("FRONTEND_DIST")
if not frontend_dist:
    candidates = [
        os.path.abspath("/app/frontend-dist"),
        os.path.join(PROJECT_DIR, "frontend", "dist"),
    ]
    frontend_dist = next((path for path in candidates if os.path.exists(path)), candidates[-1])

if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    @app.exception_handler(404)
    async def custom_404_handler(request, __):
        if request.url.path.startswith("/api"):
            return Response(status_code=404)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("ESCALA_WEB_EDITOR_PORT", 8001)))
    reload_enabled = os.getenv("UVICORN_RELOAD", "1").strip().lower() in {"1", "true", "yes", "on"}
    app_ref = "backend.main:app" if os.path.exists(os.path.join(PROJECT_DIR, "backend", "main.py")) else "main:app"
    uvicorn.run(app_ref, host=host, port=port, reload=reload_enabled)
