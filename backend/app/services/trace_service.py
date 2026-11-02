"""Trace business logic service."""

from typing import Union
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.models.api_key import APIKey
from app.models.enums import AuditAction
from app.models.project import Project
from app.models.trace import Trace
from app.models.user import User
from app.repositories.trace_repository import TraceRepository
from app.schemas.trace import TraceIn
from app.services.audit_service import AuditService


class TraceService:
    """Service encapsulating business operations for LLM trace ingestion and retrieval.

    Adheres to unit-of-work semantics: commits at the end of a successful operation,
    and rolls back on exception.

    Security invariant
    ------------------
    All tenant-scoping is derived from the authenticated ``APIKey`` or ``User``
    model passed into service methods — never from the caller's payload. The
    ``TraceIn`` schema enforces ``extra="forbid"``, so there are no
    ``organization_id``, ``project_id``, or ``environment_id`` fields in the
    payload, but we explicitly derive and set all FK values from the authenticated
    principal to guarantee this invariant even if the schema changes in future.
    """

    def __init__(self, session: Union[AsyncSession, TraceRepository]) -> None:
        if isinstance(session, TraceRepository):
            self.repo = session
            self._session = session.session
        else:
            self.repo = TraceRepository(session)
            self._session = session
        self.audit_service = AuditService(self._session)

    async def create_trace(self, api_key: APIKey, payload: TraceIn) -> Trace:
        """Ingest a single LLM trace authenticated by an API key.

        Tenant context (organization_id, project_id, environment_id, api_key_id)
        is sourced exclusively from the ``api_key`` model — never from the payload.
        ``TraceIn`` has ``extra="forbid"`` so those fields cannot appear in the
        payload, but this comment and the explicit assignment below make the
        security boundary unambiguous for future readers.

        An ``AuditAction.CREATE`` event is emitted upon successful persistence.

        Args:
            api_key: Authenticated API key — provides all tenant FK values.
            payload: Validated ingestion payload from the caller.

        Returns:
            The newly created, committed, and refreshed :class:`Trace` record.
        """
        async with self.repo.transaction():
            # --- Derive all tenant context from the authenticated API key ---
            # These are NEVER taken from the payload (see class docstring).
            organization_id: uuid.UUID = api_key.project_id  # resolved below via project
            project_id: uuid.UUID = api_key.project_id
            environment_id: uuid.UUID = api_key.environment_id
            api_key_id: uuid.UUID = api_key.id

            # Resolve organization_id from the project FK on the API key.
            # We load the project directly rather than relying on the lazy
            # relationship (lazy="raise" on Trace; api_key.project also has no
            # lazy="raise" but may not be loaded yet in this session context).
            project_row = await self._session.execute(
                select(Project).where(Project.id == project_id)
            )
            project = project_row.scalars().first()
            if project is None:
                # Should never happen if FK constraints are enforced, but guard anyway.
                raise NotFoundError(
                    f"Project with id '{project_id}' not found "
                    "(this indicates a data integrity problem)."
                )
            organization_id = project.organization_id

            # --- Build and persist the trace ---
            trace = await self.repo.create(
                organization_id=organization_id,
                project_id=project_id,
                environment_id=environment_id,
                api_key_id=api_key_id,
                request_id=payload.request_id,
                feature=payload.feature,
                model=payload.model,
                prompt=payload.prompt,
                completion=payload.completion,
                prompt_tokens=payload.prompt_tokens,
                completion_tokens=payload.completion_tokens,
                total_tokens=payload.total_tokens,
                latency_ms=payload.latency_ms,
                cost_usd=payload.cost_usd,
                prompt_version=payload.prompt_version,
                metadata_json=payload.metadata_json,
            )

            # --- Emit audit event ---
            await self.audit_service.record(
                org_id=organization_id,
                actor_id=None,  # Ingestion is a system/API-key action; no human actor.
                action=AuditAction.CREATE,
                resource_type="trace",
                resource_id=trace.id,
                metadata={
                    "feature": trace.feature,
                    "model": trace.model,
                },
            )

            return trace

    async def get_trace_for_user(
        self,
        trace_id: uuid.UUID,
        user: User,
    ) -> Trace:
        """Retrieve a trace by ID scoped to the authenticated user's organization.

        Raises :class:`NotFoundError` whether the trace does not exist *or* belongs
        to a different organization — callers must not distinguish the two cases
        to prevent cross-org enumeration attacks.

        Args:
            trace_id: Primary key of the trace to retrieve.
            user: Authenticated user; provides the ``organization_id`` scope.

        Returns:
            The :class:`Trace` record.

        Raises:
            NotFoundError: If the trace is not found within the user's organization.
        """
        trace = await self.repo.get_by_id_for_org(
            trace_id=trace_id,
            organization_id=user.organization_id,
        )
        if trace is None:
            raise NotFoundError("trace not found")
        return trace

    async def list_traces_for_user(
        self,
        user: User,
        project_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Trace], int]:
        """List traces for a project, verifying the project belongs to the user's organization.

        The project ownership check prevents a user from paginating traces in a
        project that belongs to a different organization by guessing a valid UUID.

        Args:
            user: Authenticated user; provides the ``organization_id`` scope.
            project_id: Project to list traces for.
            limit: Maximum number of traces to return.
            offset: Pagination offset.

        Returns:
            A tuple of (traces, total_count).

        Raises:
            NotFoundError: If the project does not exist or belongs to another org.
        """
        # Load the project and verify org ownership in a single query.
        project_row = await self._session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_row.scalars().first()

        # Deliberate: raise NotFoundError for both "not found" and "wrong org"
        # to avoid leaking whether a project UUID exists in a different org.
        if project is None or project.organization_id != user.organization_id:
            raise NotFoundError("trace not found")

        return await self.repo.list_by_project(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
