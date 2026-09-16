"""Backend tests for multiview optimization + bandwidth toggle."""
import os
import threading
import time

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def sources():
    r = requests.get(f"{API}/sources", timeout=10)
    assert r.status_code == 200
    return r.json()


def _find(sources, sid):
    return next((s for s in sources if s["id"] == sid), None)


# ---------- Bandwidth field ----------

def test_sources_have_bandwidth_field_default_low(sources):
    assert len(sources) >= 1
    for s in sources:
        assert "bandwidth" in s, f"missing bandwidth on {s}"
        assert s["bandwidth"] in ("low", "high")
    # default should be low
    assert all(s["bandwidth"] == "low" for s in sources)


def test_set_bandwidth_high_and_persist():
    sid = "demo::0"
    r = requests.post(f"{API}/sources/{sid}/bandwidth", json={"bandwidth": "high"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "bandwidth": "high"}

    r2 = requests.get(f"{API}/sources", timeout=10)
    assert r2.status_code == 200
    s = _find(r2.json(), sid)
    assert s is not None
    assert s["bandwidth"] == "high"

    # back to low
    r3 = requests.post(f"{API}/sources/{sid}/bandwidth", json={"bandwidth": "low"}, timeout=10)
    assert r3.status_code == 200
    assert r3.json() == {"ok": True, "bandwidth": "low"}
    s2 = _find(requests.get(f"{API}/sources", timeout=10).json(), sid)
    assert s2["bandwidth"] == "low"


def test_set_bandwidth_invalid_value_400():
    r = requests.post(
        f"{API}/sources/demo::0/bandwidth", json={"bandwidth": "medium"}, timeout=10
    )
    assert r.status_code == 400


def test_set_bandwidth_unknown_source_404():
    r = requests.post(
        f"{API}/sources/does-not-exist/bandwidth", json={"bandwidth": "low"}, timeout=10
    )
    assert r.status_code == 404


# ---------- Shared streamer optimization ----------

def _consume_stream(url, duration):
    """Consume MJPEG stream for `duration` seconds then close."""
    try:
        with requests.get(url, stream=True, timeout=duration + 5) as r:
            assert r.status_code == 200
            assert "multipart/x-mixed-replace" in r.headers.get("content-type", "")
            deadline = time.time() + duration
            for _chunk in r.iter_content(chunk_size=4096):
                if time.time() > deadline:
                    break
    except Exception:
        pass


def test_two_concurrent_viewers_do_not_double_fps():
    sid = "demo::1"
    url = f"{API}/stream/{sid}"
    t1 = threading.Thread(target=_consume_stream, args=(url, 6))
    t2 = threading.Thread(target=_consume_stream, args=(url, 6))
    t1.start()
    t2.start()
    # Wait for streamer to warm up
    time.sleep(3.5)
    r = requests.get(f"{API}/sources", timeout=10)
    s = _find(r.json(), sid)
    fps = s["fps"]
    t1.join()
    t2.join()
    # Shared streamer target is 15fps; must be well below 30 (per-connection).
    assert 5 <= fps <= 22, f"expected ~15fps with shared streamer, got {fps}"


def test_mjpeg_returns_jpeg_frames():
    sid = "demo::2"
    with requests.get(f"{API}/stream/{sid}", stream=True, timeout=8) as r:
        assert r.status_code == 200
        assert "multipart/x-mixed-replace; boundary=frame" in r.headers.get("content-type", "")
        buf = b""
        deadline = time.time() + 4
        for chunk in r.iter_content(chunk_size=4096):
            buf += chunk
            if time.time() > deadline or len(buf) > 200_000:
                break
        # JPEG SOI marker
        assert buf.count(b"\xff\xd8") >= 1


def test_fps_drops_to_zero_when_no_viewers():
    sid = "demo::3"
    # Warm up briefly
    _consume_stream(f"{API}/stream/{sid}", 3)
    # Wait for streamer to shut down
    time.sleep(6)
    r = requests.get(f"{API}/sources", timeout=10)
    s = _find(r.json(), sid)
    assert s["fps"] == 0.0, f"expected fps=0 after viewers gone, got {s['fps']}"


# ---------- Program Out ----------

def test_program_out_start_stop_and_fps():
    tiles = [
        {"source_id": "demo::0", "x": 0, "y": 0, "width": 960, "height": 540},
        {"source_id": "demo::1", "x": 960, "y": 0, "width": 960, "height": 540},
        {"source_id": "demo::2", "x": 480, "y": 540, "width": 960, "height": 540},
    ]
    payload = {
        "enabled": True,
        "ndi_name": "TEST_Program",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "canvas_width": 1920,
        "canvas_height": 1080,
        "tiles": tiles,
    }
    r = requests.post(f"{API}/program", json=payload, timeout=10)
    assert r.status_code == 200

    time.sleep(3.5)
    status = requests.get(f"{API}/program", timeout=10).json()
    # tile_count should reflect our tiles
    assert status.get("tile_count") == 3, status
    # ndi_send may be unavailable in this container; only assert fps if enabled+running
    if status.get("enabled") and status.get("running"):
        out_fps = status.get("out_fps", 0)
        assert out_fps > 15, f"expected out_fps > 15, got {out_fps}. status={status}"

    # While enabled, referenced sources should have a streamer running
    src_json = requests.get(f"{API}/sources", timeout=10).json()
    if status.get("enabled") and status.get("running"):
        for tid in ("demo::0", "demo::1", "demo::2"):
            s = _find(src_json, tid)
            assert s is not None
            assert s["fps"] > 3, f"expected source {tid} fps>3 while program running, got {s['fps']}"

    # stop
    r2 = requests.post(f"{API}/program", json={"enabled": False}, timeout=10)
    assert r2.status_code == 200
    time.sleep(1)
    stopped = requests.get(f"{API}/program", timeout=10).json()
    assert stopped.get("enabled") is False or stopped.get("running") is False


# ---------- Layouts CRUD regression ----------

def test_layouts_crud_flow():
    payload = {
        "name": "TEST_layout",
        "tiles": [
            {"id": "t1", "source_id": "demo::0", "x": 0, "y": 0, "width": 100, "height": 100, "z": 0}
        ],
    }
    r = requests.post(f"{API}/layouts", json=payload, timeout=10)
    assert r.status_code == 200
    created = r.json()
    lid = created["id"]
    assert created["name"] == "TEST_layout"

    r_list = requests.get(f"{API}/layouts", timeout=10)
    assert r_list.status_code == 200
    assert any(l["id"] == lid for l in r_list.json())

    r_get = requests.get(f"{API}/layouts/{lid}", timeout=10)
    assert r_get.status_code == 200

    upd = {"name": "TEST_layout_upd", "tiles": []}
    r_put = requests.put(f"{API}/layouts/{lid}", json=upd, timeout=10)
    assert r_put.status_code == 200
    assert r_put.json()["name"] == "TEST_layout_upd"

    r_del = requests.delete(f"{API}/layouts/{lid}", timeout=10)
    assert r_del.status_code == 200
    assert requests.get(f"{API}/layouts/{lid}", timeout=10).status_code == 404
