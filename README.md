# FinSight

FinSight is a containerized financial portfolio management application with generative AI integration. Users can track portfolios, pull live market data, compute quantitative risk/return metrics, and generate AI-written narrative reports on individual tickers or entire portfolios.

Built as the final project for *Sistemi Distribuiti e Cloud Computing* (A.A. 2025/2026).

## Features

- Portfolio and position management (CRUD) with JWT-based authentication and per-user data ownership
- Live market data via `yfinance` (prices, 52-week high/low, average volume, P/E, dividend yield, analyst targets, ETF holdings, dividend history)
- Quantitative engine: portfolio weights, 1Y/6M/3M/1M returns, annualized volatility (covariance-based)
- Generative AI (Groq + Llama 3.3 70B) for:
  - Full portfolio narrative reports (persisted in Postgres)
  - Per-ticker trend explanations
  - News summarization
  - Sector peer suggestions (generate-then-verify pattern against real market data)
- Async task processing via Celery, so slow external calls (market data, LLM) never block the API
- Rate limiting and caching backed by Redis
- Observability: Prometheus metrics + Grafana dashboards, structured JSON logging
- Streamlit dashboard as a decoupled REST client

## Architecture

**Containerized modular monolith** — a single application codebase (shared by the API and the Celery worker) split into isolated containers, rather than a microservices architecture. This avoids the operational overhead of service meshes and distributed tracing while still separating concerns (API ≠ worker ≠ datastore).

Services (Docker Compose):

| Service | Role |
|---|---|
| `api` | FastAPI async gateway (auth, rate limiting, orchestration) |
| `worker` | Celery worker — market data fetching, quant calculations, LLM calls |
| `db` | PostgreSQL 16 |
| `cache` | Redis 7 — Celery broker/result backend, cache, rate limiting |
| `frontend` | Streamlit dashboard |
| `prometheus` | Metrics scraping |
| `grafana` | Metrics dashboards |

Network design: two segmented Docker networks (`public_net`, `private_net`). The API is dual-homed; the worker, database and cache stay on `private_net` only, with no host ports exposed for `db` and `cache` — defense-in-depth via least-privilege networking.

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy 2.0 (async, `asyncpg`), Alembic, Pydantic v2
- **Async processing:** Celery, Redis
- **AI:** Groq API (`llama-3.3-70b-versatile`) via OpenAI-compatible SDK
- **Data:** yfinance, pandas, NumPy
- **Frontend:** Streamlit, Plotly
- **Auth:** JWT (PyJWT), bcrypt (passlib)
- **Observability:** Prometheus, Grafana, structured JSON logging
- **Testing/CI:** pytest, pytest-asyncio, httpx, GitHub Actions
- **Load testing:** Locust

## Getting Started

### Prerequisites

- Docker Desktop with Docker Compose
- A [Groq API key](https://console.groq.com)

### Setup

1. Clone the repository and copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Fill in `.env` with your database credentials, Redis password, JWT secret and `GROQ_API_KEY`.

3. Start the stack:

   ```bash
   docker compose up -d --build
   ```

4. Apply database migrations:

   ```bash
   docker compose exec api alembic upgrade head
   ```

### Access

| Service | URL |
|---|---|
| Frontend (Streamlit) | http://localhost:8501 |
| API docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

### Running tests

```bash
docker compose exec api pytest
```

## Project Structure

```
backend/
  app/
    api/v1/endpoints/   # FastAPI routers (auth, portfolios, positions, market, ai)
    core/               # config, security, celery app, quant engine, market provider
    crud/                # repository pattern (async CRUD per model)
    db/                  # engine, session, Alembic URL handling
    models/              # SQLAlchemy ORM models
    schemas/             # Pydantic DTOs
    services/            # GenerativeAIAnalyzer (LLM orchestration)
    tasks/                # Celery tasks (market data, AI generation)
  alembic/                # schema migrations
  tests/                  # integration tests (pytest + httpx ASGITransport)
frontend/
  app.py                  # Streamlit dashboard
infra/
  prometheus/             # Prometheus scrape config
load_tests/
  locustfile.py           # Locust load test scenarios
```

## License

This project was developed for academic purposes as part of a university exam.
