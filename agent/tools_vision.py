"""
Vision layer interface: blood-smear image -> parasite signal.

Engineer 3 owns the model (YOLOv8 / CNN trained on a BBBC041 subset) and serves it
as an HTTP endpoint (Meterless hotspot or any local server). This module is the
agent's side of that contract, so the two can be developed separately:

    POST {VISION_ENDPOINT_URL}   multipart field "image"
    200 -> {"parasite_present": true, "confidence": 0.85, "parasitemia_band": "moderate", ...}

Before anything is sent, a quick image-quality check (exposure and blur) runs
locally. A poor image is never classified: the agent answers "inconclusive, repeat
the photo or do an RDT".

With no endpoint configured the result says available=False and the triage rules
simply ignore it. Nothing is invented.
"""

from __future__ import annotations

import io
import os
import time
from typing import Any, Dict, Optional

import requests

try:
    import numpy as np
    from PIL import Image
except ImportError:  # quality check becomes a no-op
    np = None
    Image = None


def quality_check(image_bytes: bytes) -> Dict[str, Any]:
    if np is None or Image is None:
        return {"ok": True, "checked": False, "detail": "Pillow/numpy not installed; quality not checked"}
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception:
        return {"ok": False, "checked": True, "detail": "file is not a readable image"}
    img.thumbnail((640, 640))
    a = np.asarray(img, dtype=np.float32)
    brightness = float(a.mean())
    # Variance of a simple Laplacian: low values mean a blurry photo.
    lap = (-4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:])
    sharpness = float(lap.var())
    problems = []
    if brightness < 40:
        problems.append("too dark")
    if brightness > 235:
        problems.append("overexposed")
    if sharpness < 15:
        problems.append("blurry")
    return {"ok": not problems, "checked": True, "brightness": round(brightness, 1),
            "sharpness": round(sharpness, 1), "detail": ", ".join(problems) or "image quality acceptable"}


def analyze_smear(image_bytes: Optional[bytes], filename: str = "smear.jpg") -> Dict[str, Any]:
    if not image_bytes:
        return {"available": False, "detail": "no image uploaded"}
    qc = quality_check(image_bytes)
    if not qc["ok"]:
        return {"available": True, "parasite_present": None, "confidence": None, "quality": qc,
                "source": "quality-check", "detail": f"photo rejected ({qc['detail']}): retake it or do an RDT"}
    url = os.environ.get("VISION_ENDPOINT_URL", "").strip()
    if not url:
        return {"available": False, "quality": qc, "source": "none",
                "detail": "vision endpoint not configured (set VISION_ENDPOINT_URL)"}
    started = time.perf_counter()
    try:
        r = requests.post(url, files={"image": (filename, image_bytes)}, timeout=60)
        r.raise_for_status()
        out = r.json()
    except (requests.RequestException, ValueError) as e:
        return {"available": False, "quality": qc, "source": url, "detail": f"vision endpoint error: {e}"}
    return {
        "available": True,
        "parasite_present": bool(out.get("parasite_present")),
        "confidence": float(out.get("confidence", 0.0)),
        "parasitemia_band": out.get("parasitemia_band"),
        "model": out.get("model", "smear-detector"),
        "quality": qc,
        "source": url,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "detail": "proxy model trained on BBBC041 (P. vivax); a positive flag needs RDT or microscopy confirmation",
    }
