"""
AIS vessel traffic — SIRF real data.

Agar AISSTREAM_API_KEY nahi hai to ye kuch bhi return nahi karta —
koi simulated/fake vessel generate NAHI hota (ORCA simulation use karta hai,
hum nahi karte — ye hamaari design choice hai, NOTES.md me likha hai).

Free key: https://aisstream.io  (email se mil jata hai)
"""

import json
import os
import threading
import time

from .config import CACHE

BOX = [30.0, -45.0, 115.0, 35.0]      # minLon, minLat, maxLon, maxLat


def enabled():
    return bool(os.getenv("AISSTREAM_API_KEY"))


def collect(seconds=30, bbox=None, out_json=None):
    """AISSTREAM se live vessel positions collect karo (agar key ho)."""
    if not enabled():
        return {"available": False, "reason": "AISSTREAM_API_KEY set nahi hai",
                "vessels": []}
    try:
        import websockets
    except ImportError:
        return {"available": False,
                "reason": "pip install websockets (optional dependency)",
                "vessels": []}

    box = bbox or BOX
    vessels, stop = {}, threading.Event()

    async def _run():
        import asyncio
        uri = "wss://stream.aisstream.io/v0/stream"
        sub = {"APIKey": os.environ["AISSTREAM_API_KEY"],
               "BoundingBoxes": [[[box[1], box[0]], [box[3], box[2]]]]}
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps(sub))
            end = time.time() + seconds
            while time.time() < end and not stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    d = json.loads(msg)
                    m = d.get("Message", {})
                    pos = m.get("PositionReport")
                    if not pos:
                        continue
                    mmsi = pos.get("UserID")
                    vessels[mmsi] = {
                        "mmsi": mmsi,
                        "lat": pos.get("Latitude"),
                        "lon": pos.get("Longitude"),
                        "sog_kn": round(pos.get("Sog", 0) * 10) / 10,
                        "cog": pos.get("Cog"),
                        "ts": time.strftime("%H:%M:%S"),
                    }
                except Exception:
                    continue

    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(_run())
    except RuntimeError:
        t = threading.Thread(target=lambda: asyncio.run(_run()), daemon=True)
        t.start()
        t.join(seconds + 5)

    out = {"available": True, "count": len(vessels),
           "window_s": seconds, "vessels": list(vessels.values())}
    if out_json:
        CACHE.mkdir(exist_ok=True)
        Path = out_json
        Path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
