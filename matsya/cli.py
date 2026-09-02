"""MATSYA CLI — run / serve / watch / export / ingest / doctor / datasets."""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import (ais, chlorophyll as CHL, composite as CMP, config as C, export,
               geo_tools as G, ingest, physics as P, report, report_v2)
from .agents.state import AgentState
from .orchestrator import Orchestrator


# ------------------------------------------------------------------ state
def build_state(files, cfg, query, persona, no_wind=False, use_composite=False,
                want_animation=False, want_ais=False):
    print("\n[analyze] grids padh rahe hain...")
    bbox = cfg["region"]["bbox"]

    if use_composite and len(files["sst"]) > 1:
        print(f"    composite mode: {min(len(files['sst']), 8)} SST files ka median")
        sst_g = CMP.build(files["sst"], cfg, "sst", max_files=8)
        if sst_g is None:
            raise SystemExit("[error] composite nahi ban paya")
    else:
        sst_g = None
        for f in files["sst"]:
            sst_g = ingest.read_grid(str(f), kind="sst")
            if "error" not in sst_g:
                break
            sst_g = None
        if sst_g is None:
            raise SystemExit("[error] koi SST file parse nahi hui")
        ingest.kelvin_to_celsius(sst_g)
        ingest.crop_and_downsample(sst_g, bbox, cfg["region"]["max_grid"])
    print(f"    SST  -> {sst_g['data'].shape} {sst_g['units']}"
          f"{' (composite of %d)' % sst_g.get('n_files', 1) if use_composite else ''}")

    wind_g = None
    if not no_wind:
        for f in files["wind"]:
            g = ingest.read_grid(str(f), kind="wind")
            if "error" in g:
                continue
            ingest.crop_and_downsample(g, bbox, cfg["region"]["max_grid"])
            wind_g = g
            print(f"    WIND -> {g['data'].shape} {g['units']}")
            break
    if wind_g is None:
        print("    (wind layer nahi mila)")

    sst, lat, lon = sst_g["data"], sst_g.get("lat"), sst_g.get("lon")
    if lat is None or lon is None or lat.shape != sst.shape:
        raise SystemExit("[error] is file me lat/lon grid nahi mila")

    wind = wind_g["data"] if (wind_g and wind_g["data"].shape == sst.shape) else None
    if wind_g is not None and wind is None:
        try:
            from scipy.interpolate import griddata
            wl, wt = wind_g.get("lon"), wind_g.get("lat")
            if wl is not None and wt is not None:
                pts = np.column_stack([wl.ravel(), wt.ravel()])
                vals = wind_g["data"].ravel()
                ok = np.isfinite(vals) & np.isfinite(pts).all(axis=1)
                wind = griddata(pts[ok], vals[ok], (lon, lat), method="nearest")
                print("    wind resample -> SST grid")
        except Exception as e:
            print(f"    (wind resample fail: {e})")

    # --- chlorophyll (optional, real file ho to) ---
    chl = None
    chl_files = CHL.find_files(C.DATA) + CHL.find_files("data")
    if chl_files:
        for cf in chl_files[:2]:
            cg = CHL.load(cf, bbox, cfg["region"]["max_grid"])
            if cg:
                chl = CHL.resample_to(cg, lat, lon)
                if chl is not None:
                    print(f"    CHL  -> {cf.name} (real)")
                    break
    if chl is None:
        print("    CHL  -> nahi mila (MOSDAC me uplabdh nahi; NOTES.md)")

    print("[analyze] physics + geo...")
    grad = P.gradient_c_per_km(sst, lat, lon)
    in_eez = G.eez_mask(lon, lat, "India")
    dist = G.coast_distance_km(lon, lat)
    print(f"    valid px {int(np.isfinite(sst).sum()):,} | EEZ px {int(in_eez.sum()):,}")

    st = AgentState(user_query=query, persona=persona)
    st.grids = {"lat": lat, "lon": lon, "sst": sst, "grad": grad, "wind": wind,
                "dist": dist, "eez": in_eez, "chl": chl, "score": None}
    st.meta = {"cfg": cfg,
               "sst_file": Path(files["sst"][0]).name if files["sst"] else "",
               "sst_meta": sst_g.get("meta", {}),
               "wind_file": Path(files["wind"][0]).name if files["wind"] else "",
               "wind_meta": (wind_g or {}).get("meta", {}),
               "chl_file": chl_files[0].name if chl is not None and chl_files else "",
               "files": {k: [str(x) for x in v] for k, v in files.items()}}
    return st


# ------------------------------------------------------------------ pipeline
def run_pipeline(args, cfg):
    C.ensure_dirs()
    out = C.OUT
    files = {"sst": [], "wind": []}

    if args.local:
        allh5 = ingest.load_local(args.local)
        if not allh5:
            print(f"[error] {args.local} me koi .h5 nahi mila")
            return 1
        for f in allh5:
            n = f.name.upper()
            (files["wind"] if ("VSW" in n or "WIND" in n) else files["sst"]).append(f)
        print(f"[local] {len(allh5)} file(s): {len(files['sst'])} SST, {len(files['wind'])} wind")
    else:
        print("[ingest] MOSDAC se asli data...")
        files["sst"] = ingest.fetch_latest(cfg["datasets"]["sst"],
                                           cfg["fetch"]["hours_back"],
                                           getattr(args, "max", cfg["fetch"]["max_files"]))
        if cfg["datasets"].get("wind") and not args.no_wind:
            try:
                files["wind"] = ingest.fetch_latest(cfg["datasets"]["wind"],
                                                    cfg["fetch"]["hours_back"], 1)
            except Exception as e:
                print(f"  [wind] {type(e).__name__}: {e}")
    if not files["sst"]:
        print("[error] koi SST file nahi mila")
        return 1

    st = build_state(files, cfg, args.ask or "Best fishing zone kahan hai aaj?",
                     args.persona, args.no_wind,
                     use_composite=getattr(args, "composite", False))

    print("\n[agents] 7-agent swarm chal raha hai...")
    st = Orchestrator(cfg, audit_dir=out / "audit").run(st)
    for s in st.trace.steps:
        print(f"    {s['agent']:20s} {s['ms']:8.1f} ms  [{s['status']}]")
    print(f"    {'TOTAL':20s} {st.trace.total_ms:8.1f} ms")
    if st.final:
        print(f"\n    >>> {st.final['headline']}  (PFZ {st.final['score']}, risk {st.final['risk']})")

    g = st.grids
    print("\n[report] output...")
    sst_png = report.make_map(g["sst"], g["lat"], g["lon"],
                              f"SST (°C) — {st.meta['sst_file']}",
                              out / "sst_map.png", "turbo", "°C",
                              vmin=22, vmax=33, cfg=cfg)
    wind_png = (report.make_map(g["wind"], g["lat"], g["lon"],
                                f"Wind (m/s) — {st.meta['wind_file']}",
                                out / "wind_map.png", "viridis", "m/s", cfg=cfg)
                if g["wind"] is not None else None)
    pfz_png = report.make_map(g["score"], g["lat"], g["lon"], "PFZ score (0-100)",
                              out / "pfz_map.png", "RdYlGn", "score",
                              vmin=0, vmax=100, cfg=cfg)
    chl_png = (report.make_map(g["chl"], g["lat"], g["lon"], "Chlorophyll (mg/m³)",
                               out / "chl_map.png", "YlGn", "mg/m³", cfg=cfg)
               if g.get("chl") is not None else None)

    # time series + animation (real files)
    ts_png = gif = None
    if len(files["sst"]) > 1:
        rows = CMP.timeseries(files["sst"], cfg)
        if len(rows) > 1:
            ts_png = CMP.plot_timeseries(rows, out / "timeseries.png")
            print(f"    time-series: {len(rows)} files")
    if getattr(args, "animation", False) and len(files["sst"]) > 1:
        gif = CMP.animation(files["sst"], cfg, out / "animation.gif")
        if gif:
            print("    animation.gif ban gaya")

    # AIS (real, agar key ho)
    ais_out = None
    if getattr(args, "ais", False):
        ais_out = ais.collect(seconds=getattr(args, "ais_seconds", 30),
                              out_json=out / "ais_vessels.json")
        print(f"    AIS: {ais_out.get('count', 0)} vessels"
              + ("" if ais_out.get("available") else f" ({ais_out.get('reason')})"))

    prov = [
        {"layer": "SST (fronts + PFZ)", "source": "ISRO MOSDAC (INSAT-3DR)",
         "dataset": cfg["datasets"]["sst"], "file": st.meta["sst_file"],
         "time": str(st.meta["sst_meta"].get("Acquisition_Start_Time", "")), "status": "REAL"},
        {"layer": "Sea wind (safety)",
         "source": "ISRO MOSDAC (INSAT-3DR)" if g["wind"] is not None else "not fetched",
         "dataset": cfg["datasets"]["wind"] or "-", "file": st.meta["wind_file"] or "-",
         "time": str(st.meta["wind_meta"].get("Acquisition_Start_Time", "")),
         "status": "REAL" if g["wind"] is not None else "NOT AVAILABLE"},
        {"layer": "Chlorophyll-a",
         "source": "local file (MOSDAC API me nahi)" if g.get("chl") is not None
                   else "MOSDAC API me uplabdh NAHI",
         "dataset": "-", "file": st.meta.get("chl_file", "-"), "time": "-",
         "status": "REAL" if g.get("chl") is not None else "PENDING (NOTES.md)"},
        {"layer": "EEZ boundary", "source": "MarineRegions / VLIZ",
         "dataset": "WFS:MarineRegions:eez", "file": "geo/eez.json",
         "time": "v12 (2023-10-25)", "status": "REAL"},
        {"layer": "Coastline", "source": "Natural Earth",
         "dataset": "ne_50m_coastline", "file": "geo/coastline.json",
         "time": "v5.0", "status": "REAL"},
        {"layer": "AIS vessels",
         "source": "aisstream.io" if (ais_out or {}).get("available") else "no API key",
         "dataset": "AIS", "file": "-",
         "time": time.strftime("%H:%M:%S") if ais_out else "-",
         "status": "REAL" if (ais_out or {}).get("available") else "PENDING (key chahiye)"},
    ]

    spots = st.meta.get("spots", [])
    report.build_html((sst_png, wind_png, pfz_png),
                      {"lat": g["lat"], "lon": g["lon"], "sst": g["sst"],
                       "grad": g["grad"], "wind": g["wind"], "score": g["score"],
                       "dist": g["dist"], "eez": g["eez"].astype(float)},
                      spots, prov, cfg, out / "index.html")
    report.to_csv(g["lat"], g["lon"], g["sst"], g["grad"], g["wind"], g["dist"],
                  g["eez"], g["score"], out / "pfz_grid.csv")
    report.to_excel(spots, prov, out / "summary.xlsx")

    tac = report_v2.build_tactical(st, (sst_png, wind_png, pfz_png), prov, cfg,
                                   out / "tactical.html")

    gj = export.build(spots, st.meta.get("route"), "India",
                      grid={"lat": g["lat"], "lon": g["lon"], "score": g["score"]},
                      step=10, provenance=prov)
    export.write(gj, out / "matsya.geojson")

    (out / "summary.json").write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "query": st.user_query, "persona": st.persona, "intent": st.intent,
        "region": cfg["region"], "files": st.meta["files"],
        "stats": {
            "valid_pixels": int(np.isfinite(g["sst"]).sum()),
            "sst_min_c": round(float(np.nanmin(g["sst"])), 2),
            "sst_max_c": round(float(np.nanmax(g["sst"])), 2),
            "front_max_c_per_km": round(float(np.nanmax(g["grad"])), 4),
            "wind_max_ms": round(float(np.nanmax(g["wind"])), 2) if g["wind"] is not None else None,
            "chl_max_mg_m3": round(float(np.nanmax(g["chl"])), 3) if g.get("chl") is not None else None,
            "eez_pixels": int(g["eez"].sum()),
            "pfz_max": round(float(np.nanmax(g["score"])), 1),
        },
        "top_spots": spots[:12],
        "species": (st.results.get("species_forecaster") or {}).get("findings", {}).get("species", []),
        "final": st.final,
        "agents": st.trace.steps, "total_ms": st.trace.total_ms,
        "provenance": prov,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  ✅ {tac}          <-- TACTICAL COMMAND CENTER")
    for f in ("index.html", "pfz_map.png", "sst_map.png", "matsya.geojson",
              "pfz_grid.csv", "summary.xlsx", "summary.json"):
        fp = out / f
        if fp.exists():
            print(f"     {fp}")
    if ts_png:
        print(f"     {ts_png}")
    if gif:
        print(f"     {gif}")
    if chl_png:
        print(f"     {chl_png}")
    print(f"     {out/'audit/execution_audit.jsonl'}")

    if getattr(args, "serve", False):
        from .server import serve
        serve(args.port, st, Path(tac).read_text(encoding="utf-8"), cfg)
    else:
        print("\n  Live console:  python matsya.py serve\n")
    return 0


# ------------------------------------------------------------------ others
def doctor(cfg):
    print("\n=== MATSYA doctor ===\n")
    ok = True
    mods = {"numpy": "numpy", "h5py": "h5py", "matplotlib": "matplotlib",
            "scipy": "scipy (coast distance)", "requests": "requests (MOSDAC API)"}
    for m, label in mods.items():
        try:
            __import__(m)
            print(f"  OK    {label}")
        except ImportError:
            print(f"  MISS  {label}   -> pip install {m}")
            ok = False
    for m, label in (("pandas", "pandas (Excel)"), ("openpyxl", "openpyxl (Excel)"),
                     ("PIL", "pillow (animation GIF)"), ("websockets", "websockets (AIS)")):
        try:
            __import__(m)
            print(f"  OK    {label}")
        except ImportError:
            print(f"  --    {label} (optional)")

    print("\n  Geo data:")
    for f in ("geo/eez.json", "geo/coastline.json"):
        p = C.ROOT / f
        print(f"  {'OK   ' if p.exists() else 'MISS '} {f}"
              + (f" ({p.stat().st_size//1024} KB)" if p.exists() else
                 "  -> python build_geo.py"))
        if not p.exists():
            ok = False

    print("\n  Local data (.h5):")
    n = len(ingest.load_local(C.DATA)) if C.DATA.exists() else 0
    print(f"  {'OK   ' if n else '--   '} {n} file(s) in data/")

    print("\n  MOSDAC API:")
    try:
        from mosdac_client import Mosdac
        r = Mosdac().search(cfg["datasets"]["sst"], count="1")
        print(f"  OK    search works ({r.get('total')} SST files)")
    except Exception as e:
        print(f"  FAIL  {type(e).__name__}: {e}")
        ok = False

    print(f"\n  Chlorophyll: {CHL.status(C.DATA)['note']}")
    print(f"  AIS        : {'key set' if ais.enabled() else 'no key (optional)'}")
    print(f"\n  Result: {'SAB THEEK HAI ✅' if ok else 'KUCH MISSING HAI — upar dekho'}\n")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="matsya")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run")
    p.add_argument("--local", default=None)
    p.add_argument("--max", type=int, default=None, help="kitne files download karein")
    p.add_argument("--no-wind", action="store_true")
    p.add_argument("--composite", action="store_true", help="kai files ka median")
    p.add_argument("--animation", action="store_true")
    p.add_argument("--ais", action="store_true")
    p.add_argument("--ais-seconds", type=int, default=30)
    p.add_argument("--ask", default=None)
    p.add_argument("--persona", default="fisher",
                   choices=["fisher", "researcher", "coast_guard", "authority"])
    p.add_argument("--serve", action="store_true")
    p.add_argument("--port", type=int, default=8000)

    p2 = sub.add_parser("serve")
    p2.add_argument("--local", default=None)
    p2.add_argument("--max", type=int, default=None)
    p2.add_argument("--port", type=int, default=8000)

    p3 = sub.add_parser("watch")
    p3.add_argument("--interval", type=int, default=30, help="minutes")
    p3.add_argument("--hours", type=int, default=24)
    p3.add_argument("--local", default=None)
    p3.add_argument("--max", type=int, default=None)

    p4 = sub.add_parser("ingest")
    p4.add_argument("--hours", type=int, default=24)
    p4.add_argument("--max", type=int, default=2)

    p5 = sub.add_parser("doctor")
    p6 = sub.add_parser("datasets")

    args = ap.parse_args(argv)
    cfg = C.load()

    if args.cmd == "run":
        if getattr(args, "max", None) is None:
            args.max = cfg["fetch"]["max_files"]
        return run_pipeline(args, cfg)

    if args.cmd == "serve":
        args.no_wind = False
        args.ask = None
        args.persona = "fisher"
        args.composite = False
        args.animation = False
        args.ais = False
        args.serve = True
        args.max = getattr(args, "max", None) or cfg["fetch"]["max_files"]
        return run_pipeline(args, cfg)

    if args.cmd == "watch":
        print(f"[watch] har {args.interval} minute me update (Ctrl+C se roko)")
        cycle = 0
        try:
            while True:
                cycle += 1
                print(f"\n===== cycle {cycle} — {datetime.now():%H:%M:%S} =====")
                a = argparse.Namespace(local=args.local,
                                       max=args.max or cfg["fetch"]["max_files"],
                                       no_wind=False, composite=True,
                                       animation=True, ais=False, ais_seconds=30,
                                       ask="Best fishing zone?", persona="fisher",
                                       serve=False, port=8000)
                try:
                    run_pipeline(a, cfg)
                except Exception as e:
                    print(f"  [cycle error] {type(e).__name__}: {e}")
                time.sleep(max(60, args.interval * 60))
        except KeyboardInterrupt:
            print("\n[watch] band kiya")
        return 0

    if args.cmd == "ingest":
        C.ensure_dirs()
        got = ingest.fetch_latest(cfg["datasets"]["sst"], args.hours, args.max)
        print(f"  {len(got)} file(s) data/ me")
        return 0

    if args.cmd == "doctor":
        return doctor(cfg)

    if args.cmd == "datasets":
        from mosdac_client import Mosdac
        m = Mosdac()
        for name, ds in cfg["datasets"].items():
            if not ds:
                print(f"  {name:14s} -> configured NAHI (NOTES.md)")
                continue
            try:
                r = m.search(ds, count="1")
                print(f"  {name:14s} -> {ds:16s} total={r.get('total')}")
            except Exception as e:
                print(f"  {name:14s} -> ERROR {e}")
        print(f"  {'chlorophyll':14s} -> {CHL.status(C.DATA)['note']}")
        print(f"  {'AIS':14s} -> {'key set' if ais.enabled() else 'no key (optional)'}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
