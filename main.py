from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="AgriRAG")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
app.mount("/archive", StaticFiles(directory=ROOT / "dist", html=True), name="archive")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def farmer_interface():
    return FileResponse(FRONTEND / "index.html", media_type="text/html")
