"""MATSYA command line: ingest -> analyze -> report (sab real data)."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config as C, geo_tools as G, ingest, physics as P, report


def _analyze_file(path, kind, cfg, verbose=True):
    """Ek HDF5 file -> grid dict (real values)."""
    g = ingest.read_grid(path, kind=kind)
    if "error" in g:
        if verbose:
            print(f"    [skip] {Path(path).name}: {g['error'][:80]}")
        return None
    if kind == "sst":
        ingest.kelvin_to_celsius(g)
    ingest.crop_and_downsample(g, cfg["region"]["bbox"], cfg["region"]["max_grid"])
    return g


def run_pipeline(args, cfg):
    C.ensure_dirs()
    out = C.OUT
    bbox = cfg["region"]["bbox"]

    files = {"sst": [], "wind": []}
    if args.local:
        p = Path(args.local)
        allh5 = ingest.load_local(p)
        if not allh5:
            print(f"[error] {p} me koi .h5 file nahi mili")
            return 1
        # SST aur wind files ko unke naam se alag karo
        for f in allh5:
            n = f.name.upper()
            if "VSW" in n or "WIND" in n:
                files["wind"].append(f)
            else:
                files["sst"].append(f)
        print(f"[local] {len(allh5)} file(s): {len(files['sst'])} SST, {len(files['wind'])} wind")
    else:
        print("[ingest] MOSDAC se asli data la rahe hain...")
        files["sst"] = ingest.fetch_latest(cfg["datasets"]["sst"],
                                           cfg["fetch"]["hours_back"],
                                           cfg["fetch"]["max_files"])
        if cfg["datasets"].get("wind") and not args.no_wind:
            try:
                files["wind"] = ingest.fetch_latest(cfg["datasets"]["wind"],
                                                    cfg["fetch"]["hours_back"], 1)
            except Exception as e:
                print(f"  [wind] nahi mil paya: {type(e).__name__}: {e}")

    if not files["sst"]:
        print("[error] koi SST file nahi mila — bina SST ke advisory nahi ban sakti")
        return 1

    print("\n[analyze] SST grid padh rahe hain...")
    sst_g = None
    for f in files["sst"]:
        g = _analyze_file(f, "sst", cfg)
        if g:
            sst_g = g
            print(f"    SST  {Path(f).name}  ->  {g['data'].shape}  {g['units']}")
            break
    if sst_g is None:
        print("[error] SST file parse nahi hui")
        return 1

    wind_g = None
    for f in files["wind"]:
        g = _analyze_file(f, "wind", cfg)
        if g:
            wind_g = g
            print(f"    WIND {Path(f).name}  ->  {g['data'].shape}  {g['units']}")
            break
    if wind_g is None:
        print("    (wind layer nahi mila — score me wind weight neutral rahega)")

    sst, lat, lon = sst_g["data"], sst_g.get("lat"), sst_g.get("lon")
    if lat is None or lon is None or lat.shape != sst.shape:
        print("[error] is file me lat/lon grid nahi mila")
        return 1

    print("\n[analyze] physics...")
    grad = P.gradient_c_per_km(sst, lat, lon)
    in_eez = G.eez_mask(lon, lat, "India")
    dist = G.coast_distance_km(lon, lat)

    wind = None
    if wind_g is not None and wind_g["data"].shape == sst.shape:
        wind = wind_g["data"]
    elif wind_g is not None:
        # alag grid ho to nearest-neighbour se resample (simple)
        try:
            from scipy.interpolate import griddata
            wl, wt = wind_g.get("lon"), wind_g.get("lat")
            if wl is not None and wt is not None:
                pts = np.column_stack([wl.ravel(), wt.ravel()])
                vals = wind_g["data"].ravel()
                ok = np.isfinite(vals) & np.isfinite(pts).all(axis=1)
                wind = griddata(pts[ok], vals[ok], (lon, lat), method="nearest")
                print("    wind ko SST grid pe resample kiya")
        except Exception as e:
            print(f"    (wind resample fail: {e})")

    score = P.pfz_score(sst, grad, in_eez, dist, wind, cfg)
    spots = P.top_spots(score, lat, lon, sst, grad, wind, dist, in_eez,
                        n=cfg["advisory"]["top_spots"])

    valid = int(np.isfinite(sst).sum())
    print(f"    valid pixels : {valid:,}")
    print(f"    SST range    : {np.nanmin(sst):.2f} – {np.nanmax(sst):.2f} °C")
    print(f"    front max    : {np.nanmax(grad):.3f} °C/km")
    if wind is not None:
        print(f"    wind max     : {np.nanmax(wind):.1f} m/s")
    print(f"    EEZ pixels   : {int(in_eez.sum()):,}")
    print(f"    PFZ max      : {np.nanmax(score):.0f}/100")
    print(f"    top spots    : {len(spots)}")

    print("\n[report] output bana rahe hain...")
    sst_png = report.make_map(sst, lat, lon,
                              f"SST (°C) — {Path(files['sst'][0]).name}",
                              out / "sst_map.png", "turbo", "°C",
                              vmin=22, vmax=33, cfg=cfg)
    wind_png = (report.make_map(wind, lat, lon,
                                f"Wind speed (m/s) — {Path(files['wind'][0]).name}",
                                out / "wind_map.png", "viridis", "m/s", cfg=cfg)
                if wind is not None else None)
    pfz_png = report.make_map(score, lat, lon, "PFZ score (0–100)",
                              out / "pfz_map.png", "RdYlGn", "score",
                              vmin=0, vmax=100, cfg=cfg)

    csv = report.to_csv(lat, lon, sst, grad, wind, dist, in_eez, score,
                        out / "pfz_grid.csv")

    prov = [{
        "layer": "SST (thermal fronts, PFZ)",
        "source": "ISRO MOSDAC (INSAT-3DR IMAGER)",
        "dataset": cfg["datasets"]["sst"],
        "file": Path(files["sst"][0]).name,
        "time": str(sst_g["meta"].get("Acquisition_Start_Time", "")),
        "status": "REAL",
    }]
    if wind is not None:
        prov.append({
            "layer": "Sea surface wind (safety)",
            "source": "ISRO MOSDAC (INSAT-3DR IMAGER)",
            "dataset": cfg["datasets"]["wind"],
            "file": Path(files["wind"][0]).name,
            "time": str(wind_g["meta"].get("Acquisition_Start_Time", "")),
            "status": "REAL",
        })
    else:
        prov.append({"layer": "Sea surface wind", "source": "MOSDAC",
                     "dataset": cfg["datasets"]["wind"] or "-",
                     "file": "-", "time": "-", "status": "NOT AVAILABLE"})
    prov.append({"layer": "EEZ boundary", "source": "MarineRegions / VLIZ (EEZ v12)",
                 "dataset": "WFS:MarineRegions:eez", "file": "geo/eez.json",
                 "time": "v12 (2023-10-25)", "status": "REAL"})
    prov.append({"layer": "Coastline", "source": "Natural Earth (public domain)",
                 "dataset": "ne_50m_coastline", "file": "geo/coastline.json",
                 "time": "v5.0", "status": "REAL"})
    prov.append({"layer": "Chlorophyll-a", "source": "MOSDAC API me maujood NAHI",
                 "dataset": "-", "file": "-", "time": "-",
                 "status": "PENDING (NOTES.md)"})

    html = report.build_html((sst_png, wind_png, pfz_png),
                             {"lat": lat, "lon": lon, "sst": sst, "grad": grad,
                              "wind": wind, "score": score, "dist": dist,
                              "eez": in_eez.astype(float)},
                             spots, prov, cfg, out / "index.html")
    xlsx = report.to_excel(spots, prov, out / "summary.xlsx")

    (out / "summary.json").write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "region": cfg["region"],
        "files": {k: [str(x.name) for x in v] for k, v in files.items()},
        "stats": {
            "valid_pixels": valid,
            "sst_min_c": round(float(np.nanmin(sst)), 2),
            "sst_max_c": round(float(np.nanmax(sst)), 2),
            "sst_mean_c": round(float(np.nanmean(sst)), 2),
            "front_max_c_per_km": round(float(np.nanmax(grad)), 4),
            "wind_max_ms": round(float(np.nanmax(wind)), 2) if wind is not None else None,
            "eez_pixels": int(in_eez.sum()),
            "pfz_max": round(float(np.nanmax(score)), 1),
        },
        "top_spots": spots,
        "provenance": prov,
    }, indent=2), encoding="utf-8")

    print(f"\n  ✅ {html}")
    print(f"     {out/'pfz_map.png'}")
    print(f"     {csv}")
    if xlsx:
        print(f"     {xlsx}")
    print(f"     {out/'summary.json'}")
    print("\n  Browser me kholo aur map pe CLICK karo.\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="matsya", description="MATSYA real-data marine advisory")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="poora pipeline: ingest + analyze + report")
    p_run.add_argument("--local", default=None, help="local folder/file (API call nahi)")
    p_run.add_argument("--no-wind", action="store_true")
    p_run.add_argument("--region", default=None)

    p_in = sub.add_parser("ingest", help="sirf MOSDAC se data download")
    p_in.add_argument("--hours", type=int, default=24)
    p_in.add_argument("--max", type=int, default=2)

    p_ls = sub.add_parser("datasets", help="uplabdh datasets check karo (real)")

    args = ap.parse_args(argv)
    cfg = C.load()
    if getattr(args, "region", None):
        args.region = args.region

    if args.cmd == "run":
        return run_pipeline(args, cfg)
    if args.cmd == "ingest":
        C.ensure_dirs()
        got = ingest.fetch_latest(cfg["datasets"]["sst"], args.hours, args.max)
        print(f"  {len(got)} file(s) data/ me")
        return 0
    if args.cmd == "datasets":
        from mosdac_client import Mosdac
        m = Mosdac()
        for name, ds in cfg["datasets"].items():
            if not ds:
                print(f"  {name:14s} -> configured NAHI (NOTES.md)")
                continue
            try:
                r = m.search(ds, count="1")
                print(f"  {name:14s} -> {ds:16s} total={r['total']}")
            except Exception as e:
                print(f"  {name:14s} -> {ds:16s} ERROR {e}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
