# NDI Multiview — PRD

## Original problem statement
Crear una aplicación web tipo multiview NDI. Debe detectar automáticamente fuentes NDI disponibles en la red y mostrarlas en una cuadrícula configurable (2x2, 3x3, 4x4...). Cada ventana mostrará el nombre de la fuente, estado de señal y un contador FPS. Debe permitir pantalla completa y guardar layouts. Pensada para ejecutarse en un servidor Windows con acceso al NDI SDK.

## User choices
- NDI integration: backend Python (cyndilib) + MJPEG streaming HTTP.
- Layout: free-form (drag & drop, resizable) + grid presets (2×2, 3×3, 4×4, 1×2, 2×1).
- Auth: none (LAN tool).
- Theme: broadcast dark (black canvas, tally green/amber/red accents).
- Per-tile info: source name, signal LED, FPS.
- **Deployment: single Windows .exe for a VM.**

## Architecture
- **Backend (FastAPI)** — `/app/backend`
  - `ndi_service.py` — `cyndilib.Finder` + Receiver, with a 6-source demo fallback rendered with Pillow.
  - `layout_store.py` — thread-safe JSON store at `%APPDATA%\NdiMultiview\layouts.json` (no MongoDB required).
  - `server.py` — REST API + static SPA serving:
    - `GET  /api/config` — {ndi_available, mode, version, data_dir}
    - `GET  /api/sources`, `POST /api/sources/refresh`
    - `GET  /api/stream/{source_id}` — long-lived MJPEG (`multipart/x-mixed-replace`)
    - `GET/POST/PUT/DELETE /api/layouts[/{id}]`
    - `GET  /{spa path}` — serves the built React app when packaged
  - `launcher.py` — PyInstaller entry point: picks free port, prints banner, opens browser, runs uvicorn.
  - `NdiMultiview.spec` + `requirements-exe.txt` — PyInstaller configuration for a single-file `NdiMultiview.exe`.
- **Frontend (React 19 + Tailwind + react-rnd)** — `/app/frontend/src`
  - `pages/Multiview.jsx` (state, save/load, fullscreen), `components/Toolbar.jsx`, `components/SourceSidebar.jsx` (with amber DEMO-mode banner), `components/VideoTile.jsx` (drag/resize + MJPEG `<img>`).
- **Windows packaging** — `/app/build_windows.ps1` builds the frontend, installs deps, runs PyInstaller.
- **Docs** — `/app/WINDOWS_DEPLOY.md` (requirements, build steps, firewall ports, NSSM service, Discovery Server).

### FPS strategy
Backend counts JPEG frames yielded per source per second; frontend polls `/api/sources` every 2 s and prefers backend FPS, with a client-side `<img>` load-event fallback.

## What's been implemented
- **2026-01-15** — MVP: NDI discovery + demo fallback, MJPEG streaming, broadcast-style UI (Barlow Condensed / Inter / JetBrains Mono, dot-grid canvas, tally colours), free-layout canvas with react-rnd, 5 grid presets, MongoDB layouts CRUD, per-tile + global fullscreen, sonner toasts, status bar. Backend fully tested (7/7).
- **2026-01-15** — DEMO-mode banner in sidebar explaining why real LAN sources are invisible from the cloud preview; `WINDOWS_DEPLOY.md` v1 with source-install instructions.
- **2026-01-15** — Windows executable build path: `launcher.py`, `NdiMultiview.spec`, `requirements-exe.txt`, `build_windows.ps1`. Backend serves the built React SPA in same-origin. Layouts moved from MongoDB to a local JSON store (`layouts.json` in `%APPDATA%`) so the `.exe` needs no external database. PyInstaller build validated on this container (single-file 53 MB binary boots, exposes `/api/config`, discovers sources).

## User personas
- Broadcast/AV operator on a Windows control-room VM monitoring several NDI feeds simultaneously.
- Streaming/live production engineer verifying source health from a browser on the LAN.

## Static core requirements
1. Auto-discovery of NDI sources on the LAN.
2. Configurable layout (grid presets + free layout).
3. Per-tile info: source name, signal LED, FPS.
4. Fullscreen (per tile & global).
5. Save / load named layouts.
6. Ships as a single Windows executable that runs on a VM.

## Backlog (P0/P1/P2)
- **P1** — Add source manually by NDI name (helps with cross-VLAN / mDNS-blocked networks).
- **P1** — Discovery Server address settable from the UI.
- **P1** — Tally (PGM/PVW) borders per tile or from external tally source.
- **P1** — Audio VU meters + mute per tile.
- **P2** — Autoload last-used layout on startup, keyboard shortcuts (F, Del).
- **P2** — Multiple named canvases with quick page-flip.
- **P2** — WebRTC streaming path for lower latency vs MJPEG.
- **P2** — Code-sign the .exe and provide a signed MSI installer.
