"""Entry point for the packaged Windows executable.

Starts the FastAPI server (which also serves the built React frontend),
opens the default web browser at the app URL, and keeps the process alive
until Ctrl+C or the console window is closed.
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# When packaged with PyInstaller (--onefile), the working dir differs from _MEIPASS.
# Make sure the backend module is importable regardless of launch mode.
if getattr(sys, "frozen", False):
    base = Path(getattr(sys, "_MEIPASS", "")) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
    sys.path.insert(0, str(base))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _print_banner(host: str, port: int, data_dir: str) -> None:
    url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
    lines = [
        "",
        "=" * 60,
        " NDI MULTIVIEW",
        "=" * 60,
        f"  URL      : {url}",
        f"  API      : {url}/api",
        f"  Data dir : {data_dir}",
        "",
        "  Ctrl+C or close this window to stop the server.",
        "=" * 60,
        "",
    ]
    print("\n".join(lines), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="NDI Multiview server")
    parser.add_argument("--host", default=os.environ.get("NDI_HOST", "0.0.0.0"),
                        help="Host to bind (default 0.0.0.0 = all interfaces)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("NDI_PORT", "8001")),
                        help="TCP port (default 8001)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the default browser on start")
    args = parser.parse_args()

    port = _find_free_port(args.port)
    if port != args.port:
        print(f"[warn] Port {args.port} busy, using {port}", flush=True)

    # Import here so that PYTHONPATH tweaks above have taken effect.
    import uvicorn
    from server import app  # noqa: E402
    import layout_store  # noqa: E402

    _print_banner(args.host, port, str(layout_store.DATA_DIR))

    if not args.no_browser:
        def _open() -> None:
            time.sleep(1.5)
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()

    config = uvicorn.Config(app, host=args.host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
