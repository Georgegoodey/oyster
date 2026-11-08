"""Discover food vendors from OpenStreetMap, store them in Postgres, add drive times.

Data: Overpass API (free). Drive time: public OSRM demo server, with a straight-line
estimate stored first so vendors are usable immediately and upgraded batch by batch.
Refreshes run in the background; requests never wait on them. Personal-scale use only.
"""
import asyncio
import math
import time

import httpx

from . import db
from .models import Vendor

# Home: Surbiton / Kingston area.
HOME = (51.3925, -0.3040)
RADIUS_M = 35000  # generous box; travel time does the real filtering
REFRESH_AFTER_S = 7 * 24 * 3600
UA = {"User-Agent": "oyster-personal/0.1 (personal project)"}

KINDS = {
    "greengrocer": "Greengrocer",
    "farm": "Farm shop",
    "butcher": "Butcher",
    "deli": "Deli",
    "seafood": "Fishmonger",
    "bakery": "Bakery",
    "cheese": "Cheesemonger",
    "health_food": "Health food",
    "organic": "Organic",
    "marketplace": "Market",
}

QUERY = f"""[out:json][timeout:90];
(
  nwr["shop"~"^({'|'.join(k for k in KINDS if k != 'marketplace')})$"](around:{RADIUS_M},{HOME[0]},{HOME[1]});
  nwr["amenity"="marketplace"](around:{RADIUS_M},{HOME[0]},{HOME[1]});
);
out center tags 2500;"""

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Visible to the API so the page can say "still loading".
status = {"refreshing": False, "error": None}
_refresh_task: asyncio.Task | None = None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _address(t: dict) -> str:
    parts = [
        " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x),
        t.get("addr:suburb") or t.get("addr:city") or t.get("addr:town"),
        t.get("addr:postcode"),
    ]
    return ", ".join(p for p in parts if p)


def _normalise(el: dict) -> dict | None:
    t = el.get("tags", {})
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    name = t.get("name")
    kind = KINDS.get(t.get("shop") or "") or ("Market" if t.get("amenity") == "marketplace" else None)
    if not (name and lat and lon and kind):
        return None
    site = t.get("website") or t.get("contact:website")
    if site and not site.startswith("http"):
        site = "https://" + site
    km = haversine_km(HOME, (lat, lon))
    return {
        "id": f"{el['type']}/{el['id']}",
        "name": name,
        "kind": kind,
        "lat": lat,
        "lon": lon,
        "address": _address(t),
        "website": site,
        "phone": t.get("phone") or t.get("contact:phone"),
        "hours": t.get("opening_hours"),
        "km": round(km, 1),
        "minutes": round(km * 1.4 / 40 * 60),  # estimate: 1.4 road factor at ~40 km/h
    }


async def _overpass(client: httpx.AsyncClient) -> dict:
    last: Exception | None = None
    for _ in range(2):
        for url in OVERPASS:
            try:
                r = await client.post(url, data={"data": QUERY}, timeout=120, headers=UA)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as e:
                last = e
        await asyncio.sleep(5)
    raise RuntimeError(f"All Overpass servers failed: {last}")


UPSERT = """
INSERT INTO vendors (id, name, kind, lat, lon, address, website, phone, hours, km, minutes)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, kind = EXCLUDED.kind, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
    address = EXCLUDED.address, website = EXCLUDED.website, phone = EXCLUDED.phone,
    hours = EXCLUDED.hours, km = EXCLUDED.km, updated_at = now(),
    -- keep a real drive time if we already have one
    minutes = CASE WHEN vendors.minutes_source = 'driving' THEN vendors.minutes ELSE EXCLUDED.minutes END
"""


async def _upgrade_drive_times(client: httpx.AsyncClient) -> None:
    """Replace estimates with real OSRM drive times, one batch at a time (usable throughout)."""
    rows = await db.pool.fetch("SELECT id, lat, lon FROM vendors WHERE minutes_source = 'estimate' ORDER BY km")
    for i in range(0, len(rows), 90):
        batch = rows[i : i + 90]
        coords = ";".join([f"{HOME[1]},{HOME[0]}"] + [f"{r['lon']},{r['lat']}" for r in batch])
        url = f"https://router.project-osrm.org/table/v1/driving/{coords}?sources=0&annotations=duration"
        try:
            r = await client.get(url, timeout=30, headers=UA)
            durations = r.json()["durations"][0][1:]
        except Exception:
            continue  # leave this batch on estimates; the next refresh retries it
        updates = [(round(d / 60), b["id"]) for b, d in zip(batch, durations) if d is not None]
        await db.pool.executemany(
            "UPDATE vendors SET minutes = $1, minutes_source = 'driving' WHERE id = $2", updates
        )
        await asyncio.sleep(1)  # be polite to the demo server


async def refresh_vendors() -> None:
    status["refreshing"], status["error"] = True, None
    try:
        async with httpx.AsyncClient() as client:
            data = await _overpass(client)
            seen, rows = set(), []
            for el in data.get("elements", []):
                v = _normalise(el)
                if not v:
                    continue
                dedupe = (v["name"].lower(), round(v["lat"], 3))
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rows.append(
                    (v["id"], v["name"], v["kind"], v["lat"], v["lon"], v["address"], v["website"],
                     v["phone"], v["hours"], v["km"], v["minutes"])
                )
            await db.pool.executemany(UPSERT, rows)  # vendors are queryable from here on
            await db.pool.execute(
                "INSERT INTO meta (key, value) VALUES ('vendors_refreshed', $1) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                str(time.time()),
            )
            await _upgrade_drive_times(client)
    except Exception as e:
        status["error"] = str(e)
    finally:
        status["refreshing"] = False


async def ensure_fresh() -> None:
    """Start a background refresh if the table is empty or stale. Never blocks."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return
    last = await db.pool.fetchval("SELECT value FROM meta WHERE key = 'vendors_refreshed'")
    if last is None or time.time() - float(last) > REFRESH_AFTER_S:
        _refresh_task = asyncio.create_task(refresh_vendors())


async def query_vendors(max_minutes: int, kind: str | None = None, q: str | None = None) -> list[Vendor]:
    sql = (
        "SELECT id, name, kind, lat, lon, address, website, phone, hours, km, minutes, minutes_source "
        "FROM vendors WHERE minutes <= $1"
    )
    args: list = [max_minutes]
    if kind:
        args.append(kind)
        sql += f" AND lower(kind) = lower(${len(args)})"
    if q:
        args.append(f"%{q}%")
        sql += f" AND (name || ' ' || kind || ' ' || address) ILIKE ${len(args)}"
    rows = await db.pool.fetch(sql + " ORDER BY minutes, name", *args)
    return [Vendor(**dict(r)) for r in rows]
