"""Project business logic service."""

from typing import Optional, Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models.enums import EnvironmentName
from app.models.project import Project
from app.repositories.environment_repository import EnvironmentRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    """Service encapsulating business operations and validation for projects."""

    def __init__(
        self,
        session_or_repo: Union[AsyncSession, ProjectRepository],
        env_repo: Optional[EnvironmentRepository] = None,
    ) -> None:
        if isinstance(session_or_repo, ProjectRepository):
            self.project_repo = session_or_repo
            self.env_repo = env_repo or EnvironmentRepository(self.project_repo.session)
        else:
            self.project_repo = ProjectRepository(session_or_repo)
            self.env_repo = env_repo or EnvironmentRepository(session_or_repo)

    async def create_project(self, data: ProjectCreate) -> Project:
        """Create a new project and auto-create default environments (dev, staging, prod).

        Service Rule:
            When creating a project, auto-creates the three default environments
            (dev, staging, prod), with dev marked as the default environment.
        """
        existing = await self.project_repo.get_by_slug(data.organization_id, data.slug)
        if existing:
            raise ConflictError(
                f"Project with slug '{data.slug}' already exists in this organization."
            )

        project = await self.project_repo.create(
            organization_id=data.organization_id,
            name=data.name,
            slug=data.slug,
            description=data.description,
            is_archived=False,
        )

        # Auto-create the three default environments, with dev as default
        for env_name in (EnvironmentName.DEV, EnvironmentName.STAGING, EnvironmentName.PROD):
            await self.env_repo.create(
                project_id=project.id,
                name=env_name,
                is_default=(env_name == EnvironmentName.DEV),
            )

        # Return project with newly created environments loaded
        return await self.project_repo.get_with_environments(project.id) or project

    async def get_project(self, id: Union[uuid.UUID, str]) -> Project:
        """Retrieve a project by its ID, raising NotFoundError if missing."""
        project = await self.project_repo.get_with_environments(id)
        if not project:
            raise NotFoundError(f"Project with id '{id}' not found.")
        return project

    async def get_project_by_slug(
        self, org_id: Union[uuid.UUID, str], slug: str
    ) -> Project:
        """Retrieve a project by organization ID and slug, raising NotFoundError if missing."""
        project = await self.project_repo.get_by_slug(org_id, slug)
        if not project:
            raise NotFoundError(f"Project with slug '{slug}' not found.")
        return project

    async def list_projects(
        self,
        org_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
        is_archived: Optional[bool] = None,
    ) -> tuple[Sequence[Project], int]:
        """List projects belonging to an organization with pagination."""
        return await self.project_repo.list_by_org(
            org_id=org_id,
            offset=offset,
            limit=limit,
            is_archived=is_archived,
        )

    async def update_project(
        self, id: Union[uuid.UUID, str], data: ProjectUpdate
    ) -> Project:
        """Update project details, verifying slug uniqueness if slug is changed."""
        project = await self.get_project(id)
        update_data = data.model_dump(exclude_unset=True)

        if "slug" in update_data and update_data["slug"] != project.slug:
            existing = await self.project_repo.get_by_slug(
                project.organization_id, update_data["slug"]
            )
            if existing and existing.id != project.id:
                raise ConflictError(
                    f"Project with slug '{update_data['slug']}' already exists in this organization."
                )

        return await self.project_repo.update(project, **update_data)

    async def archive_project(self, id: Union[uuid.UUID, str]) -> Project:
        """Archive a project by setting is_archived to True."""
        project = await self.get_project(id)
        return await self.project_repo.update(project, is_archived=True)
