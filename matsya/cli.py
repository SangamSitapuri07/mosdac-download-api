"""MATSYA CLI: run / serve / ingest / datasets  — sab real data."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config as C, geo_tools as G, ingest, physics as P, report, report_v2
from .agents.state import AgentState
from .orchestrator import Orchestrator


def _analyze_file(path, kind, cfg, verbose=True):
    g = ingest.read_grid(path, kind=kind)
    if "error" in g:
        if verbose:
            print(f"    [skip] {Path(path).name}: {g['error'][:70]}")
        return None
    if kind == "sst":
        ingest.kelvin_to_celsius(g)
    ingest.crop_and_downsample(g, cfg["region"]["bbox"], cfg["region"]["max_grid"])
    return g


def build_state(files, cfg, query, persona, no_wind=False):
    """Real files -> AgentState (grids + meta)."""
    print("\n[analyze] grids padh rahe hain...")
    sst_g = None
    for f in files["sst"]:
        sst_g = _analyze_file(f, "sst", cfg)
        if sst_g:
            print(f"    SST  {Path(f).name} -> {sst_g['data'].shape} {sst_g['units']}")
            break
    if sst_g is None:
        raise SystemExit("[error] koi SST file parse nahi hui")

    wind_g = None
    if not no_wind:
        for f in files["wind"]:
            wind_g = _analyze_file(f, "wind", cfg)
            if wind_g:
                print(f"    WIND {Path(f).name} -> {wind_g['data'].shape} {wind_g['units']}")
                break
    if wind_g is None:
        print("    (wind layer nahi mila)")

    sst, lat, lon = sst_g["data"], sst_g.get("lat"), sst_g.get("lon")
    if lat is None or lon is None or lat.shape != sst.shape:
        raise SystemExit("[error] is file me lat/lon grid nahi mila")

    wind = None
    if wind_g is not None:
        if wind_g["data"].shape == sst.shape:
            wind = wind_g["data"]
        else:
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

    print("[analyze] physics + geo...")
    grad = P.gradient_c_per_km(sst, lat, lon)
    in_eez = G.eez_mask(lon, lat, "India")
    dist = G.coast_distance_km(lon, lat)
    print(f"    valid px {int(np.isfinite(sst).sum()):,} | EEZ px {int(in_eez.sum()):,}")

    st = AgentState(user_query=query, persona=persona)
    st.grids = {"lat": lat, "lon": lon, "sst": sst, "grad": grad,
                "wind": wind, "dist": dist, "eez": in_eez, "score": None}
    st.meta = {"cfg": cfg,
               "sst_file": Path(files["sst"][0]).name if files["sst"] else "",
               "sst_meta": sst_g["meta"],
               "wind_file": Path(files["wind"][0]).name if files["wind"] else "",
               "wind_meta": (wind_g or {}).get("meta", {}),
               "files": {k: [str(x) for x in v] for k, v in files.items()}}
    return st


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
                                           cfg["fetch"]["max_files"])
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
                     args.persona, args.no_wind)

    print("\n[agents] swarm chal raha hai...")
    st = Orchestrator(cfg, audit_dir=out / "audit").run(st)
    for s in st.trace.steps:
        print(f"    {s['agent']:16s} {s['ms']:8.1f} ms  [{s['status']}]")
    print(f"    TOTAL           {st.trace.total_ms:8.1f} ms")
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

    prov = [
        {"layer": "SST (fronts + PFZ)", "source": "ISRO MOSDAC (INSAT-3DR)",
         "dataset": cfg["datasets"]["sst"], "file": st.meta["sst_file"],
         "time": str(st.meta["sst_meta"].get("Acquisition_Start_Time", "")), "status": "REAL"},
        {"layer": "Sea wind (safety)",
         "source": "ISRO MOSDAC (INSAT-3DR)" if g["wind"] is not None else "not fetched",
         "dataset": cfg["datasets"]["wind"] or "-",
         "file": st.meta["wind_file"] or "-",
         "time": str(st.meta["wind_meta"].get("Acquisition_Start_Time", "")),
         "status": "REAL" if g["wind"] is not None else "NOT AVAILABLE"},
        {"layer": "EEZ boundary", "source": "MarineRegions / VLIZ",
         "dataset": "WFS:MarineRegions:eez", "file": "geo/eez.json",
         "time": "v12 (2023-10-25)", "status": "REAL"},
        {"layer": "Coastline", "source": "Natural Earth",
         "dataset": "ne_50m_coastline", "file": "geo/coastline.json",
         "time": "v5.0", "status": "REAL"},
        {"layer": "Chlorophyll-a", "source": "MOSDAC API me NAHI",
         "dataset": "-", "file": "-", "time": "-", "status": "PENDING (NOTES.md)"},
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

    (out / "summary.json").write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "query": st.user_query, "persona": st.persona, "intent": st.intent,
        "region": cfg["region"],
        "files": st.meta["files"],
        "stats": {
            "valid_pixels": int(np.isfinite(g["sst"]).sum()),
            "sst_min_c": round(float(np.nanmin(g["sst"])), 2),
            "sst_max_c": round(float(np.nanmax(g["sst"])), 2),
            "front_max_c_per_km": round(float(np.nanmax(g["grad"])), 4),
            "wind_max_ms": round(float(np.nanmax(g["wind"])), 2) if g["wind"] is not None else None,
            "eez_pixels": int(g["eez"].sum()),
            "pfz_max": round(float(np.nanmax(g["score"])), 1),
        },
        "top_spots": spots[:12],
        "final": st.final,
        "agents": st.trace.steps,
        "total_ms": st.trace.total_ms,
        "provenance": prov,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  ✅ {tac}          <-- TACTICAL COMMAND CENTER")
    print(f"     {out/'index.html'}")
    print(f"     {out/'pfz_map.png'}")
    print(f"     {out/'pfz_grid.csv'}")
    print(f"     {out/'summary.json'}")
    print(f"     {out/'audit/execution_audit.jsonl'}")

    if args.serve:
        from .server import serve
        serve(args.port, st, Path(tac).read_text(encoding="utf-8"), cfg)
    else:
        print("\n  Live query console chahiye?  python matsya.py serve\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="matsya")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run")
    p.add_argument("--local", default=None)
    p.add_argument("--no-wind", action="store_true")
    p.add_argument("--ask", default=None, help="natural language query")
    p.add_argument("--persona", default="fisher",
                   choices=["fisher", "researcher", "coast_guard", "authority"])
    p.add_argument("--serve", action="store_true")
    p.add_argument("--port", type=int, default=8000)

    p2 = sub.add_parser("serve")
    p2.add_argument("--local", default=None)
    p2.add_argument("--port", type=int, default=8000)

    p3 = sub.add_parser("ingest")
    p3.add_argument("--hours", type=int, default=24)
    p3.add_argument("--max", type=int, default=2)

    p4 = sub.add_parser("datasets")

    args = ap.parse_args(argv)
    cfg = C.load()

    if args.cmd == "run":
        return run_pipeline(args, cfg)
    if args.cmd == "serve":
        args.no_wind = False
        args.ask = args.ask if hasattr(args, "ask") else None
        args.persona = "fisher"
        args.serve = True
        if not hasattr(args, "port"):
            args.port = 8000
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
                print(f"  {name:14s} -> ERROR {e}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
