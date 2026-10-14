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

## Tenancy Model

Prism uses a four-level ownership hierarchy that isolates data between customers and controls access to API keys.

```
Organization
└── Project
    ├── Environment (dev)      ← default
    ├── Environment (staging)
    ├── Environment (prod)
    └── APIKey  ──────────────── scoped to one Environment
```

### Entities

| Entity | Table | Unique constraint | Notes |
|---|---|---|---|
| **Organization** | `organizations` | `slug` (global) | Top-level tenant. Every other resource belongs to exactly one org. |
| **Project** | `projects` | `(organization_id, slug)` | Logical workspace within an org. |
| **Environment** | `environments` | `(project_id, name)` | Fixed set: `dev`, `staging`, `prod`. Auto-created on project creation; `dev` is the default. |
| **APIKey** | `api_keys` | — | Scoped to a single Project + Environment pair. Only the SHA-256 hash and an 8-character public prefix are stored; the plaintext is shown once at creation and is unrecoverable. |

### Rules

- An **Organization** must exist before any Project, User, or APIKey can be created.
- A **Project** is always created with all three Environments in a single atomic transaction.
- The **default Environment** (`dev`) cannot be deleted until a different environment is promoted to default first.
- An **APIKey** is permanently linked to one Environment and cannot be moved; it can only be revoked.
- **Users** belong to an Organization (not a Project) and carry a role (`OWNER`, `ADMIN`, `MEMBER`, `VIEWER`).

## Layering

All backend code follows a strict five-layer stack. Imports only flow **downward** — no layer may import from a layer above it.

```
┌─────────────────────────────────────┐
│              API Layer              │  app/api/
│  FastAPI routers, request parsing,  │
│  response serialization (Pydantic)  │
├─────────────────────────────────────┤
│            Service Layer            │  app/services/
│  Business logic, validation rules,  │
│  unit-of-work / transaction mgmt    │
├─────────────────────────────────────┤
│          Repository Layer           │  app/repositories/
│  Async SQLAlchemy queries, CRUD,    │
│  pagination, flush/commit/rollback  │
├─────────────────────────────────────┤
│            Model Layer              │  app/models/
│  SQLAlchemy ORM declarative models  │
│  and domain enums                   │
├─────────────────────────────────────┤
│           Database (Postgres)       │
│  Tables, indexes, constraints,      │
│  JSONB columns, foreign keys        │
└─────────────────────────────────────┘
```

### Layer responsibilities

| Layer | Package | Allowed imports |
|---|---|---|
| **API** | `app.api` | Services, Schemas, Exceptions, FastAPI |
| **Service** | `app.services` | Repositories, Schemas, Models (types only), Exceptions |
| **Repository** | `app.repositories` | Models, SQLAlchemy (`sqlalchemy.*`) |
| **Model** | `app.models` | SQLAlchemy ORM declarations, Enums |
| **Schema** | `app.schemas` | Pydantic only |

### The golden rule — services never import SQLAlchemy directly

Services are the only layer that contains business logic. They must remain **database-agnostic** so that they can be unit-tested without a real database and so that the storage engine can be swapped without touching business rules.

Concretely:

- ✅ A service **may** call `await self.repo.create(...)`, `await self.repo.list(...)`, etc.
- ✅ A service **may** import model classes for type annotations.
- ❌ A service **must not** import `sqlalchemy`, `AsyncSession`, `select`, or any other SQLAlchemy symbol for use in query construction.
- ❌ A service **must not** call `session.execute(...)` or `session.flush()` directly.

The only exception is the `AsyncSession` type annotation in `__init__` signatures — this is accepted because it is used exclusively for dependency injection (the session is passed in, not created).

### Transaction semantics (unit of work)

Every mutating service method wraps its repository calls in `async with self.repo.transaction()`. The `transaction()` context manager on `BaseRepository` commits on success and rolls back on any exception — whether a domain `PrismException` or an unexpected `IntegrityError`. This means:

- Callers never need to manage commits or rollbacks.
- Partial writes are impossible within a single service operation.
- Tests can wrap operations in a savepoint and roll back cleanly after each test.

## Data Model

The diagram below shows every table and its primary foreign-key relationships.

```
organizations
  id            UUID PK
  name          VARCHAR(255)
  slug          VARCHAR(255)  UNIQUE
  is_active     BOOLEAN
  created_at    TIMESTAMPTZ
  updated_at    TIMESTAMPTZ
        │
        │ 1 ──────────────────────────────────────────────── ∞
        │                                                     │
     users                                               projects
       id              UUID PK                             id              UUID PK
       organization_id UUID FK ──► organizations           organization_id UUID FK ──► organizations
       email           VARCHAR(255)  UNIQUE                name            VARCHAR(255)
       hashed_password VARCHAR(255)                        slug            VARCHAR(255)
       full_name       VARCHAR(255)                        description     TEXT
       role            VARCHAR(50)                         is_archived     BOOLEAN
       is_active       BOOLEAN                             created_at      TIMESTAMPTZ
       last_login_at   TIMESTAMPTZ                         updated_at      TIMESTAMPTZ
       created_at      TIMESTAMPTZ                               │
       updated_at      TIMESTAMPTZ                               │ 1 ──────────────── ∞
                                                                 │                    │
                                                           environments            api_keys
                                                             id          UUID PK     id             UUID PK
                                                             project_id  UUID FK      project_id     UUID FK ──► projects
                                                             name        VARCHAR(50)  environment_id UUID FK ──► environments
                                                             is_default  BOOLEAN      name           VARCHAR(255)
                                                             created_at  TIMESTAMPTZ  key_prefix     VARCHAR(32)
                                                             updated_at  TIMESTAMPTZ  hashed_key     VARCHAR(255)
                                                                                      is_active      BOOLEAN
                                                                                      last_used_at   TIMESTAMPTZ
                                                                                      revoked_at     TIMESTAMPTZ
                                                                                      created_at     TIMESTAMPTZ
                                                                                      updated_at     TIMESTAMPTZ

audit_logs
  id              UUID PK
  organization_id UUID FK ──► organizations
  actor_user_id   UUID FK ──► users  (nullable — NULL for system events)
  action          VARCHAR(50)   [CREATE | UPDATE | DELETE | LOGIN | KEY_CREATED | KEY_REVOKED]
  resource_type   VARCHAR(255)
  resource_id     UUID          (nullable)
  metadata_json   JSONB
  ip_address      VARCHAR(255)  (nullable)
  user_agent      VARCHAR(1024) (nullable)
  created_at      TIMESTAMPTZ
  updated_at      TIMESTAMPTZ

  Indexes:
    ix_audit_logs_organization_id_created_at  (organization_id, created_at)
    ix_audit_logs_resource_type_resource_id   (resource_type, resource_id)

  Constraint: append-only — UPDATE and DELETE are prohibited at the application layer.
```

## Upcoming Phases

> [!NOTE]
> Core operational capabilities—including distributed request and prompt tracing, evaluation pipelines (golden datasets, heuristic evaluators, LLM-as-a-judge), experiment tracking, and automated A/B routing—will be added in subsequent phases. Phase 1 establishes the rock-solid foundation: FastAPI core architecture, configuration management, asynchronous database connectivity, health probing, and containerization.
