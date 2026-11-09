"""Integration tests for GET /v1/traces (cursor-paginated list endpoint).

Each test class is fully self-contained: it inserts its own traces via
POST /v1/traces using real API keys, then asserts the GET /v1/traces response.
No test shares state with another (db_session teardown wipes tables between
tests).

Auth model: GET /v1/traces uses X-API-Key (same as POST).
Org isolation: org_id is derived from the authenticated API key's project —
              callers cannot read another org's traces.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnvironmentName, UserRole
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.project import ProjectCreate
from app.services.api_key_service import APIKeyService
from app.services.project_service import ProjectService
from tests.conftest import APIKeyHeaders, SeededOrg


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _trace_body(**overrides: Any) -> dict:
    """Minimal valid TraceIn body, with arbitrary overrides applied."""
    base: dict[str, Any] = {
        "feature": "search",
        "model": "gpt-4o",
        "prompt": "Hello",
        "completion": "Hi",
        "prompt_tokens": 5,
        "completion_tokens": 3,
    }
    base.update(overrides)
    return base


async def _post_trace(
    client: AsyncClient,
    headers: dict,
    **overrides: Any,
) -> dict:
    """POST a trace and return the parsed JSON response body."""
    resp = await client.post("/v1/traces", json=_trace_body(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get_list(
    client: AsyncClient,
    headers: dict,
    **params: Any,
) -> dict:
    """GET /v1/traces with query params and return parsed JSON."""
    resp = await client.get("/v1/traces", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Empty DB → 200, empty items, null next_cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_empty_db(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """GET /v1/traces on an empty DB returns 200 with empty items and null next_cursor."""
    data = await _get_list(client, dict(api_key_for_project))
    assert data["items"] == []
    assert data["next_cursor"] is None


# ---------------------------------------------------------------------------
# 2. 3 traces, no filters, limit=50 → all 3, next_cursor=null
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_all_three_no_cursor(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """3 traces, no filters, limit=50 → all 3 returned, next_cursor is null."""
    hdrs = dict(api_key_for_project)
    for i in range(3):
        await _post_trace(client, hdrs, feature=f"feat-{i}")

    data = await _get_list(client, hdrs, limit=50)
    assert len(data["items"]) == 3
    assert data["next_cursor"] is None


# ---------------------------------------------------------------------------
# 3. 5 traces, limit=2 → paginate through all pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_full_pagination(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """5 traces with limit=2 → page1 (2 items + cursor), page2 (2 items + cursor), page3 (1 item + null)."""
    hdrs = dict(api_key_for_project)
    for i in range(5):
        await _post_trace(client, hdrs, feature=f"paginate-{i}")

    # Page 1
    page1 = await _get_list(client, hdrs, limit=2)
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    # Page 2
    page2 = await _get_list(client, hdrs, limit=2, cursor=page1["next_cursor"])
    assert len(page2["items"]) == 2
    assert page2["next_cursor"] is not None

    # Page 3 — last page
    page3 = await _get_list(client, hdrs, limit=2, cursor=page2["next_cursor"])
    assert len(page3["items"]) == 1
    assert page3["next_cursor"] is None

    # No duplicate IDs across all pages
    all_ids = (
        [t["id"] for t in page1["items"]]
        + [t["id"] for t in page2["items"]]
        + [t["id"] for t in page3["items"]]
    )
    assert len(all_ids) == len(set(all_ids)), "Duplicate trace IDs across pages"


# ---------------------------------------------------------------------------
# 4. Filter by model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_filter_by_model(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """Filter by model=gpt-4o-mini returns only matching traces."""
    hdrs = dict(api_key_for_project)
    await _post_trace(client, hdrs, model="gpt-4o")
    await _post_trace(client, hdrs, model="gpt-4o")
    await _post_trace(client, hdrs, model="gpt-4o-mini")

    data = await _get_list(client, hdrs, model="gpt-4o-mini")
    assert len(data["items"]) == 1
    assert data["items"][0]["model"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# 5. Filter by feature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_filter_by_feature(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """Filter by feature=summarizer returns only matching traces."""
    hdrs = dict(api_key_for_project)
    await _post_trace(client, hdrs, feature="summarizer")
    await _post_trace(client, hdrs, feature="summarizer")
    await _post_trace(client, hdrs, feature="search")

    data = await _get_list(client, hdrs, feature="summarizer")
    assert len(data["items"]) == 2
    assert all(t["feature"] == "summarizer" for t in data["items"])


# ---------------------------------------------------------------------------
# 6. Filter by since / until
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_filter_by_since_until(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
    db_session: AsyncSession,
) -> None:
    """since/until filters restrict the returned traces to the given time range."""
    from sqlalchemy import update
    from app.models.trace import Trace

    hdrs = dict(api_key_for_project)

    # Insert 3 traces; we'll backdate two of them directly in the DB.
    ids = []
    for _ in range(3):
        body = await _post_trace(client, hdrs)
        ids.append(uuid.UUID(body["id"]))

    now = datetime.now(tz=timezone.utc)
    old = now - timedelta(days=10)
    very_old = now - timedelta(days=20)

    # Backdate first two traces
    await db_session.execute(
        update(Trace).where(Trace.id == ids[0]).values(created_at=very_old)
    )
    await db_session.execute(
        update(Trace).where(Trace.id == ids[1]).values(created_at=old)
    )
    await db_session.commit()

    # since=5 days ago → only the recent (un-backdated) trace
    since_5d = (now - timedelta(days=5)).isoformat()
    data = await _get_list(client, hdrs, since=since_5d)
    returned_ids = {t["id"] for t in data["items"]}
    assert str(ids[2]) in returned_ids
    assert str(ids[0]) not in returned_ids
    assert str(ids[1]) not in returned_ids

    # until=15 days ago → only the very_old trace
    until_15d = (now - timedelta(days=15)).isoformat()
    data2 = await _get_list(client, hdrs, until=until_15d)
    returned_ids2 = {t["id"] for t in data2["items"]}
    assert str(ids[0]) in returned_ids2
    assert str(ids[2]) not in returned_ids2


# ---------------------------------------------------------------------------
# 7. Combined filter + pagination (filter persists across pages)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_combined_filter_and_pagination(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """4 matching + 4 non-matching traces; paging with limit=2 returns only matching rows on every page."""
    hdrs = dict(api_key_for_project)

    # Insert 4 "summarizer / claude-3" traces interleaved with 4 "search / gpt-4o" traces
    for _ in range(4):
        await _post_trace(client, hdrs, feature="summarizer", model="claude-3")
        await _post_trace(client, hdrs, feature="search", model="gpt-4o")

    # Page 1 — filter by feature=summarizer, limit=2
    page1 = await _get_list(client, hdrs, feature="summarizer", limit=2)
    assert len(page1["items"]) == 2
    assert all(t["feature"] == "summarizer" for t in page1["items"])
    assert page1["next_cursor"] is not None

    # Page 2 — still only summarizer rows
    page2 = await _get_list(
        client, hdrs, feature="summarizer", limit=2, cursor=page1["next_cursor"]
    )
    assert len(page2["items"]) == 2
    assert all(t["feature"] == "summarizer" for t in page2["items"])
    assert page2["next_cursor"] is None  # 4 total, 2+2 = done

    # All IDs across pages are unique
    all_ids = [t["id"] for t in page1["items"]] + [t["id"] for t in page2["items"]]
    assert len(all_ids) == len(set(all_ids))


# ---------------------------------------------------------------------------
# 8. Invalid cursor → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_invalid_cursor_returns_400(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """Passing a garbage cursor string returns HTTP 400."""
    resp = await client.get(
        "/v1/traces",
        headers=dict(api_key_for_project),
        params={"cursor": "this-is-not-a-valid-cursor!!!"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_traces_valid_base64_bad_json_cursor_returns_400(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
) -> None:
    """A cursor that is valid base64 but not valid JSON returns HTTP 400."""
    import base64
    bad_cursor = base64.urlsafe_b64encode(b"not json at all").decode("ascii")
    resp = await client.get(
        "/v1/traces",
        headers=dict(api_key_for_project),
        params={"cursor": bad_cursor},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. Tenant isolation — org-A key cannot see org-B traces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_traces_tenant_isolation(
    client: AsyncClient,
    api_key_for_project: APIKeyHeaders,
    seeded_org: SeededOrg,
    db_session: AsyncSession,
) -> None:
    """An API key from org-A cannot see traces belonging to org-B."""
    # --- org-A: insert 2 traces ---
    hdrs_a = dict(api_key_for_project)
    await _post_trace(client, hdrs_a, feature="org-a-feature")
    await _post_trace(client, hdrs_a, feature="org-a-feature")

    # --- org-B: create a second org, project, key, and insert 3 traces ---
    org_repo = OrganizationRepository(db_session)
    suffix = uuid.uuid4().hex[:8]
    org_b = await org_repo.create(name=f"Org B {suffix}", slug=f"org-b-{suffix}")

    proj_svc = ProjectService(db_session)
    proj_b = await proj_svc.create_project(
        ProjectCreate(
            organization_id=org_b.id,
            name=f"Proj B {suffix}",
            slug=f"proj-b-{suffix}",
        )
    )
    dev_env_b = next(e for e in proj_b.environments if e.name == EnvironmentName.DEV)
    key_svc = APIKeyService(db_session)

    # We need a user for the actor; borrow the seeded owner from org-A for the
    # service call (actor_user_id is only used for audit logging, not auth).
    record_b, plaintext_b = await key_svc.create_api_key(
        project_id=proj_b.id,
        environment_id=dev_env_b.id,
        name=f"org-b-key-{suffix}",
        actor_user_id=seeded_org.owner.id,
    )
    await db_session.commit()

    hdrs_b = {"X-API-Key": plaintext_b}
    for _ in range(3):
        await _post_trace(client, hdrs_b, feature="org-b-feature")

    # --- org-A key should see only its own 2 traces ---
    data_a = await _get_list(client, hdrs_a)
    assert len(data_a["items"]) == 2
    assert all(t["feature"] == "org-a-feature" for t in data_a["items"])

    # --- org-B key should see only its own 3 traces ---
    data_b = await _get_list(client, hdrs_b)
    assert len(data_b["items"]) == 3
    assert all(t["feature"] == "org-b-feature" for t in data_b["items"])
