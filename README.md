# MyFinance — Budget & Portfolio Tracker

A self-hosted, Docker-based application to track the value of your assets over time.
Assets are entered in their native currency (PLN / EUR / USD / CHF), in **grams for gold**,
or as **coin quantity for crypto (BTC, SOL)**, and everything is recalculated into a
single **base currency** you choose. Every update records a timestamp, so you can watch
your portfolio progress on a time chart.

## Features
- **8 asset types out of the box**: Cash, Gold (grams), Stocks, TFI Funds, National Bonds,
  Watches, Bitcoin, Solana, Savings.
- **Multi-currency input** — enter any position in PLN, EUR, USD or CHF.
- **Live prices** — gold per gram, BTC/SOL, and FX rates are fetched from public APIs,
  with static fallbacks so the app keeps working offline.
- **Configurable base currency** (PLN / EUR / USD / CHF); all values are recalculated.
- **Timestamped updates** — every change to a position is stored, powering the history and
  the portfolio-over-time chart.
- **Charts** — line chart of total value over time + allocation donut chart.
- **Docker** — one `docker compose up` to run the whole stack. Python runs in a venv.

## Quick start
```bash
docker compose up --build
```
Then open:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs (interactive OpenAPI docs)

> **Note:** `docker compose up --build` will take a couple of minutes the first time
> (it downloads and builds both images).

## Using the app
1. Go to **Settings** and pick your base currency.
2. Open **Positions** and click **+ Add** on any asset:
   - Currency assets → enter amount + currency.
   - Gold → enter grams (price/gram is fetched live).
   - Bitcoin / Solana → enter coin quantity (price/coin is fetched live).
3. To change a value, click **Update** on that asset's card — a new timestamped entry is
   recorded. Click **History** to see the full timeline for that asset.
4. The **Dashboard** shows the total, live prices, the value-over-time chart and the
   allocation breakdown.

## Architecture
| Service   | Tech                                        | Port |
|-----------|---------------------------------------------|------|
| frontend  | Next.js 14 (Pages Router), TypeScript, Tailwind, Recharts | 3000 |
| backend   | Python 3.11, FastAPI, SQLAlchemy, SQLite (in a venv) | 8000 |

- The frontend proxies `/api/*` to the backend, so no CORS issues in the browser.
- SQLite data is persisted in the `myfinance-data` Docker volume.

### Price sources (with offline fallbacks)
- FX: `open.er-api.com`
- Gold: `gold-api.com` (XAU)
- Crypto: CoinGecko (`bitcoin`, `solana`)

Prices are cached in-process for 5 minutes to stay within free-tier rate limits.

## Kubernetes

The cluster deployment lives in the `kscsc-helm-charts` repository as the `myfinance`
chart. Pushing to `main` builds both images and publishes them to GHCR tagged with the
commit SHA; deploying is then a values change:

```bash
helm upgrade --install myfinance ./myfinance -n myfinance --create-namespace \
  -f ./config/values/myfinance__myfinance.yaml \
  --set backend.image.tag=<sha> --set frontend.image.tag=<sha>
```

One caveat worth knowing before changing the frontend: **`next build` bakes the
`next.config.js` rewrite destination into `.next/routes-manifest.json`**, so
`BACKEND_ORIGIN` only has an effect at build time. It works under docker compose because
the backend is literally reachable as the host `backend`. In the cluster the gateway
routes `/api/*` to the backend Service instead, and the chart does not set the variable
at all. If you change `BASE` in `frontend/src/lib/api.ts`, change `gateway.apiPathPrefix`
in the chart to match.

## Local (non-Docker) development
```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```
Point the frontend at the backend by running it on port 3000 with the backend on 8000
(the `/api` rewrite targets `http://backend:8000`; for local dev without Docker, edit
`frontend/next.config.js` to `http://localhost:8000`).

## Resetting data
```bash
docker compose down -v   # removes the data volume
```
