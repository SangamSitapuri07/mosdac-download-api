#!/usr/bin/env python3
"""
MOSDAC DATA TOOLKIT (v2) - INSAT-3DR/3S L2B SST ke liye optimized.

API se data lao (ya local files) -> .h5 padho -> map + CSV + Excel + HTML dashboard

    python toolkit.py --demo                                  # bina credentials ke test
    python toolkit.py --local data                            # local .h5 files
    python toolkit.py --start 2026-09-01 --end 2026-09-01 --max 3
    python toolkit.py --local data --region india             # sirf India (default)
    python toolkit.py --local data --region global            # poora satellite disk
    python toolkit.py --local data --var SST_REG              # doosra variable
    python toolkit.py --local data --kelvin                   # °C ki jagah Kelvin

Output: out/dashboard.html (browser me kholo), out/*.png, out/*.csv, out/summary.xlsx
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

REGIONS = {
    "india": (68.0, 6.0, 90.0, 30.0),        # minlon, minlat, maxlon, maxlat
    "india-full": (65.0, 0.0, 100.0, 38.0),
    "indian-ocean": (40.0, -40.0, 120.0, 30.0),
    "global": (-7.2, -81.1, 155.2, 81.1),    # poora INSAT-3DR disk
    "delhi": (76.0, 27.0, 79.0, 29.5),
}


# ============================ HDF5 PARSING ============================
def _attrs(ds):
    out = {}
    for k in ds.attrs.keys():
        try:
            v = ds.attrs[k]
            v = np.array(v).flatten()
            out[str(k)] = v[0] if v.size == 1 else v
        except Exception:
            pass
    return out


def _physical(ds):
    """raw -> physical values (scale_factor, add_offset, _FillValue lagao)."""
    a = ds
    arr = np.array(a)
    at = _attrs(ds)
    fill = at.get("_FillValue", at.get("missing_value"))
    arr = arr.astype(np.float32 if arr.dtype.itemsize <= 2 else np.float64)
    if fill is not None:
        arr = np.where(arr == np.float32(fill), np.nan, arr)
    sf = at.get("scale_factor")
    ao = at.get("add_offset")
    if sf not in (None, 0):
        arr = arr * float(sf)
    if ao not in (None, 0):
        arr = arr + float(ao)
    return arr, at


def parse_h5(source, var_pref=None):
    """INSAT L2B SST structure ke hisaab se parse karta hai."""
    import h5py
    f = (h5py.File(io.BytesIO(source), "r") if isinstance(source, (bytes, bytearray))
         else h5py.File(str(source), "r"))

    datasets = {}

    def _v(n, o):
        if isinstance(o, h5py.Dataset):
            datasets[n] = o
    f.visititems(_v)

    meta = {}
    for k, v in f.attrs.items():
        try:
            v2 = np.array(v).flatten()
            meta[str(k)] = v2[0].decode() if v2.dtype.kind in ("S", "U") else v2[0] if v2.size == 1 else str(v)[:60]
        except Exception:
            meta[str(k)] = str(v)[:60]

    # ---- variable chuno ----
    names = list(datasets.keys())
    var_name = None
    if var_pref:
        cand = [n for n in names if n.lower() == var_pref.lower()]
        var_name = cand[0] if cand else None
    if var_name is None:
        for n in sorted(names):
            if n.lower() == "sst":
                var_name = n
                break
    if var_name is None:
        for n in sorted(names):
            if "sst" in n.lower() and datasets[n].ndim >= 2:
                var_name = n
                break
    if var_name is None:
        cands = [n for n in names if datasets[n].ndim >= 2 and datasets[n].size > 10000
                 and not any(k in n.lower() for k in ("lat", "lon", "flag", "qa"))]
        var_name = max(cands, key=lambda n: datasets[n].size) if cands else None
    if var_name is None:
        f.close()
        return {"error": "koi 2D dataset nahi mila", "datasets": names, "meta": meta}

    data, at = _physical(datasets[var_name])
    data = np.squeeze(data)

    lat = lon = None
    for ln in ("Latitude", "latitude", "Lat", "lat"):
        if ln in datasets:
            lat, _ = _physical(datasets[ln]); lat = np.squeeze(lat); break
    for ln in ("Longitude", "longitude", "Lon", "lon"):
        if ln in datasets:
            lon, _ = _physical(datasets[ln]); lon = np.squeeze(lon); break

    units = at.get("units")
    if isinstance(units, bytes):
        units = units.decode()
    long_name = at.get("long_name")
    if isinstance(long_name, bytes):
        long_name = long_name.decode()

    f.close()
    return {"data": data, "lat": lat, "lon": lon, "var_name": var_name,
            "units": units or "", "long_name": long_name or var_name,
            "meta": meta, "datasets": names}


def to_celsius(parsed):
    """Kelvin -> °C (sirf SST jaisi temperature variables ke liye)."""
    if str(parsed.get("units", "")).upper().startswith("K"):
        parsed["data"] = parsed["data"] - 273.15
        parsed["units"] = "degC"
        return True
    return False


def crop(parsed, bbox):
    """lat/lon hisaab se region ke bahar ke pixels NaN kar do."""
    lat, lon, data = parsed.get("lat"), parsed.get("lon"), parsed["data"]
    if lat is None or lon is None or data is None:
        return parsed
    lo1, la1, lo2, la2 = bbox
    mask = ~((lon >= lo1) & (lon <= lo2) & (lat >= la1) & (lat <= la2))
    parsed["data"] = np.where(mask, np.nan, data)
    parsed["bbox"] = bbox
    return parsed


# ============================ STATS ============================
def stats_of(arr):
    a = arr[np.isfinite(arr)]
    total = arr.size
    if a.size == 0:
        return {"valid": 0, "coverage_pct": 0.0}
    return {
        "valid": int(a.size),
        "total": int(total),
        "coverage_pct": round(100.0 * a.size / total, 1),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
        "mean": float(np.nanmean(a)),
        "std": float(np.nanstd(a)),
        "median": float(np.nanmedian(a)),
    }


# ============================ MAP ============================
def make_map(parsed, title, out_png, max_px=900):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = parsed["data"]
    lat, lon = parsed.get("lat"), parsed.get("lon")
    sh = data.shape
    step = max(1, int(max(sh) / max_px) + 1)
    d = data[::step, ::step]

    fig, ax = plt.subplots(figsize=(10, 7), dpi=110)
    if lat is not None and lon is not None and lat.shape == data.shape:
        la, lo = lat[::step, ::step], lon[::step, ::step]
        ok = np.isfinite(d) & np.isfinite(la) & np.isfinite(lo)
        # pcolormesh ko NaN-free X/Y chahiye -> invalid jagah 0 (C NaN hone se draw nahi hoga)
        pm = ax.pcolormesh(np.where(ok, lo, 0.0), np.where(ok, la, 0.0),
                           np.where(ok, d, np.nan), cmap="turbo", shading="auto")
    else:
        pm = ax.imshow(d, cmap="turbo", aspect="auto", interpolation="nearest")

    if parsed.get("bbox"):
        lo1, la1, lo2, la2 = parsed["bbox"]
        ax.set_xlim(lo1, lo2)
        ax.set_ylim(la1, la2)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.set_title(title[:100], fontsize=12)
    cb = fig.colorbar(pm, ax=ax, pad=0.02)
    cb.set_label(f"{parsed['long_name']} ({parsed['units']})")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ============================ EXPORTS ============================
def to_csv(parsed, out_csv, max_rows=60000):
    data, lat, lon = parsed["data"], parsed.get("lat"), parsed.get("lon")
    if data is None or data.ndim != 2:
        return None
    sh = data.shape
    step = max(1, int(np.sqrt(sh[0] * sh[1] / max_rows)) + 1)
    rows = []
    for i in range(0, sh[0], step):
        for j in range(0, sh[1], step):
            v = data[i, j]
            if not np.isfinite(v):
                continue
            la = lat[i, j] if lat is not None and lat.ndim == 2 else (lat[i] if lat is not None else i)
            lo = lon[i, j] if lon is not None and lon.ndim == 2 else (lon[j] if lon is not None else j)
            rows.append((round(float(lo), 4), round(float(la), 4), round(float(v), 2)))
    try:
        import pandas as pd
        pd.DataFrame(rows, columns=["lon", "lat", parsed["var_name"]]).to_csv(out_csv, index=False)
    except ImportError:
        with open(out_csv, "w", encoding="utf-8") as fh:
            fh.write(f"lon,lat,{parsed['var_name']}\n")
            for r in rows:
                fh.write(f"{r[0]},{r[1]},{r[2]}\n")
    return out_csv


def to_excel(records, out_xlsx):
    try:
        import pandas as pd
        rows = []
        for r in records:
            s, p = r["stats"], r["parsed"]
            rows.append({
                "file": r["name"],
                "satellite": p["meta"].get("Satellite_Name", ""),
                "acq_start": p["meta"].get("Acquisition_Start_Time", ""),
                "variable": p["var_name"],
                "units": p["units"],
                "shape": str(np.shape(p["data"])),
                "valid_pixels": s.get("valid"),
                "coverage_%": s.get("coverage_pct"),
                "min": s.get("min"), "max": s.get("max"),
                "mean": s.get("mean"), "std": s.get("std"), "median": s.get("median"),
            })
        pd.DataFrame(rows).to_excel(out_xlsx, index=False)
        return out_xlsx
    except Exception as e:
        print("  (Excel skip:", e, ")")
        return None


# ============================ DASHBOARD ============================
def make_dashboard(records, out_html, meta):
    cards = []
    for r in records:
        png, p, s = r.get("png"), r["parsed"], r["stats"]
        img = ""
        if png and Path(png).exists():
            img = f'<img src="data:image/png;base64,{base64.b64encode(Path(png).read_bytes()).decode()}">'
        cards.append(f"""
        <div class="card">
          <h3>{r['name']}</h3>
          <div class="tags">
            <span>{p['meta'].get('Satellite_Name','-')}</span>
            <span>{p['meta'].get('Acquisition_Start_Time','-')}</span>
            <span>{p['var_name']}</span>
          </div>
          {img}
          <table>
            <tr><th>Units</th><td>{p['units']}</td></tr>
            <tr><th>Grid</th><td>{np.shape(p['data'])}</td></tr>
            <tr><th>Valid pixels</th><td>{s.get('valid'):,} ({s.get('coverage_pct')}%)</td></tr>
            <tr><th>Min</th><td>{s.get('min'):.2f}</td></tr>
            <tr><th>Max</th><td>{s.get('max'):.2f}</td></tr>
            <tr><th>Mean</th><td>{s.get('mean'):.2f}</td></tr>
            <tr><th>Median</th><td>{s.get('median'):.2f}</td></tr>
            <tr><th>Std</th><td>{s.get('std'):.2f}</td></tr>
          </table>
        </div>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>MOSDAC Dashboard</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}}
header{{background:#1e293b;padding:18px 24px;border-bottom:1px solid #334155}}
h1{{margin:0;font-size:20px}}.sub{{color:#94a3b8;font-size:13px;margin-top:6px}}
.wrap{{padding:20px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.card h3{{margin:0 0 8px;font-size:14px;color:#7dd3fc;word-break:break-all}}
.tags span{{display:inline-block;background:#0ea5e933;color:#7dd3fc;font-size:11px;
padding:2px 8px;border-radius:10px;margin:0 6px 8px 0}}
img{{width:100%;border-radius:6px;background:#000}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}}
th{{text-align:left;color:#94a3b8;padding:4px 6px;border-bottom:1px solid #334155;width:45%}}
td{{padding:4px 6px;border-bottom:1px solid #263244}}
footer{{padding:14px 24px;color:#64748b;font-size:12px}}
</style></head><body>
<header><h1>MOSDAC Data Dashboard</h1>
<div class="sub">dataset {meta.get('dataset')} | {meta.get('start')} to {meta.get('end')} |
region {meta.get('region')} | {len(records)} files | {meta.get('time')}</div></header>
<div class="wrap">{''.join(cards)}</div>
<footer>INSAT-3DR / MOSDAC Data Download API - generated by toolkit.py</footer>
</body></html>"""
    Path(out_html).write_text(html, encoding="utf-8")
    return out_html


# ============================ DEMO (real jaisa structure) ============================
def demo_records(region):
    import h5py
    OUT.mkdir(exist_ok=True)
    recs = []
    for k in range(2):
        buf = io.BytesIO()
        ny, nx = 704, 700
        with h5py.File(buf, "w") as f:
            lat1 = np.linspace(-81, 81, ny).astype(np.float32)
            lon1 = np.linspace(-7, 155, nx).astype(np.float32)
            lon2, lat2 = np.meshgrid(lon1, lat1)
            sst = np.full((1, ny, nx), -999.0, dtype=np.float32)
            ocean = (np.abs(lat2) < 60)
            sst[0][ocean] = 273.15 + 24 + 8 * np.cos(np.radians(lat2[ocean] * 3)) \
                + np.random.rand(int(ocean.sum())) * 2
            # bilkul asli INSAT-3DR structure: int16 + scale_factor 0.01 + FillValue 32767
            dla = f.create_dataset("Latitude", data=(lat2 / 0.01).astype(np.int16))
            dla.attrs["scale_factor"] = np.float32(0.01)
            dla.attrs["add_offset"] = np.float32(0.0)
            dla.attrs["_FillValue"] = np.int16(32767)
            dla.attrs["units"] = np.bytes_(b"degrees_north")
            dlo = f.create_dataset("Longitude", data=(lon2 / 0.01).astype(np.int16))
            dlo.attrs["scale_factor"] = np.float32(0.01)
            dlo.attrs["add_offset"] = np.float32(0.0)
            dlo.attrs["_FillValue"] = np.int16(32767)
            dlo.attrs["units"] = np.bytes_(b"degrees_east")
            d = f.create_dataset("SST", data=sst)
            d.attrs["_FillValue"] = np.float32(-999.0)
            d.attrs["units"] = np.bytes_("K")
            d.attrs["long_name"] = np.bytes_("SST 1DVAR")
            f.attrs["Satellite_Name"] = np.bytes_("INSAT-3DR")
            f.attrs["Acquisition_Start_Time"] = np.bytes_(f"01-SEP-2026T0{6+k}:45:43")

        p = parse_h5(buf.getvalue())
        to_celsius(p)
        crop(p, REGIONS[region])
        st = stats_of(p["data"])
        png = make_map(p, f"DEMO INSAT-3DR SST (°C) - {region}", OUT / f"demo_{k+1}_map.png")
        to_csv(p, OUT / f"demo_{k+1}.csv")
        recs.append({"name": f"DEMO_FILE_{k+1}.h5", "parsed": p, "stats": st, "png": png})
    return recs


# ============================ MAIN ============================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="3RIMG_L2B_SST")
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--local", default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--region", default="india",
                    choices=list(REGIONS.keys()), help="map/CSV ke liye region")
    ap.add_argument("--bbox", default=None, help="custom: minlon,minlat,maxlon,maxlat")
    ap.add_argument("--var", default=None, help="variable name (SST / SST_REG / SST_FCT)")
    ap.add_argument("--kelvin", action="store_true", help="°C ke bajaye Kelvin rakho")
    ap.add_argument("--no-maps", action="store_true")
    ap.add_argument("--wait-minutes", type=int, default=5)
    a = ap.parse_args()

    bbox = REGIONS[a.region]
    if a.bbox:
        bbox = tuple(float(x) for x in a.bbox.split(","))
        a.region = "custom"

    OUT.mkdir(exist_ok=True)
    print(f"\n=== MOSDAC Toolkit v2 ===\n  out: {OUT.resolve()}\n  region: {a.region} {bbox}\n")

    records = []

    if a.demo:
        print("[demo] asli INSAT-3DR jaisa synthetic data\n")
        records = demo_records(a.region)
        meta = {"dataset": "DEMO", "start": "-", "end": "-", "region": a.region,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    else:
        sources = []
        if a.local:
            p = Path(a.local)
            sources = sorted(p.rglob("*.h5")) + sorted(p.rglob("*.H5")) if p.is_dir() else [p]
            print(f"[local] {len(sources)} file(s)\n")
        else:
            m = Mosdac()
            res = m.search(a.dataset, a.start, a.end, count=100)
            ents = (res["entries"] or [])[: a.max]
            print(f"[api] {res['total']} files mile, {len(ents)} lenge")
            if ents:
                try:
                    m.login(retries=1 + a.wait_minutes)
                    print("[api] login OK\n")
                except MosdacError as ex:
                    print(f"\n[api] LOGIN FAIL: {ex}\n  Hint: python toolkit.py --wait-minutes 30")
                    return 1
            cache = Path("data"); cache.mkdir(exist_ok=True)
            for e in ents:
                name, cached = e["identifier"], cache / e["identifier"]
                if cached.exists() and cached.stat().st_size > 1000:
                    print(f"  cached   {name}")
                    sources.append((name, str(cached))); continue
                print(f"  downloading {name} ...")
                try:
                    blob = m.download_bytes(e["id"])
                    cached.write_bytes(blob)
                    sources.append((name, blob))
                except Exception as ex:
                    print(f"    SKIP {name}: {type(ex).__name__}: {ex}")
            if ents:
                m.logout()

        meta = {"dataset": a.dataset, "start": a.start, "end": a.end,
                "region": f"{a.region} {bbox}", "time": time.strftime("%Y-%m-%d %H:%M:%S")}

        for idx, src in enumerate(sources):
            name = src[0] if isinstance(src, tuple) else Path(src).name
            data = src[1] if isinstance(src, tuple) else src
            print(f"  parsing {name}")
            try:
                p = parse_h5(data, var_pref=a.var)
            except Exception as ex:
                print("    parse fail:", ex); continue
            if "error" in p:
                print("   ", p["error"]); continue
            if not a.kelvin:
                if to_celsius(p):
                    print(f"    Kelvin -> °C convert kiya")
            crop(p, bbox)
            st = stats_of(p["data"])
            png = None if a.no_maps else make_map(
                p, f"{name}\n{p['meta'].get('Satellite_Name','')} "
                   f"{p['meta'].get('Acquisition_Start_Time','')}",
                OUT / f"{idx+1}_{Path(name).stem}_map.png")
            to_csv(p, OUT / f"{idx+1}_{Path(name).stem}.csv")
            records.append({"name": name, "parsed": p, "stats": st, "png": png})

    if not records:
        print("\nkoi data process nahi hua."); return 1

    xlsx = to_excel(records, OUT / "summary.xlsx")
    html = make_dashboard(records, OUT / "dashboard.html", meta)

    print("\n--- RESULTS ---")
    for r in records:
        s, p = r["stats"], r["parsed"]
        print(f"  {r['name'][:40]:40s} {p['var_name']:8s} "
              f"min={s['min']:.2f} max={s['max']:.2f} mean={s['mean']:.2f} {p['units']}"
              f"  valid={s['valid']:,} ({s['coverage_pct']}%)")
    print(f"\n  maps      : {OUT}/")
    print(f"  csv       : {OUT}/*.csv")
    if xlsx:
        print(f"  excel     : {xlsx}")
    print(f"  dashboard : {html}   <-- browser me kholo")
    Path(OUT / "summary.json").write_text(json.dumps(
        [{"file": r["name"], "variable": r["parsed"]["var_name"],
          "units": r["parsed"]["units"], "stats": r["stats"]} for r in records], indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
