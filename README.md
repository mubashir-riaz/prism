# Prism — AI Evaluation & Observability Platform

Prism is an open-source, self-hosted platform that sits between your application and Large Language Model (LLM) providers. It logs every prompt, completion, token count, latency metric, and cost, runs configurable evaluation pipelines (golden datasets, LLM-as-judge, heuristic checks), provides A/B routing with automatic rollback, and delivers real-time observability dashboards.

## Project Status

**Current Milestone:** Phase 3 Complete (Authentication, Role-Based Access Control, API Key Management & Audit Logging)

- [x] **Phase 1**: Core foundation, configuration management, async database connectivity, health checks, Docker containerization.
- [x] **Phase 2**: Multi-tenancy (Organization -> Project -> Environment), layered architecture, repository pattern, unit-of-work transactions.
- [x] **Phase 3**: Authentication & RBAC (Argon2id passwords, JWT issuance, `X-API-Key` machine auth, role hierarchy, audit logging).
- [ ] **Phase 4**: Prompt logging & distributed request tracing.

---

## API Surface

The Prism backend exposes the following API endpoints under `/v1` and root health probes:

### Health Probes
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/health`, `/v1/health` | Process liveness probe (returns `200 OK`). | Public |
| `GET` | `/health/ready`, `/v1/health/ready` | Readiness probe verifying active database connectivity (`SELECT 1`). | Public |

### Authentication (`/v1/auth/*`)
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/v1/auth/register` | Register a new user inside an existing organization. | Public |
| `POST` | `/v1/auth/login` | Authenticate with email + password; issues signed JWT access token. | Public |
| `GET` | `/v1/auth/me` | Fetch the authenticated user's profile and active organization context. | Bearer JWT |

### API Key Management (`/v1/keys`)
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/v1/keys` | Create an API key scoped to a project and environment; returns plaintext once. | Bearer JWT (`OWNER`, `ADMIN`) |
| `GET` | `/v1/keys` | List API key metadata for a project (never returns secret or plaintext). | Bearer JWT (`OWNER`, `ADMIN`) |
| `DELETE` | `/v1/keys/{id}` | Revoke an API key immediately. | Bearer JWT (`OWNER`, `ADMIN`) |

### Development & Smoke Testing
| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/v1/admin/ping` | Smoke test endpoint for RBAC role verification. | Bearer JWT (`OWNER`, `ADMIN`) |

---

## Documentation

- [Architecture Overview](docs/architecture/overview.md) — Life-cycle, tenancy hierarchy, layered design, auth model, and data schema.
- [Authentication & API Key Reference](docs/api/auth.md) — Detailed request/response payloads, headers, query parameters, and error codes.
