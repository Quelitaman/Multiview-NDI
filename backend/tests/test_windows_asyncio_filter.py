"""Targeted tests for the Windows asyncio ConnectionReset filter (iteration_4).

Verifies:
- Backend still boots (GET /api/config returns expected fields, filter installed).
- Unrelated 'asyncio' logger records still pass through (not globally silenced).
- Synthetic 'ConnectionResetError ... 10054' records ARE dropped by the filter.
- The asyncio loop exception handler was set and swallows ConnectionResetError.
"""
import asyncio
import logging
import os
import sys

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Make backend importable for in-process filter tests
sys.path.insert(0, "/app/backend")


def test_config_endpoint_still_healthy():
    r = requests.get(f"{API}/config", timeout=10)
    assert r.status_code == 200
    body = r.json()
    for key in ("ndi_available", "mode", "version", "data_dir", "ndi_send_available"):
        assert key in body, f"missing {key} in /api/config response: {body}"
    assert isinstance(body["ndi_available"], bool)
    assert isinstance(body["ndi_send_available"], bool)


def test_asyncio_logger_filter_drops_only_target_message():
    """Install the filter in-process and verify selective drop behavior."""
    from server import _install_windows_asyncio_filter  # type: ignore

    async def _run():
        _install_windows_asyncio_filter()

    asyncio.run(_run())

    asyncio_logger = logging.getLogger("asyncio")

    # Capture records via a handler
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    cap = _Capture(level=logging.DEBUG)
    asyncio_logger.addHandler(cap)
    prev_level = asyncio_logger.level
    asyncio_logger.setLevel(logging.DEBUG)
    # Prevent propagation so root handlers don't affect test
    prev_prop = asyncio_logger.propagate
    asyncio_logger.propagate = False

    try:
        # Unrelated warning — must pass through
        asyncio_logger.warning("unrelated test message about tasks")
        # Target Windows spam — must be dropped
        asyncio_logger.error(
            "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)"
        )
        asyncio_logger.error(
            "ConnectionResetError: [WinError 10054] connection forcibly closed"
        )

        messages = [r.getMessage() for r in records]
        assert any("unrelated test message" in m for m in messages), (
            f"Unrelated asyncio log was incorrectly filtered. Got: {messages}"
        )
        assert not any("_ProactorBasePipeTransport._call_connection_lost" in m for m in messages), (
            f"Proactor traceback message should have been filtered. Got: {messages}"
        )
        assert not any(("ConnectionResetError" in m and "10054" in m) for m in messages), (
            f"ConnectionResetError 10054 message should have been filtered. Got: {messages}"
        )
    finally:
        asyncio_logger.removeHandler(cap)
        asyncio_logger.setLevel(prev_level)
        asyncio_logger.propagate = prev_prop


def test_loop_exception_handler_swallows_connection_reset():
    """The installed handler must return silently for ConnectionResetError."""
    from server import _install_windows_asyncio_filter  # type: ignore

    async def _run():
        _install_windows_asyncio_filter()
        loop = asyncio.get_event_loop()
        handler = loop.get_exception_handler()
        assert handler is not None, "exception handler was not installed"

        called_default = {"n": 0}
        original_default = loop.default_exception_handler

        def _spy(ctx):
            called_default["n"] += 1
            return original_default(ctx)

        loop.default_exception_handler = _spy  # type: ignore[assignment]

        # ConnectionResetError -> must be swallowed (default not called)
        handler(loop, {"message": "boom", "exception": ConnectionResetError(10054, "reset")})
        # ConnectionAbortedError -> also swallowed
        handler(loop, {"message": "boom", "exception": ConnectionAbortedError()})
        # Message-only match -> swallowed
        handler(
            loop,
            {"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)"},
        )
        assert called_default["n"] == 0, "benign cases should not reach default handler"

        # Unrelated exception -> must reach default handler
        handler(loop, {"message": "other", "exception": RuntimeError("x")})
        assert called_default["n"] == 1, "unrelated exception must go to default handler"

    asyncio.run(_run())


def test_rapid_open_close_cycles_leave_no_orphans():
    """10 short streams to demo::0 in a row -> final fps=0, all 6 sources present."""
    import time

    url = f"{API}/stream/demo::0"
    for _ in range(10):
        try:
            with requests.get(url, stream=True, timeout=3) as r:
                assert r.status_code == 200
                # read a tiny bit then bail
                it = r.iter_content(chunk_size=4096)
                next(it, None)
        except Exception:
            pass

    time.sleep(6)
    r = requests.get(f"{API}/sources", timeout=10)
    assert r.status_code == 200
    src = r.json()
    assert len(src) >= 6, f"expected >=6 demo sources, got {len(src)}"
    s0 = next((s for s in src if s["id"] == "demo::0"), None)
    assert s0 is not None
    assert s0["fps"] == 0.0, f"orphan streamer? demo::0 fps={s0['fps']}"
