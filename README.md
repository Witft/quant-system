# Quant System Monorepo

This repository contains the A-Share Quantitative Investment System.

## Architecture

* **`backend/`**: Python-based system containing:
  * Daily Scanner (Tushare + LLM filtering)
  * FastAPI Server for providing data to the dashboard
* **`frontend/`**: React + Vite + Tailwind + Shadcn UI dashboard. E2E tested with Playwright.

## Development

See individual READMEs in `frontend/` and `backend/` for details.
