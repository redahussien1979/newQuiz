"""Minimal TopoJSON reader for data/countries-50m.json (world-atlas, Natural Earth 1:50m)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.path.join(HERE, "data", "countries-50m.json")

_cache = None


def features():
    """List of {'id', 'name', 'polys'}: polys = [[outer ring, holes...], ...], each ring a list of (lon, lat)."""
    global _cache
    if _cache is not None:
        return _cache
    t = json.load(open(TOPO, encoding="utf-8"))
    (sx, sy), (tx, ty) = t["transform"]["scale"], t["transform"]["translate"]
    arcs = []
    for arc in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    feats = []
    for g in t["objects"]["countries"]["geometries"]:
        if g["type"] == "Polygon":
            polys = [g["arcs"]]
        elif g["type"] == "MultiPolygon":
            polys = g["arcs"]
        else:
            polys = []
        feats.append({"id": g.get("id"), "name": g["properties"]["name"],
                      "polys": [[ring(r) for r in p] for p in polys]})
    _cache = feats
    return feats
