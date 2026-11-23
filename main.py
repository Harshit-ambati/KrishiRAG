import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from advisory_api import demos_enabled, router as advisory_router
from advisory_feedback import router as feedback_router
from evidence_admin import admin as evidence_admin_router, public as evidence_router
from evidence_index import MODEL_FILES, collection, model_directory
from evidence_store import PUBLISHED_PASSAGES, database_path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AgriRAG")
app.include_router(advisory_router)
app.include_router(feedback_router)
app.include_router(evidence_admin_router)
app.include_router(evidence_router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
if demos_enabled():
    app.mount("/archive", StaticFiles(directory=ROOT / "dist", html=True), name="archive")


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path == "/admin" or request.url.path.startswith(("/api/admin/", "/api/advisories")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def farmer_interface():
    return FileResponse(FRONTEND / "index.html", media_type="text/html")


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readiness():
    if not all((model_directory() / name).is_file() for name in MODEL_FILES):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    try:
        with closing(sqlite3.connect(database_path().resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
            connection.execute(PUBLISHED_PASSAGES + " LIMIT 1").fetchone()
        collection().count()
        return {"status": "ready"}
    except Exception:
        logger.exception("Evidence readiness check failed")
    return JSONResponse({"status": "not_ready"}, status_code=503)
