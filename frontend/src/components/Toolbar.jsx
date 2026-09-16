import React from "react";
import {
  LayoutGrid,
  Save,
  FolderOpen,
  Trash2,
  Maximize,
  Plus,
  ChevronDown,
  Radio,
  CircleDot,
} from "lucide-react";

const GRID_PRESETS = [
  { key: "2x2", cols: 2, rows: 2, label: "2×2" },
  { key: "3x3", cols: 3, rows: 3, label: "3×3" },
  { key: "4x4", cols: 4, rows: 4, label: "4×4" },
  { key: "1x2", cols: 2, rows: 1, label: "1×2" },
  { key: "2x1", cols: 1, rows: 2, label: "2×1" },
];

export default function Toolbar({
  onGridPreset,
  onSaveLayout,
  onLoadLayout,
  onDeleteLayout,
  layouts,
  currentLayoutId,
  onNewLayout,
  onGlobalFullscreen,
  onClearCanvas,
  mode,
  programStatus,
  onOpenProgramOut,
}) {
  const [openLayouts, setOpenLayouts] = React.useState(false);
  const layoutRef = React.useRef(null);

  React.useEffect(() => {
    const handler = (e) => {
      if (layoutRef.current && !layoutRef.current.contains(e.target)) {
        setOpenLayouts(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header
      className="h-14 shrink-0 flex items-center justify-between px-4 border-b border-[#262626]"
      style={{ background: "rgba(10,10,10,0.9)", backdropFilter: "blur(8px)" }}
      data-testid="app-toolbar"
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded bg-gradient-to-br from-[#34C759] to-[#0f5f2b] flex items-center justify-center shadow-[0_0_12px_rgba(52,199,89,0.4)]">
            <LayoutGrid size={14} className="text-black" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="font-condensed text-[15px] font-bold tracking-wider uppercase">
              NDI Multiview
            </span>
            <span className="text-[10px] text-neutral-500 font-mono uppercase">
              {mode === "ndi" ? "NDI RUNTIME · READY" : "DEMO MODE"}
            </span>
          </div>
        </div>

        <div className="h-6 w-px bg-[#262626] mx-2" />

        <div className="flex items-center gap-1">
          <span className="text-[10px] uppercase tracking-widest text-neutral-500 mr-2 font-condensed">
            Grid
          </span>
          {GRID_PRESETS.map((p) => (
            <button
              key={p.key}
              className="toolbar-btn"
              onClick={() => onGridPreset(p)}
              data-testid={`grid-preset-${p.key}`}
              title={`Apply ${p.label} grid`}
            >
              <span className="font-condensed font-bold">{p.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          className={`toolbar-btn ${programStatus?.enabled ? "danger" : ""}`}
          onClick={onOpenProgramOut}
          data-testid="program-out-btn"
          title="Publicar multiview como fuente NDI"
          style={
            programStatus?.enabled
              ? {
                  color: "#FF3B30",
                  borderColor: "#FF3B30",
                  background: "rgba(255,59,48,0.08)",
                }
              : undefined
          }
        >
          {programStatus?.enabled ? (
            <>
              <CircleDot size={12} className="animate-pulse" />
              <span>ON AIR · {programStatus.out_fps || 0}</span>
            </>
          ) : (
            <>
              <Radio size={12} />
              <span>Program Out</span>
            </>
          )}
        </button>

        <button
          className="toolbar-btn"
          onClick={onClearCanvas}
          data-testid="clear-canvas-btn"
          title="Clear canvas"
        >
          <Trash2 size={12} />
          <span>Clear</span>
        </button>

        <div className="relative" ref={layoutRef}>
          <button
            className="toolbar-btn"
            onClick={() => setOpenLayouts((v) => !v)}
            data-testid="layouts-dropdown-btn"
          >
            <FolderOpen size={12} />
            <span>Layouts</span>
            <ChevronDown size={12} />
          </button>
          {openLayouts && (
            <div
              className="absolute right-0 mt-1 w-64 bg-[#121212] border border-[#262626] rounded-md shadow-2xl z-50 p-1 max-h-80 overflow-y-auto thin-scroll"
              data-testid="layouts-menu"
            >
              {layouts.length === 0 && (
                <div className="px-3 py-4 text-center text-[11px] text-neutral-500">
                  No saved layouts
                </div>
              )}
              {layouts.map((l) => (
                <div
                  key={l.id}
                  className={`group flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[#1f1f1f] cursor-pointer ${
                    l.id === currentLayoutId ? "bg-[#14251a]" : ""
                  }`}
                  onClick={() => {
                    onLoadLayout(l);
                    setOpenLayouts(false);
                  }}
                  data-testid={`layout-item-${l.id}`}
                >
                  <FolderOpen size={12} className="text-neutral-500" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[12px] text-neutral-100 truncate">
                      {l.name}
                    </div>
                    <div className="text-[10px] text-neutral-500 font-mono">
                      {l.tiles?.length || 0} tiles
                    </div>
                  </div>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-neutral-500 hover:text-[#FF3B30] p-1"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteLayout(l);
                    }}
                    data-testid={`delete-layout-${l.id}`}
                    title="Delete layout"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
              <div className="border-t border-[#262626] mt-1 pt-1">
                <button
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[#1f1f1f] text-[12px] text-neutral-300"
                  onClick={() => {
                    onNewLayout();
                    setOpenLayouts(false);
                  }}
                  data-testid="new-layout-btn"
                >
                  <Plus size={12} />
                  New empty layout
                </button>
              </div>
            </div>
          )}
        </div>

        <button
          className="toolbar-btn primary"
          onClick={onSaveLayout}
          data-testid="save-layout-btn"
        >
          <Save size={12} />
          <span>Save</span>
        </button>

        <button
          className="toolbar-btn"
          onClick={onGlobalFullscreen}
          data-testid="global-fullscreen-btn"
          title="Fullscreen"
        >
          <Maximize size={12} />
        </button>
      </div>
    </header>
  );
}
