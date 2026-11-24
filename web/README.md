# NFI X9 Command Center

Modern, read-only control surface for **NostalgiaForInfinity X9** and Freqtrade.

Built with Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 and
Recharts. The browser never receives exchange or API credentials: a server-side
route proxies the local Freqtrade REST API.

## Features

- Equity curve and net P/L, including realized vs. unrealized attribution.
- Open positions with mark-to-market P/L, leverage, age and entry signal.
- Pair-level performance attribution and recent exit activity.
- Strategy health: win rate, profit factor, drawdown, free slots and stake.
- Watched pairlist, exchange, timeframe and dry-run/live status.
- Demo mode when `FREQTRADE_API_URL` is not set, so the UI is immediately
  explorable without a running bot.
- Auto-refresh every 20 seconds; manual refresh button.
- Responsive dark interface with a mobile header and horizontal-safe tables.

## Run locally

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>.

With no `FREQTRADE_API_URL`, the dashboard serves a deterministic demo dataset.
To use a running bot:

```env
FREQTRADE_API_URL=http://127.0.0.1:8080
FREQTRADE_USERNAME=freqtrader
FREQTRADE_PASSWORD=change-me
```

The Freqtrade API must expose the standard `/api/v1/*` endpoints. The proxy only
performs `GET` requests.

## Production

```bash
npm run build
npm start
```

The Next config uses `output: "standalone"`; the Docker image in this directory
copies the standalone server and static assets into a non-root runtime.

```bash
docker build -t nfi-x9-web .
docker run --rm -p 3000:3000 \
  -e FREQTRADE_API_URL=http://host.docker.internal:8080 \
  -e FREQTRADE_USERNAME=freqtrader \
  -e FREQTRADE_PASSWORD=change-me \
  nfi-x9-web
```

From the repository root, the optional Compose profile attaches the dashboard
to the same network as the `freqtrade` service:

```bash
docker compose --profile web up -d --build
```

Set `WEB_PORT` to change the published port (default `3000`).

## API surface

`GET /api/dashboard` aggregates:

- `/api/v1/status`
- `/api/v1/profit`
- `/api/v1/balance`
- `/api/v1/trades?limit=500`
- `/api/v1/performance`
- `/api/v1/show_config`
- `/api/v1/whitelist`
- `/api/v1/daily`

Partial endpoint failures are returned in `errors` and rendered as a warning;
a fully unreachable API returns HTTP 502. Credentials are read only from the
server environment and are never serialized into the response.

## Structure

```text
src/app/api/dashboard/route.ts   Freqtrade proxy + normalization
src/components/dashboard.tsx     Dashboard shell, charts and tables
src/lib/demo.ts                  Deterministic demo dataset
src/lib/types.ts                 Shared response contract
src/lib/format.ts                Currency, percentage and duration formatting
```

## Verification

```bash
npm run lint
npm run build
```
