# Oyster

Personal, friends-only site for finding food from vendors within an hour's travel of Surbiton, plus a few online shops.

- `backend/` FastAPI, httpx, BeautifulSoup, asyncpg. Vendors and cached searches live in Postgres.
- `frontend/` React (Vite). Proxies `/api` to the backend.
- `docker-compose.yml` runs Postgres 16 (host port 5433, local only; data kept in the `oyster-pgdata` volume).

## How it works

- **Vendors:** discovered from OpenStreetMap (greengrocers, farm shops, butchers, delis, fishmongers, bakeries, cheesemongers, markets) and stored in Postgres. Drive times come from the public OSRM server. A background refresh runs on startup if the data is over a week old; rows are usable immediately with estimates and upgraded to real drive times in batches.
- **Search:** `GET /api/search?q=&max_minutes=` streams newline-delimited JSON as each online shop and each of the 60 nearest vendor websites (Shopify/WooCommerce site search) finishes. Finished searches are cached in Postgres for 10 minutes.
- `GET /api/vendors?max_minutes=&kind=&q=` and `GET /api/status` for the directory.

## Run

Start Docker Desktop, then:

    docker compose up -d

Backend (port 8000), from `backend/`:

    .venv\Scripts\python -m uvicorn app.main:app --port 8000

Frontend (port 5173), from `frontend/`:

    npm run dev

Override the database with `DATABASE_URL` (default `postgresql://oyster:oyster@127.0.0.1:5433/oyster`).

## Adding a source

Add a `Source(...)` in `backend/app/scrapers/sources.py`. Parsing tries CSS selectors first (`item_selector`, `name_selector`, `price_selector`), then JSON-LD product data. For sites whose search is rendered by JavaScript, list known product pages in `product_urls`.

## Playwright

Playwright is installed (`playwright install chromium` after `pip install -r requirements.txt`) and available per source: set `use_browser=True` on a `Source` and, if plain HTTP is refused or times out, the page is retried in headless Chromium. It is off for Waitrose, Tesco and Sainsbury's because I tested it and they still block it (Tesco/Sainsbury's return 403 Access Denied, Waitrose times out), and it only added ~20s per search. Bypassing that bot protection isn't attempted.

## Known limits

Waitrose, Tesco and Sainsbury's can't be scraped, so they show a link to the shop's own search instead. Abel & Cole works. Searches are cached for 10 minutes.

## Tests

    cd backend
    .venv\Scripts\python -m pytest
