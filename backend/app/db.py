"""Postgres connection pool and schema (asyncpg)."""
import asyncio
import os

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://oyster:oyster@127.0.0.1:5433/oyster")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
    id              text PRIMARY KEY,
    name            text NOT NULL,
    kind            text NOT NULL,
    lat             double precision NOT NULL,
    lon             double precision NOT NULL,
    address         text NOT NULL DEFAULT '',
    website         text,
    phone           text,
    hours           text,
    km              real NOT NULL,
    minutes         integer NOT NULL,
    minutes_source  text NOT NULL DEFAULT 'estimate',
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS vendors_minutes_idx ON vendors (minutes);
CREATE INDEX IF NOT EXISTS vendors_kind_minutes_idx ON vendors (kind, minutes);

CREATE TABLE IF NOT EXISTS search_cache (
    key         text PRIMARY KEY,
    payload     jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta (
    key    text PRIMARY KEY,
    value  text NOT NULL
);
"""

pool: asyncpg.Pool | None = None


async def init(wait_seconds: int = 60) -> None:
    """Connect (retrying while the container starts) and create the schema."""
    global pool
    last: Exception | None = None
    for _ in range(wait_seconds):
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8)
            async with pool.acquire() as c:
                await c.execute(SCHEMA)
            return
        except (OSError, asyncpg.PostgresError) as e:
            last = e
            await asyncio.sleep(1)
    raise RuntimeError(f"Could not connect to Postgres at {DATABASE_URL}: {last}")


async def close() -> None:
    if pool:
        await pool.close()
