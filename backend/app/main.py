import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db, vendors
from .models import Vendor
from .probe import CONCURRENCY, MAX_VENDORS, probe_one
from .scrapers.base import scrape
from .scrapers.sources import SOURCES

CACHE_MINUTES = 10


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    await vendors.ensure_fresh()  # background; never blocks startup
    yield
    await db.close()


app = FastAPI(title="Oyster", lifespan=lifespan)

# Friends-only site: allow the Vite dev server; extend via CORS_ORIGINS for LAN use.
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    count = await db.pool.fetchval("SELECT count(*) FROM vendors")
    driving = await db.pool.fetchval("SELECT count(*) FROM vendors WHERE minutes_source = 'driving'")
    return {"vendors": count, "with_drive_times": driving, **vendors.status}


@app.get("/api/vendors", response_model=list[Vendor])
async def list_vendors(
    max_minutes: int = Query(60, ge=5, le=120),
    kind: str | None = None,
    q: str | None = Query(None, max_length=60),
):
    return await vendors.query_vendors(max_minutes, kind, q)


def _line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


async def _search_events(q: str, max_minutes: int):
    """Yield newline-delimited JSON events as each source/vendor finishes."""
    key = f"{q.strip().lower()}|{max_minutes}"
    cached = await db.pool.fetchval(
        "SELECT payload FROM search_cache WHERE key = $1 AND created_at > now() - make_interval(mins => $2)",
        key,
        CACHE_MINUTES,
    )
    if cached:
        for ev in json.loads(cached):
            yield _line(ev)
        return

    local = [v for v in await vendors.query_vendors(max_minutes) if v.website][:MAX_VENDORS]
    total = len(SOURCES) + len(local)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient() as client:

        async def run_source(src):
            res = await scrape(client, src, q)
            await queue.put({"type": "source", "result": res.model_dump(mode="json")})

        async def run_vendor(v):
            hit = await probe_one(client, sem, v, q)
            await queue.put({"type": "vendor", "hit": hit.model_dump(mode="json") if hit else None})

        tasks = [asyncio.create_task(run_source(s)) for s in SOURCES]
        tasks += [asyncio.create_task(run_vendor(v)) for v in local]
        events = [{"type": "start", "total": total, "sources": len(SOURCES), "vendors": len(local)}]
        yield _line(events[0])
        try:
            for done in range(1, total + 1):
                ev = await queue.get()
                ev["done"] = done
                events.append(ev)
                yield _line(ev)
        finally:
            for t in tasks:  # client went away: stop the remaining work
                t.cancel()

    events.append({"type": "end"})
    yield _line(events[-1])
    await db.pool.execute(
        "INSERT INTO search_cache (key, payload, created_at) VALUES ($1, $2::jsonb, now()) "
        "ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, created_at = now()",
        key,
        json.dumps(events),
    )


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=2, max_length=60),
    max_minutes: int = Query(60, ge=5, le=120),
):
    if not db.pool:
        raise HTTPException(503, "Database not ready")
    return StreamingResponse(_search_events(q, max_minutes), media_type="application/x-ndjson")
