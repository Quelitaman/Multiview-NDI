# NDI Multiview — PRD

## Original problem statement
Crear una aplicación web tipo multiview NDI. Debe detectar automáticamente fuentes NDI disponibles en la red y mostrarlas en una cuadrícula configurable (2x2, 3x3, 4x4...). Cada ventana mostrará el nombre de la fuente, estado de señal y un contador FPS. Debe permitir pantalla completa y guardar layouts. Pensada para ejecutarse en un servidor Windows con acceso al NDI SDK.

## User choices
- NDI integration: backend Python (cyndilib) + MJPEG streaming over HTTP.
- Layout: free-form (drag & drop, resizable) + grid presets (2×2, 3×3, 4×4, 1×2, 2×1).
- Auth: none (LAN tool).
- Theme: broadcast dark (black canvas, tally green/amber/red accents).
- Per-tile info: source name, signal LED, FPS.

## Architecture
- **Backend (FastAPI)** — `/app/backend`
  - `ndi_service.py` — wraps `cyndilib.Finder` for real NDI discovery; when no real sources are found, exposes 6 synthetic demo sources whose MJPEG frames are rendered on the fly with Pillow (animated gradient + timecode + moving marker). Each demo source generates a fresh JPEG per frame.
  - `server.py` — REST API prefixed with `/api`:
    - `GET  /api/config` — {ndi_available, mode, version}
    - `GET  /api/sources` — list of sources (`id, name, is_demo, connected, fps, width, height`)
    - `POST /api/sources/refresh` — forces a re-scan
    - `GET  /api/stream/{source_id}` — long-lived `multipart/x-mixed-replace; boundary=frame` MJPEG stream
    - `GET/POST/PUT/DELETE /api/layouts[/{id}]` — CRUD for named layouts (stored in MongoDB, `layouts` collection)
- **Frontend (React 19 + Tailwind + react-rnd)** — `/app/frontend/src`
  - `pages/Multiview.jsx` — top-level page (state, API calls, save/load dialogs, per-tile & global fullscreen)
  - `components/Toolbar.jsx` — grid presets, save/load/delete layouts, clear canvas, fullscreen
  - `components/SourceSidebar.jsx` — auto-refreshed source list (2 s poll) with filter + status LEDs
  - `components/VideoTile.jsx` — draggable/resizable NDI tile (react-rnd), MJPEG `<img>` stream, UMD (name, LED, resolution, FPS)

### FPS strategy
- Backend counts JPEG frames yielded per second per source and exposes it on `/api/sources`.
- Frontend polls `/api/sources` every 2 s and prefers backend-reported FPS; falls back to client-side `load` events on the `<img>` for immediate feedback.

## What's been implemented (2026-01-15)
- Real NDI discovery via cyndilib (Linux runtime confirmed working); automatic fallback to 6 demo sources.
- MJPEG stream endpoint with animated demo generator and downscaling for real NDI feeds.
- Broadcast-style dark UI (Barlow Condensed / Inter / JetBrains Mono, dot-grid canvas, tally colours).
- Free-layout canvas with drag & resize (react-rnd) + 5 grid presets (2×2, 3×3, 4×4, 1×2, 2×1).
- Layouts persisted in MongoDB with full CRUD.
- Per-tile fullscreen overlay and global fullscreen (browser).
- Sonner toasts, status bar (mode, NDI runtime, source count, tile count, current layout).
- Backend tested end-to-end (7/7 scenarios passing, `test_reports/iteration_1.json`).

## User personas
- Broadcast/AV operator on a Windows control-room PC monitoring several NDI feeds simultaneously.
- Streaming/live production engineer verifying source health from a browser on the LAN.

## Static core requirements
1. Auto-discovery of NDI sources on the LAN.
2. Configurable layout (grid presets + free layout).
3. Per-tile info: source name, signal LED, FPS.
4. Fullscreen (per tile & global).
5. Save / load named layouts.
6. Designed to run on Windows with the NDI SDK; graceful fallback for other platforms.

## Backlog (P0/P1/P2)
- **P1** — Audio VU meters and mute-per-tile.
- **P1** — Tally (PGM/PVW) borders driven by an external tally source or per-tile toggle.
- **P1** — Multiple named canvases / pages you can flip between.
- **P2** — WebRTC streaming path (lower latency vs MJPEG).
- **P2** — Autoload the last-used layout on startup, keyboard shortcuts (F for fullscreen, Del to remove tile).
- **P2** — Windows service installer + step-by-step deployment doc.

## Next tasks
See finish summary Next Action Items.
