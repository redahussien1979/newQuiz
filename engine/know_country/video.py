"""Know a Country: one Excel row in, one finished vertical video out (map-first explainer).

Used by the "🌍 Know a Country" tab in app.py. Everything comes from the Excel file (see the template
projects/know_country_template.xlsx): figures with dates and sources, facts, exports, comparison countries,
reference cities. Rendering: one process per scene (spawn, Windows-safe), FFmpeg from imageio-ffmpeg.
"""
import json, math, os, subprocess
import multiprocessing as mp
import numpy as np
from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFilter

from . import globe as kglobe
from .globe import Globe, load_shapes, main_bbox, main_rings
from .topo import features as topo_features
from .util import (ease, pop, lerp, icon, background, SUBREGION_AR, line, rich, seg_w, chip, leader, pin, ripples,
                   flag_badge, paste, gradients, cam_mix, smooth, WH, INK, Y, CY, PK, GR, PU, CHIP_COLORS, DATA)
from . import sound
from ..core import ffmpeg_exe

W, H, FPS = 1080, 1920, 30
XLSX = None                   # the Excel file being rendered (set by render / preview)
BRAND = "@Ma3loomaFast"       # overwritten by the 'brand' column when filled
MAP_CY = 800
OR = (255, 145, 20)           # main country colour (matches the globe highlight)
FACT_SEG = 3.8                # seconds per fact
CMP_SEG = 4.4                 # seconds per size comparison
CMP_TRAVEL = 1.5              # seconds of flight inside each comparison

# ---------------- numbers ----------------
def num(v, dec=0):
    return f"{v:,.{dec}f}"

def pop_text(p):
    if p >= 1e9:
        return f"{p / 1e9:.2f} مليار", f"{p / 1e9:.2f} billion"
    if p >= 1e6:
        return f"{p / 1e6:.1f} مليون", f"{p / 1e6:.1f} million"
    return num(p), num(p)

def borders_text(n):
    if n == 1:
        return "تحدها دولة واحدة"
    if n == 2:
        return "تحدها دولتان"
    return f"تحدها {n} دول" if n <= 10 else f"تحدها {n} دولة"

THE = {"Netherlands", "Philippines", "Bahamas", "Gambia", "Maldives", "Comoros", "Seychelles", "Marshall Islands",
       "Solomon Islands", "Cayman Islands", "Falkland Islands", "Vatican City", "Czech Republic"}

def en_name(n):
    return f"the {n}" if n.startswith("United") or "Republic" in n or n in THE else n

def compare_text(a_ar, a_en, a_area, b_ar, b_en, b_area):
    a_en, b_en = en_name(a_en), en_name(b_en)
    r = a_area / b_area
    if 0.95 <= r <= 1.05:
        return f"{a_ar} و{b_ar} *متقاربتان* في المساحة", f"{a_en} and {b_en} are about the same size"
    if 1.05 < r < 1.15:
        return f"{a_ar} أكبر من {b_ar} *بقليل*", f"{a_en} is slightly larger than {b_en}"
    if 0.87 < r < 0.95:
        return f"{a_ar} أصغر من {b_ar} *بقليل*", f"{a_en} is slightly smaller than {b_en}"
    if r > 1:
        big_ar, big_en, small_ar, small_en, k = a_ar, a_en, b_ar, b_en, r
    else:
        big_ar, big_en, small_ar, small_en, k = b_ar, b_en, a_ar, a_en, 1 / r
    kx = f"{k:.1f}" if k < 10 else f"{k:.0f}"
    big_en = big_en[0].upper() + big_en[1:]
    return f"{big_ar} أكبر من {small_ar} بنحو *{kx} مرة*", f"{big_en} is about {kx} times the size of {small_en}"

# ---------------- data (Excel) ----------------
def sheet_rows(ws):
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h).strip() if h else "" for h in rows[0]]
    return [dict(zip(hdr, r)) for r in rows[1:] if any(v not in (None, "") for v in r)]

def s(v):
    return "" if v is None else str(v).strip()

def parse_points(v):
    v = s(v)
    if not v:
        return None
    if v == "*":
        return "*"
    pts = []
    for item in v.split("|"):
        bits = [b.strip() for b in item.split("@")]
        lat, lon = (float(x) for x in bits[1].split(","))
        pts.append({"label": bits[0], "lon": lon, "lat": lat, "icon": bits[2] if len(bits) > 2 and bits[2] else None})
    return pts

def find_country(countries, key):
    key = s(key).lower()
    for c in countries:
        names = {c["name"]["common"].lower(), c["name"]["official"].lower(), c["cca3"].lower(), c["cca2"].lower()}
        names |= {a.lower() for a in c.get("altSpellings", [])}
        if key in names:
            return c
    raise ValueError(f"Country not recognised: {key}")

def excel_rows():
    wb = load_workbook(XLSX, data_only=True)
    cities = {s(r["name_en"]).lower(): r for r in sheet_rows(wb["cities"])} if "cities" in wb.sheetnames else {}
    return sheet_rows(wb["countries"]), {r["cca3"]: r for r in sheet_rows(wb["areas"])}, cities

def load_data(name):
    countries = json.load(open(os.path.join(DATA, "countries.json"), encoding="utf-8"))
    by3 = {c["cca3"]: c for c in countries}
    geo_names = {f["id"]: f["name"] for f in topo_features() if f["polys"]}
    rows, areas, cities = excel_rows()
    c = find_country(countries, name)
    if c["ccn3"] not in geo_names:
        raise ValueError(f"{c['name']['common']} is too small to appear in the map data")
    row = next((r for r in rows if find_country(countries, r["country"])["cca3"] == c["cca3"]), None)
    if row is None:
        raise ValueError(f"No row for {c['name']['common']} in {XLSX}")
    req = ["capital_ar", "capital_lat", "capital_lon", "area_km2", "population", "population_date_ar", "population_date_en"]
    missing = [k for k in req if s(row.get(k)) == ""]
    if missing:
        raise ValueError(f"{c['name']['common']}: fill these columns first: {', '.join(missing)}")
    nb = [by3[b] for b in c["borders"] if b in by3]
    d = {
        "cca3": c["cca3"], "cca2": c["cca2"].lower(), "geo_name": geo_names[c["ccn3"]],
        "name_ar": s(row.get("name_ar")) or c["translations"]["ara"]["common"], "name_en": c["name"]["common"],
        "subregion_ar": SUBREGION_AR.get(c["subregion"], c["region"]), "subregion_en": c["subregion"],
        "capital_ar": s(row["capital_ar"]), "capital_en": c["capital"][0],
        "capital_ll": (float(row["capital_lon"]), float(row["capital_lat"])),
        "area": float(row["area_km2"]), "area_date_ar": s(row.get("area_date_ar")), "area_date_en": s(row.get("area_date_en")),
        "population": float(row["population"]),
        "pop_date_ar": s(row["population_date_ar"]), "pop_date_en": s(row["population_date_en"]),
        "language_ar": s(row.get("language_ar")), "language_en": s(row.get("language_en")) or ", ".join(c["languages"].values()),
        "currency_ar": s(row.get("currency_ar")), "currency_en": s(row.get("currency_en")) or next(iter(c["currencies"].values()))["name"],
        "currency_symbol": s(row.get("currency_symbol")) or next(iter(c["currencies"].values())).get("symbol", ""),
        "sources_ar": s(row.get("sources_ar")), "sources_en": s(row.get("sources_en")),
        "n_borders": len(nb), "landlocked": c["landlocked"], "island": not c["borders"] and not c["landlocked"],
        "sea_labels": parse_points(row.get("map_labels")) or [],
        "facts": [{"ar": s(row[f"fact{i}_ar"]), "en": s(row.get(f"fact{i}_en")), "map": parse_points(row.get(f"fact{i}_map"))}
                  for i in range(1, 6) if s(row.get(f"fact{i}_ar"))],
        "labels": sorted([(x["translations"]["ara"]["common"], x["latlng"][1], x["latlng"][0], x["area"])
                          for x in countries if x["cca3"] != c["cca3"] and x["area"] > 20000 and x.get("latlng")],
                         key=lambda v: -v[3]),
    }
    global BRAND
    if s(row.get("brand")):
        BRAND = s(row.get("brand"))
    d["compare"] = []
    for key in [k for k in s(row.get("compare_with")).split(",") if k.strip()]:
        cc = find_country(countries, key)
        ar = areas.get(cc["cca3"])
        if not ar or not ar.get("area_km2"):
            raise ValueError(f"Missing area for {cc['name']['common']} in the 'areas' sheet")
        d["compare"].append({"cca3": cc["cca3"], "cca2": cc["cca2"].lower(), "geo_name": geo_names[cc["ccn3"]],
                             "name_ar": s(ar.get("name_ar")) or cc["translations"]["ara"]["common"],
                             "name_en": cc["name"]["common"], "area": float(ar["area_km2"])})
    for cp in d["compare"]:
        cp["text_ar"], cp["text_en"] = compare_text(d["name_ar"], d["name_en"], d["area"], cp["name_ar"], cp["name_en"], cp["area"])
    # neighbours: land borders from the dataset; for islands, the 'nearby' column (across the sea)
    nearby = [find_country(countries, x) for x in s(row.get("nearby")).split(",") if x.strip()]
    d["neighbors_sea"] = d["island"] and bool(nearby)
    d["neighbors"] = [{"cca3": n["cca3"], "cca2": n["cca2"].lower(), "geo_name": geo_names.get(n["ccn3"]),
                       "name_ar": n["translations"]["ara"]["common"], "name_en": n["name"]["common"]}
                      for n in (nearby or nb) if geo_names.get(n["ccn3"])]
    # straight-line (great-circle) distances from reference cities to the capital
    d["distances"] = []
    for x in [x for x in s(row.get("distance_from")).split(",") if x.strip()]:
        cr = cities.get(x.strip().lower())
        if not cr:
            raise ValueError(f"City '{x.strip()}' is not in the 'cities' sheet")
        lon, lat = float(cr["lon"]), float(cr["lat"])
        km = gc_km(lon, lat, *d["capital_ll"])
        d["distances"].append({"name_ar": s(cr["name_ar"]), "name_en": s(cr["name_en"]), "lon": lon, "lat": lat,
                               "km": int(round(km / 10.0) * 10)})
    d["exports"] = None
    items = [{"ar": s(row.get(f"export{i}_ar")), "en": s(row.get(f"export{i}_en")),
              "share": float(row.get(f"export{i}_share") or 0), "icon": s(row.get(f"export{i}_icon")) or "package"}
             for i in range(1, 6) if s(row.get(f"export{i}_ar"))]
    if items:
        d["exports"] = {"items": items, "year_ar": s(row.get("exports_year_ar")), "year_en": s(row.get("exports_year_en")),
                        "total_ar": s(row.get("exports_total_ar")), "total_en": s(row.get("exports_total_en")),
                        "source_ar": s(row.get("exports_source_ar")), "source_en": s(row.get("exports_source_en"))}
    return d

def gc_km(lon1, lat1, lon2, lat2):
    """Great-circle distance (haversine, mean Earth radius 6,371.0088 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))

# ---------------- sphere maths for the true-size drag ----------------
def xyz(lon, lat):
    lo, la = np.radians(lon), np.radians(lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)

def rodrigues(v, k, ang):
    k = k / np.linalg.norm(k)
    c, s_ = math.cos(ang), math.sin(ang)
    return v * c + np.cross(k, v) * s_ + np.outer(v @ k, k) * (1 - c)

def transplant(v, src, dst):
    """Rigid rotation (keeps true shape and size, north stays up) moving src (lon,lat) to dst."""
    dlon = math.radians((dst[0] - src[0] + 180) % 360 - 180)
    c, s_ = math.cos(dlon), math.sin(dlon)
    v = np.stack([v[:, 0] * c - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c, v[:, 2]], 1)
    east = np.array([-math.sin(math.radians(dst[0])), math.cos(math.radians(dst[0])), 0.0])
    return rodrigues(v, east, -math.radians(dst[1] - src[1]))

def proj_vec(v, cam):
    lon0, lat0, R = cam
    lam = np.arctan2(v[:, 1], v[:, 0]); phi = np.arcsin(np.clip(v[:, 2], -1, 1))
    l0, p0 = math.radians(lon0), math.radians(lat0)
    x = R * np.cos(phi) * np.sin(lam - l0)
    y = R * (math.cos(p0) * np.sin(phi) - math.sin(p0) * np.cos(phi) * np.cos(lam - l0))
    vis = math.sin(p0) * np.sin(phi) + math.cos(p0) * np.cos(phi) * np.cos(lam - l0)
    return W / 2 + x, MAP_CY - y, vis

def draw_outline(img, rings_v, cam, color, alpha, width=4):
    dr = ImageDraw.Draw(img)
    for r in rings_v:
        x, y, vis = proj_vec(r, cam)
        if (vis > 0).all() and len(x) > 2:
            pts = list(zip(x.tolist(), y.tolist()))
            dr.line(pts + [pts[0]], fill=INK + (int(200 * alpha),), width=width + 4, joint="curve")
            dr.line(pts + [pts[0]], fill=color + (int(255 * alpha),), width=width, joint="curve")

def draw_shape(img, rings_v, cam, fill, alpha, outline=WH):
    pts = [proj_vec(r, cam) for r in rings_v]
    pts = [(x, y) for x, y, vis in pts if (vis > 0).all()]
    if not pts or alpha <= 0:
        return
    allx = np.concatenate([p[0] for p in pts]); ally = np.concatenate([p[1] for p in pts])
    x0, y0 = int(max(0, allx.min() - 10)), int(max(0, ally.min() - 10))
    x1, y1 = int(min(W, allx.max() + 10)), int(min(H, ally.max() + 10))
    if x1 <= x0 or y1 <= y0:
        return
    ss = 2
    lay = Image.new("RGBA", ((x1 - x0) * ss, (y1 - y0) * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for x, y in pts:
        poly = list(zip(((x - x0) * ss).tolist(), ((y - y0) * ss).tolist()))
        if len(poly) > 2:
            dr.polygon(poly, fill=fill + (int(205 * alpha),))
    for x, y in pts:
        poly = list(zip(((x - x0) * ss).tolist(), ((y - y0) * ss).tolist()))
        if len(poly) > 2:
            dr.line(poly + [poly[0]], fill=outline + (int(255 * alpha),), width=3 * ss, joint="curve")
    img.alpha_composite(lay.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))

# ---------------- camera ----------------
def ang_dist(a, b):
    va, vb = xyz(a[0], a[1]), xyz(b[0], b[1])
    return math.acos(float(np.clip(va @ vb, -1, 1)))

def fly(a, b, k):
    """Camera flight with a zoom-out arc proportional to the distance travelled."""
    k = smooth(k)
    c = cam_mix(a, b, k)
    dip = min(1.9, ang_dist(a, b) * 1.35)
    return (c[0], c[1], c[2] * math.exp(-dip * math.sin(math.pi * k)))

def proj(lon, lat, cam):
    return Globe.project(lon, lat, W / 2, MAP_CY, cam[0], cam[1], cam[2])

def fact_cam(ctx, f):
    fit = ctx["cams"]["fit"]
    pts = f["map"]
    if not pts or pts == "*":
        return fit
    lons = [p["lon"] for p in pts]; lats = [p["lat"] for p in pts]
    clat = sum(lats) / len(lats)
    spread = max((max(lons) - min(lons)) * math.cos(math.radians(clat)), max(lats) - min(lats))
    R = W * 0.55 / math.radians(spread + 1.5) if spread > 0.1 else fit[2] * 2.0
    return (sum(lons) / len(lons), clat, min(max(R, fit[2] * 0.9), fit[2] * 2.2))

_gcache = {}
def map_layer(g, cy, cam, hl, nh, dim, phase, sid, nb=0.0):
    key = (round(cy, 1), tuple(round(v, 5) for v in cam), round(hl, 3), round(nh, 3), round(dim, 3), round(phase, 2), sid, round(nb, 3))
    if key not in _gcache:
        if len(_gcache) > 3:
            _gcache.clear()
        lay = g.render((W, H), W / 2, cy, cam[0], cam[1], cam[2], hl=hl, nh=nh, dim=dim,
                       glow_phase=phase, second_id=sid, nb=nb)
        _gcache[key] = g.borders(lay, W / 2, cy, cam[0], cam[1], cam[2])
    return _gcache[key]

# Each scene: cam(ctx,t,dur) -> (cam, cy, hl, nh, dim, phase, second_id); draw(ov, ctx, t, dur, cam)
def intro_cam(ctx, t, dur):
    cams = ctx["cams"]
    spin = (cams["space"][0] + min(t, 1.2) * 22, cams["space"][1], cams["space"][2])
    c = cam_mix(spin, cams["fit"], smooth((t - 1.2) / 3.0)) if t > 1.2 else spin
    h = ease((t - 4.0) / 0.5)
    return c, lerp(880, MAP_CY, smooth((t - 1.2) / 3.0)), h, 0, h, 0, None

def intro_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    a = ease(t / 0.35) * (1 - ease((t - 2.6) / 0.4))
    rich(ov, "تعرف على *دولة*", 116, W / 2, 330, alpha=a, scale=pop(t / 0.5))
    line(ov, [("Know a country", CY)], 46, W / 2, 450, alpha=a, weight=700)
    t2 = t - 4.2
    if t2 > 0:
        paste(ov, ctx["flag_big"], W / 2, 1330, scale=pop(t2 / 0.45))
        line(ov, [(d["name_ar"], WH)], 150, W / 2, 1530, scale=pop((t2 - 0.12) / 0.5))
        line(ov, [(d["name_en"], Y)], 60, W / 2, 1668, alpha=ease((t2 - 0.35) / 0.3))

def location_cam(ctx, t, dur):
    cams = ctx["cams"]
    return fly(cams["fit"], cams["wide"], t / 1.6), MAP_CY, 1, 0, lerp(1, 0.15, smooth((t - 0.3) / 1.3)), 0, None

def location_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    boxes = []
    free = lambda b: all(b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3] for o in boxes)
    tl = t - 1.4
    if tl > 0:
        tx, ty, _ = proj(*ctx["g"].center, cam)
        boxes.append((tx - 50, ty - 50, tx + 50, ty + 50))
        for i, p in enumerate(d["sea_labels"]):
            x, y, vis = proj(p["lon"], p["lat"], cam)
            if vis:
                wd = seg_w(p["label"], 38, 700) / 2 + 12
                boxes.append((x - wd, y - 28, x + wd, y + 28))
                line(ov, [(p["label"], CY)], 38, x, y, alpha=ease((tl - 0.4 - i * 0.12) / 0.4), weight=700)
        k = 0
        for name, lon, lat, _ in d["labels"]:
            x, y, vis = proj(lon, lat, cam)
            if not vis or not (90 < x < W - 90 and 210 < y < 1170):
                continue
            wd = seg_w(name, 40, 800) / 2 + 12
            b = (x - wd, y - 28, x + wd, y + 28)
            if not free(b):
                continue
            boxes.append(b)
            line(ov, [(name, WH)], 40, x, y, alpha=ease((tl - k * 0.07) / 0.35), scale=pop((tl - k * 0.07) / 0.45))
            k += 1
    a = ease((t - 0.3) / 0.4)
    rich(ov, f"تقع في *{d['subregion_ar']}*", 80, W / 2, 1440, alpha=a, scale=pop((t - 0.3) / 0.5))
    line(ov, [(f"Located in {d['subregion_en']}", CY)], 40, W / 2, 1545, alpha=ease((t - 0.5) / 0.4), weight=700)
    if d["island"]:
        txt = "دولة جزرية بلا حدود برية"
    elif d["landlocked"]:
        txt = "دولة حبيسة لا تطل على أي بحر"
    else:
        txt = borders_text(len(d["neighbors"]) or d["n_borders"])
    chip(ov, txt, 46, W / 2, 1680, PK, fg=WH, alpha=ease((t - 1.8) / 0.3), scale=pop((t - 1.8) / 0.45))

def capital_cam(ctx, t, dur):
    cams = ctx["cams"]
    start = cams["nb"] if ctx["d"]["neighbors"] else cams["wide"]
    return fly(start, cams["cap"], t / 1.4), MAP_CY, 1, 0, lerp(0.15, 1, smooth(t / 1.2)), 0, None

def capital_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    x, y, vis = proj(*d["capital_ll"], cam)
    tp = t - 1.3
    if tp > 0 and vis:
        ripples(ov, x, y, tp)
        pin(ov, x, y - (1 - ease(tp / 0.4)) * 220, Y, alpha=ease(tp / 0.15))
        chip(ov, d["capital_ar"], 52, min(max(x, 220), W - 220), y - 210, Y,
             alpha=ease((tp - 0.35) / 0.25), scale=pop((tp - 0.35) / 0.45))
    a = ease((t - 0.4) / 0.4)
    line(ov, [("العاصمة", CY)], 50, W / 2, 1390, alpha=a)
    line(ov, [(d["capital_ar"], Y)], 132, W / 2, 1515, alpha=a, scale=pop((t - 0.5) / 0.5))
    line(ov, [(f"Capital: {d['capital_en']}", WH)], 42, W / 2, 1650, alpha=ease((t - 0.8) / 0.4), weight=700)

def numbers_cam(ctx, t, dur):
    cams = ctx["cams"]
    start = ctx["dist"][-1]["cam"] if ctx["dist"] else cams["cap"]
    return fly(start, cams["fit"], t / 1.3), MAP_CY, 1, 0, 1, 0, None

def numbers_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    tx, ty, _ = proj(*ctx["g"].center, cam)
    p_ar, p_en = pop_text(d["population"])
    pv = d["population"] / (1e9 if d["population"] >= 1e9 else 1e6 if d["population"] >= 1e6 else 1)
    pdec = 2 if d["population"] >= 1e9 else 1 if d["population"] >= 1e6 else 0
    unit = p_ar.split(" ")[-1] if d["population"] >= 1e6 else ""
    stats = [(290, "المساحة", d["area_date_ar"], "ruler-2", Y, lambda p: f"{num(d['area'] * p)} كم²", 1.1),
             (W - 290, "السكان", d["pop_date_ar"], "users", CY, lambda p: f"{num(pv * p, pdec)} {unit}".strip(), 1.6)]
    for x, lab, date, ic, col, txt, t0 in stats:
        a = ease((t - t0) / 0.35)
        if a <= 0:
            continue
        p = ease((t - t0 - 0.1) / 1.3)
        leader(ov, (x, 390), (lerp(x, tx, a), lerp(390, ty, a)), alpha=a)
        line(ov, [(lab, WH)], 42, x, 232, alpha=a)
        if date:
            line(ov, [(date, Y if col == CY else CY)], 30, x, 280, alpha=a, weight=700)
        chip(ov, txt(p), 46, x, 345, col, alpha=a, scale=pop((t - t0) / 0.45), icon_name=ic)
    a = ease((t - 2.4) / 0.4)
    ad = f" ({d['area_date_en']})" if d["area_date_en"] else ""
    line(ov, [(f"Area: {num(d['area'])} km²{ad}", WH)], 40, W / 2, 1420, alpha=a, weight=700)
    line(ov, [(f"Population: {p_en} ({d['pop_date_en']})", WH)], 40, W / 2, 1490, alpha=ease((t - 2.6) / 0.4), weight=700)
    if d["sources_ar"]:
        line(ov, [(d["sources_ar"], CY)], 30, W / 2, 1620, alpha=ease((t - 3.0) / 0.4), weight=700, max_w=960)
    if d["sources_en"]:
        line(ov, [(d["sources_en"], (200, 214, 232))], 26, W / 2, 1670, alpha=ease((t - 3.1) / 0.4), weight=600, max_w=960)

def compare_cam(ctx, t, dur):
    cps = ctx["cmp"]
    i = min(len(cps) - 1, int(t / CMP_SEG))
    tl = t - i * CMP_SEG
    prev = ctx["cams"]["fit"] if i == 0 else cps[i - 1]["cam"]
    k = min(1.0, tl / CMP_TRAVEL)
    c = fly(prev, cps[i]["cam"], k)
    if tl < CMP_TRAVEL:  # previous country fades while flying
        nh, sid = (1 - ease(tl / 0.4), cps[i - 1]["id"]) if i > 0 else (0, None)
    else:
        nh, sid = ease((tl - CMP_TRAVEL) / 0.35), cps[i]["id"]
    return c, MAP_CY, 1, nh, 1, 0, sid

def shape_center(ctx, t):
    cps = ctx["cmp"]
    i = min(len(cps) - 1, int(t / CMP_SEG))
    tl = t - i * CMP_SEG
    a = ctx["g"].center if i == 0 else cps[i - 1]["center"]
    b = cps[i]["center"]
    k = smooth(min(1.0, tl / CMP_TRAVEL))
    return (a[0] + ((b[0] - a[0] + 180) % 360 - 180) * k, lerp(a[1], b[1], k)), i, tl

def compare_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    (clon, clat), i, tl = shape_center(ctx, t)
    cp = ctx["cmp"][i]
    rings = [transplant(r, ctx["g"].center, (clon, clat)) for r in ctx["main_v"]]
    draw_shape(ov, rings, cam, OR, min(1.0, t / 0.3))
    landed = tl - CMP_TRAVEL
    if landed > 0:  # outline of the compared country on top, so small countries stay visible
        draw_outline(ov, cp["rings_v"], cam, CY, ease(landed / 0.35))
    if landed > 0:
        x, y, _ = proj(clon, clat, cam)
        ripples(ov, x, y, landed, color=WH, alpha=1 - ease((landed - 1.2) / 0.5))
    line(ov, [("مقارنة المساحة بالحجم الحقيقي", WH)], 50, W / 2, 232, alpha=ease(t / 0.35))
    line(ov, [("True-size area comparison", CY)], 30, W / 2, 288, alpha=ease(t / 0.35), weight=700)
    sw = 1 + 0.08 * math.sin(min(1.0, max(0.0, landed) / 0.35) * math.pi) if landed > 0 else 1
    chip(ov, d["name_ar"], 44, W * 0.72, 370, OR, fg=WH, alpha=ease(t / 0.35))
    if landed > -0.2:
        a = ease((landed + 0.2) / 0.3)
        b = chip(ov, cp["name_ar"], 44, W * 0.28, 370, CY, alpha=a, scale=sw)
        if b:
            paste(ov, ctx["flags"][cp["cca3"]], b[0] - 52, 370, alpha=a)
        paste(ov, ctx["flags"][d["cca3"]], W * 0.72 + seg_w(d["name_ar"], 44, 800) / 2 + 92, 370, alpha=ease(t / 0.35))
    out = 1 - ease((tl - CMP_SEG + 0.3) / 0.3) if i < len(ctx["cmp"]) - 1 else 1
    a = ease((landed - 0.25) / 0.35) * out
    if a > 0:
        rich(ov, cp["text_ar"], 66, W / 2, 1450, alpha=a, scale=pop((landed - 0.25) / 0.5), max_w=960)
        line(ov, [(cp["text_en"], CY)], 38, W / 2, 1570, alpha=a, weight=700)
    dots = ImageDraw.Draw(ov)
    n = len(ctx["cmp"])
    for k in range(n):
        x = W / 2 + (k - (n - 1) / 2) * 40
        dots.ellipse((x - 9, 1690 - 9, x + 9, 1690 + 9), fill=(Y if k == i else (255, 255, 255)) + (int(255 * ease(t / 0.3)),))

def language_cam(ctx, t, dur):
    start = ctx["cmp"][-1]["cam"] if ctx["cmp"] else ctx["cams"]["fit"]
    nh = (1 - ease(t / 0.4)) if ctx["cmp"] else 0
    return fly(start, ctx["cams"]["fit"], t / 1.8), MAP_CY, 1, nh, 1, 0, ctx["cmp"][-1]["id"] if ctx["cmp"] else None

def language_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    tx, ty, _ = proj(*ctx["g"].center, cam)
    for x, col, ic, sym, t0 in [(250, PU, "language", None, 1.9), (W - 250, Y, None, d["currency_symbol"], 2.3)]:
        a = ease((t - t0) / 0.35)
        if a <= 0:
            continue
        y = 470 + math.sin((t - t0) * 2.4) * 12
        leader(ov, (x, y + 70), (lerp(x, tx, a), lerp(y + 70, ty, a)), alpha=a)
        sc = pop((t - t0) / 0.5)
        r = 95 * sc
        dr = ImageDraw.Draw(ov)
        dr.ellipse((x - r + 8, y - r + 10, x + r + 8, y + r + 10), fill=(0, 0, 0, int(110 * a)))
        dr.ellipse((x - r, y - r, x + r, y + r), fill=col + (int(255 * a),), outline=WH + (int(255 * a),), width=7)
        if ic:
            paste(ov, icon(ic, int(110 * sc) + 1, WH), x, y, alpha=a)
        elif sym:
            line(ov, [(sym, INK)], 110, x, y - 4, alpha=a, scale=sc, stroke=None)
    for k, (lab, v_ar, v_en, t0) in enumerate([("اللغة", d["language_ar"], f"Language: {d['language_en']}", 1.5),
                                                ("العملة", d["currency_ar"], f"Currency: {d['currency_en']}", 2.0)]):
        a = ease((t - t0) / 0.4)
        y = 1400 + k * 210
        rich(ov, f"{lab}: *{v_ar}*", 72, W / 2, y, alpha=a, scale=pop((t - t0) / 0.5))
        line(ov, [(v_en, CY)], 38, W / 2, y + 85, alpha=ease((t - t0 - 0.2) / 0.4), weight=700)

def facts_cam(ctx, t, dur):
    cams = ctx["fact_cams"]
    i = min(len(cams) - 1, int(t / FACT_SEG))
    prev = ctx["cams"]["fit"] if i == 0 else cams[i - 1]
    tl = t - i * FACT_SEG
    star = ctx["d"]["facts"][i]["map"] == "*"
    return fly(prev, cams[i], tl / 1.0), MAP_CY, 1, 0, 1, (tl * 5.0 if star and tl > 1.0 else 0), None

def facts_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    facts = d["facts"]
    n = len(facts)
    i = min(n - 1, int(t / FACT_SEG))
    tl = t - i * FACT_SEG
    f = facts[i]
    chip(ov, f"حقائق عن {d['name_ar']}", 50, W / 2, 285, PK, fg=WH, icon_name="bulb", alpha=ease(t / 0.3), scale=pop(t / 0.45))
    line(ov, [(f"{i + 1} / {n}", WH)], 34, W / 2, 375, alpha=ease(t / 0.3), weight=700)
    out = 1 - ease((tl - FACT_SEG + 0.3) / 0.3) if i < n - 1 else 1
    if isinstance(f["map"], list):
        placed = []
        for k, p in enumerate(f["map"]):
            x, y, vis = proj(p["lon"], p["lat"], cam)
            tk = tl - 0.9 - k * 0.18
            if not vis or tk <= 0:
                continue
            a = ease(tk / 0.25) * out
            col = CHIP_COLORS[k % len(CHIP_COLORS)]
            if p["icon"]:
                pin(ov, x, y, col, alpha=a, scale=pop(tk / 0.45))
                paste(ov, icon(p["icon"], 64, INK), x, y - 92, alpha=a, scale=pop(tk / 0.45))
                chip(ov, p["label"], 44, x, y - 200, col, alpha=a, scale=pop((tk - 0.15) / 0.45))
            else:
                dr = ImageDraw.Draw(ov)
                dr.ellipse((x - 13, y - 13, x + 13, y + 13), fill=col + (int(255 * a),), outline=INK + (int(255 * a),), width=4)
                hw = seg_w(p["label"], 40, 800) / 2 + 40
                ly = y - 62
                if any(abs(x - px) < hw + pw and abs(ly - py) < 75 for px, py, pw in placed):
                    ly = y + 62
                placed.append((x, ly, hw))
                chip(ov, p["label"], 40, x, ly, col, alpha=a, scale=pop(tk / 0.45))
    elif f["map"] == "*" and tl > 1.0:
        tx, ty, _ = proj(*ctx["g"].center, cam)
        ripples(ov, tx, ty, tl - 1.0, color=WH, alpha=out)
    a = ease((tl - 0.2) / 0.35) * out
    off = (1 - ease((tl - 0.2) / 0.45)) * 140
    if a > 0:
        lay = Image.new("RGBA", (W - 100, 430), (0, 0, 0, 0))
        col = CHIP_COLORS[i % len(CHIP_COLORS)]
        ImageDraw.Draw(lay).rounded_rectangle((0, 0, W - 101, 429), 44, fill=INK + (int(215 * a),),
                                              outline=col + (int(255 * a),), width=6)
        ov.alpha_composite(lay, (50, int(1325 + off)))
        rich(ov, f["ar"], 68, W / 2, 1490 + off, max_w=880, alpha=a)
        line(ov, [(f["en"], CY)], 36, W / 2, 1665 + off, alpha=a, weight=700, max_w=880)

def outro_cam(ctx, t, dur):
    cams = ctx["cams"]
    end = (cams["fit"][0] - 35 + t * 12, 22.0, 340.0)
    k = smooth(t / 2.6)
    start = ctx["fact_cams"][-1] if ctx["fact_cams"] else cams["fit"]
    return cam_mix(start, end, k), lerp(MAP_CY, 760, k), 1, 0, 1, 0, None

def outro_draw(ov, ctx, t, dur, cam):
    line(ov, [("تابعنا", WH)], 124, W / 2, 1440, alpha=ease((t - 0.6) / 0.35), scale=pop((t - 0.6) / 0.5))
    rich(ov, "لتتعرف على *دولة جديدة* كل يوم", 62, W / 2, 1575, alpha=ease((t - 0.85) / 0.4))
    line(ov, [(BRAND, CY)], 54, W / 2, 1690, alpha=ease((t - 1.1) / 0.4))

# ---------------- neighbours ----------------
NB_START, NB_STEP = 1.3, 0.65
NB_COLORS = [Y, CY, PK, GR, PU, (255, 160, 60)]

def neighbors_cam(ctx, t, dur):
    return fly(ctx["cams"]["wide"], ctx["cams"]["nb"], t / 1.1), MAP_CY, 1, 0, 0.15, 0, None

def project_clamped(v, cam):
    """Project unit vectors; points behind the globe are pushed onto its edge (keeps fills closed)."""
    x, y, vis = proj_vec(v, cam)
    dx, dy = x - W / 2, y - MAP_CY
    r = np.hypot(dx, dy) + 1e-9
    back = vis <= 0
    x = np.where(back, W / 2 + dx / r * cam[2], x)
    y = np.where(back, MAP_CY + dy / r * cam[2], y)
    return x, y, vis

def region_layer(n, cam, color):
    """Pre-drawn fill + border of one neighbour (supersampled), with its pin point."""
    ss = 2
    fill = Image.new("L", (W * ss, H * ss), 0)
    edge = Image.new("L", (W * ss, H * ss), 0)
    df, de = ImageDraw.Draw(fill), ImageDraw.Draw(edge)
    for r in n["rings_v"]:
        x, y, vis = project_clamped(r, cam)
        if (vis <= 0).all():
            continue
        pts = list(zip((x * ss).tolist(), (y * ss).tolist()))
        df.polygon(pts, fill=255)
        ok = vis > 0
        run = []
        for j in range(len(pts) + 1):
            jj = j % len(pts)
            if ok[jj]:
                run.append(pts[jj])
            else:
                if len(run) > 1:
                    de.line(run, fill=255, width=5 * ss, joint="curve")
                run = []
        if len(run) > 1:
            de.line(run, fill=255, width=5 * ss, joint="curve")
    fill = fill.resize((W, H), Image.LANCZOS)
    edge = edge.resize((W, H), Image.LANCZOS)
    lay = Image.new("RGBA", (W, H), color + (0,))
    a = np.maximum(np.asarray(fill, np.float32) * 0.30, np.asarray(edge, np.float32))
    lay.putalpha(Image.fromarray(a.astype(np.uint8)))
    # pin point: the spot deepest inside the visible part of the country (inside a safe frame)
    small = np.asarray(fill.resize((W // 4, H // 4)), np.float32) > 128
    safe = np.zeros_like(small)
    safe[260 // 4:1140 // 4, 110 // 4:(W - 110) // 4] = True
    m = small & safe
    pin_xy = None
    if m.any():
        # erode until nothing is left: the last surviving pixels are the deepest inside the country
        im, last = Image.fromarray(m.astype(np.uint8) * 255), m
        while True:
            im2 = im.filter(ImageFilter.MinFilter(3))
            a2 = np.asarray(im2) > 0
            if not a2.any():
                break
            im, last = im2, a2
        ys, xs = np.nonzero(last)
        j = int(np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2))
        pin_xy = (int(xs[j]) * 4 + 2, int(ys[j]) * 4 + 2)
    if pin_xy is None and n["rings_v"]:   # too small to fill (e.g. Vatican City): pin its centre
        x, y, vis = proj_vec(np.concatenate(n["rings_v"]), cam)
        if (vis > 0).any():
            pin_xy = (int(x.mean()), int(y.mean()))
    return lay, pin_xy

NB_FONT = 32

def place_labels(ctx):
    """Small name next to each dot, without overlapping other names, dots or the frame edges."""
    d = ctx["d"]
    dots = [lay[1] for lay in ctx["nb_layers"]]
    taken = [(x - 18, y - 18, x + 18, y + 18) for x, y in [p for p in dots if p]]
    out = []
    for k_, n in enumerate(d["neighbors"]):
        p = dots[k_]
        if not p:
            out.append((0, 0)); continue
        x, y = p
        tw, th = seg_w(n["name_ar"], NB_FONT, 800) + 16, 46
        best = None
        for dx, dy in [(0, 40), (0, -40), (-(tw / 2 + 26), 0), (tw / 2 + 26, 0), (0, 80), (0, -80)]:
            cx = min(max(x + dx, tw / 2 + 20), W - tw / 2 - 20)
            cy = min(max(y + dy, 230), 1180)
            box = (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)
            if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in taken):
                best = (cx, cy, box); break
        if best is None:
            cx, cy = min(max(x, tw / 2 + 20), W - tw / 2 - 20), y + 40
            best = (cx, cy, (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2))
        taken.append(best[2])
        out.append(best[:2])
    return out

def flash_dot(img, x, y, col, t, alpha=1.0):
    """Pulsing location dot: solid core that blinks, plus expanding rings."""
    dr = ImageDraw.Draw(img)
    for ring in range(2):
        q = ((t + ring * 0.6) % 1.2) / 1.2
        r = 10 + q * 30
        dr.ellipse((x - r, y - r, x + r, y + r), outline=col + (int(230 * (1 - q) * alpha),), width=4)
    glow = 0.65 + 0.35 * (0.5 + 0.5 * math.cos(t * 2 * math.pi / 0.6))
    r = 10
    dr.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill=INK + (int(220 * alpha),))
    dr.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(c * glow + 255 * (1 - glow)) for c in col) + (int(255 * alpha),),
               outline=WH + (int(255 * alpha),), width=3)

def neighbors_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    if t < 1.1:
        return
    if "nb_layers" not in ctx:
        ctx["nb_layers"] = [region_layer(n, ctx["cams"]["nb"], NB_COLORS[k % len(NB_COLORS)]) for k, n in enumerate(d["neighbors"])]
        ctx["nb_labels"] = place_labels(ctx)
    dr = ImageDraw.Draw(ov)
    for k, n in enumerate(d["neighbors"]):
        tk = t - NB_START - k * ctx["nb_step"]
        if tk <= 0:
            continue
        lay, pxy = ctx["nb_layers"][k]
        col = NB_COLORS[k % len(NB_COLORS)]
        a = ease(tk / 0.35)
        if a < 1:
            l2 = lay.copy(); l2.putalpha(l2.getchannel("A").point(lambda v: int(v * a))); ov.alpha_composite(l2)
        else:
            ov.alpha_composite(lay)
        if not pxy:
            continue
        x, y = pxy
        tp = tk - 0.15
        if tp <= 0:
            continue
        cx, cy = ctx["nb_labels"][k]
        flash_dot(ov, x, y, col, tp, alpha=ease(tp / 0.2))
        line(ov, [(n["name_ar"], WH)], NB_FONT, cx, cy, alpha=ease((tp - 0.15) / 0.25), weight=800)
    a = ease((t - 0.3) / 0.4)
    if d["neighbors_sea"]:
        rich(ov, "دول مجاورة *عبر البحر*", 78, W / 2, 1450, alpha=a, scale=pop((t - 0.3) / 0.5))
        line(ov, [("Neighbours across the sea", CY)], 40, W / 2, 1555, alpha=ease((t - 0.5) / 0.4), weight=700)
    else:
        n = len(d["neighbors"])
        rich(ov, f"*{borders_text(n)}*", 78, W / 2, 1450, alpha=a, scale=pop((t - 0.3) / 0.5))
        line(ov, [(f"Borders {n} countr{'y' if n == 1 else 'ies'}", CY)], 40, W / 2, 1555, alpha=ease((t - 0.5) / 0.4), weight=700)

# ---------------- distances from world cities ----------------
DIST_SEG, DIST_TRAVEL, DIST_DRAW = 3.6, 1.0, 1.2

def slerp_pts(a, b, n):
    ang = math.acos(float(np.clip(a @ b, -1, 1)))
    s_ = np.linspace(0, 1, n)[:, None]
    if ang < 1e-6:
        return np.repeat(a[None], n, 0), s_[:, 0]
    return (np.sin((1 - s_) * ang) * a + np.sin(s_ * ang) * b) / math.sin(ang), s_[:, 0]

def dist_cam(ctx, t, dur):
    ds = ctx["dist"]
    i = min(len(ds) - 1, int(t / DIST_SEG))
    tl = t - i * DIST_SEG
    prev = ctx["cams"]["cap"] if i == 0 else ds[i - 1]["cam"]
    return fly(prev, ds[i]["cam"], tl / DIST_TRAVEL), MAP_CY, 1, 0, 1, 0, None

def dist_draw(ov, ctx, t, dur, cam):
    d = ctx["d"]
    ds = ctx["dist"]
    i = min(len(ds) - 1, int(t / DIST_SEG))
    tl = t - i * DIST_SEG
    x_ = ds[i]
    out = 1 - ease((tl - DIST_SEG + 0.3) / 0.3) if i < len(ds) - 1 else 1
    line(ov, [(f"المسافة المباشرة إلى {d['capital_ar']}", WH)], 50, W / 2, 232, alpha=ease(t / 0.35))
    line(ov, [(f"Straight-line distance to {d['capital_en']}", CY)], 30, W / 2, 288, alpha=ease(t / 0.35), weight=700)
    k = ease((tl - DIST_TRAVEL) / DIST_DRAW) if tl > DIST_TRAVEL else 0
    pts, sp = slerp_pts(x_["v"], ctx["capv"], 140)
    h = 0.11 * min(1.0, x_["ang"] / 0.9) * np.sin(np.pi * sp)
    px, py, vis = proj_vec(pts, cam)
    px = W / 2 + (px - W / 2) * (1 + h); py = MAP_CY + (py - MAP_CY) * (1 + h)
    vis = (vis > 0) | (np.hypot(px - W / 2, py - MAP_CY) > cam[2])
    dr = ImageDraw.Draw(ov)
    m = max(2, int(k * len(px)))
    if k > 0:
        seg = [(float(px[j]), float(py[j])) for j in range(m) if vis[j]]
        if len(seg) > 1:
            dr.line(seg, fill=INK + (int(200 * out),), width=12, joint="curve")
            dr.line(seg, fill=Y + (int(255 * out),), width=6, joint="curve")
        hx, hy = px[m - 1], py[m - 1]
        if k < 1:
            dr.ellipse((hx - 12, hy - 12, hx + 12, hy + 12), fill=WH + (255,), outline=Y + (255,), width=4)
    for (lon, lat), col, label in ((( x_["lon"], x_["lat"]), WH, x_["name_ar"]), (d["capital_ll"], OR, d["capital_ar"])):
        sx, sy, sv = proj(lon, lat, cam)
        if sv and tl > 0.6:
            a = ease((tl - 0.6) / 0.3) * out
            dr.ellipse((sx - 12, sy - 12, sx + 12, sy + 12), fill=col + (int(255 * a),), outline=INK + (int(255 * a),), width=4)
            chip(ov, label, 38, sx, sy + 52, col, fg=INK if col == WH else WH, alpha=a)
    if k > 0:
        j = len(px) // 2
        a = ease((tl - DIST_TRAVEL - DIST_DRAW + 0.2) / 0.3) * out
        chip(ov, f"{num(x_['km'] * k)} كم", 44, px[j], py[j] - 50, Y, alpha=a, scale=pop((tl - DIST_TRAVEL - DIST_DRAW + 0.2) / 0.45))
    a = ease((tl - 0.5) / 0.35) * out
    rich(ov, f"من *{x_['name_ar']}* إلى {d['capital_ar']}", 62, W / 2, 1420, alpha=a)
    line(ov, [(f"نحو {num(x_['km'] * k)} كم", Y)], 92, W / 2, 1540, alpha=a * (1 if k > 0 else 0))
    line(ov, [(f"{x_['name_en']} to {d['capital_en']}: about {num(x_['km'])} km", CY)], 36, W / 2, 1650,
         alpha=ease((tl - DIST_TRAVEL - DIST_DRAW) / 0.35) * out, weight=700)
    n = len(ds)
    for j in range(n):
        x = W / 2 + (j - (n - 1) / 2) * 40
        dr.ellipse((x - 9, 1760 - 9, x + 9, 1760 + 9), fill=(Y if j == i else WH) + (int(255 * ease(t / 0.3)),))

# ---------------- main exports ----------------
EXP_DUR = 7.0

def exports_cam(ctx, t, dur):
    return ctx["cams"]["fit"], MAP_CY, 1, 0, 1, 0, None

def exports_draw(ov, ctx, t, dur, cam):
    ex = ctx["d"]["exports"]
    tx, ty, _ = proj(*ctx["g"].center, cam)
    dr = ImageDraw.Draw(ov)
    # trade routes leaving the country
    a0 = ease((t - 0.2) / 0.5)
    for j in range(7):
        ang = math.radians(-160 + j * 50)
        ex_, ey_ = tx + math.cos(ang) * 900, ty + math.sin(ang) * 900
        mx, my = (tx + ex_) / 2 + math.cos(ang + 1.57) * 120, (ty + ey_) / 2 + math.sin(ang + 1.57) * 120
        curve = [((1 - u) ** 2 * tx + 2 * (1 - u) * u * mx + u * u * ex_, (1 - u) ** 2 * ty + 2 * (1 - u) * u * my + u * u * ey_)
                 for u in np.linspace(0, 1, 40)]
        dr.line(curve, fill=Y + (int(90 * a0),), width=3)
        for q in range(3):
            u = ((t * 0.45 + j * 0.13 + q / 3) % 1.0)
            x, y = ((1 - u) ** 2 * tx + 2 * (1 - u) * u * mx + u * u * ex_, (1 - u) ** 2 * ty + 2 * (1 - u) * u * my + u * u * ey_)
            r = 7
            dr.ellipse((x - r, y - r, x + r, y + r), fill=Y + (int(230 * a0 * (1 - u)),))
    chip(ov, f"أهم الصادرات {ex['year_ar']}".strip(), 50, W / 2, 250, GR, fg=WH, icon_name="package",
         alpha=ease(t / 0.3), scale=pop(t / 0.45))
    if ex["total_ar"]:
        rich(ov, f"إجمالي الصادرات: *{ex['total_ar']}*", 44, W / 2, 345, alpha=ease((t - 0.5) / 0.35))
    if ex["total_en"]:
        line(ov, [(f"Total exports {ex['year_en']}: {ex['total_en']}", CY)], 30, W / 2, 400, alpha=ease((t - 0.6) / 0.35), weight=700)
    items = ex["items"]
    mx_share = max(it["share"] for it in items) or 1
    y0 = 1240 if len(items) <= 3 else 1150
    line(ov, [("النسبة من إجمالي الصادرات", CY)], 32, W / 2, y0 - 118, alpha=ease((t - 0.9) / 0.3), weight=700)
    for i, it in enumerate(items):
        t0 = 1.1 + i * 0.45
        a = ease((t - t0) / 0.35)
        if a <= 0:
            continue
        y = y0 + i * 175
        off = (1 - a) * 120
        lay = Image.new("RGBA", (W - 100, 150), (0, 0, 0, 0))
        ImageDraw.Draw(lay).rounded_rectangle((0, 0, W - 101, 149), 34, fill=INK + (int(215 * a),),
                                              outline=(70, 86, 110, int(255 * a)), width=2)
        ov.alpha_composite(lay, (int(50 + off), int(y - 75)))
        cx = W - 125 + off
        r = 48
        dr.ellipse((cx - r, y - r, cx + r, y + r), fill=CHIP_COLORS[i % 4] + (int(255 * a),))
        paste(ov, icon(it["icon"], 58, INK), cx, y, alpha=a)
        line(ov, [(it["ar"], WH)], 42, W - 200 + off, y - 32, align="r", alpha=a, max_w=560)
        line(ov, [(it["en"], CY)], 26, W - 200 + off, y + 8, align="r", alpha=a, weight=700, max_w=560)
        p = ease((t - t0 - 0.1) / 1.0)
        bx1, bx0 = W - 200 + off, 230 + off
        bw = (bx1 - bx0) * it["share"] / mx_share * p
        dr.rounded_rectangle((bx0, y + 38, bx1, y + 56), 9, fill=(255, 255, 255, int(40 * a)))
        if bw > 18:
            dr.rounded_rectangle((bx1 - bw, y + 38, bx1, y + 56), 9, fill=CHIP_COLORS[i % 4] + (int(255 * a),))
        line(ov, [(f"{it['share'] * p:.1f}%", Y)], 46, 145 + off, y + 2, alpha=a)
    if ex["source_ar"]:
        line(ov, [(ex["source_ar"], (200, 214, 232))], 28, W / 2, 1790, alpha=ease((t - 2.4) / 0.4), weight=700)
    if ex["source_en"]:
        line(ov, [(ex["source_en"], (170, 186, 208))], 24, W / 2, 1832, alpha=ease((t - 2.5) / 0.4), weight=600)

# ---------------- scene list + sound cues (built per country) ----------------
def build_scenes(ctx):
    d = ctx["d"]
    sc = [("intro", 6.0, intro_cam, intro_draw,
           [(0.1, "bell_low"), (1.15, "whoosh_long"), (3.95, "impact"), (4.2, "pop"), (4.35, "shimmer")]),
          ("location", 6.0, location_cam, location_draw,
           [(0.0, "whoosh"), (0.3, "pop"), (1.8, "pop")] + [(1.4 + k * 0.07, "click") for k in range(6)]),
          ]
    if d["neighbors"]:
        n = len(d["neighbors"])
        st = ctx["nb_step"] = min(NB_STEP, 5.0 / n)
        sc.append(("neighbors", 3.2 + st * n, neighbors_cam, neighbors_draw,
                   [(0.2, "swell")] + [e for k in range(n) for e in ((NB_START + k * st, "whoosh" if st > 0.4 else "click"),
                                                                       (NB_START + k * st + 0.3, "pop"))]))
    sc.append(("capital", 5.0, capital_cam, capital_draw, [(0.0, "whoosh"), (1.42, "pin_drop"), (1.65, "pop")]))
    if d["distances"]:
        ev = []
        for i in range(len(d["distances"])):
            b = i * DIST_SEG
            ev += [(b, "whoosh"), (b + DIST_TRAVEL, "swell"), (b + DIST_TRAVEL + 0.05, "counter"),
                   (b + DIST_TRAVEL + DIST_DRAW, "pop"), (b + DIST_TRAVEL + DIST_DRAW + 0.2, "click")]
        sc.append(("distances", DIST_SEG * len(d["distances"]), dist_cam, dist_draw, ev))
    sc.append(("numbers", 6.0, numbers_cam, numbers_draw,
               [(0.0, "whoosh"), (1.1, "pop"), (1.2, "counter"), (1.6, "pop"), (1.7, "counter"), (2.4, "click"), (3.0, "click")]))
    if d["compare"]:
        ev = []
        for i in range(len(d["compare"])):
            b = i * CMP_SEG
            ev += [(b, "whoosh_long"), (b + CMP_TRAVEL - 0.05, "impact"), (b + CMP_TRAVEL + 0.25, "pop"), (b + CMP_TRAVEL + 0.5, "click")]
        sc.append(("compare", CMP_SEG * len(d["compare"]), compare_cam, compare_draw, [(0.0, "riser")] + ev))
    sc.append(("language", 5.5, language_cam, language_draw,
               [(0.0, "whoosh_long"), (1.5, "pop"), (1.9, "impact_soft"), (2.0, "pop"), (2.3, "pop")]))
    if d["exports"]:
        n = len(d["exports"]["items"])
        sc.append(("exports", EXP_DUR, exports_cam, exports_draw,
                   [(0.0, "whoosh"), (0.3, "pop"), (0.6, "click")] +
                   [(e, k) for i in range(n) for e, k in ((1.1 + i * 0.45, "pop"), (1.2 + i * 0.45, "counter"))]))
    if d["facts"]:
        ev = []
        for i, f in enumerate(d["facts"]):
            b = i * FACT_SEG
            ev += [(b, "whoosh"), (b + 0.2, "pop"), (b + 0.95, "shimmer")]
            if isinstance(f["map"], list):
                ev += [(b + 0.9 + k * 0.18, "click") for k in range(len(f["map"]))]
        sc.append(("facts", FACT_SEG * len(d["facts"]), facts_cam, facts_draw, ev))
    sc.append(("outro", 4.0, outro_cam, outro_draw, [(0.0, "whoosh_down"), (0.6, "impact_soft"), (0.9, "bell")]))
    return sc

# ---------------- context ----------------
def make_ctx(country):
    d = load_data(country)
    shapes = load_shapes()
    by_name = {sh[2]: sh for sh in shapes}
    bb = main_bbox(by_name[d["geo_name"]][3])
    c0 = (((bb[0] + bb[2]) / 2 + 180) % 360 - 180, (bb[1] + bb[3]) / 2)
    ext_main = max((bb[2] - bb[0]) * math.cos(math.radians(c0[1])), bb[3] - bb[1])
    cmp = []
    for cp in d["compare"]:
        b = main_bbox(by_name[cp["geo_name"]][3])
        cc = (((b[0] + b[2]) / 2 + 180) % 360 - 180, (b[1] + b[3]) / 2)
        ext = max((b[2] - b[0]) * math.cos(math.radians(cc[1])), b[3] - b[1])
        R = W * 0.74 / math.radians(max(ext_main, ext) * 1.12)
        rr = sorted(by_name[cp["geo_name"]][3], key=lambda r: -len(r))
        rr = [r for r in rr if len(r) >= max(6, len(rr[0]) * 0.02)]
        cmp.append({**cp, "center": cc, "cam": (cc[0], cc[1], R), "bbox": b, "id": None,
                    "rings_v": [xyz(r[:, 0], r[:, 1]) for r in rr]})
    g = Globe(d["geo_name"], [n["geo_name"] for n in d["neighbors"]], extra_regions=[(*c["bbox"], c["cam"][2]) for c in cmp])
    for c in cmp:
        c["id"] = g.id_of[c["geo_name"]]
    fitR = g.fit_radius(W, 0.8)
    cl = d["capital_ll"]
    cams = {"space": (c0[0] - 75, 12.0, 330.0), "fit": (g.center[0], g.center[1], fitR),
            "wide": (g.center[0], g.center[1], fitR * 0.6),
            "cap": (lerp(g.center[0], cl[0], 0.75), lerp(g.center[1], cl[1], 0.75), fitR * 1.8)}
    rings = main_rings(by_name[d["geo_name"]][3])  # the shape that gets dragged (no far territories)
    rings = [r for r in rings if len(r) >= max(6, len(rings[0]) * 0.01)]
    ctx = {"d": d, "g": g, "cams": cams, "cmp": cmp, "main_v": [xyz(r[:, 0], r[:, 1]) for r in rings]}
    ctx["fact_cams"] = [fact_cam(ctx, f) for f in d["facts"]]
    # neighbours: label each at its point nearest to the main country
    cv = xyz(*g.center)
    for n in d["neighbors"]:
        pts = np.concatenate([r for r in by_name[n["geo_name"]][3]])
        v = xyz(pts[:, 0], pts[:, 1])
        j = int(np.argmax(v @ cv))
        n["anchor"] = (float(pts[j, 0]), float(pts[j, 1]))
        rr = sorted(by_name[n["geo_name"]][3], key=lambda r: -len(r))
        n["rings_v"] = [xyz(r[:, 0], r[:, 1]) for r in rr if len(r) >= max(4, len(rr[0]) * 0.003)]
    if d["neighbors"]:
        lons = [g.bbox[0], g.bbox[2]] + [n["anchor"][0] for n in d["neighbors"]]
        lats = [g.bbox[1], g.bbox[3]] + [n["anchor"][1] for n in d["neighbors"]]
        clon, clat = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
        ext = max((max(lons) - min(lons)) * math.cos(math.radians(clat)), (max(lats) - min(lats)) * 0.62)
        R = W * 0.80 / math.radians(ext + 3)
        cams["nb"] = (clon, clat + ext * 0.10, min(max(R, fitR * 0.5), fitR * 1.2))
    # distance views: camera south of the arc's midpoint so the raised arc reads clearly
    capv = xyz(*d["capital_ll"])
    ctx["dist"] = []
    for x in d["distances"]:
        a = xyz(x["lon"], x["lat"])
        ang = math.acos(float(np.clip(a @ capv, -1, 1)))
        mid = (a + capv) / np.linalg.norm(a + capv) if ang < math.pi - 1e-3 else capv
        mlon, mlat = math.degrees(math.atan2(mid[1], mid[0])), math.degrees(math.asin(mid[2]))
        R = min(fitR * 0.9, W * 0.36 / math.sin(min(math.radians(80), ang / 2 + math.radians(10))))
        ctx["dist"].append({**x, "v": a, "ang": ang, "cam": (mlon, mlat - 10, R)})
    ctx["capv"] = capv
    ctx["flag_big"] = flag_badge(d["cca2"], 250)
    ctx["flags"] = {d["cca3"]: flag_badge(d["cca2"], 66), **{c["cca3"]: flag_badge(c["cca2"], 66) for c in cmp},
                    **{n["cca3"]: flag_badge(n["cca2"], 56) for n in d["neighbors"]}}
    ctx["scenes"] = build_scenes(ctx)
    return ctx

# ---------------- render ----------------
_ctx = None
def _init(country, xlsx=None, cache_dir=None):
    global _ctx, XLSX
    if xlsx:
        XLSX = xlsx
    if cache_dir:
        kglobe.CACHE_DIR = cache_dir
    _ctx = make_ctx(country)

def chrome(img, i, n, t, dur):
    dr = ImageDraw.Draw(img)
    seg, gap = (W - 120 - (n - 1) * 10) / n, 10
    for k in range(n):
        x0 = 60 + k * (seg + gap)
        dr.rounded_rectangle((x0, 66, x0 + seg, 76), 5, fill=(255, 255, 255, 90))
        f = 1 if k < i else (min(1, t / dur) if k == i else 0)
        if f > 0:
            dr.rounded_rectangle((x0, 66, x0 + seg * f, 76), 5, fill=Y + (255,))
    line(img, [(BRAND, WH)], 32, W / 2, 128, weight=700)

def frame(i, t):
    scenes = _ctx["scenes"]
    name, dur, cam_fn, draw_fn, _ = scenes[i]
    vals = cam_fn(_ctx, t, dur)
    cam, cy, hl, nh, dim, phase, sid = vals[:7]
    img = background()
    img.alpha_composite(map_layer(_ctx["g"], cy, cam, hl, nh, dim, phase, sid, vals[7] if len(vals) > 7 else 0.0))
    img.alpha_composite(gradients())
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_fn(ov, _ctx, t, dur, cam)
    if i < len(scenes) - 1:
        a = 1 - ease((t - (dur - 0.3)) / 0.3)
        if a < 1:
            ov.putalpha(ov.getchannel("A").point(lambda v: int(v * a)))
    img.alpha_composite(ov)
    chrome(img, i, len(scenes), t, dur)
    rgb = img.convert("RGB")
    fade = min(1.0, t / 0.3) if i == 0 else 1.0
    if i == len(scenes) - 1:
        fade = min(fade, (dur - t) / 0.6)
    if fade < 1:
        rgb = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), rgb, max(0.0, fade))
    return rgb

def render_scene(args):
    i, path = args
    name, dur = _ctx["scenes"][i][0], _ctx["scenes"][i][1]
    tmp = path[:-4] + ".part.mp4"
    p = subprocess.Popen([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "18",
                          "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(int(round(dur * FPS))):
        p.stdin.write(frame(i, f / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {name}")
    os.replace(tmp, path)
    return name

def render(country, out, xlsx, cache_dir=None, workers=2, progress=None, should_stop=None):
    """Render one country (a row of the Excel file) to out (.mp4). progress(fraction, text) is called as
    scenes finish. Returns out."""
    global XLSX
    XLSX = xlsx
    light = {"d": load_data(country)}       # the scene plan needs only the Excel row, not the heavy globe
    scenes = build_scenes(light)
    name = light["d"]["name_en"]
    work = os.path.splitext(out)[0] + "_scenes"
    os.makedirs(work, exist_ok=True)
    jobs = [(i, os.path.join(work, f"{i:02d}_{scenes[i][0]}.mp4")) for i in range(len(scenes))]
    order = sorted(jobs, key=lambda j: -scenes[j[0]][1])
    total = sum(sc[1] for sc in scenes)
    done = 0.0
    if progress:
        progress(0.02, f"{name}: preparing the map…")
    env = os.environ.get("VS_WORKERS")
    workers = int(env) if env and env.isdigit() else workers
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor
    from concurrent.futures import wait as wait_futures
    from concurrent.futures.process import BrokenProcessPool
    try:
        with ProcessPoolExecutor(max(1, min(workers, len(order))), mp_context=mp.get_context("spawn"),
                                 initializer=_init, initargs=(country, xlsx, cache_dir)) as pool:
            todo = {pool.submit(render_scene, job) for job in order}
            try:
                while todo:  # wake up twice a second to see whether ⏹ Stop was pressed
                    ready, todo = wait_futures(todo, timeout=0.5, return_when=FIRST_COMPLETED)
                    if should_stop and should_stop():
                        from ..core import RenderStopped
                        raise RenderStopped("Rendering stopped.")
                    for fut in ready:
                        nm = fut.result()
                        done += next(sc[1] for sc in scenes if sc[0] == nm)
                        if progress:
                            progress(0.02 + 0.9 * done / total, f"{name}: rendered {nm}")
            except BaseException:  # stop now: end the drawing processes instead of waiting for their scenes
                procs = list(getattr(pool, "_processes", {}).values())
                for proc in procs:
                    proc.terminate()
                for proc in procs:  # gone before their folder is removed
                    proc.join(5)
                pool.shutdown(wait=False, cancel_futures=True)
                import shutil
                shutil.rmtree(work, ignore_errors=True)
                raise
    except BrokenProcessPool:
        raise RuntimeError("A drawing process stopped unexpectedly (usually not enough free memory). Close other "
                           "programs and try again, or set the environment variable VS_WORKERS=1 to draw on one process.")
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{os.path.abspath(p).replace(os.sep, '/')}'\n" for _, p in jobs)
    silent = os.path.join(work, "silent.mp4")
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    events, off = [], 0.0
    for sc in scenes:
        events += [(off + t, kk) for t, kk in sc[4]]
        off += sc[1]
    wav = os.path.join(work, "audio.wav")
    sound.mix(off, events, wav)
    tmp = os.path.splitext(out)[0] + ".part.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", tmp], check=True)
    os.replace(tmp, out)
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, f"{name}: done")
    return out

def preview(country, xlsx, out_png, cache_dir=None):
    """A quick still (end of the intro) to check a row before the long render."""
    _init(country, xlsx, cache_dir)
    names = [s[0] for s in _ctx["scenes"]]
    i = names.index("intro")
    frame(i, _ctx["scenes"][i][1] - 0.4).save(out_png)
    release()
    return out_png


def release():
    """Free the globe textures held by this process (about 1 GB)."""
    global _ctx
    _ctx = None
    _gcache.clear()


def countries_in(xlsx):
    """Country names of the rows in the Excel file (for the app's drop-down)."""
    global XLSX
    XLSX = xlsx
    return [s(r["country"]) for r in excel_rows()[0] if s(r.get("country"))]
