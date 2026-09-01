#!/usr/bin/env python3
"""
MOSDAC .h5 file inspector - file ke andar kya hai, sab bata deta hai.

    python inspect.py data                 # poora folder
    python inspect.py data/xxx.h5          # ek file
    python inspect.py data --values        # min/max/mean bhi (thoda slow)

Output: screen + out/h5inspect.txt
"""

import argparse
import sys
from pathlib import Path

try:
    import h5py
    import numpy as np
except ImportError:
    print("pehle install karo:  pip install h5py numpy")
    sys.exit(1)


def fmt(v):
    try:
        s = str(v)
        return s if len(s) < 70 else s[:67] + "..."
    except Exception:
        return "?"


def describe(group, prefix=""):
    """Saare datasets ki list with shape/dtype/attrs."""
    out = []

    def _v(name, obj):
        if isinstance(obj, h5py.Dataset):
            attrs = {k: fmt(obj.attrs[k]) for k in list(obj.attrs.keys())[:8]}
            out.append({
                "name": prefix + name,
                "shape": str(obj.shape),
                "dtype": str(obj.dtype),
                "size": int(obj.size),
                "attrs": attrs,
                "obj": obj,
            })
    group.visititems(_v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="data")
    ap.add_argument("--values", action="store_true", help="har dataset ka min/max/mean nikale")
    a = ap.parse_args()

    p = Path(a.path)
    files = sorted(p.rglob("*.h5")) if p.is_dir() else [p]
    if not files:
        print(f"{p} me koi .h5 file nahi mili")
        return 1

    Path("out").mkdir(exist_ok=True)
    lines = []
    say = lambda s: (print(s), lines.append(str(s)))

    for f in files:
        say("\n" + "=" * 70)
        say(f"FILE : {f.name}   ({f.stat().st_size/1024/1024:.2f} MB)")
        say("=" * 70)
        try:
            h5 = h5py.File(f, "r")
        except Exception as e:
            say(f"  ERROR khol nahi paye: {e}")
            continue

        say("\n--- File-level attributes ---")
        if len(h5.attrs) == 0:
            say("  (koi nahi)")
        for k, v in h5.attrs.items():
            say(f"  {k} = {fmt(v)}")

        ds = describe(h5)
        say(f"\n--- Datasets ({len(ds)}) ---")
        say(f"  {'NAME':42s} {'SHAPE':20s} {'DTYPE':12s} SIZE")
        for d in ds:
            say(f"  {d['name'][:42]:42s} {d['shape'][:20]:20s} {d['dtype'][:12]:12s} {d['size']:,}")

        say("\n--- Important datasets (detail) ---")
        for d in ds:
            low = d["name"].lower()
            if any(k in low for k in ("sst", "lat", "lon", "bt", "tbb", "img", "rad")) or d["size"] > 100000:
                say(f"\n  [{d['name']}]  shape={d['shape']} dtype={d['dtype']}")
                for k, v in d["attrs"].items():
                    say(f"      @{k} = {v}")
                if a.values:
                    try:
                        arr = np.array(d["obj"])
                        if arr.size > 4_000_000:
                            arr = arr[::4, ::4]
                        fa = arr[np.isfinite(arr)] if np.issubdtype(arr.dtype, np.floating) else arr
                        if fa.size:
                            say(f"      min={np.min(fa):.3f}  max={np.max(fa):.3f}  mean={np.mean(fa):.3f}")
                    except Exception as e:
                        say(f"      (values nahi nikale: {e})")
        h5.close()

    Path("out/h5inspect.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n\nSaved -> out/h5inspect.txt  (ise yahan paste kar do)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
