from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import uuid
import logging
import json
from datetime import datetime, timezone
from bridge import EscalaBridge

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

UPLOAD_DIR = "uploads"
CALENDAR_DIR = "calendars"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CALENDAR_DIR, exist_ok=True)

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

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        bridge = EscalaBridge(file_path)
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
    
    logger.info(f"💾 Escala salva. Link gerado: {calendar_url}")
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

# --- SERVIR FRONTEND ---
frontend_dist = os.path.abspath("/app/frontend-dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    @app.exception_handler(404)
    async def custom_404_handler(request, __):
        if request.url.path.startswith("/api"):
            return Response(status_code=404)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    # Reload habilitado para atualizações em tempo real
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
