"""
Program NDI Sender — composites the current multiview canvas into a single
video frame and publishes it as an NDI source on the network so it can be
consumed by vMix, OBS/NDI, Studio Monitor, TriCaster, etc.
"""
import threading
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from cyndilib.sender import Sender
    from cyndilib.video_frame import VideoSendFrame
    from cyndilib.wrapper.ndi_structs import FourCC
    NDI_SEND_AVAILABLE = True
except Exception:  # pragma: no cover
    NDI_SEND_AVAILABLE = False


@dataclass
class ProgramTile:
    source_id: Optional[str]
    x: float
    y: float
    width: float
    height: float


@dataclass
class ProgramConfig:
    enabled: bool = False
    ndi_name: str = "NdiMultiview"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    canvas_width: float = 1920.0
    canvas_height: float = 1080.0
    tiles: List[ProgramTile] = field(default_factory=list)


class ProgramSender:
    """Background thread that renders + sends the composite NDI feed."""

    def __init__(self, ndi_service: Any):
        self._ndi = ndi_service
        self._cfg = ProgramConfig()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sender: Optional["Sender"] = None
        self._video_frame: Optional["VideoSendFrame"] = None
        self._out_fps = 0.0
        self._frame_count = 0
        self._last_error: Optional[str] = None
        # Sources this sender is currently subscribed to (added as streamer
        # viewers so the shared capture+encode loop stays alive).
        self._active_sources: set = set()

    # ---------- Public API ----------

    @property
    def available(self) -> bool:
        return NDI_SEND_AVAILABLE

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            cfg = self._cfg
            return {
                "available": NDI_SEND_AVAILABLE,
                "enabled": cfg.enabled and self._thread is not None and self._thread.is_alive(),
                "ndi_name": cfg.ndi_name,
                "width": cfg.width,
                "height": cfg.height,
                "fps": cfg.fps,
                "tile_count": len(cfg.tiles),
                "out_fps": round(self._out_fps, 1),
                "error": self._last_error,
            }

    def apply(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update config, and start/stop the sender thread accordingly."""
        with self._lock:
            cfg = self._cfg
            new_name = str(payload.get("ndi_name", cfg.ndi_name) or "NdiMultiview")[:64]
            new_w = int(payload.get("width", cfg.width))
            new_h = int(payload.get("height", cfg.height))
            new_fps = int(payload.get("fps", cfg.fps))
            new_cw = float(payload.get("canvas_width", cfg.canvas_width) or new_w)
            new_ch = float(payload.get("canvas_height", cfg.canvas_height) or new_h)
            new_tiles_raw = payload.get("tiles", None)
            new_enabled = bool(payload.get("enabled", cfg.enabled))

            tiles: List[ProgramTile] = cfg.tiles
            if new_tiles_raw is not None:
                tiles = [
                    ProgramTile(
                        source_id=t.get("source_id"),
                        x=float(t.get("x", 0)),
                        y=float(t.get("y", 0)),
                        width=float(t.get("width", 0)),
                        height=float(t.get("height", 0)),
                    )
                    for t in new_tiles_raw
                    if t.get("width", 0) > 0 and t.get("height", 0) > 0
                ]

            restart_needed = (
                new_name != cfg.ndi_name
                or new_w != cfg.width
                or new_h != cfg.height
                or new_fps != cfg.fps
            )

            self._cfg = ProgramConfig(
                enabled=new_enabled,
                ndi_name=new_name,
                width=max(320, min(3840, new_w)),
                height=max(180, min(2160, new_h)),
                fps=max(5, min(60, new_fps)),
                canvas_width=new_cw,
                canvas_height=new_ch,
                tiles=tiles,
            )

        # Manage lifecycle
        if not self._cfg.enabled:
            self._stop_thread()
            self._sync_viewers(set())
        else:
            # Subscribe/unsubscribe streamers based on the new tile set.
            self._sync_viewers({t.source_id for t in self._cfg.tiles if t.source_id})
            if restart_needed:
                self._stop_thread()
            self._start_thread()
        return self.get_status()

    def shutdown(self):
        self._stop_thread()
        self._sync_viewers(set())

    def _sync_viewers(self, desired: set):
        """Add/remove ourselves as viewers on the source streamers so they
        only run their capture loop when we actually need frames."""
        to_add = desired - self._active_sources
        to_remove = self._active_sources - desired
        for sid in to_add:
            try:
                self._ndi.add_viewer(sid)
            except Exception:
                pass
        for sid in to_remove:
            try:
                self._ndi.remove_viewer(sid)
            except Exception:
                pass
        self._active_sources = set(desired)

    # ---------- Thread management ----------

    def _start_thread(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ProgramSender", daemon=True)
            self._thread.start()

    def _stop_thread(self):
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None
        self._close_sender()

    def _open_sender(self, cfg: ProgramConfig) -> bool:
        if not NDI_SEND_AVAILABLE:
            self._last_error = "NDI runtime not available"
            return False
        try:
            sender = Sender(ndi_name=cfg.ndi_name)
            vf = VideoSendFrame()
            vf.set_resolution(cfg.width, cfg.height)
            vf.set_fourcc(FourCC.BGRA)
            vf.set_frame_rate(Fraction(cfg.fps, 1))
            sender.set_video_frame(vf)
            sender.open()
            self._sender = sender
            self._video_frame = vf
            self._last_error = None
            return True
        except Exception as e:  # pragma: no cover
            self._last_error = f"sender open failed: {e}"
            return False

    def _close_sender(self):
        if self._sender is not None:
            try:
                self._sender.close()
            except Exception:
                pass
        self._sender = None
        self._video_frame = None

    # ---------- Render loop ----------

    def _run(self):
        cfg_snapshot = self._cfg
        if not self._open_sender(cfg_snapshot):
            return

        frame_interval = 1.0 / max(1, cfg_snapshot.fps)
        frame_times: List[float] = []

        # Reusable output buffer (BGRA)
        w, h = cfg_snapshot.width, cfg_snapshot.height
        out = np.zeros((h, w, 4), dtype=np.uint8)
        out[..., 3] = 255  # alpha opaque

        try:
            while not self._stop.is_set():
                start = time.time()
                with self._lock:
                    cfg = self._cfg
                if cfg.width != w or cfg.height != h:
                    # Recreate buffer if resolution changed
                    w, h = cfg.width, cfg.height
                    out = np.zeros((h, w, 4), dtype=np.uint8)
                    out[..., 3] = 255
                    frame_interval = 1.0 / max(1, cfg.fps)

                # Clear
                out[..., 0:3] = 8  # near-black

                self._composite(out, cfg)

                # Send
                try:
                    if self._sender is not None:
                        # write_video_async expects a 1-D uint8 buffer in BGRA order.
                        self._sender.write_video_async(out.reshape(-1))
                except Exception as e:
                    self._last_error = f"send failed: {e}"

                now = time.time()
                frame_times.append(now)
                cutoff = now - 1.0
                while frame_times and frame_times[0] < cutoff:
                    frame_times.pop(0)
                self._out_fps = float(len(frame_times))
                self._frame_count += 1

                elapsed = time.time() - start
                sleep_for = frame_interval - elapsed
                if sleep_for > 0:
                    self._stop.wait(sleep_for)
        finally:
            self._close_sender()
            self._out_fps = 0.0

    # ---------- Composite ----------

    def _composite(self, out: np.ndarray, cfg: ProgramConfig):
        H, W, _ = out.shape
        canvas_w = cfg.canvas_width if cfg.canvas_width > 0 else W
        canvas_h = cfg.canvas_height if cfg.canvas_height > 0 else H
        sx = W / canvas_w
        sy = H / canvas_h

        for tile in cfg.tiles:
            if not tile.source_id:
                continue
            # Target rect in output pixel space
            tx = int(round(tile.x * sx))
            ty = int(round(tile.y * sy))
            tw = int(round(tile.width * sx))
            th = int(round(tile.height * sy))
            if tw <= 4 or th <= 4:
                continue
            # Clip
            x0 = max(0, tx)
            y0 = max(0, ty)
            x1 = min(W, tx + tw)
            y1 = min(H, ty + th)
            if x1 <= x0 or y1 <= y0:
                continue

            arr = self._ndi.get_frame_rgb(tile.source_id)
            if arr is None:
                # Draw a placeholder rect with source id text
                self._draw_placeholder(out, x0, y0, x1, y1, tile.source_id)
                continue

            # Resize source frame to (x1-x0, y1-y0)
            img = Image.fromarray(arr, "RGB")
            img = img.resize((x1 - x0, y1 - y0), Image.BILINEAR)
            rgb = np.array(img, dtype=np.uint8)
            # RGB -> BGRA
            out[y0:y1, x0:x1, 0] = rgb[..., 2]
            out[y0:y1, x0:x1, 1] = rgb[..., 1]
            out[y0:y1, x0:x1, 2] = rgb[..., 0]
            out[y0:y1, x0:x1, 3] = 255

    def _draw_placeholder(self, out: np.ndarray, x0: int, y0: int, x1: int, y1: int, label: str):
        # Draw a subtle grey rectangle with the source label using PIL, then copy back
        w = x1 - x0
        h = y1 - y0
        img = Image.new("RGB", (w, h), (20, 20, 20))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, w - 1, h - 1], outline=(60, 60, 60), width=2)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        draw.text((10, 10), "NO SIGNAL", fill=(255, 59, 48), font=font)
        draw.text((10, 40), (label or "")[:48], fill=(180, 180, 180), font=font)
        rgb = np.array(img, dtype=np.uint8)
        out[y0:y1, x0:x1, 0] = rgb[..., 2]
        out[y0:y1, x0:x1, 1] = rgb[..., 1]
        out[y0:y1, x0:x1, 2] = rgb[..., 0]
        out[y0:y1, x0:x1, 3] = 255
