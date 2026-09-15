import React from "react";
import { Rnd } from "react-rnd";
import { Radio, Signal, Gauge, X, Maximize2 } from "lucide-react";

/**
 * A single video tile shown on the multiview canvas.
 * Streams MJPEG from backend and displays UMD info.
 */
export default function VideoTile({
  tile,
  source,
  streamUrl,
  selected,
  onSelect,
  onChange,
  onRemove,
  onFullscreen,
  bounds,
}) {
  const [naturalFps, setNaturalFps] = React.useState(0);
  const [signalOk, setSignalOk] = React.useState(false);
  const imgRef = React.useRef(null);
  const framesRef = React.useRef([]);
  const timeoutRef = React.useRef(null);

  // Use backend-reported FPS if available (more reliable for MJPEG),
  // otherwise fall back to the client-side load-event counter.
  const displayedFps = source?.fps > 0 ? Math.round(source.fps) : naturalFps;

  React.useEffect(() => {
    if (!streamUrl) return undefined;
    const img = imgRef.current;
    if (!img) return undefined;

    const onLoad = () => {
      const now = performance.now();
      framesRef.current.push(now);
      const cutoff = now - 1000;
      while (framesRef.current.length && framesRef.current[0] < cutoff) {
        framesRef.current.shift();
      }
      setNaturalFps(framesRef.current.length);
      setSignalOk(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setSignalOk(false), 2000);
    };
    // MJPEG in <img> fires "load" every frame in most browsers
    img.addEventListener("load", onLoad);
    return () => {
      img.removeEventListener("load", onLoad);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [streamUrl]);

  const ledClass = !source
    ? "led led-off"
    : (signalOk || source?.fps > 0)
    ? "led led-green"
    : "led led-amber";

  const isLive = source && (signalOk || source?.fps > 0);
  const statusText = !source ? "NO SOURCE" : isLive ? "LIVE" : "WAITING";

  return (
    <Rnd
      size={{ width: tile.width, height: tile.height }}
      position={{ x: tile.x, y: tile.y }}
      bounds={bounds}
      minWidth={220}
      minHeight={130}
      onDragStart={() => onSelect?.(tile.id)}
      onDragStop={(_, d) => onChange?.(tile.id, { x: d.x, y: d.y })}
      onResizeStop={(_, __, ref, ___, pos) =>
        onChange?.(tile.id, {
          width: parseFloat(ref.style.width),
          height: parseFloat(ref.style.height),
          x: pos.x,
          y: pos.y,
        })
      }
      dragHandleClassName="tile-drag-handle"
      className="tile-wrap"
      data-testid={`video-tile-${tile.id}`}
    >
      <div
        className={`tile-shell w-full h-full flex flex-col ${selected ? "selected" : ""}`}
        onClick={() => onSelect?.(tile.id)}
      >
        {/* Drag handle bar */}
        <div
          className="tile-drag-handle no-select flex items-center justify-between px-2 py-1 bg-black/70 backdrop-blur-sm cursor-move"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Radio size={12} className="text-neutral-400 shrink-0" />
            <span
              className="font-condensed text-[13px] font-semibold text-white truncate"
              title={source?.name || "No source assigned"}
              data-testid={`tile-name-${tile.id}`}
            >
              {source?.name || "— NO SOURCE —"}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="p-1 text-neutral-400 hover:text-white transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                onFullscreen?.(tile.id);
              }}
              title="Fullscreen"
              data-testid={`tile-fullscreen-${tile.id}`}
            >
              <Maximize2 size={12} />
            </button>
            <button
              className="p-1 text-neutral-400 hover:text-[#FF3B30] transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                onRemove?.(tile.id);
              }}
              title="Remove tile"
              data-testid={`tile-remove-${tile.id}`}
            >
              <X size={12} />
            </button>
          </div>
        </div>

        {/* Video area */}
        <div className="relative flex-1 bg-black overflow-hidden">
          {streamUrl ? (
            <img
              ref={imgRef}
              src={streamUrl}
              alt={source?.name || ""}
              className="w-full h-full object-contain block"
              draggable={false}
              data-testid={`tile-stream-${tile.id}`}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-neutral-600 text-xs uppercase tracking-widest">
              Drop a source here
            </div>
          )}

          {/* UMD (Under Monitor Display) overlay */}
          <div className="absolute bottom-2 left-2 right-2 bg-black/75 backdrop-blur-sm border border-white/10 rounded-md flex items-stretch overflow-hidden">
            <div className="flex items-center gap-2 px-2 py-1.5 flex-1 min-w-0">
              <span className={ledClass} data-testid={`tile-led-${tile.id}`} />
              <span className="font-condensed text-[12px] font-semibold text-white uppercase tracking-wide">
                {statusText}
              </span>
              <span className="text-neutral-500 text-[11px] font-mono ml-auto truncate">
                {source?.width && source?.height ? `${source.width}×${source.height}` : ""}
              </span>
            </div>
            <div
              className="flex items-center gap-1 px-2 py-1.5 border-l border-white/10 bg-black/50"
              data-testid={`tile-fps-${tile.id}`}
            >
              <Gauge size={11} className="text-neutral-400" />
              <span className="font-mono text-[12px] font-bold text-[#34C759]">
                {String(displayedFps).padStart(2, "0")}
              </span>
              <span className="text-[10px] text-neutral-500">FPS</span>
            </div>
          </div>
        </div>
      </div>
    </Rnd>
  );
}
