"""Handle administrator read and workspace-management HTTP operations."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.agents.infrastructure.configuration.registry import get_agent
from features.chat.api.presenters import (
    serialize_conversation,
    serialize_conversation_detail,
)
from features.identity.api.dependencies import admin_user, get_db
from features.identity.api.presenters import serialize_admin_user
from features.workspace.api.presenters import serialize_file_entries
from features.workspace.api.schemas import AccessPolicyBody, FolderBody, RenameBody
from features.workspace.api.user_router import (
    image_preview_response,
    pdf_page_response,
    preview_response,
)
from features.workspace.application.policies.operations import (
    move_path_policies,
    protected_paths,
    remove_path_policies,
    set_path_policy,
    write_agent_policy_file,
)
from features.workspace.infrastructure.filesystem.service import (
    list_directory,
    remove_path,
    rename_path,
    safe_path,
    save_upload,
    workspace_size,
)
from features.workspace.infrastructure.previews.rendering import MAX_PREVIEW_BYTES, preview_kind
from infrastructure.database.models import Conversation, User
from infrastructure.settings import settings

router = APIRouter()


def conversation_export_response(
    conversation_id: uuid.UUID,
    content: dict,
) -> JSONResponse:
    """Build a JSON attachment response for an exported conversation."""
    return JSONResponse(
        content=jsonable_encoder(content),
        headers={
            "Content-Disposition": f'attachment; filename="conversation-{conversation_id}.json"'
        },
    )


async def managed_user(
    user_id: uuid.UUID,
    session: AsyncSession,
) -> User:
    """Return a regular user whose workspace can be managed by an administrator."""
    user = await session.scalar(
        select(User).where(User.id == user_id, User.is_admin.is_(False), User.agent_id.is_not(None))
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Managed user not found")
    return user


@router.get("/api/admin/users")
async def admin_users(
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """List regular users available to the administrator."""
    users = await session.scalars(
        select(User).where(User.is_admin.is_(False)).order_by(User.username)
    )
    return [serialize_admin_user(user) for user in users if user.agent_id]


@router.get("/api/admin/users/{user_id}/conversations")
async def admin_conversations(
    user_id: uuid.UUID,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """List conversations belonging to one managed user."""
    target_user = await managed_user(user_id, session)
    conversations = await session.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == target_user.id,
            Conversation.agent_id == target_user.agent_id,
        )
        .order_by(Conversation.updated_at.desc())
    )
    return [serialize_conversation(conversation) for conversation in conversations]


@router.get("/api/admin/users/{user_id}/conversations/{conversation_id}")
async def admin_conversation_detail(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Return one managed user's conversation as read-only history."""
    target_user = await managed_user(user_id, session)
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == target_user.id,
            Conversation.agent_id == target_user.agent_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await serialize_conversation_detail(conversation, session, administrator=True)


@router.get("/api/admin/users/{user_id}/conversations/{conversation_id}/export")
async def admin_export_conversation(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Download one managed user's complete persisted conversation as JSON."""
    return conversation_export_response(
        conversation_id,
        await admin_conversation_detail(
            user_id,
            conversation_id,
            _,
            session,
        ),
    )


@router.get("/api/admin/users/{user_id}/files")
async def admin_files(
    user_id: uuid.UUID,
    path: str = "",
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """List any regular user's workspace for administration."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    protected = await protected_paths(session, agent.id)
    return {
        "path": path,
        "entries": serialize_file_entries(
            list_directory(agent.workspace_root, path), protected, administrator=True
        ),
        "used_bytes": workspace_size(agent.workspace_root),
        "limit_bytes": settings.max_workspace_bytes,
    }


@router.post("/api/admin/users/{user_id}/files/upload", status_code=201)
async def admin_upload_file(
    user_id: uuid.UUID,
    path: str = Form(default=""),
    upload: UploadFile = File(),
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Upload a file into a managed user's workspace."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    filename = Path(upload.filename or "upload.bin").name
    destination_dir = (
        safe_path(agent.workspace_root, path, must_exist=True) if path else agent.workspace_root
    )
    if not destination_dir.is_dir():
        raise HTTPException(status_code=400, detail="Upload path is not a directory")
    destination = safe_path(agent.workspace_root, str(Path(path) / filename))
    size = await save_upload(
        upload,
        destination,
        settings.max_upload_bytes,
        settings.max_workspace_bytes,
        agent.workspace_root,
    )
    return {"path": str(destination.relative_to(agent.workspace_root)), "size": size}


@router.post("/api/admin/users/{user_id}/files/folder", status_code=201)
async def admin_create_folder(
    user_id: uuid.UUID,
    body: FolderBody,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a folder in a managed user's workspace."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, body.path)
    try:
        target.mkdir()
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Path already exists")
    return {"path": str(target.relative_to(agent.workspace_root))}


@router.patch("/api/admin/users/{user_id}/files")
async def admin_rename_file(
    user_id: uuid.UUID,
    body: RenameBody,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Rename a managed workspace file and preserve its access policies."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    destination = rename_path(agent.workspace_root, body.path, body.new_name)
    destination_relative = str(destination.relative_to(agent.workspace_root))
    await move_path_policies(session, agent.id, body.path, destination_relative)
    await write_agent_policy_file(session, agent.id, agent.workspace_root)
    return {"path": destination_relative}


@router.delete("/api/admin/users/{user_id}/files", status_code=204)
async def admin_delete_file(
    user_id: uuid.UUID,
    path: str,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete a managed workspace path and its access policies."""
    if not path:
        raise HTTPException(status_code=400, detail="Workspace root cannot be deleted")
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    remove_path(target)
    await remove_path_policies(session, agent.id, path)
    await write_agent_policy_file(session, agent.id, agent.workspace_root)


@router.put("/api/admin/users/{user_id}/files/access")
async def admin_set_file_access(
    user_id: uuid.UUID,
    body: AccessPolicyBody,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Set or remove inherited no-user-access protection for a workspace path."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, body.path, must_exist=True)
    if body.no_user_access:
        protected_files = (
            [target]
            if target.is_file()
            else [item for item in target.rglob("*") if item.is_file() and not item.is_symlink()]
        )
        unsupported = [
            item
            for item in protected_files
            if preview_kind(item) is None or item.stat().st_size > MAX_PREVIEW_BYTES
        ]
        if unsupported:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No user access requires every file to support a bounded read-only preview"
                ),
            )
    await set_path_policy(session, agent.id, body.path, body.no_user_access)
    await write_agent_policy_file(session, agent.id, agent.workspace_root)
    return {"path": body.path, "no_user_access": body.no_user_access}


@router.get("/api/admin/users/{user_id}/files/download")
async def admin_download_file(
    user_id: uuid.UUID,
    path: str,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Download a file from a managed user's workspace."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    return FileResponse(target, filename=target.name)


@router.get("/api/admin/users/{user_id}/files/preview")
async def admin_preview_file(
    request: Request,
    user_id: uuid.UUID,
    path: str,
    sheet: str | None = None,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Preview a supported managed-workspace file."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    return await preview_response(target, request, sheet)


@router.get("/api/admin/users/{user_id}/files/preview/pdf-page")
async def admin_preview_pdf_page(
    user_id: uuid.UUID,
    path: str,
    page: int = 1,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Render one PDF page from a managed user's workspace."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    return await pdf_page_response(target, page)


@router.get("/api/admin/users/{user_id}/files/preview/image")
async def admin_preview_image(
    user_id: uuid.UUID,
    path: str,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Return one validated raster image from a managed user's workspace."""
    target_user = await managed_user(user_id, session)
    agent = get_agent(target_user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    return await image_preview_response(target)
