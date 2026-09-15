import React from "react";
import { RefreshCw, Radio, Signal, Search } from "lucide-react";

/**
 * Sidebar listing discovered NDI sources.
 * Click adds a tile to the canvas. Existing tiles are highlighted.
 */
export default function SourceSidebar({
  sources,
  onRefresh,
  onAddSource,
  activeSourceIds,
  loading,
}) {
  const [q, setQ] = React.useState("");
  const filtered = sources.filter((s) =>
    s.name.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <aside
      className="w-72 shrink-0 h-full flex flex-col border-r border-[#262626]"
      style={{ background: "var(--bg-surface)" }}
      data-testid="source-sidebar"
    >
      <div className="px-4 py-3 border-b border-[#262626] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio size={14} className="text-[#34C759]" />
          <h2 className="font-condensed text-sm font-bold uppercase tracking-widest text-neutral-200">
            NDI Sources
          </h2>
        </div>
        <button
          className="toolbar-btn !py-1 !px-2"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh sources"
          data-testid="refresh-sources-btn"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="px-3 py-2 border-b border-[#262626]">
        <div className="relative">
          <Search
            size={12}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-neutral-500"
          />
          <input
            className="w-full bg-[#0A0A0A] border border-[#262626] rounded-md pl-7 pr-2 py-1.5 text-xs text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-[#525252]"
            placeholder="Filter sources…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="source-filter-input"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto thin-scroll p-3 space-y-2">
        {sources.length > 0 && sources.every((s) => s.is_demo) && (
          <div
            className="mb-1 p-3 rounded-md border border-[#FF9500]/40 bg-[#FF9500]/[0.08]"
            data-testid="demo-only-banner"
          >
            <div className="text-[11px] font-condensed uppercase tracking-widest text-[#FFB454] font-bold">
              Modo Demo
            </div>
            <div className="text-[11px] text-neutral-300 mt-1 leading-snug">
              Este entorno no ve tu LAN — mDNS multicast está bloqueado. Ejecuta el
              backend en tu servidor Windows para detectar las fuentes NDI reales.
              Ver <span className="font-mono text-neutral-100">WINDOWS_DEPLOY.md</span>.
            </div>
          </div>
        )}
        {filtered.length === 0 && (
          <div className="text-center text-neutral-500 text-xs py-8">
            {sources.length === 0
              ? "No NDI sources detected."
              : "No results for your filter."}
          </div>
        )}
        {filtered.map((s) => {
          const active = activeSourceIds.includes(s.id);
          return (
            <button
              key={s.id}
              className={`source-item w-full text-left ${active ? "active" : ""}`}
              onClick={() => onAddSource(s)}
              data-testid={`ndi-source-item-${s.id}`}
              title={active ? "Already on canvas — click to add another" : "Add to canvas"}
            >
              <span className={s.connected ? "led led-green" : "led led-red"} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-neutral-100 truncate">
                  {s.name}
                </div>
                <div className="text-[10px] text-neutral-500 font-mono flex items-center gap-2 mt-0.5">
                  {s.is_demo ? (
                    <span className="chip chip-amber !py-[1px]">DEMO</span>
                  ) : (
                    <span className="chip chip-green !py-[1px]">NDI</span>
                  )}
                  {s.width > 0 && (
                    <span>
                      {s.width}×{s.height}
                    </span>
                  )}
                </div>
              </div>
              <Signal size={12} className="text-neutral-500" />
            </button>
          );
        })}
      </div>

      <div className="px-3 py-2 border-t border-[#262626] text-[11px] text-neutral-500 font-mono flex justify-between">
        <span>{sources.length} sources</span>
        <span>{sources.filter((s) => s.connected).length} live</span>
      </div>
    </aside>
  );
}
