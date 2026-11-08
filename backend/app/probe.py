"""Probe local vendors' own websites for a product query.

Most small shops run Shopify or WooCommerce, which expose a predictable site search.
We try those two URL patterns and read product links from the result page. Sites without
a searchable shop simply return nothing. Fetches are small, capped and run with low
concurrency; personal use only.
"""
import asyncio

import httpx

from .models import Product, Vendor, VendorHit
from .scrapers.base import HEADERS, Source, parse

PATTERNS = [
    "/search?q={q}&type=product",  # Shopify
    "/?s={q}&post_type=product",  # WooCommerce
]
CONCURRENCY = 8
MAX_VENDORS = 60
PER_SITE_TIMEOUT = 7


async def probe_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, v: Vendor, query: str) -> VendorHit | None:
    base = (v.website or "").rstrip("/")
    if not base:
        return None
    async with sem:
        for pat in PATTERNS:
            src = Source(
                name=v.name,
                search_url=base + pat,
                base_url=base,
                item_selector='a[href*="/product"]',
            )
            url = src.url_for(query)
            try:
                r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=PER_SITE_TIMEOUT)
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                    continue
                products: list[Product] = parse(r.text, src, query, url)
            except (httpx.HTTPError, ValueError):
                continue
            if products:
                return VendorHit(vendor=v, search_url=url, products=products[:8])
    return None
