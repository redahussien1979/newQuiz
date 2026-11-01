"""Studio polish applied to finished frames: virtual camera (drift / push-in), transitions (zoom-through,
whip pan) and a cinematic finish (bloom, vignette, film grain, light leaks)."""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from .core import H, W


def camera(img, zoom=1.0, ox=0.0, oy=0.0):
    """Look at the frame through a camera that is zoomed in by `zoom` (>= 1) and shifted by (ox, oy) pixels."""
    zoom = max(1.0, zoom)
    w, h = W / zoom, H / zoom
    x0 = min(max((W - w) / 2 - ox, 0.0), W - w)
    y0 = min(max((H - h) / 2 - oy, 0.0), H - h)
    return img.convert("RGB").resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


def zoom_blur(img, amount, n=8):
    """Radial (zoom) blur, `amount` = how much bigger the last copy is (0.25 = 25 %)."""
    if amount <= 0.005:
        return img
    rgb = img.convert("RGB")
    acc = np.zeros((H, W, 3), np.float32)
    for i in range(n):
        s = 1 + amount * i / (n - 1)
        w, h = W / s, H / s
        acc += np.asarray(rgb.transform((W, H), Image.EXTENT, ((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2),
                                        Image.BILINEAR), np.float32)
    return Image.fromarray((acc / n).astype(np.uint8)).convert("RGBA")


def whip(img, amount):
    """Horizontal motion smear for a whip pan (box blur along x, `amount` pixels)."""
    k = int(amount)
    if k < 2:
        return img
    a = np.asarray(img.convert("RGB"), np.float32)
    pad = np.pad(a, ((0, 0), (k, 0), (0, 0)), mode="edge")
    cs = np.cumsum(pad, axis=1)
    sm = (cs[:, k:] - cs[:, :-k]) / k
    sm = np.concatenate([a[:, :1], sm], axis=1)[:, :W]
    return Image.fromarray(np.clip(sm, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=1)
def _vig_grain():
    """Six tiles of vignette x film grain, applied with a single multiply."""
    yy, xx = np.mgrid[0:H, 0:W]
    v = np.clip(1.12 - 0.62 * (((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2), 0.55, 1.0)
    tiles = []
    for i in range(6):
        g = np.random.default_rng(i).normal(0, 1, (H // 2, W // 2)).astype(np.float32)
        g = np.asarray(Image.fromarray(((g * 40) + 128).clip(0, 255).astype(np.uint8), "L")
                       .resize((W, H), Image.BILINEAR), np.float32) - 128
        m = Image.fromarray(np.clip(v * (1 + g * 0.0009) * 255, 0, 255).astype(np.uint8), "L")
        tiles.append(Image.merge("RGB", (m, m, m)))
    return tiles


@lru_cache(maxsize=1)
def _leak():
    yy, xx = np.mgrid[0:H, 0:W]
    m = np.clip(1 - np.sqrt(((xx - W * 0.85) / 700.0) ** 2 + ((yy - H * 0.2) / 900.0) ** 2), 0, 1)
    return Image.fromarray((m[..., None] * np.array([255, 150, 60])).astype(np.uint8), "RGB")


_BLOOM_LUT = [min(255, int(max(0, v - 170) * 3 * 0.45)) for v in range(256)] * 3


def grade(img, frame_no, leak=0.0):
    """Cinematic finish: bloom on bright parts, vignette, film grain, optional light leak."""
    rgb = img.convert("RGB")
    bloom = rgb.reduce(6).point(_BLOOM_LUT).filter(ImageFilter.GaussianBlur(4))
    out = ImageChops.screen(rgb, bloom.resize((W, H), Image.BILINEAR))
    out = ImageChops.multiply(out, _vig_grain()[frame_no % 6])
    if leak > 0.005:
        k = min(1.0, leak)
        out = ImageChops.screen(out, _leak().point(lambda v: int(v * k)))
    return out
