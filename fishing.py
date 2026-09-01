#!/usr/bin/env python3
"""
MOSDAC FISHING ADVISORY - interactive map: click karo, jano "wahan jana chahiye ya nahi".

Logic (INCOIS PFZ jaisa, simplified):
  * THERMAL FRONT  : SST gradient zyada -> machhliyan wahan jama hoti hain  (50 points)
  * SST RANGE      : 26-30 °C Indian waters ke liye best                    (50 points)
  Score 0-100 -> 70+ "jao", 50-70 "theek", 30-50 "shayad", <30 "mat jao"

    python fishing.py --local data --region india
    python fishing.py --local data --region indian-ocean
    python fishing.py --start 2026-09-01 --end 2026-09-01 --max 1

Output: out/fishing.html   <-- browser me kholo, map pe CLICK karo
"""

import argparse
import base64
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mosdac_client import Mosdac, MosdacError  # noqa: E402
from toolkit import REGIONS, crop, parse_h5, to_celsius  # noqa: E402

OUT = Path("out")
DATA = Path("data")

VERDICTS = [
    (70, "#22c55e", "✅ BAHUT ACCHA - yahan jao"),
    (55, "#84cc16", "👍 THEEK HAI - jaa sakte ho"),
    (40, "#eab308", "🤔 SHAYAD - himmat hai to jao"),
    (0,  "#ef4444", "❌ MAT JAO - bekaar jagah"),
]


def verdict(score):
    for thr, col, txt in VERDICTS:
        if score >= thr:
            return col, txt
    return VERDICTS[-1][1], VERDICTS[-1][2]


def gradient_km(data, lat, lon):
    """SST gradient in °C/km (thermal front strength)."""
    if lat is None or lon is None or lat.shape != data.shape:
        gy, gx = np.gradient(np.nan_to_num(data))
        return np.sqrt(gx ** 2 + gy ** 2)

    ny, nx = data.shape
    # pixel size in km (approx)
    dlat = float(np.nanmean(np.abs(np.diff(lat, axis=0)))) or 0.05
    dlon = float(np.nanmean(np.abs(np.diff(lon, axis=1)))) or 0.05
    latm = np.nanmean(lat)
    dy_km = dlat * 111.0
    dx_km = dlon * 111.0 * math.cos(math.radians(latm))
    d = np.where(np.isfinite(data), data, np.nan)
    gy, gx = np.gradient(d)
    return np.sqrt((gx / max(dx_km, 1e-6)) ** 2 + (gy / max(dy_km, 1e-6)) ** 2)


def fishing_score(sst_c, grad):
    """0-100 score from SST + front strength."""
    front = np.clip(grad / 0.05, 0, 1) * 45.0          # 0.05 °C/km = strong front
    opt = np.exp(-(((sst_c - 28.0) / 3.2) ** 2)) * 40.0  # 28 °C ke aas-paas best
    suit = np.clip((30.0 - np.abs(sst_c - 28.5)) / 6.0, 0, 1) * 15.0
    score = front + opt + suit
    score = np.where(np.isfinite(sst_c), score, np.nan)
    return np.clip(score, 0, 100)


def render(data, lat, lon, title, out_png, cmap="turbo", label="", vmin=None, vmax=None,
           contours=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    step = max(1, int(max(data.shape) / 800) + 1)
    d = data[::step, ::step]
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=105)
    if lat is not None and lon is not None and lat.shape == data.shape:
        la, lo = lat[::step, ::step], lon[::step, ::step]
        ok = np.isfinite(d) & np.isfinite(la) & np.isfinite(lo)
        pm = ax.pcolormesh(np.where(ok, lo, 0.0), np.where(ok, la, 0.0),
                           np.where(ok, d, np.nan), cmap=cmap, shading="auto",
                           vmin=vmin, vmax=vmax)
        if contours is not None:
            c = contours[::step, ::step]
            try:
                ax.contour(np.where(ok, lo, 0.0), np.where(ok, la, 0.0),
                           np.where(ok, c, np.nan), levels=6, colors="k",
                           linewidths=0.4, alpha=0.5)
            except Exception:
                pass
    else:
        pm = ax.imshow(d, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
    ax.set_facecolor("#c9d4e0")
    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.set_title(title, fontsize=12)
    cb = fig.colorbar(pm, ax=ax, pad=0.02); cb.set_label(label)
    fig.tight_layout(); fig.savefig(out_png, dpi=105, bbox_inches="tight"); plt.close(fig)
    return out_png


def top_spots(score, sst, grad, lat, lon, n=10, block=40):
    """Sabse best fishing spots (block-wise maxima)."""
    if lat is None or lon is None:
        return []
    ny, nx = score.shape
    out = []
    for i in range(0, ny - block, block):
        for j in range(0, nx - block, block):
            blk = score[i:i + block, j:j + block]
            if not np.isfinite(blk).any():
                continue
            idx = np.nanargmax(blk)
            r, c = np.unravel_index(idx, blk.shape)
            ri, ci = i + r, j + c
            s = float(score[ri, ci])
            if not np.isfinite(s) or s < 35:
                continue
            out.append({
                "lat": round(float(lat[ri, ci]), 3),
                "lon": round(float(lon[ri, ci]), 3),
                "score": round(s, 1),
                "sst": round(float(sst[ri, ci]), 2) if np.isfinite(sst[ri, ci]) else None,
                "front": round(float(grad[ri, ci]), 4) if np.isfinite(grad[ri, ci]) else None,
            })
    out.sort(key=lambda x: -x["score"])
    seen, uniq = set(), []
    for o in out:
        key = (round(o["lat"]), round(o["lon"]))
        if key in seen:
            continue
        seen.add(key); uniq.append(o)
    return uniq[:n]


def downsample(arr, maxn=180):
    sh = arr.shape
    step = max(1, int(max(sh) / maxn) + 1)
    return arr[::step, ::step], step


def build_html(maps, grids, spots, meta, out_html):
    b64 = lambda p: base64.b64encode(Path(p).read_bytes()).decode() if Path(p).exists() else ""

    def enc(a):
        a = np.where(np.isfinite(a), a, np.nan)
        r = [[None if not np.isfinite(v) else round(float(v), 3) for v in row] for row in a]
        return json.dumps(r, separators=(",", ":"))

    sst_png, score_png = maps
    g = grids
    spot_rows = "".join(
        f"<tr><td>{i+1}</td><td>{s['lat']:.3f}°N, {s['lon']:.3f}°E</td>"
        f"<td><b style='color:{verdict(s['score'])[0]}'>{s['score']:.0f}</b></td>"
        f"<td>{s['sst'] if s['sst'] is not None else '-'} °C</td>"
        f"<td>{s['front'] if s['front'] is not None else '-'}</td>"
        f"<td>{verdict(s['score'])[1]}</td></tr>"
        for i, s in enumerate(spots))

    name_u = str(meta['source']).upper()
    synth = ("DEMO" in name_u) or ("TEST" in name_u) or ("FAKE" in name_u)
    badge = ("<span style='background:#ef444433;color:#ef4444;padding:2px 9px;border-radius:10px;"
             "font-size:12px;font-weight:700'>NAKLI (DEMO) DATA - test ke liye</span>"
             if synth else
             "<span style='background:#22c55e33;color:#22c55e;padding:2px 9px;border-radius:10px;"
             "font-size:12px;font-weight:700'>ASLI DATA - MOSDAC/INSAT-3DR</span>")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MOSDAC Fishing Advisory</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
header{{background:#1e293b;padding:16px 24px;border-bottom:1px solid #334155}}
h1{{margin:0;font-size:20px}}.sub{{color:#94a3b8;font-size:13px;margin-top:5px}}
.wrap{{padding:18px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.card.big{{grid-column:1/-1}}
h3{{margin:0 0 10px;font-size:14px;color:#7dd3fc}}
.mapbox{{position:relative;display:inline-block;width:100%}}
img{{width:100%;border-radius:6px;display:block;cursor:crosshair}}
#tip{{position:absolute;pointer-events:none;background:#0b1120ee;border:1px solid #38bdf8;
border-radius:6px;padding:6px 9px;font-size:12px;white-space:nowrap;display:none;z-index:9}}
#pin{{position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border:3px solid #f43f5e;
border-radius:50%;display:none;z-index:8}}
.btns button{{background:#0ea5e9;border:0;color:#04202e;font-weight:600;padding:7px 14px;
border-radius:6px;cursor:pointer;margin:0 6px 10px 0}}
.btns button.off{{background:#334155;color:#cbd5e1}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}
th{{text-align:left;color:#94a3b8;padding:5px 6px;border-bottom:1px solid #334155}}
td{{padding:5px 6px;border-bottom:1px solid #263244}}
#detail{{min-height:96px;font-size:13.5px;line-height:1.7}}
.tag{{display:inline-block;padding:2px 9px;border-radius:10px;font-size:12px;font-weight:600}}
footer{{padding:12px 24px;color:#64748b;font-size:12px}}
</style></head><body>
<header><h1>MOSDAC Fishing Advisory</h1>
<div class="sub">{badge} &nbsp; file: <b>{meta['source']}</b> | region {meta['region']} | acq: {meta['time']}</div>
<div class="sub">Map pe <b>click</b> karo - us jagah ka SST, thermal front aur "jana chahiye ya nahi" milega</div>
</header>
<div class="wrap">
<div class="card big">
  <div class="btns">
    <button id="b0" onclick="show(0)">🌡️ SST (°C)</button>
    <button id="b1" class="off" onclick="show(1)">🎣 Fishing Score</button>
  </div>
  <div class="mapbox">
    <img id="img0" src="data:image/png;base64,{b64(sst_png)}">
    <img id="img1" src="data:image/png;base64,{b64(score_png)}" style="display:none">
    <div id="pin"></div><div id="tip"></div>
  </div>
  <div id="detail" style="margin-top:12px"><i>Map pe click karo...</i></div>
</div>
<div class="card big"><h3>🏆 Top fishing spots (best 10)</h3>
<table><tr><th>#</th><th>Location (lat, lon)</th><th>Score</th><th>SST</th>
<th>Front °C/km</th><th>Verdict</th></tr>{spot_rows}</table></div>
<div class="card"><h3>📖 Score kaise banta hai</h3>
<table>
<tr><th>Thermal front (45)</th><td>SST gradient 0.05 °C/km ya usse zyada = strong front</td></tr>
<tr><th>SST optimum (40)</th><td>28 °C ke aas-paas sabse best (Indian waters)</td></tr>
<tr><th>Suitability (15)</th><td>26.5-30.5 °C range</td></tr>
<tr><th>70-100</th><td><span class="tag" style="background:#22c55e33;color:#22c55e">JAO</span></td></tr>
<tr><th>55-70</th><td><span class="tag" style="background:#84cc1633;color:#84cc16">THEEK</span></td></tr>
<tr><th>40-55</th><td><span class="tag" style="background:#eab30833;color:#eab308">SHAYAD</span></td></tr>
<tr><th>&lt; 40</th><td><span class="tag" style="background:#ef444433;color:#ef4444">MAT JAO</span></td></tr>
</table></div>
</div>
<footer>MOSDAC / INSAT-3DR L2B SST - fishing.py | Yeh advisory satellite data par adharit hai,
hamesha local weather aur coast guard ke notice bhi check karein.</footer>
<script>
const LAT={enc(g['lat'])}, LON={enc(g['lon'])}, SST={enc(g['sst'])},
      GRAD={enc(g['grad'])}, SCORE={enc(g['score'])};
const NY=LAT.length, NX=LAT[0].length;
const BB={json.dumps(meta['bbox'])};
const imgs=[document.getElementById('img0'),document.getElementById('img1')];
let cur=0;
function show(k){{cur=k;imgs[0].style.display=k===0?'block':'none';
 imgs[1].style.display=k===1?'block':'none';
 document.getElementById('b0').className=k===0?'':'off';
 document.getElementById('b1').className=k===1?'':'off';}}
function vd(s){{if(s>=70)return['#22c55e','✅ BAHUT ACCHA - yahan jao'];
 if(s>=55)return['#84cc16','👍 THEEK HAI - jaa sakte ho'];
 if(s>=40)return['#eab308','🤔 SHAYAD - himmat hai to jao'];
 return['#ef4444','❌ MAT JAO - bekaar jagah'];}}
function pick(e,rect){{
 const x=(e.clientX-rect.left)/rect.width, y=(e.clientY-rect.top)/rect.height;
 let j=Math.round(x*(NX-1)), i=Math.round(y*(NY-1));
 i=Math.max(0,Math.min(NY-1,i)); j=Math.max(0,Math.min(NX-1,j)); return [i,j];}}
function tip(e){{
 const img=imgs[cur], rect=img.getBoundingClientRect();
 const [i,j]=pick(e,rect);
 const sst=SST[i][j], gr=GRAD[i][j], sc=SCORE[i][j];
 const tip=document.getElementById('tip');
 if(sst===null||sst===undefined){{tip.style.display='none';return;}}
 const [c,txt]=vd(sc===null?0:sc);
 tip.innerHTML=`📍 ${{LAT[i][j].toFixed(2)}}°N, ${{LON[i][j].toFixed(2)}}°E<br>
   🌡️ SST <b>${{sst.toFixed(2)}} °C</b><br>〰️ Front ${{gr===null?'-':gr.toFixed(3)}} °C/km<br>
   🎯 Score <b style="color:${{c}}">${{(sc||0).toFixed(0)}}</b> - ${{txt}}`;
 tip.style.display='block';
 tip.style.left=Math.min(e.clientX-rect.left+12, rect.width-230)+'px';
 tip.style.top=(e.clientY-rect.top+14)+'px';}}
function click(e){{
 const img=imgs[cur], rect=img.getBoundingClientRect();
 const [i,j]=pick(e,rect);
 const sst=SST[i][j], gr=GRAD[i][j], sc=SCORE[i][j];
 if(sst===null||sst===undefined){{document.getElementById('detail').innerHTML=
   '<i>Yahan koi data nahi (zameen ya cloud)</i>';return;}}
 const [c,txt]=vd(sc||0);
 document.getElementById('detail').innerHTML=`
   <div style="font-size:15px"><b>${{LAT[i][j].toFixed(3)}}°N, ${{LON[i][j].toFixed(3)}}°E</b></div>
   <span class="tag" style="background:${{c}}33;color:${{c}}">${{txt}}</span>
   <table style="margin-top:10px">
   <tr><th>Sea Surface Temp</th><td><b>${{sst.toFixed(2)}} °C</b></td></tr>
   <tr><th>Thermal front</th><td>${{gr===null?'-':gr.toFixed(4)}} °C/km ${{(gr||0)>0.05?'<b>(strong front!)</b>':''}}</td></tr>
   <tr><th>Fishing score</th><td><b style="color:${{c}}">${{(sc||0).toFixed(0)}}/100</b></td></tr>
   <tr><th>Google Maps</th><td><a style="color:#38bdf8" target="_blank"
     href="https://www.google.com/maps?q=${{LAT[i][j].toFixed(4)}},${{LON[i][j].toFixed(4)}}">yahan kholo</a></td></tr>
   </table>`;
 const pin=document.getElementById('pin');
 pin.style.display='block';
 pin.style.left=((j/(NX-1))*rect.width)+'px';
 pin.style.top=((i/(NY-1))*rect.height)+'px';}}
imgs.forEach(im=>{{im.addEventListener('mousemove',tip);
 im.addEventListener('mouseleave',()=>document.getElementById('tip').style.display='none');
 im.addEventListener('click',click);}});
</script></body></html>"""
    OUT.mkdir(exist_ok=True)
    Path(out_html).write_text(html, encoding="utf-8")
    return out_html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="3RIMG_L2B_SST")
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--max", type=int, default=1)
    ap.add_argument("--local", default=None)
    ap.add_argument("--file", default=None, help="ek specific .h5 file")
    ap.add_argument("--region", default="indian-ocean", choices=list(REGIONS.keys()))
    ap.add_argument("--bbox", default=None)
    a = ap.parse_args()

    bbox = tuple(float(x) for x in a.bbox.split(",")) if a.bbox else REGIONS[a.region]
    OUT.mkdir(exist_ok=True)

    src = None
    if a.file:
        src = Path(a.file)
    elif a.local:
        p = Path(a.local)
        files = sorted(p.rglob("*.h5")) if p.is_dir() else [p]
        src = files[-1] if files else None
    else:
        m = Mosdac()
        res = m.search(a.dataset, a.start, a.end, count=a.max)
        ents = res["entries"] or []
        if not ents:
            print("koi file nahi mila"); return 1
        m.login(retries=4)
        DATA.mkdir(exist_ok=True)
        e = ents[0]
        cached = DATA / e["identifier"]
        if not cached.exists():
            cached.write_bytes(m.download_bytes(e["id"]))
        m.logout()
        src = cached

    if src is None or not Path(src).exists():
        print("file nahi mila:", src); return 1

    print(f"\n=== Fishing Advisory ===\n  file: {src.name}")
    p = parse_h5(str(src))
    if "error" in p:
        print(p["error"]); return 1
    to_celsius(p)
    crop(p, bbox)
    sst, lat, lon = p["data"], p.get("lat"), p.get("lon")

    grad = gradient_km(sst, lat, lon)
    score = fishing_score(sst, grad)

    print(f"  SST   : {np.nanmin(sst):.2f} - {np.nanmax(sst):.2f} °C "
          f"(valid {int(np.isfinite(sst).sum()):,} px)")
    print(f"  Front : max {np.nanmax(grad):.3f} °C/km")
    print(f"  Score : max {np.nanmax(score):.0f}/100")

    sst_png = render(sst, lat, lon, f"SST (°C) - {src.name}", OUT / "sst_map.png",
                     "turbo", "°C", vmin=24, vmax=32)
    score_png = render(score, lat, lon, "Fishing score (0-100)", OUT / "score_map.png",
                       "RdYlGn", "score", vmin=0, vmax=100)

    spots = top_spots(score, sst, grad, lat, lon)
    print(f"\n  Top spots:")
    for i, s in enumerate(spots[:5]):
        print(f"   {i+1}. {s['lat']:.2f}N, {s['lon']:.2f}E  score={s['score']:.0f}  "
              f"SST={s['sst']}°C  {verdict(s['score'])[1]}")

    _, step = downsample(sst)
    grids = {"lat": lat[::step, ::step] if lat is not None else None,
             "lon": lon[::step, ::step] if lon is not None else None,
             "sst": sst[::step, ::step], "grad": grad[::step, ::step],
             "score": score[::step, ::step]}

    html = build_html((sst_png, score_png), grids, spots,
                      {"source": src.name, "region": a.region, "bbox": list(bbox),
                       "time": p["meta"].get("Acquisition_Start_Time", "")},
                      OUT / "fishing.html")
    print(f"\n  ✅ {html}   <-- browser me kholo, map pe CLICK karo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
