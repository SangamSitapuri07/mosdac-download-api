"""
CHLOROPHYLL-a layer (optional).

MOSDAC API me OCM chlorophyll abhi uplabdh NAHI hai — isliye ye layer
tabhi chalti hai jab tumhare paas real chlorophyll file ho:

  data/ me koi bhi file jiske naam me CHL / CHLA / OCM ho
  (Oceansat/EOS-06 OCM L2C, Bhuvan se download, ya Copernicus/NASA OceanColor)

Agar file na mile to layer skip ho jati hai aur PFZ score baaki layers se banta hai.
KABHI bhi fake chlorophyll values generate nahi kiye jate.
"""

import re
from pathlib import Path

import numpy as np

from . import config as C, ingest

PATTERNS = re.compile(r"(chl|chla|chlorophyll|ocm)", re.I)


def find_files(folder):
    p = Path(folder)
    if p.is_file():
        return [p] if PATTERNS.search(p.name) else []
    out = []
    for ext in ("*.h5", "*.H5", "*.nc", "*.tif", "*.tiff"):
        out += [f for f in p.rglob(ext) if PATTERNS.search(f.name)]
    return sorted(out)


def load(path, bbox, max_grid=700):
    """Chlorophyll grid (mg/m3) padho. NetCDF/GeoTIFF ke liye best-effort."""
    p = Path(path)
    if p.suffix.lower() in (".h5", ".h5"):
        g = ingest.read_grid(str(p), kind="chlorophyll")
        if "error" in g:
            return None
        # OCM L2C chlorophyll aksar log10 ya mg/m3 me hota hai
        d = g["data"]
        med = float(np.nanmedian(d))
        if med < 0 or med > 100:         # log scale ya invalid
            d = np.where(np.isfinite(d), 10.0 ** d, np.nan) if -5 < med < 5 else d
        g["data"] = np.clip(d, 0, 100)
        g["units"] = "mg m-3"
        ingest.crop_and_downsample(g, bbox, max_grid)
        return g
    # NetCDF
    if p.suffix.lower() == ".nc":
        try:
            from netCDF4 import Dataset
        except ImportError:
            try:
                from scipy.io import netcdf_file as Dataset
            except ImportError:
                return None
        try:
            f = Dataset(str(p))
            varnames = [v for v in f.variables]
            key = next((v for v in varnames if PATTERNS.search(v)), None)
            if key is None:
                return None
            d = np.array(f.variables[key][:]).squeeze()
            lat = np.array(f.variables["lat"][:]) if "lat" in varnames else None
            lon = np.array(f.variables["lon"][:]) if "lon" in varnames else None
            if lat is None:
                lat = np.array(f.variables["latitude"][:])
                lon = np.array(f.variables["longitude"][:])
            if lat.ndim == 1 and lon.ndim == 1:
                lon, lat = np.meshgrid(lon, lat)
            g = {"data": np.where(d > 100, np.nan, d).astype(float),
                 "lat": lat, "lon": lon, "units": "mg m-3",
                 "meta": {"file": p.name}}
            ingest.crop_and_downsample(g, bbox, max_grid)
            return g
        except Exception:
            return None
    # GeoTIFF
    if p.suffix.lower() in (".tif", ".tiff"):
        try:
            import rasterio
        except ImportError:
            return None
        with rasterio.open(str(p)) as src:
            d = src.read(1).astype(float)
            d = np.where(d <= 0, np.nan, d)
            h, w = d.shape
            lons = np.linspace(src.bounds.left, src.bounds.right, w)
            lats = np.linspace(src.bounds.top, src.bounds.bottom, h)
            lon, lat = np.meshgrid(lons, lats)
            g = {"data": d, "lat": lat, "lon": lon, "units": "mg m-3",
                 "meta": {"file": p.name}}
            ingest.crop_and_downsample(g, bbox, max_grid)
            return g
    return None


def resample_to(chl_g, lat, lon):
    """Chlorophyll grid ko SST grid pe lao (nearest neighbour)."""
    if chl_g is None:
        return None
    clat, clon, data = chl_g.get("lat"), chl_g.get("lon"), chl_g["data"]
    if clat is None or clon is None:
        return None
    try:
        from scipy.interpolate import griddata
        pts = np.column_stack([clon.ravel(), clat.ravel()])
        vals = data.ravel()
        ok = np.isfinite(vals) & np.isfinite(pts).all(axis=1)
        if ok.sum() < 10:
            return None
        out = griddata(pts[ok], vals[ok], (lon, lat), method="nearest")
        return out
    except Exception:
        return None


def status(data_folder):
    files = find_files(data_folder or C.DATA)
    return {"available": bool(files), "files": [str(f.name) for f in files],
            "note": "MOSDAC API me OCM chlorophyll nahi mila — Bahuvan/NASA/"
                    "Copernicus se file laakar data/ me daalo (NOTES.md)"}
