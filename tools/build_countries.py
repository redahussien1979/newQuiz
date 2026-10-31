"""Rebuild data/countries.json and data/flags/ (run once by the developer, not needed by the app).

    python tools/build_countries.py ne_50m_admin_0_countries.geojson [--flags]

Outlines: Natural Earth 1:50m Admin 0 countries (public domain, https://www.naturalearthdata.com).
Flags (--flags): PNGs from flagcdn.com (public-domain flag images), 640 px wide.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "countries.json")
FLAGS = os.path.join(ROOT, "data", "flags")
SKIP = {"KAS", "ATC"}  # Siachen Glacier, Ashmore and Cartier Is. (not countries)
TOL = 0.02  # simplification tolerance in degrees (about 2 km)


def _rdp(pts, tol):
    """Ramer-Douglas-Peucker line simplification."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            dist = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / n if n else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            if dist > best:
                best, idx = dist, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def main(src, flags=False):
    feats = json.load(open(src, encoding="utf-8"))["features"]
    out = {}
    for f in feats:
        p, g = f["properties"], f["geometry"]
        code = p["ADM0_A3"]
        if code in SKIP:
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            raw = [tuple(pt) for pt in poly[0]]
            r = _rdp(raw, TOL)
            if len(r) < 4:  # tiny islands / micro-states: keep the original outline
                r = raw
            if len(r) >= 4:
                rings.append([[round(x, 3), round(y, 3)] for x, y in r])
        if not rings:
            continue
        iso2 = p.get("ISO_A2_EH") or p.get("ISO_A2") or "-99"
        out[code] = {"ar": p.get("NAME_AR") or p["NAME"], "en": p["NAME"],
                     "iso2": "" if iso2 == "-99" else iso2.lower(), "rings": rings}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(out)} countries -> {OUT} ({os.path.getsize(OUT) // 1024} KB)")
    if flags:
        os.makedirs(FLAGS, exist_ok=True)
        for c in sorted({v["iso2"] for v in out.values() if v["iso2"]}):
            dst = os.path.join(FLAGS, c + ".png")
            if os.path.isfile(dst):
                continue
            try:
                urllib.request.urlretrieve(f"https://flagcdn.com/w640/{c}.png", dst)
            except Exception as e:  # a missing flag only means that country falls back to its map icon
                print("no flag:", c, e)
            time.sleep(0.05)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], "--flags" in sys.argv)
