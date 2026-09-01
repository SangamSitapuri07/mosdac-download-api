"""Reports: interactive HTML + PNG maps + CSV + Excel + JSON (sab real values)."""

import base64
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config as C, geo_tools as G, physics as P


# ---------------- maps ----------------
def _basemap(ax):
    for seg in G.coastline_segments():
        xs = [p[0] for p in seg]
        ys = [p[1] for p in seg]
        ax.plot(xs, ys, color="#0f172a", linewidth=0.5, alpha=0.85, zorder=3)
    for name, polys in G.eez_rings().items():
        main = (name == "India")
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.plot(xs, ys, color="#0891b2" if main else "#64748b",
                    linewidth=1.2 if main else 0.6,
                    linestyle="--" if main else ":",
                    alpha=0.95 if main else 0.45, zorder=4)


def make_map(data, lat, lon, title, out_png, cmap="turbo", label="",
             vmin=None, vmax=None, cfg=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7.6), dpi=105)
    if lat is not None and lon is not None and lat.shape == data.shape:
        ok = np.isfinite(data) & np.isfinite(lat) & np.isfinite(lon)
        pm = ax.pcolormesh(np.where(ok, lon, 0.0), np.where(ok, lat, 0.0),
                           np.where(ok, data, np.nan), cmap=cmap, shading="auto",
                           vmin=vmin, vmax=vmax)
    else:
        pm = ax.imshow(data, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)
    ax.set_facecolor("#dbe3ec")
    try:
        _basemap(ax)
    except Exception:
        pass
    bbox = (cfg or {}).get("region", {}).get("bbox")
    if bbox:
        ax.set_xlim(bbox[0], bbox[2]); ax.set_ylim(bbox[1], bbox[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    ax.grid(alpha=0.25, linestyle="--", linewidth=0.4)
    ax.set_title(title, fontsize=12)
    cb = fig.colorbar(pm, ax=ax, pad=0.02)
    cb.set_label(label)
    fig.tight_layout()
    fig.savefig(out_png, dpi=105, bbox_inches="tight")
    plt.close(fig)
    return str(out_png)


# ---------------- exports ----------------
def to_csv(lat, lon, sst, grad, wind, dist, eez, score, out_csv, step=3):
    rows = []
    ny, nx = score.shape
    for i in range(0, ny, step):
        for j in range(0, nx, step):
            s = score[i, j]
            if not np.isfinite(s):
                continue
            rows.append((
                round(float(lat[i, j]), 3), round(float(lon[i, j]), 3),
                None if sst is None or not np.isfinite(sst[i, j]) else round(float(sst[i, j]), 2),
                None if grad is None or not np.isfinite(grad[i, j]) else round(float(grad[i, j]), 4),
                None if wind is None or not np.isfinite(wind[i, j]) else round(float(wind[i, j]), 1),
                None if dist is None or not np.isfinite(dist[i, j]) else round(float(dist[i, j]), 0),
                bool(eez[i, j]) if eez is not None else None,
                round(float(s), 1)))
    try:
        import pandas as pd
        pd.DataFrame(rows, columns=["lat", "lon", "sst_c", "front_c_per_km",
                                    "wind_ms", "coast_km", "in_india_eez",
                                    "pfz_score"]).to_csv(out_csv, index=False)
    except ImportError:
        with open(out_csv, "w", encoding="utf-8") as fh:
            fh.write("lat,lon,sst_c,front_c_per_km,wind_ms,coast_km,in_india_eez,pfz_score\n")
            for r in rows:
                fh.write(",".join("" if v is None else str(v) for v in r) + "\n")
    return str(out_csv)


def to_excel(spots, summary, out_xlsx):
    try:
        import pandas as pd
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            pd.DataFrame(spots).to_excel(w, sheet_name="Top spots", index=False)
            pd.DataFrame(summary).to_excel(w, sheet_name="Sources", index=False)
        return str(out_xlsx)
    except Exception as e:
        print(f"  (Excel skip: {e})")
        return None


# ---------------- HTML ----------------
def _enc(a, step_cap=360):
    if a is None:
        return "null"
    sh = a.shape
    st = max(1, int(max(sh) / step_cap) + 1)
    b = a[::st, ::st]
    r = [[None if not np.isfinite(v) else round(float(v), 3) for v in row] for row in b]
    return json.dumps(r, separators=(",", ":"))


def build_html(maps, grids, spots, prov, cfg, out_html):
    b64 = lambda p: base64.b64encode(Path(p).read_bytes()).decode() if p and Path(p).exists() else ""
    sst_png, wind_png, pfz_png = maps

    rows = "".join(
        f"<tr><td>{i+1}</td>"
        f"<td><a class='gm' target='_blank' href='https://www.google.com/maps?q={s['lat']},{s['lon']}'>"
        f"{s['lat']:.3f}°N, {s['lon']:.3f}°E</a></td>"
        f"<td><b style='color:{P.verdict(s['score'], cfg)[1]}'>{s['score']:.0f}</b></td>"
        f"<td>{s['sst'] if s['sst'] is not None else '—'}</td>"
        f"<td>{s['wind'] if s['wind'] is not None else '—'}</td>"
        f"<td>{s['front'] if s['front'] is not None else '—'}</td>"
        f"<td>{int(s['coast_km']) if s['coast_km'] is not None else '—'}</td>"
        f"<td>{'🇮🇳 EEZ' if s['in_eez'] else ('bahar' if s['in_eez'] is False else '—')}</td>"
        f"<td style='color:{P.verdict(s['score'], cfg)[1]}'>{P.verdict(s['score'], cfg)[0]}</td></tr>"
        for i, s in enumerate(spots))

    prov_rows = "".join(
        f"<tr><td>{p['layer']}</td><td>{p['source']}</td><td>{p['dataset']}</td>"
        f"<td>{p['file']}</td><td>{p['time']}</td><td>{p['status']}</td></tr>"
        for p in prov)

    w = cfg["physics"]["weights"]
    eez_json = json.dumps(G.eez_rings(), separators=(",", ":"))

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MATSYA - Marine Fishing Advisory</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
header{{background:#1e293b;padding:18px 24px;border-bottom:1px solid #334155}}
h1{{margin:0;font-size:21px}}.sub{{color:#94a3b8;font-size:13px;margin-top:5px}}
.wrap{{padding:18px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.card.big{{grid-column:1/-1}}
h3{{margin:0 0 10px;font-size:14px;color:#7dd3fc}}
.mapbox{{position:relative;display:inline-block;width:100%}}
img{{width:100%;border-radius:6px;display:block;cursor:crosshair}}
#tip{{position:absolute;pointer-events:none;background:#0b1120f2;border:1px solid #38bdf8;
border-radius:6px;padding:7px 10px;font-size:12px;line-height:1.55;display:none;z-index:9}}
#pin{{position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border:3px solid #f43f5e;
border-radius:50%;display:none;z-index:8}}
.btns button{{background:#0ea5e9;border:0;color:#04202e;font-weight:600;padding:7px 13px;
border-radius:6px;cursor:pointer;margin:0 6px 10px 0}}
.btns button.off{{background:#334155;color:#cbd5e1}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:12.5px}}
th{{text-align:left;color:#94a3b8;padding:5px 6px;border-bottom:1px solid #334155}}
td{{padding:5px 6px;border-bottom:1px solid #263244}}
a.gm{{color:#38bdf8;text-decoration:none}}
#detail{{min-height:110px;font-size:13.5px;line-height:1.7}}
.ok{{color:#22c55e}}.bad{{color:#ef4444}}
footer{{padding:14px 24px;color:#64748b;font-size:12px}}
</style></head><body>
<header><h1>MATSYA — Real-Data Marine Fishing Advisory</h1>
<div class="sub">ISRO MOSDAC (INSAT-3DR) + MarineRegions EEZ + Natural Earth coastline
 — <b>100% real satellite &amp; geospatial data</b></div>
<div class="sub">Region: {cfg['region']['name']} {cfg['region']['bbox']} |
generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | files analysed: {len(prov)}</div>
</header>
<div class="wrap">
<div class="card big">
  <div class="btns">
    <button id="b0" onclick="show(0)">🌡️ SST (°C)</button>
    <button id="b1" class="off" onclick="show(1)">💨 Wind (m/s)</button>
    <button id="b2" class="off" onclick="show(2)">🎣 PFZ Score</button>
  </div>
  <div class="mapbox">
    <img id="i0" src="data:image/png;base64,{b64(sst_png)}">
    <img id="i1" src="data:image/png;base64,{b64(wind_png)}" style="display:none">
    <img id="i2" src="data:image/png;base64,{b64(pfz_png)}" style="display:none">
    <div id="pin"></div><div id="tip"></div>
  </div>
  <div id="detail" style="margin-top:12px"><i>Map pe click karo — us jagah ka poora analysis</i></div>
</div>

<div class="card big"><h3>Top fishing spots (real data se)</h3>
<table><tr><th>#</th><th>Location</th><th>Score</th><th>SST °C</th><th>Wind m/s</th>
<th>Front °C/km</th><th>Coast km</th><th>Zone</th><th>Verdict</th></tr>{rows}</table></div>

<div class="card big"><h3>Data provenance (kaunsa data, kahan se aaya)</h3>
<table><tr><th>Layer</th><th>Source</th><th>Dataset</th><th>File</th><th>Acquisition</th><th>Status</th></tr>
{prov_rows}</table></div>

<div class="card"><h3>Score kaise banta hai</h3>
<table>
<tr><th>Thermal front ({w['front']})</th><td>SST gradient, {cfg['physics']['front_ref_c_per_km']} °C/km = strong front</td></tr>
<tr><th>SST optimum ({w['sst']})</th><td>{cfg['physics']['sst_optimum_c']} °C ke aas-paas sabse best</td></tr>
<tr><th>EEZ ({w['eez']})</th><td>India EEZ ke andar = full marks, bahar = 15%</td></tr>
<tr><th>Shelf ({w['shelf']})</th><td>coast se {cfg['physics']['shelf_max_km']:.0f} km ke andar behtar</td></tr>
<tr><th>Wind ({w['wind']})</th><td>&lt;{cfg['physics']['wind_calm_ms']} m/s shant, &gt;{cfg['physics']['wind_danger_ms']} m/s khatra</td></tr>
</table></div>

<div class="card"><h3>Chetehavni / Disclaimer</h3>
<p style="font-size:13px;line-height:1.7;color:#cbd5e1">
Ye advisory <b>INSAT-3DR satellite SST + wind</b> aur <b>MarineRegions EEZ</b> par adharit hai.
Hamesha local weather forecast, Indian Coast Guard / INCOIS ke notices, monsoon fishing ban
(61 din) aur apni boat ki capacity zaroor check karein. Chlorophyll (OCM) is API me uplabdh
nahi hai — isliye PFZ score me shamil nahi (NOTES.md dekho).
</p></div>
</div>
<footer>MATSYA v1.0 • Data: ISRO/MOSDAC, MarineRegions (VLIZ, CC BY 4.0), Natural Earth (public domain)</footer>
<script>
const LAT={_enc(grids['lat'])},LON={_enc(grids['lon'])},SST={_enc(grids['sst'])},
 WIND={_enc(grids['wind'])},GRAD={_enc(grids['grad'])},PFZ={_enc(grids['score'])},DIST={_enc(grids['dist'])},
 EEZ={_enc(grids['eez'], 600)};
const RINGS={eez_json};
const imgs=[document.getElementById('i0'),document.getElementById('i1'),document.getElementById('i2')];
let cur=0;
function show(k){{cur=k;for(let i=0;i<3;i++){{imgs[i].style.display=(i===k)?'block':'none';
 document.getElementById('b'+i).className=(i===k)?'':'off';}}}}
function pip(pt,ring){{let c=false;
 for(let i=0,j=ring.length-1;i<ring.length;j=i++){{const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
  if(((yi>pt[1])!=(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c;}}return c;}}
function eezOf(lo,la){{for(const k in RINGS){{for(const poly of RINGS[k]){{if(pip([lo,la],poly[0]))return k;}}}}return null;}}
function vd(s){{if(!isFinite(s))return['NO DATA','#64748b'];
 if(s>=70)return['JAO - best zone','#22c55e'];if(s>=55)return['THEEK HAI','#84cc16'];
 if(s>=40)return['SHAYAD','#eab308'];return['MAT JAO','#ef4444'];}}
function cell(e,img){{const r=img.getBoundingClientRect();
 let j=Math.round((e.clientX-r.left)/r.width*(LAT[0].length-1));
 let i=Math.round((e.clientY-r.top)/r.height*(LAT.length-1));
 i=Math.max(0,Math.min(LAT.length-1,i));j=Math.max(0,Math.min(LAT[0].length-1,j));return[i,j];}}
function tip(e){{const img=imgs[cur];const[i,j]=cell(e,img);const s=SST[i][j];
 const t=document.getElementById('tip');
 if(s===null||s===undefined){{t.style.display='none';return;}}
 const[vt,vc]=vd(PFZ[i][j]||0);const zn=eezOf(LON[i][j],LAT[i][j]);
 t.innerHTML=`📍 ${{LAT[i][j].toFixed(2)}}°N, ${{LON[i][j].toFixed(2)}}°E<br>
  🌡️ SST <b>${{s.toFixed(2)}} °C</b><br>
  💨 Wind ${{WIND&&WIND[i][j]!==null?WIND[i][j].toFixed(1)+' m/s':'—'}}<br>
  🎯 PFZ <b style="color:${{vc}}">${{(PFZ[i][j]||0).toFixed(0)}}</b> — ${{vt}}<br>
  🗺️ ${{zn?zn+' EEZ':'International waters'}}`;
 t.style.display='block';
 t.style.left=Math.min(e.clientX-img.getBoundingClientRect().left+12,
   img.getBoundingClientRect().width-220)+'px';
 t.style.top=(e.clientY-img.getBoundingClientRect().top+14)+'px';}}
function click(e){{const img=imgs[cur];const[i,j]=cell(e,img);const s=SST[i][j];
 const d=document.getElementById('detail');
 if(s===null||s===undefined){{d.innerHTML='<i>Yahan data nahi (zameen / cloud / swath ke bahar)</i>';return;}}
 const[vt,vc]=vd(PFZ[i][j]||0);const zn=eezOf(LON[i][j],LAT[i][j]);
 const wm=(WIND&&WIND[i][j]!==null)?WIND[i][j]:null;
 d.innerHTML=`<div style="font-size:15px"><b>${{LAT[i][j].toFixed(3)}}°N, ${{LON[i][j].toFixed(3)}}°E</b></div>
 <span style="background:${{vc}}33;color:${{vc}};padding:2px 9px;border-radius:10px;font-weight:600">${{vt}}</span>
 <table style="margin-top:10px">
 <tr><th>Sea Surface Temp</th><td><b>${{s.toFixed(2)}} °C</b></td></tr>
 <tr><th>Thermal front</th><td>${{(GRAD&&GRAD[i][j]!==null)?GRAD[i][j].toFixed(3)+' °C/km':'—'}}</td></tr>
 <tr><th>Wind speed</th><td>${{wm!==null?wm.toFixed(1)+' m/s':'—'}}</td></tr>
 <tr><th>Coast se doori</th><td>${{(DIST&&DIST[i][j]!==null)?DIST[i][j].toFixed(0)+' km':'—'}}</td></tr>
 <tr><th>Zones</th><td><b>${{zn?zn+' EEZ':'International waters (High Seas)'}}</b></td></tr>
 <tr><th>PFZ score</th><td><b style="color:${{vc}}">${{(PFZ[i][j]||0).toFixed(0)}}/100</b></td></tr>
 <tr><th>Google Maps</th><td><a class="gm" target="_blank"
   href="https://www.google.com/maps?q=${{LAT[i][j].toFixed(4)}},${{LON[i][j].toFixed(4)}}">location kholo</a></td></tr>
 </table>`;
 const p=document.getElementById('pin');p.style.display='block';
 p.style.left=((j/(LAT[0].length-1))*img.getBoundingClientRect().width)+'px';
 p.style.top=((i/(LAT.length-1))*img.getBoundingClientRect().height)+'px';}}
imgs.forEach(im=>{{im.addEventListener('mousemove',tip);
 im.addEventListener('mouseleave',()=>document.getElementById('tip').style.display='none');
 im.addEventListener('click',click);}});
</script></body></html>"""
    Path(out_html).write_text(html, encoding="utf-8")
    return str(out_html)
