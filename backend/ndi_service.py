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
    # runtime
    connected: bool = False
    fps: float = 0.0
    width: int = 0
    height: int = 0
    last_frame_time: float = field(default_factory=lambda: 0.0)


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
                    bandwidth=RecvBandwidth.highest,
                )
                video_frame = VideoFrameSync()
                recv.frame_sync.set_video_frame(video_frame)
                recv.set_source(src_obj)
                self._receivers[info.id] = recv
                self._video_frames[info.id] = video_frame
                return recv
            except Exception:
                return None

    def _pull_ndi_jpeg(self, info: SourceInfo) -> Optional[bytes]:
        arr = self._pull_ndi_rgb(info)
        if arr is None:
            return None
        h, w = arr.shape[:2]
        img = Image.fromarray(arr, "RGB")
        # Downscale large frames for browser efficiency
        if w > 960:
            new_w = 960
            new_h = int(h * new_w / w)
            img = img.resize((new_w, new_h), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

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
                arr = arr.reshape(h, w, 4)[:, :, :3]
            except Exception:
                total = arr.size
                if total == h * w * 4:
                    arr = arr.reshape(h, w, 4)[:, :, :3]
                else:
                    return None
            info.width, info.height = w, h
            info.connected = True
            return arr
        except Exception:
            return None

    def get_frame_rgb(self, source_id: str) -> Optional[np.ndarray]:
        """Return the latest frame for a source as an RGB uint8 ndarray.

        Used by both the MJPEG endpoint and the program (composite) NDI sender.
        """
        info = self.get_source(source_id)
        if info is None:
            return None
        if info.is_demo:
            stream = self._demo_streams.get(source_id)
            if stream is None:
                return None
            return stream.render_frame_array()
        return self._pull_ndi_rgb(info)

    def mjpeg_stream(self, source_id: str):
        """Generator yielding a multipart MJPEG stream for the given source."""
        info = self.get_source(source_id)
        if info is None:
            return
        boundary = b"--frame"
        target_fps = 25
        frame_interval = 1.0 / target_fps
        # For FPS metric
        frame_times: List[float] = []

        try:
            while True:
                start = time.time()
                jpeg: Optional[bytes] = None
                if info.is_demo:
                    stream = self._demo_streams.get(source_id)
                    if stream is not None:
                        jpeg = stream.render_frame()
                        info.width = stream.width
                        info.height = stream.height
                        info.connected = True
                else:
                    jpeg = self._pull_ndi_jpeg(info)

                if jpeg is None:
                    # send a placeholder "no signal" frame
                    jpeg = _no_signal_jpeg(info.name)

                now = time.time()
                frame_times.append(now)
                cutoff = now - 1.0
                while frame_times and frame_times[0] < cutoff:
                    frame_times.pop(0)
                info.fps = float(len(frame_times))
                info.last_frame_time = now

                yield (
                    b"\r\n" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" +
                    jpeg
                )

                # Pace the loop for both demo and real NDI sources so we
                # never spin at hundreds of FPS when the source hasn't
                # produced a fresh frame yet.
                elapsed = time.time() - start
                sleep_for = frame_interval - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        except (GeneratorExit, ConnectionResetError):
            return
        except Exception:
            return

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
