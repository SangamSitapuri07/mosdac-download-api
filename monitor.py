#!/usr/bin/env python3
"""
MOSDAC LIVE MONITOR - chalta rahega aur dashboard ko khud-ba-khud update karta rahega.

    python monitor.py --once                      # ek baar chalao (test)
    python monitor.py --interval 30               # har 30 min me naya data lao
    python monitor.py --interval 30 --hours 24    # pichhle 24 ghante ka data
    python monitor.py --interval 30 --gif         # din bhar ki animation bhi banao

Dashboard: out/dashboard.html  (browser me kholo - ye khud refresh bhi hota hai)
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mosdac_client import Mosdac, MosdacError  # noqa: E402
from toolkit import (REGIONS, crop, make_map, parse_h5, stats_of,  # noqa: E402
                     to_celsius)

OUT = Path("out")
STATE = OUT / "state.json"
DATA = Path("data")


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"files": {}}


def save_state(s):
    OUT.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _acq_time(meta):
    """Acquisition_Start_Time = '01-SEP-2026T06:45:43' -> datetime"""
    for k in ("Acquisition_Start_Time", "Acquisition_Time_in_GMT", "Acquisition_Date"):
        v = meta.get(k)
        if not v:
            continue
        v = str(v)
        for fmt in ("%d-%b-%YT%H:%M:%S", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(v, fmt)
            except Exception:
                continue
    return None


def process_file(client, name, rec_id, region_bbox, var=None, kelvin=False, src_path=None):
    """Download (ya cache se) + parse + stats. Returns dict."""
    DATA.mkdir(exist_ok=True)
    cached = Path(src_path) if src_path else (DATA / name)
    if not (cached.exists() and cached.stat().st_size > 1000):
        if client is None:
            return None
        blob = client.download_bytes(rec_id)
        cached.write_bytes(blob)
    p = parse_h5(str(cached), var_pref=var)
    if "error" in p:
        return None
    if not kelvin:
        to_celsius(p)
    crop(p, region_bbox)
    st = stats_of(p["data"])
    t = _acq_time(p["meta"])
    png = make_map(p, f"{name}\n{p['meta'].get('Satellite_Name','')} "
                      f"{p['meta'].get('Acquisition_Start_Time','')}",
                   OUT / f"{Path(name).stem}_map.png")
    return {"name": name, "time": t.isoformat() if t else "",
            "stats": st, "units": p["units"], "var": p["var_name"],
            "png": str(png), "sat": p["meta"].get("Satellite_Name", "")}


def make_timeseries(entries, out_png):
    """Mean SST ka time-series graph."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = [(e["time"], e["stats"].get("mean")) for e in entries
           if e.get("time") and e["stats"].get("mean") is not None]
    pts.sort()
    if len(pts) < 2:
        return None
    xs = [datetime.fromisoformat(t) for t, _ in pts]
    ys = [v for _, v in pts]
    fig, ax = plt.subplots(figsize=(10, 3.4), dpi=110)
    ax.plot(xs, ys, marker="o", linewidth=2, color="#38bdf8", markersize=5)
    ax.set_facecolor("#111c31")
    fig.patch.set_facecolor("#111c31")
    ax.set_ylabel(f"Mean SST ({entries[0]['units']})", color="#cbd5e1", fontsize=9)
    ax.set_xlabel("Time (UTC)", color="#cbd5e1", fontsize=9)
    ax.grid(alpha=0.25, linestyle="--", linewidth=0.5, color="#64748b")
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#334155")
    ax.set_title("Mean SST over region", color="#e2e8f0", fontsize=11)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    return out_png


def make_gif(entries, out_gif, fps=4):
    """Din bhar ke maps se animation."""
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow nahi hai - pip install pillow)")
        return None
    imgs = [Image.open(e["png"]).convert("RGB") for e in entries if Path(e["png"]).exists()]
    if len(imgs) < 2:
        return None
    w, h = imgs[0].size
    imgs = [im.resize((w // 2, h // 2)) for im in imgs]
    imgs[0].save(out_gif, save_all=True, append_images=imgs[1:],
                 duration=int(1000 / fps), loop=0)
    return out_gif


def build_dashboard(entries, meta, refresh_sec, gif=None, ts=None, live=True):
    b64 = lambda p: base64.b64encode(Path(p).read_bytes()).decode() if p and Path(p).exists() else ""
    latest = entries[-1] if entries else None

    latest_card = ""
    if latest:
        s = latest["stats"]
        latest_card = f"""
        <div class="card big">
          <h3>LATEST: {latest['name']}</h3>
          <div class="tags"><span>{latest['sat']}</span><span>{latest['time']}</span>
          <span>{latest['var']}</span></div>
          <img src="data:image/png;base64,{b64(latest['png'])}">
          <table>
            <tr><th>Valid pixels</th><td>{s.get('valid',0):,} ({s.get('coverage_pct')}%)</td></tr>
            <tr><th>Min / Max</th><td>{s.get('min'):.2f} / {s.get('max'):.2f} {latest['units']}</td></tr>
            <tr><th>Mean / Median</th><td>{s.get('mean'):.2f} / {s.get('median'):.2f} {latest['units']}</td></tr>
            <tr><th>Std</th><td>{s.get('std'):.2f}</td></tr>
          </table>
        </div>"""

    ts_html = f'<div class="card big"><h3>Time series</h3><img src="data:image/png;base64,{b64(ts)}"></div>' if ts else ""
    gif_html = f'<div class="card big"><h3>Animation (din bhar)</h3><img src="data:image/gif;base64,{b64(gif)}"></div>' if gif else ""

    rows = "".join(
        f"<tr><td>{e['name'][:38]}</td><td>{e['time'][:19]}</td>"
        f"<td>{e['stats'].get('mean'):.2f}</td><td>{e['stats'].get('min'):.2f}</td>"
        f"<td>{e['stats'].get('max'):.2f}</td><td>{e['stats'].get('valid',0):,}</td></tr>"
        for e in reversed(entries[-40:]))

    refresh_meta = (f'<meta http-equiv="refresh" content="{refresh_sec}">'
                    if refresh_sec else "")
    badge = ("LIVE - monitor.py chal raha hai, naya data aate hi update hoga"
             if live else "STATIC SNAPSHOT - ek baar banaya gaya, update nahi hoga")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
{refresh_meta}
<title>MOSDAC Live Monitor</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
header{{background:#1e293b;padding:16px 24px;border-bottom:1px solid #334155}}
h1{{margin:0;font-size:20px}}.sub{{color:#94a3b8;font-size:13px;margin-top:5px}}
.live{{display:inline-block;width:9px;height:9px;background:#22c55e;border-radius:50%;
margin-right:6px;animation:p 1.6s infinite}}@keyframes p{{50%{{opacity:.25}}}}
.wrap{{padding:18px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.card.big{{grid-column:1/-1}}
h3{{margin:0 0 8px;font-size:14px;color:#7dd3fc;word-break:break-all}}
.tags span{{display:inline-block;background:#0ea5e933;color:#7dd3fc;font-size:11px;
padding:2px 8px;border-radius:10px;margin:0 6px 8px 0}}
img{{width:100%;border-radius:6px;background:#0b1120}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:12.5px}}
th{{text-align:left;color:#94a3b8;padding:4px 6px;border-bottom:1px solid #334155}}
td{{padding:4px 6px;border-bottom:1px solid #263244}}
footer{{padding:12px 24px;color:#64748b;font-size:12px}}
</style></head><body>
<header><h1><span class="live"></span>MOSDAC Live SST Monitor</h1>
<div class="sub">dataset {meta['dataset']} | region {meta['region']} | {len(entries)} files |
last updated {meta['now']}</div>
<div class="sub">{badge}</div></header>
<div class="wrap">{latest_card}{ts_html}{gif_html}
<div class="card big"><h3>All files (naye upar)</h3>
<table><tr><th>File</th><th>Time (UTC)</th><th>Mean</th><th>Min</th><th>Max</th><th>Valid px</th></tr>
{rows}</table></div></div>
<footer>MOSDAC Data Download API - INSAT-3DR L2B SST - monitor.py</footer>
</body></html>"""
    OUT.mkdir(exist_ok=True)
    path = OUT / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="3RIMG_L2B_SST")
    ap.add_argument("--hours", type=int, default=24, help="kitne ghante pichhe tak dekhein")
    ap.add_argument("--interval", type=int, default=30, help="kitne minute me dobara check karein")
    ap.add_argument("--region", default="india", choices=list(REGIONS.keys()))
    ap.add_argument("--var", default=None)
    ap.add_argument("--kelvin", action="store_true")
    ap.add_argument("--gif", action="store_true", help="animation bhi banayein")
    ap.add_argument("--once", action="store_true", help="ek hi baar chalao")
    ap.add_argument("--local", default=None, help="API call kiye bina local files se banayein")
    ap.add_argument("--limit", type=int, default=60, help="max kitne files process karein")
    a = ap.parse_args()

    bbox = REGIONS[a.region]
    OUT.mkdir(exist_ok=True)
    state = load_state()

    cycle = 0
    while True:
        cycle += 1
        now = datetime.now(timezone.utc)
        print(f"\n===== cycle {cycle} | {now.strftime('%Y-%m-%d %H:%M UTC')} =====")
        client = None

        if a.local:
            p = Path(a.local)
            files = sorted((p.rglob("*.h5") if p.is_dir() else [p]))[: a.limit]
            for f in files:
                if f.name in state["files"]:
                    continue
                print(f"  parsing {f.name}")
                try:
                    r = process_file(None, f.name, None, bbox, a.var, a.kelvin, src_path=str(f))
                    if r:
                        state["files"][f.name] = r
                except Exception as e:
                    print(f"    fail: {type(e).__name__}: {e}")
        else:
            start = (now - timedelta(hours=a.hours)).strftime("%Y-%m-%d")
            end = now.strftime("%Y-%m-%d")
            try:
                client = Mosdac()
                res = client.search(a.dataset, start, end, count=100)
                ents = (res["entries"] or [])[-a.limit:]
                new = [e for e in ents if e["identifier"] not in state["files"]]
                print(f"  {len(ents)} files mile, {len(new)} naye")
                if new:
                    client.login(retries=4)
                    for e in new:
                        print(f"  new -> {e['identifier']}")
                        try:
                            r = process_file(client, e["identifier"], e["id"], bbox, a.var, a.kelvin)
                            if r:
                                state["files"][r["name"]] = r
                        except Exception as ex:
                            print(f"    fail: {type(ex).__name__}: {ex}")
                    client.logout()
            except MosdacError as e:
                print(f"  [SKIP] {e}")

        save_state(state)
        entries = sorted(state["files"].values(), key=lambda x: x.get("time", ""))
        if not entries:
            print("  abhi koi data nahi.")
        else:
            ts = make_timeseries(entries, OUT / "timeseries.png")
            gif = make_gif(entries, OUT / "animation.gif") if a.gif else None
            meta = {"dataset": a.dataset, "region": a.region,
                    "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            refresh = 0 if a.once else max(60, a.interval * 60 // 2)
            path = build_dashboard(entries, meta, refresh, gif, ts, live=not a.once)
            print(f"  dashboard: {path}")
            print(f"  latest   : {entries[-1]['name']} "
                  f"mean={entries[-1]['stats'].get('mean'):.2f}{entries[-1]['units']}")

        if a.once:
            break
        print(f"  agla check {a.interval} min baad... (Ctrl+C se roko)")
        try:
            time.sleep(a.interval * 60)
        except KeyboardInterrupt:
            print("\nband kiya."); break
    return 0


if __name__ == "__main__":
    sys.exit(main())
