from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.api.ask import router as ask_router
from app.api.ws import router as ws_router
from app.api.memory import router as memory_router
from app.api.models import router as models_router
from app.llm.openai_compatible import refresh_llm_config
from app.core.sys_config import refresh_ai_config_cache

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(ask_router)
app.include_router(ws_router)
app.include_router(memory_router)
app.include_router(models_router)


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"success": True, "message": "ok", "database": "connected"}
    except Exception as e:
        return {"success": False, "message": str(e), "database": "disconnected"}


@app.post("/api/admin/reload-config")
def reload_config():
    """Force reload all cached config from database (LLM + sys_config)."""
    refresh_llm_config()
    refresh_ai_config_cache()
    return {"success": True, "message": "config reloaded"}
