"""Shared scraping helpers. Each source supplies a search URL and (optionally)
CSS selectors; JSON-LD structured data is used as the fallback."""
import asyncio
import json
import threading
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from ..models import Product, SourceResult

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

BROWSER_TIMEOUT_MS = 20000
PRICE_IN_NAME = re.compile(r"^(.*?)\s+((?:from\s+)?£\d[\d.,]*.*)$", re.I)
KING = re.compile(r"king\s+(oyster|trumpet)|eryngii", re.I)


@dataclass
class Source:
    name: str
    search_url: str  # contains {q}
    base_url: str = ""
    item_selector: str | None = None
    name_selector: str | None = None
    price_selector: str | None = None
    link_selector: str = "a"
    image_selector: str = "img"
    # Fallback for sites whose search is rendered by JavaScript: known product pages
    # (fetched directly; their JSON-LD is read and filtered by the query).
    product_urls: list[str] = field(default_factory=list)
    # Retry with headless Chromium (Playwright) if plain HTTP is refused or times out.
    use_browser: bool = False

    def url_for(self, query: str) -> str:
        return self.search_url.format(q=quote_plus(query))


def _text(el) -> str | None:
    return el.get_text(" ", strip=True) if el else None


def _jsonld_products(soup: BeautifulSoup, src: Source, page_url: str = "") -> list[Product]:
    out: list[Product] = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types and node.get("name"):
                offers = node.get("offers")
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                price = None
                if isinstance(offers, dict) and offers.get("price"):
                    price = f"£{offers['price']}"
                img = node.get("image")
                if isinstance(img, list):
                    img = img[0] if img else None
                out.append(
                    Product(
                        source=src.name,
                        name=str(node["name"]),
                        price=price,
                        url=urljoin(src.base_url, node.get("url") or node.get("@id") or page_url),
                        image=img if isinstance(img, str) else None,
                    )
                )
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(tag.string or ""))
        except (ValueError, TypeError):
            continue
    return out


def _selector_products(soup: BeautifulSoup, src: Source) -> list[Product]:
    if not src.item_selector:
        return []
    out = []
    for item in soup.select(src.item_selector):
        name_el = item.select_one(src.name_selector) if src.name_selector else item
        link_el = item if item.name == "a" else item.select_one(src.link_selector)
        name = _text(name_el)
        href = link_el.get("href") if link_el else None
        if not name or not href:
            continue
        img = item.select_one(src.image_selector)
        price = _text(item.select_one(src.price_selector)) if src.price_selector else None
        if not price:  # price is sometimes inside the link text, e.g. "Kit From £22.50"
            m = PRICE_IN_NAME.match(name)
            if m:
                name, price = m.group(1), m.group(2)
        out.append(
            Product(
                source=src.name,
                name=name,
                price=price,
                url=urljoin(src.base_url, href),
                image=urljoin(src.base_url, img.get("src")) if img and img.get("src") else None,
            )
        )
    return out


def parse(html: str, src: Source, query: str, page_url: str = "") -> list[Product]:
    soup = BeautifulSoup(html, "lxml")
    products = _selector_products(soup, src) or _jsonld_products(soup, src, page_url)
    wanted = [w for w in query.lower().split() if w]
    q = query.lower()
    exclude_king = "oyster" in q and "king" not in q  # oysters != king oysters
    seen, result = set(), []
    for p in products:
        lname = p.name.lower()
        if exclude_king and KING.search(p.name):
            continue
        if not all(w.rstrip("s") in lname for w in wanted):
            continue
        key = p.url.split("?")[0].split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result[:20]


async def _get(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=12)
    r.raise_for_status()
    return r.text


_browser_lock = threading.Lock()


def _browser_fetch_sync(url: str) -> str:
    """Render a page in headless Chromium. Runs in a worker thread (Playwright's sync
    API) so it doesn't depend on the event loop type. Raises on navigation failure."""
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    with _browser_lock, sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-http2"])
        try:
            ctx = browser.new_context(locale="en-GB", user_agent=HEADERS["User-Agent"])
            page = ctx.new_page()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                if resp is not None and resp.status >= 400:
                    raise httpx.HTTPError(f"browser got {resp.status}")
                page.wait_for_timeout(3000)  # let client-side rendering finish
                return page.content()
            except PWError as e:
                raise httpx.HTTPError(f"browser: {str(e).splitlines()[0][:80]}") from e
        finally:
            browser.close()


async def _browser_fetch(url: str) -> str:
    return await asyncio.to_thread(_browser_fetch_sync, url)


async def scrape(client: httpx.AsyncClient, src: Source, query: str) -> SourceResult:
    url = src.url_for(query)
    try:
        try:
            html = await _get(client, url)
        except httpx.HTTPError:
            if not src.use_browser:
                raise
            html = await _browser_fetch(url)  # raises if the site blocks browsers too
        products = parse(html, src, query, url)
        if not products and src.product_urls:
            pages = await asyncio.gather(*(_get(client, u) for u in src.product_urls), return_exceptions=True)
            for u, page in zip(src.product_urls, pages):
                if isinstance(page, str):
                    products += parse(page, src, query, u)
        return SourceResult(source=src.name, search_url=url, ok=True, products=products)
    except httpx.HTTPStatusError as e:
        msg = f"Site returned {e.response.status_code} (it blocks automated requests)"
    except httpx.HTTPError as e:
        msg = f"Could not fetch: {str(e) or type(e).__name__}"
    return SourceResult(source=src.name, search_url=url, ok=False, error=msg)
