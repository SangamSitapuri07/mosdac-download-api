"""
Real data ingest: MOSDAC API se SST / wind files download + HDF5 padh kar grid banao.
"""

import sys
from pathlib import Path

import numpy as np

from . import config as C


# ---------------- HDF5 ----------------
def _attrs(ds):
    out = {}
    for k in ds.attrs.keys():
        try:
            v = np.array(ds.attrs[k]).flatten()
            out[str(k)] = v[0].decode() if v.dtype.kind in ("S", "U") else (v[0] if v.size == 1 else v)
        except Exception:
            pass
    return out


def _phys(ds):
    a = np.array(ds)
    at = _attrs(ds)
    arr = a.astype(np.float32 if a.dtype.itemsize <= 2 else np.float64)
    fill = at.get("_FillValue", at.get("missing_value"))
    if fill is not None:
        arr = np.where(arr == np.float32(fill), np.nan, arr)
    sf, ao = at.get("scale_factor"), at.get("add_offset")
    if sf not in (None, 0):
        arr = arr * float(np.array(sf).flatten()[0])
    if ao not in (None, 0):
        arr = arr + float(np.array(ao).flatten()[0])
    return arr, at


def list_datasets(path):
    import h5py
    with h5py.File(str(path), "r") as f:
        out = {}

        def _v(n, o):
            if hasattr(o, "shape"):
                out[n] = {"shape": o.shape, "dtype": str(o.dtype), "size": int(o.size)}
        f.visititems(_v)
        return out


def read_grid(path, prefer=None, kind="sst"):
    """
    HDF5 se variable + lat/lon nikalo.
    kind: 'sst' | 'wind'  (wind me speed ya u/v components dhoondhta hai)
    """
    import h5py

    with h5py.File(str(path), "r") as f:
        ds = {}

        def _v(n, o):
            if isinstance(o, h5py.Dataset):
                ds[n] = o
        f.visititems(_v)

        meta = {}
        for k, v in f.attrs.items():
            try:
                v2 = np.array(v).flatten()
                meta[str(k)] = v2[0].decode() if v2.dtype.kind in ("S", "U") else str(v2[0])
            except Exception:
                meta[str(k)] = str(v)[:60]

        names = list(ds.keys())
        var = None
        if prefer and prefer in ds:
            var = prefer
        if var is None and kind == "sst":
            for n in sorted(names):
                if n.lower() == "sst":
                    var = n
                    break
            if var is None:
                for n in sorted(names):
                    if "sst" in n.lower():
                        var = n
                        break
        if var is None and kind == "wind":
            lows = [n.lower() for n in names]
            for key in ("wind_speed", "wspd", "windspeed", "speed"):
                for n in names:
                    if key in n.lower() and "dir" not in n.lower():
                        var = n
                        break
                if var:
                    break
            if var is None:                       # u / v components?
                u = next((n for n in names if n.lower() in ("u", "uwind", "zonal", "u10")), None)
                v = next((n for n in names if n.lower() in ("v", "vwind", "meridional", "v10")), None)
                if u and v:
                    uu, _ = _phys(ds[u])
                    vv, _ = _phys(ds[v])
                    arr = np.sqrt(np.nan_to_num(uu) ** 2 + np.nan_to_num(vv) ** 2)
                    data, at = arr, {"units": "m s-1"}
                    var = f"sqrt({u}^2+{v}^2)"
                else:
                    lows = [n for n in names if n.lower() not in
                            ("latitude", "longitude", "lat", "lon", "geox", "geoy", "time")]
                    cands = [n for n in lows if ds[n].ndim >= 2 and ds[n].size > 10000]
                    var = max(cands, key=lambda n: ds[n].size) if cands else None
        if var is None:
            lows = [n for n in names if n.lower() not in
                    ("latitude", "longitude", "lat", "lon", "geox", "geoy", "time")]
            cands = [n for n in lows if ds[n].ndim >= 2 and ds[n].size > 10000]
            var = max(cands, key=lambda n: ds[n].size) if cands else None
        if var is None:
            return {"error": f"koi 2D variable nahi mila ({names})", "meta": meta}

        if "data" not in dir() or var in ds:
            data, at = _phys(ds[var])
        data = np.squeeze(data)

        lat = lon = None
        for n in ("Latitude", "latitude", "Lat", "lat"):
            if n in ds:
                lat, _ = _phys(ds[n]); lat = np.squeeze(lat); break
        for n in ("Longitude", "longitude", "Lon", "lon"):
            if n in ds:
                lon, _ = _phys(ds[n]); lon = np.squeeze(lon); break

        units = at.get("units") or ""
        if isinstance(units, bytes):
            units = units.decode()
        long_name = at.get("long_name") or var
        if isinstance(long_name, bytes):
            long_name = long_name.decode()

    if lat is not None and lon is not None and lat.ndim == 1 and lon.ndim == 1:
        lon, lat = np.meshgrid(lon, lat)
    if lat is not None and lat.shape != data.shape:
        lat = lon = None
    return {"data": data, "lat": lat, "lon": lon, "var": var,
            "units": units, "long_name": long_name, "meta": meta, "file": str(path)}


def kelvin_to_celsius(g):
    if g and str(g.get("units", "")).upper().startswith("K"):
        g["data"] = g["data"] - 273.15
        g["units"] = "degC"
    return g


def crop_and_downsample(g, bbox, max_grid=700):
    """bbox ke hisaab se kaato + grid chhota karo (memory/RAM bachao)."""
    data, lat, lon = g["data"], g.get("lat"), g.get("lon")
    if lat is not None and lon is not None and lat.shape == data.shape:
        lo1, la1, lo2, la2 = bbox
        m = (lon >= lo1) & (lon <= lo2) & (lat >= la1) & (lat <= la2)
        if m.any():
            rows = np.where(m.any(axis=1))[0]
            cols = np.where(m.any(axis=0))[0]
            r0, r1 = rows.min(), rows.max() + 1
            c0, c1 = cols.min(), cols.max() + 1
            data = data[r0:r1, c0:c1]
            lat = lat[r0:r1, c0:c1]
            lon = lon[r0:r1, c0:c1]
    step = max(1, int(max(data.shape) / max_grid) + 1)
    if step > 1:
        data = data[::step, ::step]
        if lat is not None:
            lat = lat[::step, ::step]
            lon = lon[::step, ::step]
    g["data"], g["lat"], g["lon"] = data, lat, lon
    g["step"] = step
    return g


# ---------------- MOSDAC download ----------------
def client():
    root = str(C.ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from mosdac_client import Mosdac
    return Mosdac()


def fetch_latest(dataset_id, hours_back=24, max_files=2, verbose=True):
    """MOSDAC se naye files lao (data/ me cache ke saath). Returns list of paths."""
    C.ensure_dirs()
    m = client()
    from datetime import datetime, timedelta
    end = datetime.utcnow()
    start = end - timedelta(hours=hours_back)
    res = m.search(dataset_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), count=100)
    ents = (res.get("entries") or [])[-max_files:]
    if not ents:
        if verbose:
            print(f"  [{dataset_id}] koi file nahi mila")
        return []
    m.login(retries=6)
    got = []
    for e in ents:
        dest = C.DATA / e["identifier"]
        if dest.exists() and dest.stat().st_size > 1000:
            if verbose:
                print(f"  [cache]  {e['identifier']}")
            got.append(dest)
            continue
        if verbose:
            print(f"  [download] {e['identifier']}")
        dest.write_bytes(m.download_bytes(e["id"]))
        got.append(dest)
    m.logout()
    return got


def load_local(folder):
    p = Path(folder)
    if p.is_file():
        return [p]
    return sorted(list(p.rglob("*.h5")) + list(p.rglob("*.H5")))
