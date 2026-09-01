#!/usr/bin/env python3
"""
Example: downloaded .h5 (HDF5) file ko padho - data values, CSV export, map.

    pip install h5py numpy matplotlib
    python examples/read_h5.py data/3RIMG_01SEP2026_0715_L2B_SST_V02R00.h5

Agar file local nahi hai to API se direct memory me manga lega:
    python examples/read_h5.py --id 18334808
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import h5py
    import numpy as np
except ImportError:
    print("pehle install karo:  pip install h5py numpy")
    sys.exit(1)


def show(name, obj):
    if isinstance(obj, h5py.Dataset):
        print(f"  DATASET {name:45s} shape={str(obj.shape):18s} dtype={obj.dtype}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rec_id = next((sys.argv[i + 1] for i, a in enumerate(sys.argv)
                   if a == "--id"), None)

    if rec_id:
        from mosdac_client import Mosdac
        print(f"API se file mangwa rahe hain (id={rec_id})...")
        f = Mosdac().read_h5(rec_id)          # disk pe kuch save nahi hota
        src = f"memory (record {rec_id})"
    else:
        path = args[0] if args else "data"
        p = Path(path)
        if p.is_dir():
            files = sorted(p.rglob("*.h5"))
            if not files:
                print(f"{p} me koi .h5 file nahi mili")
                return 1
            p = files[0]
        print(f"File: {p}  ({p.stat().st_size/1024/1024:.2f} MB)")
        f = h5py.File(p, "r")
        src = str(p)

    print(f"\n--- Structure ({src}) ---")
    f.visititems(show)

    # pehla bada 2D dataset dhoondo (SST / image band)
    target, target_name = None, None
    f.visititems(lambda n, o: None)
    for name, obj in find_datasets(f):
        if obj.ndim >= 2 and obj.size > 1000:
            target, target_name = obj, name
            break

    if target is None:
        print("\nkoi 2D dataset nahi mila")
        return 0

    arr = np.array(target)
    print(f"\n--- '{target_name}' ---")
    print(f"shape : {arr.shape}   dtype: {arr.dtype}")
    finite = arr[np.isfinite(arr)] if np.issubdtype(arr.dtype, np.floating) else arr
    if finite.size:
        print(f"min   : {np.nanmin(finite):.2f}   max: {np.nanmax(finite):.2f}   "
              f"mean: {np.nanmean(finite):.2f}")

    # CSV me nikalna ho to (sample - pehli 5 row)
    csv_path = Path("data") / "sample.csv"
    csv_path.parent.mkdir(exist_ok=True)
    np.savetxt(csv_path, arr[:5, :5] if arr.ndim >= 2 else arr[:5],
               delimiter=",", fmt="%.2f")
    print(f"sample CSV (5x5): {csv_path}")

    # map banana ho to (matplotlib ho to)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        png = Path("data") / "preview.png"
        plt.figure(figsize=(8, 6))
        plt.imshow(np.squeeze(arr)[::4, ::4], cmap="jet", aspect="auto")
        plt.colorbar(label=target_name.split("/")[-1])
        plt.title(target_name)
        plt.tight_layout()
        plt.savefig(png, dpi=100)
        print(f"preview image   : {png}")
    except ImportError:
        print("(matplotlib nahi hai - pip install matplotlib kar ke map bana sakte ho)")
    except Exception as e:
        print("plot skip:", e)

    return 0


def find_datasets(f):
    out = []

    def _v(name, obj):
        if isinstance(obj, h5py.Dataset):
            out.append((name, obj))
    f.visititems(_v)
    return out


if __name__ == "__main__":
    sys.exit(main())
