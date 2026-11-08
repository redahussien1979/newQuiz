"""Know a Country: 3D globe renderer (orthographic): colourful political map, highlighted target, atmosphere."""
import json, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import topo

CACHE_DIR = None  # set by video.py (the user's data folder); the world raster is cached there (~70 MB)

GW, GH = 8192, 4096          # global texture: 22.75 px per degree

# Style B "dark news": one slate land colour, near-black ocean, light-grey vector borders
OCEAN = (12, 20, 36)
PALETTE = np.array([(50, 60, 76)], np.uint8)
MUTED = np.array([50, 60, 76], np.float32)
BORDER = (150, 166, 188)
BORDER_W = 1.8
TARGET = np.array([255, 145, 20], np.float32)
SECOND = np.array([30, 190, 255], np.float32)
WHITE = np.array([255, 255, 255], np.float32)
ATMO = np.array([70, 130, 210], np.float32)


def load_shapes():
    shapes = []
    for i, f in enumerate(topo.features(), start=1):
        if not f["polys"]:
            continue
        shapes.append((i, f["id"], f["name"], [np.array(p[0], float) for p in f["polys"]]))
    return shapes


def rasterize(shapes, lon0, lat1, res, w, h):
    img = Image.new("I", (w, h), 0)
    d = ImageDraw.Draw(img)
    for idx, _, _, rings in shapes:
        parts = []
        for r in rings:
            if r[:, 0].max() - r[:, 0].min() > 180:  # crosses the 180° line: unwrap, draw on both sides
                u = r.copy()
                u[u[:, 0] < 0, 0] += 360
                parts += [u, u - [360, 0]]
            else:
                parts.append(r)
        for r in parts:
            xs = (r[:, 0] - lon0) * res
            ys = (lat1 - r[:, 1]) * res
            if xs.max() < 0 or xs.min() > w or ys.max() < 0 or ys.min() > h:
                continue
            d.polygon(list(zip(xs.tolist(), ys.tolist())), fill=idx)
    return np.asarray(img, dtype=np.int32).astype(np.uint16)


def edges(ids):
    e = np.zeros(ids.shape, bool)
    e[:, 1:] |= ids[:, 1:] != ids[:, :-1]
    e[1:, :] |= ids[1:, :] != ids[:-1, :]
    return e


def dilate(mask, size):
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(size))) > 0


class Texture:
    """Colour image + masks (target, neighbours, land, target outline), sampled bilinearly."""

    def __init__(self, ids, lon0, lat1, res, target_idx, neigh_idx, wrap, fine):
        self.lon0, self.lat1, self.res, self.wrap = lon0, lat1, res, wrap
        land = ids > 0
        e = edges(ids)
        if fine:
            e = dilate(e, 3)
        lut = PALETTE[(np.arange(int(ids.max()) + 1) * 5 + 3) % len(PALETTE)]
        lut[0] = OCEAN
        self.base = lut[ids]  # flat fills; borders are drawn as vectors (Globe.borders)
        tgt = ids == target_idx
        ring = dilate(tgt, 7 if fine else 3) & ~tgt
        ngh = np.isin(ids, list(neigh_idx)) if neigh_idx else np.zeros_like(tgt)
        self.masks = np.stack([tgt, ngh, land, ring], -1).astype(np.uint8) * 255
        self.ids = ids
        self.h, self.w = ids.shape

    def coords(self, lon, lat):
        return (lon - self.lon0) * self.res - 0.5, (self.lat1 - lat) * self.res - 0.5

    def inside(self, lon, lat):
        x, y = self.coords(lon, lat)
        return (x >= 0) & (x < self.w - 1) & (y >= 0) & (y < self.h - 1)

    def sample(self, lon, lat, active=None):
        x, y = self.coords(lon, lat)
        x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
        fx = (x - x0)[..., None].astype(np.float32); fy = (y - y0)[..., None].astype(np.float32)
        y0 = np.clip(y0, 0, self.h - 2); y1 = y0 + 1
        if self.wrap:
            x0 %= self.w; x1 = (x0 + 1) % self.w
        else:
            x0 = np.clip(x0, 0, self.w - 2); x1 = x0 + 1
        out = []
        for arr in (self.base, self.masks):
            a = arr[y0, x0].astype(np.float32); b = arr[y0, x1].astype(np.float32)
            c = arr[y1, x0].astype(np.float32); d = arr[y1, x1].astype(np.float32)
            out.append((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
        if active:
            ids = self.ids
            a = (ids[y0, x0] == active).astype(np.float32); b = (ids[y0, x1] == active).astype(np.float32)
            c = (ids[y1, x0] == active).astype(np.float32); d = (ids[y1, x1] == active).astype(np.float32)
            fx1, fy1 = fx[..., 0], fy[..., 0]
            sec = (a * (1 - fx1) + b * fx1) * (1 - fy1) + (c * (1 - fx1) + d * fx1) * fy1
        else:
            sec = np.zeros(lon.shape, np.float32)
        return out[0], out[1] / 255.0, sec


def ring_bbox(r):
    """Bounding box of one ring; rings crossing the 180° line are unwrapped (lon may exceed 180)."""
    lon = r[:, 0]
    if lon.max() - lon.min() > 180:
        lon = np.where(lon < 0, lon + 360, lon)
    return lon.min(), r[:, 1].min(), lon.max(), r[:, 1].max()


def main_rings(rings, pad=12.0):
    """The country's main land mass plus everything near it (drops far territories such as Alaska
    for the USA or French Guiana for France); works across the 180° line."""
    rings = sorted(rings, key=lambda r: -len(r))
    b0 = ring_bbox(rings[0])
    c0 = (b0[0] + b0[2]) / 2
    keep = []
    for r in rings:
        b = ring_bbox(r)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        cx += 360 * round((c0 - cx) / 360)
        if b0[0] - pad <= cx <= b0[2] + pad and b0[1] - pad <= cy <= b0[3] + pad:
            keep.append(r)
    return keep


def main_bbox(rings):
    """Bounding box of the main land masses (ignores tiny islets and far territories)."""
    rings = main_rings(rings)
    big = [r for r in rings if len(r) >= max(12, len(rings[0]) * 0.05)]
    c0 = (ring_bbox(rings[0])[0] + ring_bbox(rings[0])[2]) / 2
    bbs = []
    for r in big:
        b = ring_bbox(r)
        sh = 360 * round((c0 - (b[0] + b[2]) / 2) / 360)
        bbs.append((b[0] + sh, b[1], b[2] + sh, b[3]))
    return (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))


class Globe:
    def __init__(self, target_name, neighbor_names, screen_w=1080, screen_h=1920, extra_regions=()):
        shapes = load_shapes()
        by_name = {s[2]: s for s in shapes}
        self.id_of = {s[2]: s[0] for s in shapes}
        self.rings_rad = [(np.radians(r[:, 0]), np.radians(r[:, 1])) for s in shapes for r in s[3]]
        t = by_name[target_name]
        neigh = {by_name[n][0] for n in neighbor_names if n in by_name}
        cache = os.path.join(CACHE_DIR, "kc_world_ids.npy") if CACHE_DIR else None
        if cache and os.path.exists(cache):
            gids = np.load(cache)
        else:
            gids = rasterize(shapes, -180, 90, GW / 360, GW, GH)
            if cache:
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    np.save(cache + ".tmp.npy", gids)
                    os.replace(cache + ".tmp.npy", cache)
                except OSError:
                    pass
        self.glob = Texture(gids, -180, 90, GW / 360, t[0], neigh, wrap=True, fine=False)
        self.bbox = main_bbox(t[3])
        lo0, la0, lo1, la1 = self.bbox
        self.center = (((lo0 + lo1) / 2 + 180) % 360 - 180, (la0 + la1) / 2)
        self.span = max(lo1 - lo0, (la1 - la0) * 1.25)
        # detailed regional texture, resolution matched to the closest zoom used
        fitR = self.fit_radius(screen_w)
        res = min(260.0, max(30.0, fitR * 2.4 * math.pi / 180))
        m = math.degrees(screen_h / 2 / fitR) + 6
        rl0, rl1 = max(-180, lo0 - m), min(180, lo1 + m)
        ra0, ra1 = max(-89, la0 - m), min(89, la1 + m)
        if rl1 <= rl0:  # whole window lies past 180 after unwrapping
            rl0, rl1 = max(-180, lo0 - m - 360), min(180, lo1 + m - 360)
        while (rl1 - rl0) * (ra1 - ra0) * res * res > 50e6:
            res *= 0.85
        w, h = int((rl1 - rl0) * res), int((ra1 - ra0) * res)
        rids = rasterize(shapes, rl0, ra1, res, w, h)
        self.regs = [Texture(rids, rl0, ra1, res, t[0], neigh, wrap=False, fine=True)]
        # extra detailed textures where the camera will go (e.g. comparison countries)
        for (b0, b1, b2, b3, R) in extra_regions:
            res = min(200.0, max(25.0, R * 2.0 * math.pi / 180))
            m = math.degrees(screen_h / 2 / R) + 4
            rl0, rl1 = max(-180, b0 - m), min(180, b2 + m)
            ra0, ra1 = max(-89, b1 - m), min(89, b3 + m)
            while (rl1 - rl0) * (ra1 - ra0) * res * res > 16e6:
                res *= 0.85
            w, h = int((rl1 - rl0) * res), int((ra1 - ra0) * res)
            self.regs.append(Texture(rasterize(shapes, rl0, ra1, res, w, h), rl0, ra1, res, t[0], neigh, wrap=False, fine=True))

    def fit_radius(self, width_px, fill=0.72):
        return width_px * fill / math.radians(max(self.span, 2.0))

    def render(self, size, cx, cy, lon0, lat0, R, hl=1.0, nh=0.0, dim=1.0, glow_phase=0.0, second_id=None, nb=0.0):
        Wd, Hd = size
        pad = R * 0.12
        x0, x1 = int(max(0, cx - R - pad)), int(min(Wd, cx + R + pad))
        y0, y1 = int(max(0, cy - R - pad)), int(min(Hd, cy + R + pad))
        layer = np.zeros((Hd, Wd, 4), np.float32)
        if x1 <= x0 or y1 <= y0:
            return Image.fromarray(layer.astype(np.uint8), "RGBA")
        xs = (np.arange(x0, x1, dtype=np.float32) + 0.5 - cx) / R
        ys = -(np.arange(y0, y1, dtype=np.float32) + 0.5 - cy) / R
        px, py = np.meshgrid(xs, ys)
        rho = np.sqrt(px * px + py * py)
        inside = rho < 1.0
        halo = np.clip(1 - (rho - 1) / 0.09, 0, 1) ** 2.2 * (rho >= 0.995)
        rgba = np.zeros(px.shape + (4,), np.float32)
        rgba[..., :3] = ATMO
        rgba[..., 3] = halo * 170
        if inside.any():
            p = px[inside]; q = py[inside]; r = np.maximum(rho[inside], 1e-9)
            c = np.arcsin(np.clip(r, 0, 1))
            phi0, lam0 = math.radians(lat0), math.radians(lon0)
            sc, cc = np.sin(c), np.cos(c)
            lat = np.degrees(np.arcsin(np.clip(cc * math.sin(phi0) + q * sc * math.cos(phi0) / r, -1, 1)))
            lon = np.degrees(lam0 + np.arctan2(p * sc, r * math.cos(phi0) * cc - q * math.sin(phi0) * sc))
            lon = (lon + 180) % 360 - 180
            act = second_id if nh > 0 else None
            col, m, sec = self.glob.sample(lon, lat, act)
            done = np.zeros(lon.shape, bool)
            for reg in self.regs:
                sel = reg.inside(lon, lat) & ~done
                if sel.any():
                    col[sel], m[sel], sec[sel] = reg.sample(lon[sel], lat[sel], act)
                    done |= sel
            tg, ng, land, ring = m[:, 0], m[:, 1], m[:, 2], m[:, 3]
            dk = (dim * 0.6 * (1 - sec * nh) * (1 - tg * hl) * land)[:, None]
            col = col * (1 - dk) + MUTED * dk
            sh = np.maximum(sec * nh, ng * nb * 0.6)[:, None]  # compared country or all neighbours
            col = col * (1 - sh) + SECOND * sh
            tcol = np.clip(TARGET * (1 + 0.1 * math.sin(glow_phase)), 0, 255)
            th = (tg * hl)[:, None]
            col = col * (1 - th) + tcol * th
            rh = (ring * hl * (1 - tg))[:, None]
            col = col * (1 - rh) + WHITE * rh
            z = np.sqrt(np.clip(1 - r * r, 0, 1))
            light = np.clip(-0.45 * p + 0.5 * q + 0.74 * z, 0, 1)
            col = col * (0.62 + 0.45 * light)[:, None]
            rim = (np.clip((r - 0.78) / 0.22, 0, 1) ** 2)[:, None]
            col = col * (1 - 0.4 * rim) + ATMO * 0.4 * rim
            aa = np.clip((1 - r) * R, 0, 1)[:, None]
            a_h = rgba[inside][:, 3:4] / 255
            out_a = aa + a_h * (1 - aa)
            out_c = (col * aa + ATMO * a_h * (1 - aa)) / np.maximum(out_a, 1e-6)
            rgba[inside] = np.concatenate([out_c, out_a * 255], 1)
        layer[y0:y1, x0:x1] = rgba
        return Image.fromarray(np.clip(layer, 0, 255).astype(np.uint8), "RGBA")

    def borders(self, layer, cx, cy, lon0, lat0, R, color=BORDER, width=BORDER_W):
        """Stroke every country outline at a constant width (supersampled), clipped to the globe."""
        ss = 2
        big = Image.new("RGBA", (layer.width * ss, layer.height * ss), (0, 0, 0, 0))
        dr = ImageDraw.Draw(big)
        l0, p0 = math.radians(lon0), math.radians(lat0)
        sp0, cp0 = math.sin(p0), math.cos(p0)
        lim = layer.width * ss * 0.5
        fill = tuple(color) + (230,)
        wpx = max(1, int(round(width * ss)))
        for lam, phi in self.rings_rad:
            cphi = np.cos(phi); dl = lam - l0
            cosc = sp0 * np.sin(phi) + cp0 * cphi * np.cos(dl)
            if cosc.max() <= 0:
                continue
            x = (cx + R * cphi * np.sin(dl)) * ss
            y = (cy - R * (cp0 * np.sin(phi) - sp0 * cphi * np.cos(dl))) * ss
            if x.max() < 0 or x.min() > big.width or y.max() < 0 or y.min() > big.height:
                continue
            ok = cosc > 0
            brk = np.zeros(len(x), bool)
            brk[1:] = (np.hypot(np.diff(x), np.diff(y)) > lim) | ~ok[1:] | ~ok[:-1]
            starts = np.flatnonzero(brk | (np.arange(len(x)) == 0))
            ends = np.append(starts[1:], len(x))
            for s0, e0 in zip(starts, ends):
                if e0 - s0 > 1 and ok[s0]:
                    dr.line(list(zip(x[s0:e0].tolist(), y[s0:e0].tolist())), fill=fill, width=wpx, joint="curve")
        big = big.resize(layer.size, Image.LANCZOS)
        a = np.minimum(np.asarray(big.getchannel("A")), np.asarray(layer.getchannel("A")))
        big.putalpha(Image.fromarray(a))
        out = layer.copy()
        out.alpha_composite(big)
        return out

    @staticmethod
    def project(lon, lat, cx, cy, lon0, lat0, R):
        phi, lam = math.radians(lat), math.radians(lon)
        phi0, lam0 = math.radians(lat0), math.radians(lon0)
        cosc = math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(lam - lam0)
        x = R * math.cos(phi) * math.sin(lam - lam0)
        y = R * (math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(lam - lam0))
        return cx + x, cy - y, cosc > 0.05
