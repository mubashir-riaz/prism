"""Environment business logic service."""

from typing import Sequence, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import EnvironmentName
from app.models.environment import Environment
from app.repositories.environment_repository import EnvironmentRepository
from app.schemas.environment import EnvironmentCreate, EnvironmentUpdate


class EnvironmentService:
    """Service encapsulating business operations and validation for project environments."""

    def __init__(self, session_or_repo: Union[AsyncSession, EnvironmentRepository]) -> None:
        if isinstance(session_or_repo, EnvironmentRepository):
            self.repo = session_or_repo
        else:
            self.repo = EnvironmentRepository(session_or_repo)

    async def create_environment(self, data: EnvironmentCreate) -> Environment:
        """Create a new environment within a project, validating uniqueness."""
        existing = await self.repo.get_by_name(data.project_id, data.name)
        if existing:
            raise ConflictError(
                f"Environment '{data.name}' already exists in this project."
            )

        if data.is_default:
            await self.repo.clear_default(data.project_id)

        return await self.repo.create(
            project_id=data.project_id,
            name=data.name,
            is_default=data.is_default,
        )

    async def get_environment(self, id: Union[uuid.UUID, str]) -> Environment:
        """Retrieve an environment by its ID, raising NotFoundError if missing."""
        return await self.repo.get(id)

    async def get_environment_by_name(
        self, project_id: Union[uuid.UUID, str], name: Union[EnvironmentName, str]
    ) -> Environment:
        """Retrieve an environment by project ID and name, raising NotFoundError if missing."""
        env = await self.repo.get_by_name(project_id, name)
        if not env:
            raise NotFoundError(
                f"Environment '{name}' not found in project '{project_id}'."
            )
        return env

    async def list_environments(
        self,
        project_id: Union[uuid.UUID, str],
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Environment], int]:
        """List all environments belonging to a project with pagination."""
        return await self.repo.list_by_project(project_id, offset=offset, limit=limit)

    async def set_default_environment(
        self,
        project_id: Union[uuid.UUID, str],
        environment_id: Union[uuid.UUID, str],
    ) -> Environment:
        """Reassign the default environment for a project."""
        env = await self.get_environment(environment_id)
        if str(env.project_id) != str(project_id):
            raise ValidationError("Environment does not belong to the specified project.")

        await self.repo.clear_default(project_id)
        return await self.repo.update(env, is_default=True)

    async def update_environment(
        self, id: Union[uuid.UUID, str], data: EnvironmentUpdate
    ) -> Environment:
        """Update environment attributes."""
        env = await self.get_environment(id)
        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != env.name:
            existing = await self.repo.get_by_name(env.project_id, update_data["name"])
            if existing and existing.id != env.id:
                raise ConflictError(
                    f"Environment '{update_data['name']}' already exists in this project."
                )

        if update_data.get("is_default") is True and not env.is_default:
            await self.repo.clear_default(env.project_id)

        return await self.repo.update(env, **update_data)

    async def delete_environment(self, id: Union[uuid.UUID, str]) -> None:
        """Delete an environment from a project.

        Service Rule:
            Cannot delete an environment if it is the default environment
            (must reassign the default environment first).
        """
        env = await self.get_environment(id)
        if env.is_default:
            raise ValidationError(
                "Cannot delete the default environment. Reassign the default environment first."
            )

        await self.repo.delete(env)
