# Architecture Overview

## Overview

Prism is an open-source, self-hosted AI evaluation and observability platform designed to sit between production applications and Large Language Model (LLM) providers. It intercepts and records every prompt, completion, token count, latency metric, and cost calculation, while offering automated evaluation pipelines (including golden dataset matching, heuristic checks, and LLM-as-a-judge), dynamic A/B routing with automated fallback/rollback, and comprehensive real-time observability dashboards.

## How the Backend Boots

The Prism backend follows a structured, deterministic lifecycle from initial process launch to serving incoming requests:

```mermaid
flowchart LR
    A["1. Config (Pydantic Settings)"] --> B["2. Logging (Structlog & JSON)"]
    B --> C["3. Database Connectivity (SELECT 1)"]
    C --> D["4. Health Endpoints Active (/health, /health/ready)"]
```

1. **Config (`app.core.config.Settings`)**:
   - The application instantiates `Settings`, powered by `pydantic-settings`.
   - Configuration values are loaded hierarchically from environment variables and `.env` files (both root `.env` and `backend/.env`).
   - Strict validation verifies environment-specific prerequisites (such as non-empty `DATABASE_URL` in staging and production).

2. **Logging (`app.core.logging.configure_logging`)**:
   - When the FastAPI application lifespan begins (`lifespan` in `app.main`), structured logging is initialized.
   - `structlog` and `python-json-logger` format logs consistently across all environments.
   - `RequestIDMiddleware` generates or extracts incoming `X-Request-ID` headers and binds them to the async logging context for end-to-end request tracing.

3. **Database (`app.db.session.engine`)**:
   - An asynchronous SQLAlchemy engine (`asyncpg`) initializes the connection pool.
   - As part of the lifespan startup hook, a lightweight connectivity probe (`SELECT 1`) is executed against the database.
   - If database connectivity fails in staging/production, application startup fails fast; in development, connection errors are logged while allowing the server to boot.
   - During application shutdown, the lifespan hook cleanly disposes of the database engine and connection pool.

4. **Health (`app.api.v1.health`)**:
   - Once startup completes, FastAPI exposes two health endpoints:
     - **Liveness (`GET /health`)**: A pure liveness check returning `{"status": "ok"}` with status code `200` without querying the database, indicating the process is running.
     - **Readiness (`GET /health/ready`)**: Verifies active database availability with an executed `SELECT 1` query, returning `200` (`{"status": "ready", "db": "ok"}`) when ready and `503` if the database is unreachable.

## Upcoming Phases

> [!NOTE]
> Core operational capabilities—including distributed request and prompt tracing, evaluation pipelines (golden datasets, heuristic evaluators, LLM-as-a-judge), experiment tracking, and automated A/B routing—will be added in subsequent phases. Phase 1 establishes the rock-solid foundation: FastAPI core architecture, configuration management, asynchronous database connectivity, health probing, and containerization.
