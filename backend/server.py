from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from ndi_service import ndi_service, NDI_AVAILABLE


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

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


# ---------- Endpoints ----------

@api_router.get("/")
async def root():
    return {"message": "NDI Multiview API", "mode": ndi_service.mode}


@api_router.get("/config", response_model=ConfigOut)
async def get_config():
    return ConfigOut(ndi_available=NDI_AVAILABLE, mode=ndi_service.mode)


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
    ndi_service.refresh(force=True)
    return await list_sources(refresh=False)


@api_router.get("/stream/{source_id}")
async def stream_source(source_id: str):
    info = ndi_service.get_source(source_id)
    if info is None:
        # Try a refresh in case it just showed up
        ndi_service.refresh(force=True)
        info = ndi_service.get_source(source_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return StreamingResponse(
        ndi_service.mjpeg_stream(source_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


# ---------- Layouts CRUD ----------

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


@api_router.get("/layouts", response_model=List[LayoutOut])
async def list_layouts():
    docs = await db.layouts.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return [_serialize_layout(d) for d in docs]


@api_router.post("/layouts", response_model=LayoutOut)
async def create_layout(payload: LayoutIn):
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "tiles": [t.model_dump() for t in payload.tiles],
        "created_at": now,
        "updated_at": now,
    }
    await db.layouts.insert_one(doc)
    return _serialize_layout(doc)


@api_router.get("/layouts/{layout_id}", response_model=LayoutOut)
async def get_layout(layout_id: str):
    doc = await db.layouts.find_one({"id": layout_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Layout not found")
    return _serialize_layout(doc)


@api_router.put("/layouts/{layout_id}", response_model=LayoutOut)
async def update_layout(layout_id: str, payload: LayoutIn):
    now = _now_iso()
    update_doc = {
        "name": payload.name,
        "tiles": [t.model_dump() for t in payload.tiles],
        "updated_at": now,
    }
    result = await db.layouts.update_one({"id": layout_id}, {"$set": update_doc})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Layout not found")
    doc = await db.layouts.find_one({"id": layout_id}, {"_id": 0})
    return _serialize_layout(doc)


@api_router.delete("/layouts/{layout_id}")
async def delete_layout(layout_id: str):
    result = await db.layouts.delete_one({"id": layout_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Layout not found")
    return {"ok": True}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def _startup():
    ndi_service.refresh(force=True)
    logger.info(f"NDI Multiview API up. Mode={ndi_service.mode} ndi_available={NDI_AVAILABLE}")


@app.on_event("shutdown")
async def _shutdown():
    ndi_service.shutdown()
    client.close()
