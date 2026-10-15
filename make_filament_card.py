#!/usr/bin/env python3
"""
Parametric filament sample card generator (Bambu Studio 3MF).

    python3 make_filament_card.py "材料类型" "颜色名" "编号" "HEX色号" [浮雕高度mm] [options]

Example:
    python3 make_filament_card.py "PLA MATTE" "Iridium Gold" "(13008)" "#A2D312" 1.2
    python3 make_filament_card.py "PLA 哑光" "铱金" "13008" "A2D312" --preview

What it does
------------
* Takes template/card_template.3mf (= the short sample card plate with the
  exact print settings of 耗材样本卡v3.3mf, already fixed for the prime tower:
  card + text + swatch are ONE object, so there is only one layer height).
* Renders the 4 text fields + separator line as relief part "Text_Info"
  (filament 2) and a round swatch as part "Color_Swatch" (filament 3).
* Sets filament 3's colour to the given HEX, filament 2 to white (#FFFFFF),
  and filament 1 to card base (#B39B84). The profile has exactly 3 filaments.

Printability for a 0.4 mm nozzle
--------------------------------
* Large, bold CJK-capable font (Hiragino Sans GB W6), auto-fitted per row.
* Crisp vector outlines extracted directly from the font, producing clean,
  watertight 3D relief text that prints cleanly with modern slicers (Arachne engine).
* Optional --thicken flag: morphologically expands thin strokes if needed for
  coarse nozzles without Arachne.

Relief height (浮雕高度) is measured from the pocket floor. The card's top
surface is 0.5 mm above the pocket floor, so the default 1.2 mm sticks out
0.7 mm above the card; 0.5 gives a flush multi-colour inlay.
"""
import argparse
import json
import os
import re
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = (
    os.path.join(HERE, "card_template.3mf")
    if os.path.exists(os.path.join(HERE, "card_template.3mf"))
    else os.path.join(HERE, "template", "card_template.3mf")
)

# ---------------------------------------------------------------- geometry --
# Card-local coordinates (card mesh centred at origin, z -1..1).
POCKET_CX, POCKET_CY = -6.3, 0.0       # pocket x -26.5..13.9, y -15.2..15.2
POCKET_W, POCKET_H = 40.4, 30.4         # corner radius ~2 mm
POCKET_FLOOR_Z = 0.5                    # card top surface is at z = 1.0

TEXT_FILAMENT = 2                       # filament slot for the text
SWATCH_FILAMENT = 3                     # filament slot for the swatch

PPM = 40                                # raster resolution, px per mm
MARGIN = 2.2                            # keep-out from pocket wall

# ------------------------------------------------------------------- fonts --
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),        # W6, Latin + CJK
    ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
    ("/Library/Fonts/Arial Unicode.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
]


def pick_font(path, index):
    if path:
        return path, index
    for p, i in FONT_CANDIDATES:
        if os.path.exists(p):
            return p, i
    sys.exit("No usable font found, pass --font")


def has_cjk(s):
    return any(ord(ch) >= 0x2E80 for ch in s)


# ============================================================ text raster ==
class Canvas:
    """Raster in pocket-local mm (origin = pocket centre, y up)."""

    def __init__(self):
        self.w = int(round(POCKET_W * PPM))
        self.h = int(round(POCKET_H * PPM))
        self.img = np.zeros((self.h, self.w), np.uint8)

    def col(self, x):
        return int(round((x + POCKET_W / 2) * PPM))

    def row(self, y):
        return int(round((POCKET_H / 2 - y) * PPM))

    def paste(self, glyphs, x, baseline_y, align="left"):
        """glyphs = (mask, baseline_row_in_mask)."""
        m, base = glyphs
        gh, gw = m.shape
        c0 = self.col(x)
        if align == "right":
            c0 -= gw
        elif align == "center":
            c0 -= gw // 2
        r0 = self.row(baseline_y) - base
        r1, c1 = r0 + gh, c0 + gw
        rr0, cc0 = max(r0, 0), max(c0, 0)
        rr1, cc1 = min(r1, self.h), min(c1, self.w)
        if rr1 <= rr0 or cc1 <= cc0:
            return
        self.img[rr0:rr1, cc0:cc1] |= m[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0]


class TextRenderer:
    def __init__(self, font_path, font_index):
        self.path, self.index = font_path, font_index
        self.warnings = []

    def _font(self, px):
        return ImageFont.truetype(self.path, max(int(round(px)), 4), index=self.index)

    def _ref_ratio(self, text):
        """ink height of a reference glyph per px of font size."""
        ref = "H国" if has_cjk(text) else "H"
        f = self._font(1000)
        b = f.getbbox(ref, anchor="ls")
        return (b[3] - b[1]) / 1000.0

    def render(self, text, ink_h, max_w, min_scale=0.6, max_condense=0.8, label=""):
        """Render `text` so the reference glyph is `ink_h` mm tall and the
        line is at most `max_w` mm wide. Returns ((mask, baseline_row), h_mm)."""
        size_px = ink_h * PPM / self._ref_ratio(text)
        scale = 1.0
        for _ in range(2):
            f = self._font(size_px * scale)
            l, t, r, b = f.getbbox(text, anchor="ls")
            w_mm = (r - l) / PPM
            if w_mm <= max_w:
                sx = 1.0
                break
            need = max_w / w_mm
            if need >= max_condense:
                sx = need
                break
            sx = max_condense
            scale *= need / max_condense
        else:
            sx = min(1.0, max_w / w_mm)
        if scale < min_scale:
            self.warnings.append(
                f"'{text}' ({label}) is long: shrunk to {scale:.0%}; strokes may crowd.")
        pad = 4
        im = Image.new("L", (r - l + 2 * pad, b - t + 2 * pad), 0)
        ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=255, anchor="ls")
        m = np.array(im)
        base = pad - t
        if sx < 0.999:
            m = cv2.resize(m, (max(1, int(m.shape[1] * sx)), m.shape[0]),
                           interpolation=cv2.INTER_AREA)
        m = (m > 127).astype(np.uint8) * 255
        cols = np.where(m.any(axis=0))[0]
        if len(cols):
            m = m[:, cols[0]:cols[-1] + 1]
        return (m, base), ink_h * scale


def disk(r_px):
    r = max(int(round(r_px)), 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def ridge_of(mask):
    d = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
    ridge = (d >= cv2.dilate(d, np.ones((3, 3), np.uint8)) - 1e-3) & (mask > 0)
    return d, ridge


def enforce_min_feature(mask, min_stroke, min_gap):
    """Thicken strokes thinner than min_stroke; don't let added material make
    gaps narrower than min_gap. Original glyph pixels are always kept."""
    r = min_stroke / 2 * PPM
    m = mask > 0
    d, ridge = ridge_of(mask)
    local_max = cv2.dilate(d, disk(r))
    near_max = cv2.dilate(d, disk(max(2, r * 0.6)))
    seeds = (ridge & (local_max < r) & (d >= 0.75 * near_max)).astype(np.uint8)
    grown = cv2.dilate(seeds, disk(r)) > 0
    out = m | grown

    g = min_gap / 2 * PPM
    bg = (~out).astype(np.uint8)
    dbg, rbg = ridge_of(bg)
    carve_seeds = (rbg & (dbg < g)).astype(np.uint8)
    carve = cv2.dilate(carve_seeds, disk(g)) > 0
    out = m | (out & ~carve)
    return out.astype(np.uint8) * 255


def stroke_report(mask, min_stroke):
    d, ridge = ridge_of(mask)
    # ignore ridge pixels near stroke ends: keep those that are local thickness maxima
    lm = cv2.dilate(d, disk(min_stroke / 2 * PPM))
    core = ridge & (d >= 0.9 * lm) & (d > 1)
    w = 2 * d[core] / PPM
    if len(w) == 0:
        return float("nan")
    return float(np.percentile(w, 1))


# ======================================================= polygons / mesh ==
def mask_to_polygons(mask, eps_mm=0.02):
    """-> list of (outer CCW ring, [hole CW rings]) in pocket-local mm."""
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]

    def ring(c):
        c = cv2.approxPolyDP(c, eps_mm * PPM, True).reshape(-1, 2).astype(float)
        x = (c[:, 0] + 0.5) / PPM - POCKET_W / 2
        y = POCKET_H / 2 - (c[:, 1] + 0.5) / PPM
        return np.stack([x, y], 1)

    polys = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:
            continue
        outer = ring(c)
        if len(outer) < 3 or abs(signed_area(outer)) < 0.01:
            continue
        if signed_area(outer) < 0:
            outer = outer[::-1]
        holes = []
        j = hier[i][2]
        while j != -1:
            h = ring(cnts[j])
            if len(h) >= 3 and abs(signed_area(h)) > 0.005:
                if signed_area(h) > 0:
                    h = h[::-1]
                holes.append(h)
            j = hier[j][0]
        polys.append((outer, holes))
    return polys


def signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def bridge_holes(P, outer_idx, holes_idx):
    """Eberly hole elimination. P: (n,2) coords; returns merged index list."""
    poly = list(outer_idx)
    holes = sorted(holes_idx, key=lambda h: -P[h, 0].max())
    for h in holes:
        h = list(h)
        mi = int(np.argmax(P[h, 0]))
        M = P[h[mi]]
        A = P[poly]
        B = np.roll(A, -1, 0)
        cross_y = (A[:, 1] > M[1]) != (B[:, 1] > M[1])
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (M[1] - A[:, 1]) / (B[:, 1] - A[:, 1])
            xi = A[:, 0] + t * (B[:, 0] - A[:, 0])
        valid = cross_y & (xi >= M[0])
        if not valid.any():
            continue
        e = int(np.argmin(np.where(valid, xi, np.inf)))
        I = np.array([xi[e], M[1]])
        k = e if A[e, 0] > B[e, 0] else (e + 1) % len(poly)
        Pc = P[poly[k]]
        # reflex vertices inside triangle (M, I, Pc) -> pick best visible one
        prev = np.roll(A, 1, 0)
        nxt = np.roll(A, -1, 0)
        cr = (A[:, 0] - prev[:, 0]) * (nxt[:, 1] - A[:, 1]) - (A[:, 1] - prev[:, 1]) * (nxt[:, 0] - A[:, 0])
        reflex = cr <= 0
        if reflex.any():
            tri = (M, I, Pc) if (I[0] - M[0]) * (Pc[1] - M[1]) - (I[1] - M[1]) * (Pc[0] - M[0]) > 0 else (M, Pc, I)
            ins = points_in_tri(A, *tri, eps=-1e-12) & reflex
            ins[k] = False
            if ins.any():
                cand = np.where(ins)[0]
                v = A[cand] - M
                ang = np.abs(np.arctan2(v[:, 1], v[:, 0]))
                dist = np.hypot(v[:, 0], v[:, 1])
                k = int(cand[np.lexsort((dist, ang))[0]])
        poly = poly[:k + 1] + h[mi:] + h[:mi + 1] + poly[k:]
    return poly


def points_in_tri(pts, a, b, c, eps=1e-12):
    def cr(p, q, r):
        return (q[0] - p[0]) * (r[:, 1] - p[1]) - (q[1] - p[1]) * (r[:, 0] - p[0])
    return (cr(a, b, pts) > eps) & (cr(b, c, pts) > eps) & (cr(c, a, pts) > eps)


def earclip(P, idx):
    V = list(idx)
    tris = []
    guard = 0
    while len(V) > 3:
        guard += 1
        if guard > 100000:
            raise RuntimeError("triangulation did not converge")
        A = P[V]
        prev = np.roll(A, 1, 0)
        nxt = np.roll(A, -1, 0)
        cr = (A[:, 0] - prev[:, 0]) * (nxt[:, 1] - A[:, 1]) - (A[:, 1] - prev[:, 1]) * (nxt[:, 0] - A[:, 0])
        reflex_pts = A[cr <= 0]
        n = len(V)
        clipped = False
        for i in np.argsort(-cr):           # best-shaped (most convex) first
            if cr[i] <= 0:
                break
            a, b, c = prev[i], A[i], nxt[i]
            if len(reflex_pts):
                ins = points_in_tri(reflex_pts, a, b, c)
                if ins.any():
                    # ignore duplicates of the triangle corners (bridge vertices)
                    q = reflex_pts[ins]
                    same = (np.all(np.isclose(q, a), 1) | np.all(np.isclose(q, b), 1) |
                            np.all(np.isclose(q, c), 1))
                    if not same.all():
                        continue
            tris.append((V[(i - 1) % n], V[i], V[(i + 1) % n]))
            del V[i]
            clipped = True
            break
        if not clipped:
            # degenerate (collinear / zero-area) vertex: drop it with a sliver
            i = int(np.argmax(cr))
            tris.append((V[(i - 1) % n], V[i], V[(i + 1) % n]))
            del V[i]
    tris.append(tuple(V))
    return tris


def extrude(polys, z0, z1, dx=0.0, dy=0.0):
    verts, tris = [], []
    for outer, holes in polys:
        rings = [outer] + holes
        P = np.vstack(rings)
        base = len(verts)
        n = len(P)
        offs, o = [], 0
        for r in rings:
            offs.append(list(range(o, o + len(r))))
            o += len(r)
        merged = bridge_holes(P, offs[0], offs[1:])
        top = earclip(P, merged)
        for x, y in P:
            verts.append((x + dx, y + dy, z0))
        for x, y in P:
            verts.append((x + dx, y + dy, z1))
        for a, b, c in top:
            tris.append((base + n + a, base + n + b, base + n + c))   # top, up
            tris.append((base + a, base + c, base + b))               # bottom, down
        for ring in offs:
            m = len(ring)
            for k in range(m):
                i, j = ring[k], ring[(k + 1) % m]
                bi, bj, ti, tj = base + i, base + j, base + n + i, base + n + j
                tris.append((bi, bj, tj))
                tris.append((bi, tj, ti))
    return np.array(verts, float), np.array(tris, int)


def circle_poly(cx, cy, r, seg=96):
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    return [(np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], 1), [])]


def check_watertight(tris):
    from collections import Counter
    e = Counter()
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            e[(u, v)] += 1
    bad = sum(1 for (u, v), k in e.items() if k != 1 or e.get((v, u), 0) != 1)
    return bad


# ================================================================= layout ==
def build_layout(args, fr):
    cv_dark = Canvas()
    x0, x1 = -POCKET_W / 2 + MARGIN, POCKET_W / 2 - MARGIN
    y_top, y_bot = POCKET_H / 2 - MARGIN, -POCKET_H / 2 + MARGIN
    usable = x1 - x0

    # swatch, top-right
    sw_r = args.swatch_d / 2
    sw_cx, sw_cy = x1 - sw_r, y_top - sw_r

    # row 1: material
    mat_h = 3.0
    g, _ = fr.render(args.material.upper(), mat_h, usable - args.swatch_d - 1.5, label="材料类型")
    cv_dark.paste(g, x0, sw_cy - mat_h / 2)

    # separator + row 3 (code / hex)
    meta_h = 2.8
    meta_base = y_bot + 0.6
    sep_t = 0.8
    sep_y = meta_base + meta_h + 1.6            # bottom edge of separator
    gc, hc = fr.render(args.code, meta_h, usable, label="编号"), fr.render(args.hex, meta_h, usable, label="HEX")
    wc, wh = gc[0][0].shape[1] / PPM, hc[0][0].shape[1] / PPM
    if wc + wh + 2.0 > usable:                 # shrink both to share the row
        s = (usable - 2.0) / (wc + wh)
        gc = fr.render(args.code, meta_h * s, usable, label="编号")
        hc = fr.render(args.hex, meta_h * s, usable, label="HEX")
    cv_dark.paste(gc[0], x0, meta_base)
    cv_dark.paste(hc[0], x1, meta_base, align="right")
    cv_dark.img[cv_dark.row(sep_y + sep_t):cv_dark.row(sep_y), cv_dark.col(x0):cv_dark.col(x1)] = 255

    # row 2: colour name, centred in the band between swatch and separator
    band_top = sw_cy - sw_r - 0.8
    band_bot = sep_y + sep_t + 1.4             # room for descenders
    band_h = band_top - band_bot
    name = args.color
    big_h = min(5.5, band_h * 0.78)
    g, h = fr.render(name, big_h, usable, min_scale=0.0, label="颜色名")
    words = name.split()
    if h < big_h * 0.62 and len(words) > 1:    # too long: wrap to two lines
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            score = max(len(a), len(b))
            if best is None or score < best[0]:
                best = (score, a, b)
        _, a, b = best
        line_h = min(3.6, (band_h - 1.6) / 2)
        ga, _ = fr.render(a, line_h, usable, label="颜色名")
        gb, _ = fr.render(b, line_h, usable, label="颜色名")
        b2 = band_bot + 0.2
        b1 = b2 + line_h + 1.6
        cv_dark.paste(ga, x0, b1)
        cv_dark.paste(gb, x0, b2)
    else:
        if h < big_h * 0.62:
            fr.warnings.append(f"颜色名 '{name}' is long; consider a shorter name or a space to allow wrapping.")
        base = band_bot + (band_h - h) / 2
        cv_dark.paste(g, x0, base)

    return cv_dark.img, (sw_cx, sw_cy, sw_r)


# ============================================================ 3MF output ==
MODEL_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<model unit="millimeter" xml:lang="en-US" '
    'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
    'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
    'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
    'requiredextensions="p">\n'
    ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
    ' <resources>\n'
)


def mesh_xml(obj_id, uuid, V, T):
    out = [f'  <object id="{obj_id}" p:UUID="{uuid}" type="model">\n   <mesh>\n    <vertices>\n']
    out += [f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>\n' for x, y, z in V]
    out.append('    </vertices>\n    <triangles>\n')
    out += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in T]
    out.append('    </triangles>\n   </mesh>\n  </object>\n')
    return "".join(out)


def center_mesh(V):
    c = (V.min(0) + V.max(0)) / 2
    return V - c, c


def fmt(v):
    return "%.6f" % v


def write_3mf(template, out_path, text_mesh, swatch_mesh, hex_color, base_hex=None, text_hex=None):
    hex_color = normalize_hex(hex_color)
    base_hex = normalize_hex(base_hex) if base_hex else hex_color
    text_hex = normalize_hex(text_hex) if text_hex else auto_contrast_color(base_hex)
    (Vt, Tt), (Vs, Ts) = text_mesh, swatch_mesh
    Vt, ct = center_mesh(Vt)
    Vs, cs = center_mesh(Vs)
    obj_model = (MODEL_HEADER
                 + mesh_xml(3, "00120000-81cb-4c03-9d28-80fed5dfa1dc", Vt, Tt)
                 + mesh_xml(4, "00120001-81cb-4c03-9d28-80fed5dfa1dc", Vs, Ts)
                 + ' </resources>\n <build/>\n</model>\n')

    def tr(c):
        return "1 0 0 0 1 0 0 0 1 %s %s %s" % (fmt(c[0]), fmt(c[1]), fmt(c[2]))

    def mat(c):
        return "1 0 0 %s 0 1 0 %s 0 0 1 %s 0 0 0 1" % (fmt(c[0]), fmt(c[1]), fmt(c[2]))

    zin = zipfile.ZipFile(template)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            name = info.filename
            if name == "3D/Objects/object_18.model":
                data = obj_model.encode("utf-8")
            elif name == "3D/3dmodel.model":
                s = data.decode("utf-8")
                for oid, c in (("3", ct), ("4", cs)):
                    s = re.sub(r'(<component p:path="/3D/Objects/object_18\.model" objectid="%s"[^>]*transform=")[^"]*(")' % oid,
                               lambda m: m.group(1) + tr(c) + m.group(2), s)
                data = s.encode("utf-8")
            elif name == "Metadata/model_settings.config":
                s = data.decode("utf-8")
                for pid, c, nt in (("3", ct, len(Tt)), ("4", cs, len(Ts))):
                    def fix_part(m):
                        p = re.sub(r'(<metadata key="matrix" value=")[^"]*(")',
                                   lambda mm: mm.group(1) + mat(c) + mm.group(2), m.group(0))
                        return re.sub(r'(<mesh_stat face_count=")\d+', lambda mm: mm.group(1) + str(nt), p)
                    s = re.sub(r'<part id="%s" .*?</part>' % pid, fix_part, s, flags=re.S)
                for vid, c in (("1", ct), ("2", cs)):
                    s = re.sub(r'(<assemble_item object_id="2" volume_id="%s" transform=")[^"]*(")' % vid,
                               lambda m: m.group(1) + tr(c) + m.group(2), s)
                card_faces = 3472
                s = re.sub(r'(<object id="2">.*?<metadata face_count=")\d+',
                           lambda m: m.group(1) + str(card_faces + len(Tt) + len(Ts)), s, count=1, flags=re.S)
                data = s.encode("utf-8")
            elif name == "Metadata/model_settings.config":
                s = data.decode("utf-8")
                for pid, c, nt in (("3", ct, len(Tt)), ("4", cs, len(Ts))):
                    def fix_part(m):
                        p = re.sub(r'(<metadata key="matrix" value=")[^"]*(")',
                                   lambda mm: mm.group(1) + mat(c) + mm.group(2), m.group(0))
                        return re.sub(r'(<mesh_stat face_count=")\d+', lambda mm: mm.group(1) + str(nt), p)
                    s = re.sub(r'<part id="%s" .*?</part>' % pid, fix_part, s, flags=re.S)
                for vid, c in (("1", ct), ("2", cs)):
                    s = re.sub(r'(<assemble_item object_id="2" volume_id="%s" transform=")[^"]*(")' % vid,
                               lambda m: m.group(1) + tr(c) + m.group(2), s)
                card_faces = 3472
                s = re.sub(r'(<object id="2">.*?<metadata face_count=")\d+',
                           lambda m: m.group(1) + str(card_faces + len(Tt) + len(Ts)), s, count=1, flags=re.S)
                # Ensure parts 3 and 4 map to extruders 2 and 3, and plate maps 3 filaments
                s = re.sub(r'(<part id="3" [^>]*?><metadata key="name" value="Text_Info"/>.*?<metadata key="extruder" value=")\d+(")', r'\g<1>2\2', s, flags=re.S)
                s = re.sub(r'(<part id="4" [^>]*?><metadata key="name" value="Color_Swatch"/>.*?<metadata key="extruder" value=")\d+(")', r'\g<1>3\2', s, flags=re.S)
                s = re.sub(r'(<metadata key="filament_maps" value=")[^"]*(")', r'\g<1>1 1 1\2', s)
                s = re.sub(r'(<metadata key="filament_volume_maps" value=")[^"]*(")', r'\g<1>0 0 0\2', s)
                data = s.encode("utf-8")
            elif name == "Metadata/project_settings.config":
                cfg = json.loads(data.decode("utf-8"))
                # Automatically trim down to 3 filaments if template has more
                if len(cfg.get("filament_colour", [])) > 3:
                    sel = [0, 1, 9] if len(cfg["filament_colour"]) >= 10 else [0, 1, 2]
                    n_old = len(cfg["filament_colour"])
                    for k, v in list(cfg.items()):
                        if not isinstance(v, list):
                            continue
                        if len(v) == n_old:
                            cfg[k] = [v[i] for i in sel]
                        elif len(v) == 2 * n_old:
                            cfg[k] = [x for i in sel for x in v[2*i : 2*i + 2]]
                        elif len(v) == 4 * n_old:
                            cfg[k] = [x for i in sel for x in v[4*i : 4*i + 4]]
                        elif len(v) == n_old * n_old:
                            cfg[k] = [v[r * n_old + c_idx] for r in sel for c_idx in sel]
                        elif k in ["inherits_group", "different_settings_to_system"]:
                            cfg[k] = [v[0]] + [v[1 + i] for i in sel] + [v[-1]]
                    cfg["filament_self_index"] = ["1", "1", "2", "2", "3", "3"]
                n_cols = len(cfg.get("filament_colour", []))
                if n_cols >= 1:
                    cfg["filament_colour"][0] = normalize_hex(base_hex)
                if n_cols == 3:
                    cfg["filament_colour"][1] = normalize_hex(text_hex)
                    cfg["filament_colour"][2] = normalize_hex(hex_color)
                else:
                    if n_cols >= TEXT_FILAMENT:
                        cfg["filament_colour"][TEXT_FILAMENT - 1] = normalize_hex(text_hex)
                    if n_cols >= SWATCH_FILAMENT:
                        cfg["filament_colour"][SWATCH_FILAMENT - 1] = normalize_hex(hex_color)
                cfg["initial_layer_print_height"] = "0.1"
                cfg["layer_height"] = "0.1"
                data = json.dumps(cfg, indent=4, ensure_ascii=False).encode("utf-8")
            elif name == "Metadata/plate_1.json":
                pj = json.loads(data.decode("utf-8"))
                for obj in pj.get("bbox_objects", []):
                    obj["layer_height"] = 0.1
                data = json.dumps(pj, ensure_ascii=False).encode("utf-8")
            zout.writestr(info, data)


# =================================================================== main ==
def normalize_hex(h):
    s = h.strip().lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", s):
        raise ValueError(f"Invalid HEX colour: {h}")
    return "#" + s


def auto_contrast_color(hex_color):
    """Return '#1A1A1A' for light backgrounds, '#FFFFFF' for dark backgrounds."""
    s = normalize_hex(hex_color).lstrip("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#1A1A1A" if lum > 0.5 else "#FFFFFF"


class ArgsWrapper:
    def __init__(self, material, color, code, hex_val, relief=0.5, swatch_d=7.0,
                 template=DEFAULT_TEMPLATE, thicken=False, min_stroke=0.8, min_gap=0.5,
                 font=None, font_index=0, preview=False, out=None,
                 base_hex=None, text_hex=None):
        self.material = material
        self.color = color
        self.code = code
        self.hex = normalize_hex(hex_val)
        self.relief = relief
        self.swatch_d = swatch_d
        self.template = template
        self.thicken = thicken
        self.min_stroke = min_stroke
        self.min_gap = min_gap
        self.font = font
        self.font_index = font_index
        self.preview = preview
        self.out = out
        self.base_hex = normalize_hex(base_hex) if base_hex else self.hex
        self.text_hex = normalize_hex(text_hex) if text_hex else auto_contrast_color(self.base_hex)


def render_preview_image(material, color, code, hex_color, swatch_d=7.0,
                         thicken=False, min_stroke=0.8, min_gap=0.5,
                         font_path=None, font_index=0,
                         base_hex=None, text_hex=None):
    """Render 2D preview image of the card pocket. Returns (bgr_img, warnings, stroke_info)."""
    hex_color = normalize_hex(hex_color)
    base_hex = normalize_hex(base_hex) if base_hex else hex_color
    text_hex = normalize_hex(text_hex) if text_hex else auto_contrast_color(base_hex)
    font_path, font_index = pick_font(font_path, font_index)
    fr = TextRenderer(font_path, font_index)

    args = ArgsWrapper(material=material, color=color, code=code, hex_val=hex_color,
                       swatch_d=swatch_d, thicken=thicken, min_stroke=min_stroke, min_gap=min_gap,
                       base_hex=base_hex, text_hex=text_hex)
    raw, (sw_cx, sw_cy, sw_r) = build_layout(args, fr)

    if thicken:
        before = stroke_report(raw, min_stroke)
        dark = enforce_min_feature(raw, min_stroke, min_gap)
        after = stroke_report(dark, min_stroke)
    else:
        dark = raw
        before = stroke_report(raw, 0.4)
        after = before

    base_rgb = tuple(int(base_hex[i:i + 2], 16) for i in (1, 3, 5))
    text_rgb = tuple(int(text_hex[i:i + 2], 16) for i in (1, 3, 5))
    prev = np.full(raw.shape + (3,), base_rgb[::-1], np.uint8)  # card colour (BGR)
    prev[dark > 0] = text_rgb[::-1]                             # text colour (BGR)
    if thicken:
        prev[(dark > 0) & (raw == 0)] = (0, 0, 220)  # added material in red
    cvs = Canvas()
    rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    cv2.circle(prev, (cvs.col(sw_cx), cvs.row(sw_cy)), int(sw_r * PPM), rgb[::-1], -1, cv2.LINE_AA)
    # Subtle outline ring so the circular swatch has clear 3D definition even when base == swatch
    ring_col = (40, 40, 40) if auto_contrast_color(hex_color) == "#1A1A1A" else (220, 220, 220)
    cv2.circle(prev, (cvs.col(sw_cx), cvs.row(sw_cy)), int(sw_r * PPM), ring_col, 2, cv2.LINE_AA)

    stroke_info = {
        "before": before,
        "after": after,
        "thicken": thicken
    }
    return prev, fr.warnings, stroke_info


def render_full_card(material, color, code, hex_color, out_path=None, ppm=25,
                     base_hex=None, text_hex=None):
    """Render high-resolution 2D preview image of the ENTIRE card (75x36mm) matching MakerWorld #70155."""
    hex_color = normalize_hex(hex_color)
    base_hex = normalize_hex(base_hex) if base_hex else hex_color
    text_hex = normalize_hex(text_hex) if text_hex else auto_contrast_color(base_hex)

    hex_clean = hex_color.lstrip('#')
    h_rgb = tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
    base_clean = base_hex.lstrip('#')
    card_base_rgb = tuple(int(base_clean[i:i+2], 16) for i in (0, 2, 4))
    clean_t_hex = text_hex.lstrip('#')
    txt_rgb = tuple(int(clean_t_hex[i:i+2], 16) for i in (0, 2, 4))
    is_light = (0.299 * card_base_rgb[0] + 0.587 * card_base_rgb[1] + 0.114 * card_base_rgb[2]) > 128

    pad_mm = 4.0
    W_mm = 75.0 + pad_mm * 2
    H_mm = 36.0 + pad_mm * 2
    W_px = int(W_mm * ppm)
    H_px = int(H_mm * ppm)
    ox = W_px // 2
    oy = H_px // 2

    rendered_from_mesh = False
    if os.path.exists(DEFAULT_TEMPLATE):
        try:
            import zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(DEFAULT_TEMPLATE, 'r') as z:
                m_xml = z.read('3D/Objects/object_2.model')
                root = ET.fromstring(m_xml)
                obj = root.find('.//{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}object[@id="1"]')
                m = obj.find('{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}mesh')
                verts = np.array([[float(v.get('x')), float(v.get('y')), float(v.get('z'))] for v in m.find('{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}vertices')])
                triangles = np.array([[int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))] for t in m.find('{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}triangles')])

            card_img = np.zeros((H_px, W_px, 4), dtype=np.uint8)
            tri_max_z = np.max(verts[triangles, 2], axis=1)
            order = np.argsort(tri_max_z)

            L = np.array([-0.35, 0.45, 0.82])
            L /= np.linalg.norm(L)

            for idx in order:
                t = triangles[idx]
                v = verts[t]
                n = np.cross(v[1] - v[0], v[2] - v[0])
                norm_len = np.linalg.norm(n)
                if norm_len < 1e-6 or n[2] <= 0.05:
                    continue
                n /= norm_len
                diff = max(0.0, np.dot(n, L))
                shade = 0.60 + 0.40 * diff
                pts = np.array([[int(ox + p[0] * ppm), int(oy - p[1] * ppm)] for p in v], dtype=np.int32)

                z_mean = np.mean(v[:, 2])
                if z_mean >= 0.95:
                    c = card_base_rgb
                elif z_mean >= 0.45:
                    c = tuple(int(card_base_rgb[i] * 0.96) for i in range(3))
                elif z_mean >= -0.05:
                    c = tuple(int(card_base_rgb[i] * 0.90) for i in range(3))
                else:
                    white = (255, 255, 255)
                    if z_mean >= -0.25:
                        op = 0.92
                    elif z_mean >= -0.45:
                        op = 0.80
                    elif z_mean >= -0.65:
                        op = 0.65
                    elif z_mean >= -0.85:
                        op = 0.45
                    else:
                        op = 0.28
                    c = tuple(int(card_base_rgb[i] * op + white[i] * (1.0 - op)) for i in range(3))

                col_bgr = (int(c[2] * shade), int(c[1] * shade), int(c[0] * shade), 255)
                cv2.fillConvexPoly(card_img, pts, col_bgr, lineType=cv2.LINE_AA)

            pil_img = Image.fromarray(cv2.cvtColor(card_img, cv2.COLOR_BGRA2RGBA))
            rendered_from_mesh = True
        except Exception:
            pass

    if not rendered_from_mesh:
        pil_img = Image.new('RGBA', (W_px, H_px), (255, 255, 255, 0))
        d = ImageDraw.Draw(pil_img)
        x0 = int(ox - 37.5 * ppm)
        y0 = int(oy - 18.0 * ppm)
        x1 = int(ox + 37.5 * ppm)
        y1 = int(oy + 18.0 * ppm)
        border_col = (140, 140, 140, 180) if is_light else (220, 220, 220, 180)
        d.rounded_rectangle([x0, y0, x1, y1], radius=int(4.0 * ppm), fill=(*card_base_rgb, 255), outline=border_col, width=int(0.4*ppm))
        px0 = int(ox + (-6.3 - 40.4/2) * ppm)
        py0 = int(oy - 15.2 * ppm)
        px1 = int(ox + (-6.3 + 40.4/2) * ppm)
        py1 = int(oy + 15.2 * ppm)
        pocket_fill = tuple(int(card_base_rgb[i] * 0.96) for i in range(3))
        d.rounded_rectangle([px0, py0, px1, py1], radius=int(2.0*ppm), fill=(*pocket_fill, 255), outline=border_col, width=int(0.4*ppm))

    # Cut out lanyard slot hole cleanly: X in [-34.5, -28.5], Y in [-13.0, 13.0]
    sx0 = int(ox - 34.5 * ppm)
    sy0 = int(oy - 13.0 * ppm)
    sx1 = int(ox - 28.5 * ppm)
    sy1 = int(oy + 13.0 * ppm)
    sr = int(3.0 * ppm)
    
    hole_mask = Image.new('L', pil_img.size, 255)
    h_draw = ImageDraw.Draw(hole_mask)
    h_draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=sr, fill=0)
    
    r, g, b, a = pil_img.split()
    a = Image.fromarray(np.minimum(np.array(a), np.array(hole_mask)))
    pil_img = Image.merge('RGBA', (r, g, b, a))

    draw = ImageDraw.Draw(pil_img)
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=sr, outline=(185, 180, 172, 220), width=int(0.35 * ppm))

    # Clean number strip (.8, .6, .4, .2, .1)
    ns_x0 = int(ox + 15.5 * ppm)
    ns_x1 = int(ox + 21.5 * ppm)
    ns_y0 = int(oy - 15.0 * ppm)
    ns_y1 = int(oy + 15.0 * ppm)
    strip_fill = tuple(int(card_base_rgb[i] * 0.92) for i in range(3))
    draw.rectangle([ns_x0, ns_y0, ns_x1, ns_y1], fill=(*strip_fill, 255))
    line_col = (110, 110, 110, 160) if is_light else (210, 210, 210, 160)
    draw.line([ns_x0, ns_y0, ns_x0, ns_y1], fill=line_col, width=1)
    draw.line([ns_x1, ns_y0, ns_x1, ns_y1], fill=line_col, width=1)

    num_x = int(ox + 18.5 * ppm)
    step_ys = [12.0, 6.0, 0.0, -6.0, -12.0]
    step_labels = ['.8', '.6', '.4', '.2', '.1']
    try:
        font_num = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', int(3.2 * ppm))
    except Exception:
        font_num = ImageFont.load_default()

    num_col = (35, 35, 35, 240) if is_light else (245, 245, 245, 240)
    shadow_col = (255, 255, 255, 180) if is_light else (0, 0, 0, 180)
    for y_mm, label in zip(step_ys, step_labels):
        ny = int(oy - y_mm * ppm)
        draw.text((num_x + 1, ny + 1), label, font=font_num, fill=shadow_col, anchor='mm')
        draw.text((num_x, ny), label, font=font_num, fill=num_col, anchor='mm')

    for y_div in [9.0, 3.0, -3.0, -9.0]:
        dy = int(oy - y_div * ppm)
        step_x_start = int(ox + 21.5 * ppm)
        step_x_end = int(ox + 34.5 * ppm)
        draw.line([step_x_start, dy, step_x_end, dy], fill=line_col, width=1)

    # Composite pocket text and swatch
    font_path, font_idx = pick_font(None, 0)
    fr = TextRenderer(font_path, font_idx)
    args = ArgsWrapper(material=material, color=color, code=code, hex_val=hex_color, swatch_d=7.0,
                       base_hex=base_hex, text_hex=text_hex)
    raw_pocket, (sw_cx, sw_cy, sw_r) = build_layout(args, fr)

    px0 = int(ox + (-6.3 - 40.4/2) * ppm)
    py0 = int(oy - 15.2 * ppm)
    pw = int(40.4 * ppm)
    ph = int(30.4 * ppm)

    resized_pocket = cv2.resize(raw_pocket, (pw, ph), interpolation=cv2.INTER_AREA)

    for y in range(ph):
        for x in range(pw):
            alpha = resized_pocket[y, x]
            if alpha > 0:
                fg_a = alpha / 255.0
                curr = pil_img.getpixel((px0 + x, py0 + y))
                out_r = int(txt_rgb[0] * fg_a + curr[0] * (1 - fg_a))
                out_g = int(txt_rgb[1] * fg_a + curr[1] * (1 - fg_a))
                out_b = int(txt_rgb[2] * fg_a + curr[2] * (1 - fg_a))
                pil_img.putpixel((px0 + x, py0 + y), (out_r, out_g, out_b, 255))

    sw_px = int(ox + (-6.3 + sw_cx) * ppm)
    sw_py = int(oy - (0.0 + sw_cy) * ppm)
    sw_r_px = int(sw_r * ppm)
    sw_outline = (35, 35, 35, 180) if is_light else (235, 235, 235, 200)
    draw.ellipse([sw_px - sw_r_px, sw_py - sw_r_px, sw_px + sw_r_px, sw_py + sw_r_px],
                 fill=(*h_rgb, 255), outline=sw_outline, width=int(0.4 * ppm))

    # Drop shadow
    shadow_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    cx0 = int(ox - 37.5 * ppm)
    cy0 = int(oy - 18.0 * ppm)
    cx1 = int(ox + 37.5 * ppm)
    cy1 = int(oy + 18.0 * ppm)
    s_offset = int(1.2 * ppm)
    s_draw.rounded_rectangle([cx0 + s_offset, cy0 + s_offset, cx1 + s_offset, cy1 + s_offset],
                             radius=int(4.0 * ppm), fill=(0, 0, 0, 45))
    s_draw.rounded_rectangle([sx0 + s_offset, sy0 + s_offset, sx1 + s_offset, sy1 + s_offset],
                             radius=sr, fill=(0, 0, 0, 0))

    shadow_img.alpha_composite(pil_img)
    if out_path:
        shadow_img.save(out_path)
    return shadow_img


def generate_card(material, color, code, hex_color, relief=0.5, out_path=None,
                  template_path=DEFAULT_TEMPLATE, thicken=False, min_stroke=0.8,
                  min_gap=0.5, swatch_d=7.0, font_path=None, font_index=0,
                  preview=False, base_hex=None, text_hex=None):
    """Generate 3MF filament card and optional preview PNG. Returns metadata dict."""
    hex_color = normalize_hex(hex_color)
    base_hex = normalize_hex(base_hex) if base_hex else hex_color
    text_hex = normalize_hex(text_hex) if text_hex else auto_contrast_color(base_hex)
    if relief < 0.2:
        raise ValueError("relief must be >= 0.2 mm")

    out = out_path or os.path.join(
        os.getcwd(), "耗材样本卡_%s.3mf" % re.sub(r'[\\/:*?"<>|\s]+', "_", color).strip("_"))

    font_path, font_index = pick_font(font_path, font_index)
    fr = TextRenderer(font_path, font_index)

    args = ArgsWrapper(material=material, color=color, code=code, hex_val=hex_color,
                       relief=relief, swatch_d=swatch_d, template=template_path,
                       thicken=thicken, min_stroke=min_stroke, min_gap=min_gap,
                       base_hex=base_hex, text_hex=text_hex)
    raw, (sw_cx, sw_cy, sw_r) = build_layout(args, fr)

    if thicken:
        before = stroke_report(raw, min_stroke)
        dark = enforce_min_feature(raw, min_stroke, min_gap)
        after = stroke_report(dark, min_stroke)
    else:
        dark = raw
        before = stroke_report(raw, 0.4)
        after = before

    z0 = POCKET_FLOOR_Z
    z1 = POCKET_FLOOR_Z + relief
    text_polys = mask_to_polygons(dark)
    Vt, Tt = extrude(text_polys, z0, z1, POCKET_CX, POCKET_CY)
    Vs, Ts = extrude(circle_poly(sw_cx, sw_cy, sw_r), z0, z1, POCKET_CX, POCKET_CY)
    bad = check_watertight(Tt) + check_watertight(Ts)

    write_3mf(template_path, out, (Vt, Tt), (Vs, Ts), hex_color, base_hex=base_hex, text_hex=text_hex)

    preview_path = None
    if preview:
        preview_path = os.path.splitext(out)[0] + "_preview.png"
        render_full_card(material, color, code, hex_color, out_path=preview_path, base_hex=base_hex, text_hex=text_hex)

    return {
        "out_path": out,
        "preview_path": preview_path,
        "font_name": os.path.basename(font_path),
        "font_index": font_index,
        "relief": relief,
        "top_z": z1 + 1.0,
        "thinnest_stroke_before": before,
        "thinnest_stroke_after": after,
        "text_islands": len(text_polys),
        "triangles": len(Tt),
        "open_edges": bad,
        "warnings": fr.warnings,
        "hex": hex_color,
        "base_hex": base_hex,
        "text_hex": text_hex,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("material", help="材料类型, e.g. 'PLA MATTE'")
    ap.add_argument("color", help="颜色名, e.g. 'Iridium Gold'")
    ap.add_argument("code", help="编号, e.g. '(13008)'")
    ap.add_argument("hex", help="HEX色号, e.g. '#A2D312'")
    ap.add_argument("relief", nargs="?", type=float, default=0.5,
                    help="浮雕高度 mm above pocket floor (default 0.5 = flush with card top; 1.2 = raised)")
    ap.add_argument("-o", "--out", help="output .3mf (default: 耗材样本卡_<颜色名>.3mf)")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--base-hex", default=None, help="卡片底座HEX色号 (default: 同选中的耗材HEX色号)")
    ap.add_argument("--text-hex", default=None, help="文字HEX色号 (default: 自动计算黑/白高对比度)")
    ap.add_argument("--thicken", action="store_true",
                    help="启用细笔画形态学加粗 (默认关闭，直接使用平整平滑的字体原生外形)")
    ap.add_argument("--min-stroke", type=float, default=0.8,
                    help="笔画最小宽度 mm (配合 --thicken 使用, default 0.8)")
    ap.add_argument("--min-gap", type=float, default=0.5,
                    help="笔画间最小间隙 mm (配合 --thicken 使用, default 0.5)")
    ap.add_argument("--swatch-d", type=float, default=7.0, help="colour swatch diameter mm")
    ap.add_argument("--font", help="font file (TTF/TTC/OTF)")
    ap.add_argument("--font-index", type=int, default=0, help="face index inside a .ttc")
    ap.add_argument("--preview", action="store_true", help="also write a PNG preview of the relief")
    args = ap.parse_args()

    info = generate_card(
        material=args.material,
        color=args.color,
        code=args.code,
        hex_color=args.hex,
        relief=args.relief,
        out_path=args.out,
        template_path=args.template,
        thicken=args.thicken,
        min_stroke=args.min_stroke,
        min_gap=args.min_gap,
        swatch_d=args.swatch_d,
        font_path=args.font,
        font_index=args.font_index,
        preview=args.preview,
        base_hex=args.base_hex,
        text_hex=args.text_hex,
    )

    print(f"✅ {info['out_path']}")
    print(f"   font: {info['font_name']}[{info['font_index']}]  relief: {info['relief']} mm "
          f"(top at {info['top_z']:.2f} mm, card top 2.00 mm)")
    print(f"   filaments (3 slots): [1] Base {info['base_hex']}  [2] Text {info['text_hex']}  [3] Swatch {info['hex']}")
    if args.thicken:
        print(f"   thinnest stroke: {info['thinnest_stroke_before']:.2f} mm -> {info['thinnest_stroke_after']:.2f} mm (target {args.min_stroke}, thickened)")
    else:
        print(f"   thinnest stroke: {info['thinnest_stroke_before']:.2f} mm (native font outline)")
    print(f"   text: {info['text_islands']} islands, {info['triangles']} triangles; swatch {info['hex']}; "
          f"open edges: {info['open_edges']}")
    for w in info['warnings']:
        print("   ⚠️ ", w)


if __name__ == "__main__":
    main()

