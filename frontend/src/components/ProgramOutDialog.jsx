import React from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Radio, CircleDot } from "lucide-react";

const RESOLUTIONS = [
  { label: "1280 × 720 (720p)", w: 1280, h: 720 },
  { label: "1920 × 1080 (1080p)", w: 1920, h: 1080 },
  { label: "2560 × 1440 (1440p)", w: 2560, h: 1440 },
  { label: "3840 × 2160 (2160p)", w: 3840, h: 2160 },
];
const FPS_OPTIONS = [25, 30, 50, 60];

export default function ProgramOutDialog({
  api,
  open,
  onClose,
  status,
  onStatusChange,
  tiles,
  canvasSize,
}) {
  const [ndiName, setNdiName] = React.useState(status?.ndi_name || "NdiMultiview");
  const [resolution, setResolution] = React.useState(
    `${status?.width || 1920}x${status?.height || 1080}`
  );
  const [fps, setFps] = React.useState(status?.fps || 30);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setNdiName(status?.ndi_name || "NdiMultiview");
    setResolution(`${status?.width || 1920}x${status?.height || 1080}`);
    setFps(status?.fps || 30);
  }, [open, status]);

  if (!open) return null;

  const submit = async (enabled) => {
    const [w, h] = resolution.split("x").map(Number);
    const payload = {
      enabled,
      ndi_name: ndiName.trim() || "NdiMultiview",
      width: w,
      height: h,
      fps,
      canvas_width: canvasSize?.width || w,
      canvas_height: canvasSize?.height || h,
      tiles: (tiles || []).map((t) => ({
        source_id: t.source_id,
        x: t.x,
        y: t.y,
        width: t.width,
        height: t.height,
      })),
    };
    setBusy(true);
    try {
      const { data } = await axios.post(`${api}/program`, payload);
      onStatusChange?.(data);
      toast.success(enabled ? "Program Out on air" : "Program Out stopped");
      onClose?.();
    } catch (e) {
      console.error(e);
      toast.error("Program Out failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[999] flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
      data-testid="program-out-dialog"
    >
      <div
        className="bg-[#121212] border border-[#262626] rounded-lg p-5 w-[440px] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Radio size={16} className="text-[#FF3B30]" />
            <h3 className="font-condensed text-lg font-bold uppercase tracking-wider">
              Program Out (NDI)
            </h3>
          </div>
          <button
            className="text-neutral-500 hover:text-neutral-200"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <p className="text-[12px] text-neutral-500 mb-4 leading-snug">
          Publica el multiview compuesto como una fuente NDI en la red. Otros equipos
          (vMix, OBS/NDI, Studio Monitor…) la verán con el nombre que elijas.
        </p>

        <label className="block text-[11px] uppercase tracking-widest text-neutral-500 font-condensed mt-2">
          NDI Source Name
        </label>
        <input
          value={ndiName}
          onChange={(e) => setNdiName(e.target.value)}
          className="w-full mt-1 bg-[#0A0A0A] border border-[#262626] rounded-md px-3 py-2 text-sm text-neutral-100 focus:outline-none focus:border-[#34C759]"
          placeholder="NdiMultiview"
          data-testid="program-name-input"
        />
        <div className="text-[10px] text-neutral-600 mt-1 font-mono">
          Aparecerá como <span className="text-neutral-400">HOSTNAME ({ndiName || "NdiMultiview"})</span>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-4">
          <div>
            <label className="block text-[11px] uppercase tracking-widest text-neutral-500 font-condensed">
              Resolution
            </label>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              className="w-full mt-1 bg-[#0A0A0A] border border-[#262626] rounded-md px-2 py-2 text-sm text-neutral-100 focus:outline-none focus:border-[#34C759]"
              data-testid="program-resolution-select"
            >
              {RESOLUTIONS.map((r) => (
                <option key={`${r.w}x${r.h}`} value={`${r.w}x${r.h}`}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-widest text-neutral-500 font-condensed">
              Frame rate
            </label>
            <select
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              className="w-full mt-1 bg-[#0A0A0A] border border-[#262626] rounded-md px-2 py-2 text-sm text-neutral-100 focus:outline-none focus:border-[#34C759]"
              data-testid="program-fps-select"
            >
              {FPS_OPTIONS.map((f) => (
                <option key={f} value={f}>
                  {f} fps
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 p-3 rounded-md bg-[#0A0A0A] border border-[#262626] text-[12px]">
          <div className="flex items-center justify-between">
            <span className="text-neutral-500 font-condensed uppercase tracking-widest text-[10px]">
              Estado
            </span>
            {status?.enabled ? (
              <span className="flex items-center gap-1 text-[#FF3B30] font-bold">
                <CircleDot size={12} className="animate-pulse" /> ON AIR · {status?.out_fps || 0} fps
              </span>
            ) : (
              <span className="text-neutral-500">OFF</span>
            )}
          </div>
          {status?.error && (
            <div className="text-[11px] text-[#FF6961] mt-1 font-mono">
              {status.error}
            </div>
          )}
          <div className="text-[11px] text-neutral-500 mt-1 font-mono">
            {(tiles || []).length} tiles enviados en el composite
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          {status?.enabled && (
            <button
              className="toolbar-btn danger"
              disabled={busy}
              onClick={() => submit(false)}
              data-testid="program-stop-btn"
            >
              Stop
            </button>
          )}
          <button
            className="toolbar-btn"
            disabled={busy}
            onClick={onClose}
            data-testid="program-cancel-btn"
          >
            Cancel
          </button>
          <button
            className="toolbar-btn primary"
            disabled={busy || (tiles || []).length === 0}
            onClick={() => submit(true)}
            data-testid="program-start-btn"
          >
            {status?.enabled ? "Update" : "Go On Air"}
          </button>
        </div>
      </div>
    </div>
  );
}
