import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

from ndi_service import NDI_AVAILABLE, ndi_service
import layout_store


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


app = FastAPI(title="NDI Multiview API")
api_router = APIRouter(prefix="/api")


# ---------- Models ----------

class SourceOut(BaseModel):
    id: str
    name: str
    is_demo: bool
    connected: bool
    fps: float
    width: int
    height: int


class TileConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    source_id: Optional[str] = None
    x: float
    y: float
    width: float
    height: float
    z: int = 0


class LayoutIn(BaseModel):
    name: str
    tiles: List[TileConfig] = Field(default_factory=list)


class LayoutOut(LayoutIn):
    id: str
    created_at: str
    updated_at: str


class ConfigOut(BaseModel):
    ndi_available: bool
    mode: str
    version: str = "1.0.0"
    data_dir: str = ""


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_layout(doc: Dict[str, Any]) -> LayoutOut:
    return LayoutOut(
        id=doc["id"],
        name=doc["name"],
        tiles=[TileConfig(**t) for t in doc.get("tiles", [])],
        created_at=doc.get("created_at", _now_iso()),
        updated_at=doc.get("updated_at", _now_iso()),
    )


# ---------- Endpoints ----------

@api_router.get("/")
async def root():
    return {"message": "NDI Multiview API", "mode": ndi_service.mode}


@api_router.get("/config", response_model=ConfigOut)
async def get_config():
    return ConfigOut(
        ndi_available=NDI_AVAILABLE,
        mode=ndi_service.mode,
        data_dir=str(layout_store.DATA_DIR),
    )


@api_router.get("/sources", response_model=List[SourceOut])
async def list_sources(refresh: bool = False):
    ndi_service.refresh(force=refresh)
    return [
        SourceOut(
            id=s.id,
            name=s.name,
            is_demo=s.is_demo,
            connected=s.connected,
            fps=round(s.fps, 1),
            width=s.width,
            height=s.height,
        )
        for s in ndi_service.list_sources()
    ]


@api_router.post("/sources/refresh", response_model=List[SourceOut])
async def refresh_sources():
    return await list_sources(refresh=True)


@api_router.get("/stream/{source_id}")
async def stream_source(source_id: str):
    info = ndi_service.get_source(source_id)
    if info is None:
        ndi_service.refresh(force=True)
        info = ndi_service.get_source(source_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return StreamingResponse(
        ndi_service.mjpeg_stream(source_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


# ---------- Layouts CRUD (JSON store, no DB required) ----------

@api_router.get("/layouts", response_model=List[LayoutOut])
async def list_layouts():
    return [_serialize_layout(d) for d in layout_store.list_layouts()]


@api_router.post("/layouts", response_model=LayoutOut)
async def create_layout(payload: LayoutIn):
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "tiles": [t.model_dump() for t in payload.tiles],
    }
    doc = layout_store.create_layout(doc)
    return _serialize_layout(doc)


@api_router.get("/layouts/{layout_id}", response_model=LayoutOut)
async def get_layout(layout_id: str):
    doc = layout_store.get_layout(layout_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Layout not found")
    return _serialize_layout(doc)


@api_router.put("/layouts/{layout_id}", response_model=LayoutOut)
async def update_layout(layout_id: str, payload: LayoutIn):
    patch = {
        "name": payload.name,
        "tiles": [t.model_dump() for t in payload.tiles],
    }
    doc = layout_store.update_layout(layout_id, patch)
    if not doc:
        raise HTTPException(status_code=404, detail="Layout not found")
    return _serialize_layout(doc)


@api_router.delete("/layouts/{layout_id}")
async def delete_layout(layout_id: str):
    ok = layout_store.delete_layout(layout_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Layout not found")
    return {"ok": True}


app.include_router(api_router)


# ---------- CORS ----------

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Static frontend (for packaged .exe) ----------

def _resolve_frontend_dir() -> Optional[Path]:
    # 1) Explicit override
    env_dir = os.environ.get("NDI_FRONTEND_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    # 2) When frozen by PyInstaller, files are unpacked to _MEIPASS
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        candidate = meipass / "frontend_build"
        if candidate.exists():
            return candidate
    # 3) Alongside the executable / source
    for candidate in [
        ROOT_DIR / "frontend_build",
        ROOT_DIR.parent / "frontend" / "build",
    ]:
        if candidate.exists():
            return candidate
    return None


_frontend_dir = _resolve_frontend_dir()
if _frontend_dir is not None:
    # Serve JS/CSS assets
    assets_dir = _frontend_dir / "static"
    if assets_dir.exists():
        app.mount("/static", StaticFiles(directory=str(assets_dir)), name="static")

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        # Never intercept API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = _frontend_dir / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        index_html = _frontend_dir / "index.html"
        if index_html.exists():
            return FileResponse(index_html)
        raise HTTPException(status_code=404)


# ---------- Lifecycle ----------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def _startup():
    ndi_service.refresh(force=True)
    logger.info(
        "NDI Multiview API up. mode=%s ndi_available=%s data_dir=%s frontend=%s",
        ndi_service.mode,
        NDI_AVAILABLE,
        layout_store.DATA_DIR,
        _frontend_dir or "(none)",
    )


@app.on_event("shutdown")
async def _shutdown():
    ndi_service.shutdown()
