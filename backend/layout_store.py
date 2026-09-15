"""Simple thread-safe JSON file store for layouts.

Used instead of MongoDB so the Windows .exe is fully self-contained
(no external database required on the VM).
"""
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_data_dir() -> Path:
    override = os.environ.get("NDI_MULTIVIEW_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "NdiMultiview"
    return Path.home() / ".ndi_multiview"


DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LAYOUTS_FILE = DATA_DIR / "layouts.json"


_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> List[Dict[str, Any]]:
    if not LAYOUTS_FILE.exists():
        return []
    try:
        with LAYOUTS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _write_all(items: List[Dict[str, Any]]) -> None:
    tmp = LAYOUTS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    tmp.replace(LAYOUTS_FILE)


def list_layouts() -> List[Dict[str, Any]]:
    with _lock:
        items = _read_all()
    items.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
    return items


def get_layout(layout_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for it in _read_all():
            if it.get("id") == layout_id:
                return it
    return None


def create_layout(doc: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        items = _read_all()
        doc.setdefault("created_at", _now_iso())
        doc["updated_at"] = _now_iso()
        items.append(doc)
        _write_all(items)
    return doc


def update_layout(layout_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with _lock:
        items = _read_all()
        for i, it in enumerate(items):
            if it.get("id") == layout_id:
                it.update(patch)
                it["updated_at"] = _now_iso()
                items[i] = it
                _write_all(items)
                return it
    return None


def delete_layout(layout_id: str) -> bool:
    with _lock:
        items = _read_all()
        new_items = [it for it in items if it.get("id") != layout_id]
        if len(new_items) == len(items):
            return False
        _write_all(new_items)
        return True
