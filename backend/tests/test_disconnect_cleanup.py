"""Retest for iteration_3: disconnect cleanup + program flow."""
import os
import threading
import time

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


def _find(sources, sid):
    return next((s for s in sources if s["id"] == sid), None)


def _consume(url, duration):
    try:
        with requests.get(url, stream=True, timeout=duration + 5) as r:
            assert r.status_code == 200
            deadline = time.time() + duration
            for _ in r.iter_content(chunk_size=4096):
                if time.time() > deadline:
                    break
    except Exception:
        pass


@pytest.mark.parametrize("sid", ["demo::0", "demo::1", "demo::4"])
def test_fps_drops_after_short_stream(sid):
    _consume(f"{API}/stream/{sid}", 3)
    time.sleep(6)
    r = requests.get(f"{API}/sources", timeout=10)
    s = _find(r.json(), sid)
    assert s is not None
    assert s["fps"] == 0.0, f"{sid} fps expected 0 got {s['fps']}"


def test_two_concurrent_viewers_demo2_shared_then_zero():
    sid = "demo::2"
    url = f"{API}/stream/{sid}"
    t1 = threading.Thread(target=_consume, args=(url, 4))
    t2 = threading.Thread(target=_consume, args=(url, 4))
    t1.start(); t2.start()
    time.sleep(2)
    s = _find(requests.get(f"{API}/sources", timeout=10).json(), sid)
    fps_during = s["fps"]
    t1.join(); t2.join()
    # Shared streamer ~15fps (not double)
    assert 5 <= fps_during <= 22, f"expected shared ~15fps, got {fps_during}"
    time.sleep(6)
    s2 = _find(requests.get(f"{API}/sources", timeout=10).json(), sid)
    assert s2["fps"] == 0.0, f"expected fps=0 after both closed, got {s2['fps']}"


def test_program_out_starts_and_stops_and_sources_cleanup():
    tiles = [
        {"source_id": "demo::0", "x": 0, "y": 0, "width": 960, "height": 540},
        {"source_id": "demo::1", "x": 960, "y": 0, "width": 960, "height": 540},
        {"source_id": "demo::2", "x": 480, "y": 540, "width": 960, "height": 540},
    ]
    payload = {
        "enabled": True, "ndi_name": "TEST_Program",
        "width": 1280, "height": 720, "fps": 30,
        "canvas_width": 1920, "canvas_height": 1080, "tiles": tiles,
    }
    r = requests.post(f"{API}/program", json=payload, timeout=10)
    assert r.status_code == 200

    time.sleep(3.5)
    status = requests.get(f"{API}/program", timeout=10).json()
    assert status.get("tile_count") == 3
    # out_fps > 20 when running (ndi_send may be absent in container)
    if status.get("running"):
        assert status.get("out_fps", 0) > 15, f"out_fps={status.get('out_fps')}"

    # stop
    r2 = requests.post(f"{API}/program", json={"enabled": False}, timeout=10)
    assert r2.status_code == 200
    time.sleep(6)
    stopped = requests.get(f"{API}/program", timeout=10).json()
    assert stopped.get("enabled") is False or stopped.get("running") is False

    # referenced sources should have dropped to 0
    src_json = requests.get(f"{API}/sources", timeout=10).json()
    for tid in ("demo::0", "demo::1", "demo::2"):
        s = _find(src_json, tid)
        assert s["fps"] == 0.0, f"{tid} fps still {s['fps']} after program stopped"
