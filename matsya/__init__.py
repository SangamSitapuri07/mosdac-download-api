"""
MATSYA - Real-data marine fishing advisory from ISRO MOSDAC satellites.

100% real data:
  * SST        : INSAT-3DR L2B SST  (MOSDAC API)   -> thermal fronts, PFZ
  * Wind       : INSAT-3DR L2P VSW  (MOSDAC API)   -> sea state / safety
  * EEZ        : MarineRegions EEZ v12 (VLIZ)      -> legal fishing zone
  * Coastline  : Natural Earth                     -> distance from coast

Koi bhi simulated/dummy data nahi. Jo layer uplabdh nahi hai (jaise chlorophyll),
wo NOTES.md me "pending" likha hai aur code usko gracefully skip karta hai.
"""

__version__ = "1.0.0"
