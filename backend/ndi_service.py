"""
NDI service - discovers NDI sources on the network and streams frames.
Falls back to demo mode with synthetic sources when no real NDI sources are found.
"""
import io
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from cyndilib.finder import Finder
    from cyndilib.receiver import Receiver
    from cyndilib.video_frame import VideoFrameSync
    from cyndilib.wrapper.ndi_recv import RecvBandwidth, RecvColorFormat
    NDI_AVAILABLE = True
except Exception:  # pragma: no cover - cyndilib not installed / no NDI runtime
    NDI_AVAILABLE = False


@dataclass
class SourceInfo:
    id: str
    name: str
    is_demo: bool = False
    # bandwidth mode: "low" (NDI proxy, ~640×360) or "high" (full bandwidth)
    bandwidth: str = "low"
    # runtime
    connected: bool = False
    fps: float = 0.0
    width: int = 0
    height: int = 0
    last_frame_time: float = field(default_factory=lambda: 0.0)


class SourceStreamer:
    """One capture+encode loop per source, shared across all viewers.

    Multiple MJPEG connections to the same source share the same producer
    thread; the program sender reads the latest RGB frame from here too.
    Runs while `_viewers > 0` (viewers = MJPEG clients + program sender).
    """

    TARGET_FPS = 15
    MAX_WIDTH = 480
    JPEG_QUALITY = 60

    def __init__(self, service: "NDIService", source_id: str):
        self.service = service
        self.source_id = source_id
        self._latest_jpeg: Optional[bytes] = None
        self._latest_rgb: Optional[np.ndarray] = None
        self._latest_id = 0
        self._cond = threading.Condition()
        self._viewers = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def add_viewer(self):
        with self._cond:
            self._viewers += 1
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._run, name=f"streamer:{self.source_id}", daemon=True
                )
                self._thread.start()

    def remove_viewer(self):
        with self._cond:
            self._viewers = max(0, self._viewers - 1)
            if self._viewers == 0:
                self._stop.set()
                self._cond.notify_all()

    def wait_next_frame(self, last_id: int, timeout: float = 2.0):
        with self._cond:
            deadline = time.time() + timeout
            while not self._stop.is_set() and self._latest_id == last_id:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=remaining)
            return self._latest_id, self._latest_jpeg

    def get_latest_rgb(self) -> Optional[np.ndarray]:
        with self._cond:
            return self._latest_rgb

    def clear_cache(self):
        with self._cond:
            self._latest_jpeg = None
            self._latest_rgb = None
            self._cond.notify_all()

    def _run(self):
        interval = 1.0 / self.TARGET_FPS
        info = self.service.get_source(self.source_id)
        frame_times: List[float] = []
        while not self._stop.is_set():
            t0 = time.time()
            rgb = self.service._get_rgb_frame(self.source_id)
            if rgb is not None:
                jpeg = self._encode_jpeg(rgb)
                with self._cond:
                    self._latest_rgb = rgb
                    self._latest_jpeg = jpeg
                    self._latest_id += 1
                    self._cond.notify_all()
                if info is not None:
                    now = time.time()
                    frame_times.append(now)
                    cutoff = now - 1.0
                    while frame_times and frame_times[0] < cutoff:
                        frame_times.pop(0)
                    info.fps = float(len(frame_times))
                    info.last_frame_time = now
            elapsed = time.time() - t0
            sleep_for = interval - elapsed
            if sleep_for > 0:
                self._stop.wait(sleep_for)
        # Cleanup on exit
        if info is not None:
            info.fps = 0.0

    def _encode_jpeg(self, rgb: np.ndarray) -> bytes:
        h, w = rgb.shape[:2]
        # Fast integer-step downscale via numpy slicing; keeps CPU low.
        if w > self.MAX_WIDTH:
            step = max(1, int(round(w / self.MAX_WIDTH)))
            rgb = rgb[::step, ::step]
        img = Image.fromarray(rgb, "RGB")
        buf = io.BytesIO()
        img.save(
            buf,
            format="JPEG",
            quality=self.JPEG_QUALITY,
            subsampling=2,  # 4:2:0
            optimize=False,
            progressive=False,
        )
        return buf.getvalue()


class DemoStream:
    """Generates a synthetic video stream for a fake NDI source."""

    PALETTES = [
        [(255, 59, 48), (255, 149, 0)],   # red -> amber
        [(52, 199, 89), (0, 122, 255)],   # green -> blue
        [(88, 86, 214), (255, 45, 85)],   # indigo -> pink
        [(255, 204, 0), (52, 199, 89)],   # yellow -> green
        [(64, 200, 224), (94, 92, 230)],  # teal -> purple
        [(255, 149, 0), (255, 59, 48)],   # amber -> red
    ]

    def __init__(self, name: str, index: int, width: int = 640, height: int = 360, fps: int = 30):
        self.name = name
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.palette = self.PALETTES[index % len(self.PALETTES)]
        self._t0 = time.time()

    def render_frame_array(self) -> np.ndarray:
        """Render one demo frame as an RGB uint8 ndarray (h, w, 3)."""
        t = time.time() - self._t0
        w, h = self.width, self.height
        # Gradient background
        c1 = np.array(self.palette[0], dtype=np.float32)
        c2 = np.array(self.palette[1], dtype=np.float32)
        # animate gradient direction
        angle = t * 0.4
        gx = math.cos(angle)
        gy = math.sin(angle)
        xs = np.linspace(-1, 1, w)[None, :] * gx
        ys = np.linspace(-1, 1, h)[:, None] * gy
        grad = (xs + ys) * 0.5 + 0.5
        grad = np.clip(grad, 0, 1)[:, :, None]
        arr = (c1 * (1 - grad) + c2 * grad).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
        # Darken slightly for text legibility
        overlay = Image.new("RGB", (w, h), (0, 0, 0))
        img = Image.blend(img, overlay, 0.25)
        draw = ImageDraw.Draw(img)

        # Big source name
        try:
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            font_tc = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 24)
        except Exception:
            font_lg = ImageFont.load_default()
            font_sm = ImageFont.load_default()
            font_tc = ImageFont.load_default()

        draw.text((24, 18), self.name, fill=(255, 255, 255), font=font_lg)
        draw.text((24, 58), "DEMO NDI SOURCE", fill=(230, 230, 230), font=font_sm)

        # Timecode
        tc = time.strftime("%H:%M:%S", time.gmtime()) + f".{int((time.time() % 1) * 100):02d}"
        draw.text((24, h - 44), tc, fill=(255, 255, 255), font=font_tc)

        # Moving square (motion indicator)
        cx = int((math.sin(t * 1.2) * 0.4 + 0.5) * w)
        cy = int((math.cos(t * 0.9) * 0.35 + 0.55) * h)
        r = 26
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=3)

        # Corner marks
        for (x, y) in [(6, 6), (w - 6, 6), (6, h - 6), (w - 6, h - 6)]:
            draw.rectangle([x - 12, y - 2, x, y] if x > 6 else [x, y - 2, x + 12, y], fill=(255, 255, 255))

        return np.array(img, dtype=np.uint8)

    def render_frame(self) -> bytes:
        arr = self.render_frame_array()
        img = Image.fromarray(arr, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()


class NDIService:
    """Discovers NDI sources and provides MJPEG streams for each."""

    REFRESH_INTERVAL = 2.0  # seconds

    def __init__(self):
        self.mode = "ndi" if NDI_AVAILABLE else "demo"
        self._finder: Optional["Finder"] = None
        self._finder_started = False
        self._sources: Dict[str, SourceInfo] = {}
        self._demo_streams: Dict[str, DemoStream] = {}
        self._receivers: Dict[str, "Receiver"] = {}
        self._video_frames: Dict[str, "VideoFrameSync"] = {}
        self._streamers: Dict[str, SourceStreamer] = {}
        self._lock = threading.RLock()
        self._last_refresh = 0.0

        self._init_demo_sources()
        if NDI_AVAILABLE:
            try:
                self._finder = Finder()
                self._finder.open()
                self._finder_started = True
            except Exception:
                self._finder_started = False

    def _init_demo_sources(self):
        demo_names = [
            "STUDIO-A (CAM 1)",
            "STUDIO-A (CAM 2)",
            "STUDIO-B (WIDE)",
            "GRAPHICS ENGINE",
            "REPLAY OUT",
            "GUEST FEED",
        ]
        for i, name in enumerate(demo_names):
            sid = f"demo::{i}"
            info = SourceInfo(id=sid, name=name, is_demo=True, connected=True, width=640, height=360)
            self._sources[sid] = info
            self._demo_streams[sid] = DemoStream(name=name, index=i)

    def refresh(self, force: bool = False) -> List[SourceInfo]:
        now = time.time()
        if not force and now - self._last_refresh < self.REFRESH_INTERVAL:
            return self.list_sources()
        self._last_refresh = now

        real_ids = set()
        if NDI_AVAILABLE and self._finder_started:
            try:
                # Poll finder for updated sources
                self._finder.wait_for_sources(0.2)
                names = self._finder.get_source_names()
                for name in names:
                    sid = f"ndi::{name}"
                    real_ids.add(sid)
                    with self._lock:
                        if sid not in self._sources:
                            self._sources[sid] = SourceInfo(
                                id=sid, name=name, is_demo=False, connected=True
                            )
                        else:
                            # Discovered = available on the network
                            self._sources[sid].connected = True
            except Exception:
                pass

        # Prune real sources that disappeared (keep demo sources always)
        with self._lock:
            to_remove = [
                sid for sid, s in self._sources.items()
                if not s.is_demo and sid not in real_ids
            ]
            for sid in to_remove:
                self._drop_receiver(sid)
                self._sources.pop(sid, None)

        return self.list_sources()

    def list_sources(self) -> List[SourceInfo]:
        with self._lock:
            return list(self._sources.values())

    def get_source(self, source_id: str) -> Optional[SourceInfo]:
        with self._lock:
            return self._sources.get(source_id)

    # -------- Streaming --------

    def _drop_receiver(self, source_id: str):
        recv = self._receivers.pop(source_id, None)
        self._video_frames.pop(source_id, None)
        if recv is not None:
            try:
                recv.disconnect()
            except Exception:
                pass

    def _ensure_receiver(self, info: SourceInfo) -> Optional["Receiver"]:
        if not NDI_AVAILABLE:
            return None
        with self._lock:
            if info.id in self._receivers:
                return self._receivers[info.id]
            # Find the actual Source object by name
            try:
                self._finder.wait_for_sources(0.2)
                src_obj = None
                for s in self._finder.iter_sources():
                    if s.name == info.name:
                        src_obj = s
                        break
                if src_obj is None:
                    return None
                recv = Receiver(
                    color_format=RecvColorFormat.RGBX_RGBA,
                    bandwidth=(
                        RecvBandwidth.lowest
                        if info.bandwidth == "low"
                        else RecvBandwidth.highest
                    ),
                )
                video_frame = VideoFrameSync()
                recv.frame_sync.set_video_frame(video_frame)
                recv.set_source(src_obj)
                self._receivers[info.id] = recv
                self._video_frames[info.id] = video_frame
                return recv
            except Exception:
                return None

    def _pull_ndi_rgb(self, info: SourceInfo) -> Optional[np.ndarray]:
        recv = self._ensure_receiver(info)
        if recv is None:
            return None
        video_frame = self._video_frames.get(info.id)
        if video_frame is None:
            return None
        try:
            recv.frame_sync.capture_video()
            w, h = video_frame.get_resolution()
            if w <= 0 or h <= 0:
                return None
            arr = np.asarray(video_frame.get_array(), dtype=np.uint8, copy=False)
            try:
                # Copy is required — cyndilib overwrites the buffer on the
                # next capture_video() call.
                arr = arr.reshape(h, w, 4)[:, :, :3].copy()
            except Exception:
                total = arr.size
                if total == h * w * 4:
                    arr = arr.reshape(h, w, 4)[:, :, :3].copy()
                else:
                    return None
            info.width, info.height = w, h
            info.connected = True
            return arr
        except Exception:
            return None

    # ---- Streamer / bandwidth ----

    def _get_streamer(self, source_id: str) -> Optional[SourceStreamer]:
        with self._lock:
            if source_id not in self._sources:
                return None
            streamer = self._streamers.get(source_id)
            if streamer is None:
                streamer = SourceStreamer(self, source_id)
                self._streamers[source_id] = streamer
            return streamer

    def _get_rgb_frame(self, source_id: str) -> Optional[np.ndarray]:
        """Producer helper — called only from a SourceStreamer thread."""
        info = self.get_source(source_id)
        if info is None:
            return None
        if info.is_demo:
            stream = self._demo_streams.get(source_id)
            return stream.render_frame_array() if stream is not None else None
        return self._pull_ndi_rgb(info)

    def set_bandwidth(self, source_id: str, bandwidth: str) -> bool:
        if bandwidth not in ("low", "high"):
            return False
        info = self.get_source(source_id)
        if info is None:
            return False
        if info.bandwidth == bandwidth:
            return True
        with self._lock:
            info.bandwidth = bandwidth
            if not info.is_demo:
                # Recreate the receiver with the new bandwidth mode.
                self._drop_receiver(source_id)
            streamer = self._streamers.get(source_id)
        if streamer is not None:
            streamer.clear_cache()
        return True

    def add_viewer(self, source_id: str):
        s = self._get_streamer(source_id)
        if s is not None:
            s.add_viewer()

    def remove_viewer(self, source_id: str):
        s = self._streamers.get(source_id)
        if s is not None:
            s.remove_viewer()

    def get_frame_rgb(self, source_id: str) -> Optional[np.ndarray]:
        """Latest RGB frame from the shared cache (used by ProgramSender)."""
        s = self._streamers.get(source_id)
        if s is None:
            return None
        return s.get_latest_rgb()

    def mjpeg_stream(self, source_id: str):
        """Generator yielding a multipart MJPEG stream for the given source.

        Uses the shared SourceStreamer so multiple viewers of the same source
        share a single capture+encode loop.
        """
        info = self.get_source(source_id)
        streamer = self._get_streamer(source_id)
        if streamer is None or info is None:
            return
        boundary = b"--frame"
        streamer.add_viewer()
        last_id = 0
        try:
            while True:
                new_id, jpeg = streamer.wait_next_frame(last_id, timeout=2.0)
                if jpeg is None:
                    jpeg = _no_signal_jpeg(info.name)
                last_id = new_id
                yield (
                    b"\r\n" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" +
                    jpeg
                )
        except (GeneratorExit, ConnectionResetError):
            return
        except Exception:
            return
        finally:
            streamer.remove_viewer()

    def shutdown(self):
        with self._lock:
            for sid in list(self._receivers.keys()):
                self._drop_receiver(sid)
            if self._finder is not None and self._finder_started:
                try:
                    self._finder.close()
                except Exception:
                    pass


_no_signal_cache: Dict[str, bytes] = {}


def _no_signal_jpeg(name: str) -> bytes:
    key = f"nosig::{name}"
    if key in _no_signal_cache:
        return _no_signal_cache[key]
    w, h = 640, 360
    img = Image.new("RGB", (w, h), (10, 10, 10))
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
    draw.text((24, 20), name, fill=(230, 230, 230), font=font_lg)
    draw.text((24, h - 44), "NO SIGNAL", fill=(255, 59, 48), font=font_lg)
    draw.text((24, 62), "Waiting for NDI feed…", fill=(150, 150, 150), font=font_sm)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    _no_signal_cache[key] = buf.getvalue()
    return buf.getvalue()


ndi_service = NDIService()
