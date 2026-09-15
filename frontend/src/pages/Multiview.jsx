import React from "react";
import axios from "axios";
import { toast, Toaster } from "sonner";
import { X } from "lucide-react";

import Toolbar from "@/components/Toolbar";
import SourceSidebar from "@/components/SourceSidebar";
import VideoTile from "@/components/VideoTile";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const uid = () => Math.random().toString(36).slice(2, 10);

export default function Multiview() {
  const [config, setConfig] = React.useState({ mode: "demo", ndi_available: false });
  const [sources, setSources] = React.useState([]);
  const [tiles, setTiles] = React.useState([]);
  const [selectedTileId, setSelectedTileId] = React.useState(null);
  const [layouts, setLayouts] = React.useState([]);
  const [currentLayoutId, setCurrentLayoutId] = React.useState(null);
  const [currentLayoutName, setCurrentLayoutName] = React.useState("Untitled layout");
  const [saveDialogOpen, setSaveDialogOpen] = React.useState(false);
  const [saveName, setSaveName] = React.useState("");
  const [loadingSources, setLoadingSources] = React.useState(false);
  const [fullscreenTileId, setFullscreenTileId] = React.useState(null);

  const canvasRef = React.useRef(null);
  const appRef = React.useRef(null);

  const streamUrl = React.useCallback(
    (sourceId) =>
      sourceId ? `${API}/stream/${encodeURIComponent(sourceId)}?ts=${Date.now()}` : null,
    []
  );

  // ------- API loaders -------
  const loadConfig = React.useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/config`);
      setConfig(data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const loadSources = React.useCallback(async (force = false) => {
    setLoadingSources(true);
    try {
      const url = force ? `${API}/sources/refresh` : `${API}/sources`;
      const { data } = force
        ? await axios.post(url)
        : await axios.get(url);
      setSources(data);
    } catch (e) {
      console.error(e);
      toast.error("Could not load sources");
    } finally {
      setLoadingSources(false);
    }
  }, []);

  const loadLayouts = React.useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/layouts`);
      setLayouts(data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  React.useEffect(() => {
    loadConfig();
    loadSources(false);
    loadLayouts();
    const t = setInterval(() => loadSources(false), 2000);
    return () => clearInterval(t);
  }, [loadConfig, loadSources, loadLayouts]);

  // ------- Tile ops -------
  const addTileForSource = (source) => {
    const canvas = canvasRef.current;
    const cw = canvas?.clientWidth || 1200;
    const ch = canvas?.clientHeight || 700;
    const w = 360;
    const h = 210;
    const idx = tiles.length;
    const x = 40 + (idx % 4) * 40;
    const y = 40 + (idx % 4) * 40;
    setTiles((prev) => [
      ...prev,
      {
        id: uid(),
        source_id: source.id,
        x: Math.min(x, cw - w - 20),
        y: Math.min(y, ch - h - 20),
        width: w,
        height: h,
        z: (prev[prev.length - 1]?.z || 0) + 1,
      },
    ]);
  };

  const updateTile = (id, changes) => {
    setTiles((prev) => prev.map((t) => (t.id === id ? { ...t, ...changes } : t)));
  };

  const removeTile = (id) => {
    setTiles((prev) => prev.filter((t) => t.id !== id));
    if (fullscreenTileId === id) setFullscreenTileId(null);
  };

  const clearCanvas = () => {
    if (tiles.length === 0) return;
    setTiles([]);
    setCurrentLayoutId(null);
    setCurrentLayoutName("Untitled layout");
    toast.success("Canvas cleared");
  };

  const applyGridPreset = (preset) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const cw = canvas.clientWidth;
    const ch = canvas.clientHeight;
    const gap = 10;
    const cols = preset.cols;
    const rows = preset.rows;
    const totalSlots = cols * rows;
    const tileW = (cw - gap * (cols + 1)) / cols;
    const tileH = (ch - gap * (rows + 1)) / rows;
    // reuse assignments from current tiles; fill remaining with first available sources
    const usedSourceIds = tiles.map((t) => t.source_id).filter(Boolean);
    const availableSources = sources
      .map((s) => s.id)
      .filter((id) => !usedSourceIds.includes(id));
    const assignments = [];
    for (let i = 0; i < totalSlots; i++) {
      if (i < tiles.length) assignments.push(tiles[i].source_id);
      else if (availableSources.length) assignments.push(availableSources.shift());
      else assignments.push(sources[i % Math.max(1, sources.length)]?.id || null);
    }
    const newTiles = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        newTiles.push({
          id: uid(),
          source_id: assignments[idx],
          x: gap + c * (tileW + gap),
          y: gap + r * (tileH + gap),
          width: tileW,
          height: tileH,
          z: idx + 1,
        });
      }
    }
    setTiles(newTiles);
    toast.success(`Applied ${preset.label} grid`);
  };

  // ------- Layouts -------
  const openSaveDialog = () => {
    setSaveName(currentLayoutName === "Untitled layout" ? "" : currentLayoutName);
    setSaveDialogOpen(true);
  };

  const doSaveLayout = async () => {
    const name = (saveName || "").trim();
    if (!name) {
      toast.error("Enter a name for the layout");
      return;
    }
    try {
      const payload = { name, tiles };
      if (currentLayoutId) {
        const { data } = await axios.put(`${API}/layouts/${currentLayoutId}`, payload);
        setCurrentLayoutName(data.name);
        toast.success("Layout updated");
      } else {
        const { data } = await axios.post(`${API}/layouts`, payload);
        setCurrentLayoutId(data.id);
        setCurrentLayoutName(data.name);
        toast.success("Layout saved");
      }
      setSaveDialogOpen(false);
      loadLayouts();
    } catch (e) {
      console.error(e);
      toast.error("Save failed");
    }
  };

  const loadLayout = (layout) => {
    setTiles(
      (layout.tiles || []).map((t) => ({
        id: t.id || uid(),
        source_id: t.source_id,
        x: t.x,
        y: t.y,
        width: t.width,
        height: t.height,
        z: t.z || 0,
      }))
    );
    setCurrentLayoutId(layout.id);
    setCurrentLayoutName(layout.name);
    toast.success(`Loaded "${layout.name}"`);
  };

  const deleteLayout = async (layout) => {
    if (!window.confirm(`Delete layout "${layout.name}"?`)) return;
    try {
      await axios.delete(`${API}/layouts/${layout.id}`);
      if (currentLayoutId === layout.id) {
        setCurrentLayoutId(null);
        setCurrentLayoutName("Untitled layout");
      }
      loadLayouts();
      toast.success("Layout deleted");
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  const newLayout = () => {
    setTiles([]);
    setCurrentLayoutId(null);
    setCurrentLayoutName("Untitled layout");
  };

  // ------- Fullscreen -------
  const goGlobalFullscreen = () => {
    const el = appRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.();
    }
  };

  const activeSourceIds = tiles.map((t) => t.source_id).filter(Boolean);
  const sourceById = React.useMemo(() => {
    const m = new Map();
    sources.forEach((s) => m.set(s.id, s));
    return m;
  }, [sources]);

  // ------- Render -------
  const fullscreenTile = tiles.find((t) => t.id === fullscreenTileId);
  const fullscreenSource = fullscreenTile ? sourceById.get(fullscreenTile.source_id) : null;

  return (
    <div
      ref={appRef}
      className="h-screen w-screen flex flex-col text-neutral-100"
      style={{ background: "var(--bg-canvas)" }}
      data-testid="multiview-app"
    >
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: { background: "#121212", border: "1px solid #262626", color: "#F3F4F6" },
        }}
      />

      <Toolbar
        mode={config.mode}
        layouts={layouts}
        currentLayoutId={currentLayoutId}
        onGridPreset={applyGridPreset}
        onSaveLayout={openSaveDialog}
        onLoadLayout={loadLayout}
        onDeleteLayout={deleteLayout}
        onNewLayout={newLayout}
        onGlobalFullscreen={goGlobalFullscreen}
        onClearCanvas={clearCanvas}
      />

      <div className="flex flex-1 min-h-0">
        <SourceSidebar
          sources={sources}
          onRefresh={() => loadSources(true)}
          onAddSource={addTileForSource}
          activeSourceIds={activeSourceIds}
          loading={loadingSources}
        />

        <main className="flex-1 min-w-0 flex flex-col">
          <div
            ref={canvasRef}
            className="canvas-grid flex-1 relative overflow-hidden"
            data-testid="canvas-area"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setSelectedTileId(null);
            }}
          >
            {tiles.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="text-center">
                  <div className="font-condensed text-2xl font-bold tracking-wider text-neutral-700 uppercase">
                    Empty Canvas
                  </div>
                  <div className="text-xs text-neutral-600 mt-2">
                    Click a source in the sidebar or apply a grid preset
                  </div>
                </div>
              </div>
            )}
            {tiles.map((tile) => {
              const source = sourceById.get(tile.source_id);
              return (
                <VideoTile
                  key={tile.id}
                  tile={tile}
                  source={source}
                  streamUrl={streamUrl(tile.source_id)}
                  selected={selectedTileId === tile.id}
                  bounds="parent"
                  onSelect={setSelectedTileId}
                  onChange={updateTile}
                  onRemove={removeTile}
                  onFullscreen={setFullscreenTileId}
                />
              );
            })}
          </div>

          <div className="status-bar">
            <span>MODE: {config.mode.toUpperCase()}</span>
            <span>NDI RUNTIME: {config.ndi_available ? "OK" : "N/A"}</span>
            <span>SOURCES: {sources.length}</span>
            <span>TILES: {tiles.length}</span>
            <span className="ml-auto truncate" data-testid="current-layout-name">
              LAYOUT: {currentLayoutName}
              {currentLayoutId ? "" : "  *"}
            </span>
          </div>
        </main>
      </div>

      {/* Save dialog */}
      {saveDialogOpen && (
        <div
          className="fixed inset-0 z-[999] flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setSaveDialogOpen(false)}
          data-testid="save-dialog"
        >
          <div
            className="bg-[#121212] border border-[#262626] rounded-lg p-5 w-[380px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-condensed text-lg font-bold uppercase tracking-wider">
                {currentLayoutId ? "Update layout" : "Save layout"}
              </h3>
              <button
                className="text-neutral-500 hover:text-neutral-200"
                onClick={() => setSaveDialogOpen(false)}
              >
                <X size={16} />
              </button>
            </div>
            <label className="text-[11px] uppercase tracking-widest text-neutral-500 font-condensed">
              Layout name
            </label>
            <input
              autoFocus
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") doSaveLayout();
              }}
              className="w-full mt-1 bg-[#0A0A0A] border border-[#262626] rounded-md px-3 py-2 text-sm text-neutral-100 focus:outline-none focus:border-[#34C759]"
              placeholder="e.g. Studio A · Show open"
              data-testid="save-layout-name-input"
            />
            <div className="flex justify-end gap-2 mt-5">
              <button
                className="toolbar-btn"
                onClick={() => setSaveDialogOpen(false)}
                data-testid="save-cancel-btn"
              >
                Cancel
              </button>
              <button
                className="toolbar-btn primary"
                onClick={doSaveLayout}
                data-testid="save-confirm-btn"
              >
                {currentLayoutId ? "Update" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Per-tile fullscreen overlay */}
      {fullscreenTile && (
        <div
          className="fixed inset-0 z-[998] bg-black flex flex-col"
          data-testid="tile-fullscreen-overlay"
        >
          <div className="h-12 flex items-center justify-between px-4 border-b border-[#262626] bg-[#0A0A0A]">
            <div className="flex items-center gap-2">
              <span className="led led-green" />
              <span className="font-condensed text-lg font-bold uppercase tracking-wider">
                {fullscreenSource?.name || "No source"}
              </span>
            </div>
            <button
              className="toolbar-btn"
              onClick={() => setFullscreenTileId(null)}
              data-testid="close-fullscreen-btn"
            >
              <X size={14} />
              Close
            </button>
          </div>
          <div className="flex-1 flex items-center justify-center overflow-hidden">
            {fullscreenTile.source_id && (
              <img
                src={streamUrl(fullscreenTile.source_id)}
                alt=""
                className="max-w-full max-h-full object-contain"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
