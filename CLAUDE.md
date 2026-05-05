# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A-Share quantitative investment system monorepo: daily Graham-value stock scanning, AI-powered analysis (MiniMax LLM), and a web dashboard. Data pipeline: Tushare API → Python scanner → PostgreSQL → FastAPI → React dashboard.

## Monorepo Layout

- `backend/` — Python scripts (scanner, backtest, AI analysis) + FastAPI API server
- `frontend/` — React 19 SPA (Vite + TypeScript + Tailwind + shadcn/ui)
- Data flows: scanner scripts write to PostgreSQL on a remote VPS; the API reads from the same DB and serves the frontend

## Commands

### Frontend (run from `frontend/`)

```bash
npm run dev          # Vite dev server on port 5173
npm run build        # Production build to dist/
npm run lint         # ESLint (TypeScript + React rules)
npm run test:e2e     # Playwright E2E tests (auto-starts dev server)
npx playwright test tests/smoke.spec.ts   # Run a single test file
```

### Backend (run from `backend/`)

```bash
python daily_scanner.py       # Daily Graham value scan + AI report
python structured_output.py   # Full pipeline: scan → AI → PostgreSQL upsert
python backtest_evaluator.py  # Evaluate historical picks vs current prices
```

### Backend API (run from `backend/api/`)

```bash
python main.py                     # Start FastAPI on port 8000
uvicorn main:app --host 0.0.0.0 --port 8000
docker-compose up                  # Containerized API (connects to external postgres_default network)
```

## Architecture Details

**Frontend** is a single-page app in `frontend/src/App.tsx` that fetches from two API endpoints:
- `GET /api/stats` → `{ total_days, total_picks, avg_margin, avg_roe }`
- `GET /api/picks` → `{ data: [...] }` of stock pick records

The API base URL is currently hardcoded in `App.tsx`. No proxy config or env variable exists.

**Backend scripts** are standalone Python files (no shared package structure). `daily_scanner.py` uses Tushare for stock data and applies Graham value formula with fundamental filters. `structured_output.py` extends this with MiniMax LLM analysis and writes to PostgreSQL via raw SQL (psycopg2, no ORM).

**Backend API** (`backend/api/main.py`) is a FastAPI app with two endpoints that query the `stock_picks` PostgreSQL table. It also serves a legacy Chart.js HTML dashboard at `/`.

## Key Tech Stack

- **Frontend:** React 19, Vite 8, TypeScript 6, Tailwind 3, shadcn/ui, Recharts, Axios
- **Backend:** Python 3.12, FastAPI, psycopg2-binary (raw SQL), pandas, tushare, MiniMax LLM API
- **DB:** PostgreSQL (remote VPS)
- **Testing:** Playwright (E2E only, Chromium, workers=1); no backend tests exist
- **shadcn/ui:** Configured in `components.json` with `@/` path alias, slate base color, CSS variables style

## Path Aliases

Frontend uses `@/` alias mapped to `./src/` (configured in `vite.config.ts` and `tsconfig.app.json`).
