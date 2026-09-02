"""
MULTI-FILE COMPOSITE + TIME SERIES + ANIMATION (sab real files se).

Cloud gaps bharta hai (median over N files) aur waqt ke saath SST ka trend dikhata hai.
"""

import numpy as np

from . import config as C, ingest


def build(files, cfg, kind="sst", max_files=8, verbose=True):
    """Kai files ka median composite (cloud kam, coverage zyada)."""
    bbox = cfg["region"]["bbox"]
    grids = []
    for f in files[-max_files:]:
        g = ingest.read_grid(str(f), kind=kind)
        if "error" in g:
            continue
        if kind == "sst":
            ingest.kelvin_to_celsius(g)
        ingest.crop_and_downsample(g, bbox, cfg["region"]["max_grid"])
        grids.append(g)
        if verbose:
            print(f"    + {f.name} -> {g['data'].shape}")
    if not grids:
        return None

    shape = min(grids, key=lambda g: g["data"].size)["data"].shape
    stack = []
    for g in grids:
        d = g["data"]
        if d.shape != shape:
            yi = (np.linspace(0, d.shape[0] - 1, shape[0])).astype(int)
            xi = (np.linspace(0, d.shape[1] - 1, shape[1])).astype(int)
            d = d[np.ix_(yi, xi)]
        stack.append(d)
    stack = np.stack(stack)
    with np.errstate(all="ignore"):
        med = np.nanmedian(stack, axis=0)
    med[~np.isfinite(med)] = np.nan

    base = min(grids, key=lambda g: g["data"].size)
    out = {"data": med, "lat": base["lat"], "lon": base["lon"],
           "units": grids[0]["units"], "var": grids[0]["var"],
           "n_files": len(grids),
           "meta": {"composite_of": [f.name for g, f in zip(grids, files[-max_files:])]}}
    if verbose:
        print(f"    composite: {len(grids)} files, coverage "
              f"{np.isfinite(med).mean() * 100:.1f}%")
    return out


def timeseries(files, cfg, kind="sst", max_files=24):
    """Har file ke liye mean/min/max SST + timestamp."""
    bbox = cfg["region"]["bbox"]
    rows = []
    for f in files[-max_files:]:
        g = ingest.read_grid(str(f), kind=kind)
        if "error" in g:
            continue
        if kind == "sst":
            ingest.kelvin_to_celsius(g)
        ingest.crop_and_downsample(g, bbox, 250)
        d = g["data"]
        if not np.isfinite(d).any():
            continue
        rows.append({
            "file": f.name,
            "time": str(g["meta"].get("Acquisition_Start_Time", f.name)),
            "mean": float(np.nanmean(d)), "min": float(np.nanmin(d)),
            "max": float(np.nanmax(d)),
            "valid": int(np.isfinite(d).sum()),
        })
    return rows


def plot_timeseries(rows, out_png, title="SST time series (real MOSDAC files)"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rows:
        return None
    y = [r["mean"] for r in rows]
    lo = [r["min"] for r in rows]
    hi = [r["max"] for r in rows]
    x = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(9, 3.4), dpi=110)
    ax.fill_between(x, lo, hi, color="#0ea5e9", alpha=0.22, label="min–max")
    ax.plot(x, y, color="#0284c7", lw=2, marker="o", ms=3.5, label="mean SST")
    ax.set_ylabel("°C"); ax.set_xlabel("file (time order)")
    ax.set_title(title, fontsize=11)
    ax.grid(alpha=0.3, ls="--", lw=0.5); ax.legend(fontsize=8)
    labels = [r["time"][:16] for r in rows]
    step = max(1, len(labels) // 8)
    ax.set_xticks(x[::step]); ax.set_xticklabels(labels[::step], rotation=35, fontsize=7)
    fig.tight_layout(); fig.savefig(out_png, bbox_inches="tight"); plt.close(fig)
    return str(out_png)


def animation(files, cfg, out_gif, max_frames=12, fps=2):
    """Real files se SST animation GIF."""
    bbox = cfg["region"]["bbox"]
    frames = []
    for f in files[-max_frames:]:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            g = ingest.read_grid(str(f), kind="sst")
            if "error" in g:
                continue
            ingest.kelvin_to_celsius(g)
            ingest.crop_and_downsample(g, bbox, 300)
            fig, ax = plt.subplots(figsize=(6, 4.4), dpi=90)
            d, lat, lon = g["data"], g.get("lat"), g.get("lon")
            if lat is not None and lon is not None and lat.shape == d.shape:
                ok = np.isfinite(d) & np.isfinite(lat) & np.isfinite(lon)
                ax.pcolormesh(np.where(ok, lon, 0), np.where(ok, lat, 0),
                              np.where(ok, d, np.nan), cmap="turbo",
                              vmin=22, vmax=33, shading="auto")
            else:
                ax.imshow(d, cmap="turbo", vmin=22, vmax=33, aspect="auto")
            try:
                from . import geo_tools as G
                from .report import _basemap
                _basemap(ax)
            except Exception:
                pass
            ax.set_facecolor("#dbe3ec")
            ax.set_xlim(bbox[0], bbox[2]); ax.set_ylim(bbox[1], bbox[3])
            ax.set_title(f"{f.name[:34]}\n{g['meta'].get('Acquisition_Start_Time','')}",
                         fontsize=8)
            fig.tight_layout()
            fig.canvas.draw()
            w, h = fig.canvas.get_width_height()
            buf = np.asarray(fig.canvas.buffer_rgba()).reshape(h, w, 4)
            frames.append(buf[:, :, :3])
            plt.close(fig)
        except Exception:
            continue
    if len(frames) < 2:
        return None
    try:
        from PIL import Image
        imgs = [Image.fromarray(f) for f in frames]
        imgs[0].save(out_gif, save_all=True, append_images=imgs[1:],
                     duration=int(1000 / fps), loop=0)
        return str(out_gif)
    except Exception:
        return None
