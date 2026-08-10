from __future__ import annotations

import io
from datetime import datetime

import mss
from PIL import Image


def _left_monitor(monitors: list[dict]) -> dict:
    """Pick the leftmost physical monitor (skip virtual monitors[0])."""
    physical = monitors[1:]
    if not physical:
        return monitors[0]
    return min(physical, key=lambda m: (m["left"], m["top"]))


def grab_screenshot_jpeg(quality: int = 70) -> tuple[bytes, str]:
    """Capture only the left monitor into one JPEG and return (bytes, filename)."""
    with mss.mss() as sct:
        monitor = _left_monitor(sct.monitors)
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return buffer.getvalue(), f"screen_left_{stamp}.jpg"
