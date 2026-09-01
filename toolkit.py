#!/usr/bin/env python3
"""
MOSDAC DATA TOOLKIT - ek command me sab kuch.

API se data mangwata hai, .h5 padhta hai, aur bana deta hai:
  * Map images (PNG)           out/*_map.png
  * CSV (lat, lon, value)      out/data.csv
  * Excel                      out/data.xlsx
  * HTML dashboard             out/dashboard.html   <-- browser me kholo

Usage:
    python toolkit.py                                   # aaj ka din, 3 files
    python toolkit.py --start 2026-09-01 --end 2026-09-01 --max 5
    python toolkit.py --dataset 3SIMG_L1B_STD --max 2
    python toolkit.py --local data                      # pehle se download hui files se
    python toolkit.py --demo                            # bina credentials ke test (fake data)
"""

import argparse
import base64
import io
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mosdac_client import Mosdac, MosdacError  # noqa: E402

OUT = Path("out")


# ============================ HDF5 PARSING ============================
def _scale(ds, arr):
    """scale_factor / add_offset / _FillValue lagao (satellite HDF5 standard)."""
    arr = arr.astype(np.float64)
    fill = None
    for key in ("_FillValue", "missing_value", "fill_value"):
        if key in ds.attrs:
            try:
                fill = float(np.array(ds.attrs[key]).flatten()[0])
            except Exception:
                pass
            break
    sf = ds.attrs.get("scale_factor")
    ao = ds.attrs.get("add_offset")
    if sf is not None:
        arr = arr * float(np.array(sf).flatten()[0])
    if ao is not None:
        arr = arr + float(np.array(ao).flatten()[0])
    if fill is not None:
        arr = np.where(np.isclose(arr, fill), np.nan, arr)
    # bache hue unrealistic values hatao
    if np.issubdtype(arr.dtype, np.floating) and np.isfinite(arr).any():
        pass
    return arr


def parse_h5(source):
    """source: path (str/Path) ya bytes. Returns dict with data arrays + meta."""
    import h5py
    if isinstance(source, (bytes, bytearray)):
        f = h5py.File(io.BytesIO(source), "r")
    else:
        f = h5py.File(str(source), "r")

    names, datasets = [], {}

    def _visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            names.append(name)
            datasets[name] = obj
    f.visititems(_visit)

    # ---- variable dhoondo (SST prefer, warna sabse bada 2D) ----
    var_name = None
    for n in names:
        low = n.lower()
        if "sst" in low and datasets[n].ndim >= 2:
            var_name = n
            break
    if var_name is None:
        cands = [n for n in names
                 if datasets[n].ndim >= 2 and datasets[n].size > 1000
                 and not any(k in n.lower() for k in ("lat", "lon", "time", "flag", "qa"))]
        if cands:
            var_name = max(cands, key=lambda n: datasets[n].size)

    # ---- lat / lon dhoondo ----
    def find_coord(keys):
        for n in names:
            low = n.lower()
            if any(k in low for k in keys):
                return n
        return None

    lat_name = find_coord(["lat"])
    lon_name = find_coord(["lon"])

    result = {
        "file": str(source)[:80] if not isinstance(source, (bytes, bytearray)) else "<memory>",
        "datasets": names[:25],
        "var_name": var_name,
        "lat_name": lat_name,
        "lon_name": lon_name,
        "attrs": {},
    }
    for k, v in f.attrs.items():
        try:
            result["attrs"][str(k)] = str(v)
        except Exception:
            pass

    if var_name is None:
        f.close()
        return result

    var = datasets[var_name]
    arr = _scale(var, np.array(var))
    arr = np.squeeze(arr)
    result["data"] = arr

    if lat_name and lon_name:
        lat = _scale(datasets[lat_name], np.array(datasets[lat_name])).squeeze()
        lon = _scale(datasets[lon_name], np.array(datasets[lon_name])).squeeze()
        result["lat"] = lat
        result["lon"] = lon

    result["units"] = str(var.attrs.get("units", ""))
    f.close()
    return result


def stats_of(arr):
    a = arr[np.isfinite(arr)] if np.issubdtype(arr.dtype, np.floating) else arr
    if a.size == 0:
        return {"count": 0}
    return {
        "count": int(a.size),
        "valid": int(np.isfinite(a).sum()) if np.issubdtype(a.dtype, np.floating) else int(a.size),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
        "mean": float(np.nanmean(a)),
        "std": float(np.nanstd(a)),
    }


# ============================ MAP ============================
def make_map(parsed, title, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arr = parsed.get("data")
    if arr is None:
        return None
    lat = parsed.get("lat")
    lon = parsed.get("lon")
    step = max(1, arr.shape[0] // 500)  # bade arrays ko chhota karo
    view = arr[::step, ::step] if arr.ndim == 2 else arr

    extent = None
    if lat is not None and lon is not None and lat.ndim == 1 and lon.ndim == 1:
        extent = [float(np.nanmin(lon)), float(np.nanmax(lon)),
                  float(np.nanmin(lat)), float(np.nanmax(lat))]
    elif lat is not None and lon is not None and lat.ndim == 2:
        extent = [float(np.nanmin(lon)), float(np.nanmax(lon)),
                  float(np.nanmin(lat)), float(np.nanmax(lat))]

    fig, ax = plt.subplots(figsize=(9, 6), dpi=110)
    im = ax.imshow(view, cmap="turbo" if "sst" in str(parsed.get("var_name", "")).lower() else "gray",
                   origin="upper", extent=extent, aspect="auto", interpolation="nearest")
    ax.set_title(title[:90], fontsize=11)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.25, linestyle="--", linewidth=0.4)
    fig.colorbar(im, ax=ax, label=parsed.get("units") or parsed.get("var_name", "value"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    return out_png


# ============================ EXPORTS ============================
def to_csv(parsed, out_csv, max_points=40000):
    arr = parsed.get("data")
    if arr is None or arr.ndim != 2:
        return None
    lat, lon = parsed.get("lat"), parsed.get("lon")
    sh = arr.shape
    step = max(1, int(np.sqrt(sh[0] * sh[1] / max_points)) + 1)
    rows = []
    for i in range(0, sh[0], step):
        for j in range(0, sh[1], step):
            v = arr[i, j]
            la = lat[i] if lat is not None and lat.ndim == 1 else (lat[i, j] if lat is not None and lat.ndim == 2 else i)
            lo = lon[j] if lon is not None and lon.ndim == 1 else (lon[i, j] if lon is not None and lon.ndim == 2 else j)
            rows.append((float(lo), float(la), float(v)))
    try:
        import pandas as pd
        pd.DataFrame(rows, columns=["lon", "lat", "value"]).to_csv(out_csv, index=False)
    except ImportError:
        with open(out_csv, "w", encoding="utf-8") as fh:
            fh.write("lon,lat,value\n")
            for r in rows:
                fh.write(f"{r[0]:.4f},{r[1]:.4f},{r[2]:.3f}\n")
    return out_csv


def to_excel(records, out_xlsx):
    try:
        import pandas as pd
        rows = []
        for r in records:
            rows.append({
                "file": r["name"],
                "variable": r["parsed"].get("var_name"),
                "units": r["parsed"].get("units"),
                "shape": str(np.shape(r["parsed"].get("data"))),
                "min": r["stats"].get("min"),
                "max": r["stats"].get("max"),
                "mean": r["stats"].get("mean"),
                "std": r["stats"].get("std"),
                "valid_pixels": r["stats"].get("valid"),
            })
        pd.DataFrame(rows).to_excel(out_xlsx, index=False)
        return out_xlsx
    except ImportError:
        print("  (pandas/openpyxl nahi hai - Excel skip. pip install pandas openpyxl)")
        return None
    except Exception as e:
        print("  (Excel skip:", e, ")")
        return None


# ============================ DASHBOARD ============================
def make_dashboard(records, out_html, meta):
    parts = []
    for r in records:
        png = r.get("png")
        img = ""
        if png and Path(png).exists():
            b64 = base64.b64encode(Path(png).read_bytes()).decode()
            img = f'<img src="data:image/png;base64,{b64}" alt="map">'
        s = r["stats"]
        parts.append(f"""
        <div class="card">
          <h3>{r['name']}</h3>
          {img}
          <table>
            <tr><th>Variable</th><td>{r['parsed'].get('var_name','-')}</td></tr>
            <tr><th>Units</th><td>{r['parsed'].get('units','-') or '-'}</td></tr>
            <tr><th>Shape</th><td>{np.shape(r['parsed'].get('data'))}</td></tr>
            <tr><th>Min</th><td>{s.get('min')}</td></tr>
            <tr><th>Max</th><td>{s.get('max')}</td></tr>
            <tr><th>Mean</th><td>{s.get('mean')}</td></tr>
            <tr><th>Std</th><td>{s.get('std')}</td></tr>
            <tr><th>Valid pixels</th><td>{s.get('valid')}</td></tr>
          </table>
        </div>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MOSDAC Dashboard</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
header{{background:#1e293b;padding:18px 24px;border-bottom:1px solid #334155}}
h1{{margin:0;font-size:20px}} .sub{{color:#94a3b8;font-size:13px;margin-top:4px}}
.wrap{{padding:20px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.card h3{{margin:0 0 10px;font-size:14px;color:#7dd3fc;word-break:break-all}}
img{{width:100%;border-radius:6px;background:#000}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}}
th{{text-align:left;color:#94a3b8;padding:4px 6px;border-bottom:1px solid #334155;width:40%}}
td{{padding:4px 6px;border-bottom:1px solid #263244}}
footer{{padding:14px 24px;color:#64748b;font-size:12px}}
</style></head><body>
<header><h1>🛰️ MOSDAC Data Dashboard</h1>
<div class="sub">dataset: {meta.get('dataset')} | range: {meta.get('start')} → {meta.get('end')} | files: {len(records)} | generated: {meta.get('time')}</div></header>
<div class="wrap">{''.join(parts)}</div>
<footer>MOSDAC Data Download API • generated by toolkit.py</footer>
</body></html>"""
    Path(out_html).write_text(html, encoding="utf-8")
    return out_html


# ============================ MAIN ============================
def demo_records():
    """Credentials ke bina test ke liye synthetic data."""
    import h5py
    Path("out").mkdir(exist_ok=True)
    recs = []
    for k in range(2):
        buf = io.BytesIO()
        with h5py.File(buf, "w") as f:
            lat = np.linspace(-10, 30, 180).astype(np.float32)
            lon = np.linspace(60, 100, 220).astype(np.float32)
            sst = (np.random.rand(180, 220) * 80 + 200).astype(np.int16)
            f.create_dataset("Latitude", data=lat)
            f.create_dataset("Longitude", data=lon)
            d = f.create_dataset("SST", data=sst)
            d.attrs["scale_factor"] = 0.1
            d.attrs["add_offset"] = 270.0
            d.attrs["units"] = "K"
        parsed = parse_h5(buf.getvalue())
        parsed["file"] = f"DEMO_FILE_{k+1}.h5"
        stats = stats_of(parsed["data"])
        png = make_map(parsed, f"DEMO {k+1} (synthetic SST)", f"out/demo_{k+1}_map.png")
        to_csv(parsed, OUT / f"demo_{k+1}.csv")
        recs.append({"name": f"DEMO_FILE_{k+1}.h5", "parsed": parsed,
                     "stats": stats, "png": png})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="3RIMG_L2B_SST")
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--max", type=int, default=3, help="kitni files process karein")
    ap.add_argument("--local", default=None, help="local folder/file (API call nahi karega)")
    ap.add_argument("--demo", action="store_true", help="bina credentials ke test")
    ap.add_argument("--no-maps", action="store_true")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    print(f"\n=== MOSDAC Toolkit ===\n  out folder: {OUT.resolve()}\n")

    records = []

    if a.demo:
        print("[demo mode] synthetic data use kar rahe hain\n")
        records = demo_records()
        meta = {"dataset": "DEMO (synthetic)", "start": "-", "end": "-",
                "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    else:
        sources = []
        if a.local:
            p = Path(a.local)
            sources = sorted(p.rglob("*.h5")) if p.is_dir() else [p]
            print(f"[local] {len(sources)} file(s) mili\n")
        else:
            m = Mosdac()
            print(f"[api] search {a.dataset} {a.start} → {a.end}")
            res = m.search(a.dataset, a.start, a.end, count=100)
            ents = (res["entries"] or [])[: a.max]
            print(f"[api] {res['total']} files mile, {len(ents)} process karenge\n")
            if ents:
                m.login()
                print("[api] login OK\n")
            cache = Path("data")
            cache.mkdir(exist_ok=True)
            for e in ents:
                name = e["identifier"]
                cached = cache / name
                if cached.exists() and cached.stat().st_size > 1000:
                    print(f"  cached   {name} (pehle se hai)")
                    sources.append((name, str(cached)))
                    continue
                print(f"  downloading {name} ...")
                try:
                    blob = m.download_bytes(e["id"])
                    cached.write_bytes(blob)          # cache: agli baar dobara download nahi
                    sources.append((name, blob))
                except Exception as ex:               # network error pe poora script na mare
                    print(f"    SKIP {name}: {type(ex).__name__}: {ex}")
            if ents:
                m.logout()
                print("[api] logged out\n")

        meta = {"dataset": a.dataset, "start": a.start, "end": a.end,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")}

        for idx, src in enumerate(sources):
            name = src[0] if isinstance(src, tuple) else Path(src).name
            data = src[1] if isinstance(src, tuple) else src
            print(f"  parsing {name}")
            try:
                parsed = parse_h5(data)
            except Exception as ex:
                print("    parse fail:", ex)
                continue
            if parsed.get("data") is None:
                print("    koi 2D dataset nahi mila, skip")
                continue
            st = stats_of(parsed["data"])
            png = None if a.no_maps else make_map(parsed, name, OUT / f"{idx+1}_{Path(name).stem}_map.png")
            to_csv(parsed, OUT / f"{idx+1}_{Path(name).stem}.csv")
            parsed["file"] = name
            records.append({"name": name, "parsed": parsed, "stats": st, "png": png})

    if not records:
        print("\nkoi data process nahi hua.")
        return 1

    xlsx = to_excel(records, OUT / "summary.xlsx")
    html = make_dashboard(records, OUT / "dashboard.html", meta)

    print("\n--- RESULTS ---")
    for r in records:
        s = r["stats"]
        print(f"  {r['name'][:45]:45s} var={str(r['parsed'].get('var_name'))[:18]:18s} "
              f"min={s.get('min'):.2f} max={s.get('max'):.2f} mean={s.get('mean'):.2f}")
    print(f"\n  maps      : {OUT}/ (PNG)")
    print(f"  csv       : {OUT}/*.csv")
    if xlsx:
        print(f"  excel     : {xlsx}")
    print(f"  dashboard : {html}   <-- browser me kholo")
    Path(OUT / "summary.json").write_text(json.dumps(
        [{"file": r["name"], "variable": r["parsed"].get("var_name"),
          "stats": r["stats"]} for r in records], indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
