from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from advisory_api import router as advisory_router

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="AgriRAG")
app.include_router(advisory_router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
app.mount("/archive", StaticFiles(directory=ROOT / "dist", html=True), name="archive")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def farmer_interface():
    return FileResponse(FRONTEND / "index.html", media_type="text/html")
