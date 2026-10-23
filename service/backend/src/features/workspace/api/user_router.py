"""Handle regular-user workspace operations and document previews."""

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from features.agents.infrastructure.configuration.registry import get_agent
from features.identity.api.dependencies import agent_user, get_db
from features.workspace.api.presenters import serialize_file_entries
from features.workspace.api.schemas import FolderBody, RenameBody
from features.workspace.application.policies.operations import (
    is_path_protected,
    protected_paths,
    require_user_mutable_path,
)
from features.workspace.infrastructure.confidentiality.guard import (
    RestrictedContentGuard,
    cached_derivative_path_check,
)
from features.workspace.infrastructure.filesystem.service import (
    list_directory,
    remove_path,
    rename_path,
    safe_path,
    save_upload,
    workspace_size,
)
from features.workspace.infrastructure.previews.cache import (
    cached_document_preview,
    cached_pdf_page,
)
from features.workspace.infrastructure.previews.rendering import (
    ensure_previewable,
    image_preview,
)
from infrastructure.database.models import User
from infrastructure.settings import settings

router = APIRouter()


@router.get("/api/files")
async def files(
    path: str = "",
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """List the current user's workspace with effective access capabilities."""
    agent = get_agent(user.agent_id)
    protected = await protected_paths(session, agent.id)
    return {
        "path": path,
        "entries": serialize_file_entries(
            list_directory(agent.workspace_root, path), protected, administrator=False
        ),
        "used_bytes": workspace_size(agent.workspace_root),
        "limit_bytes": settings.max_workspace_bytes,
    }


@router.post("/api/files/upload", status_code=201)
async def upload_file(
    path: str = Form(default=""),
    upload: UploadFile = File(),
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Upload file."""
    agent = get_agent(user.agent_id)
    filename = Path(upload.filename or "upload.bin").name
    relative_destination = str(Path(path) / filename)
    await require_user_mutable_path(session, agent.id, relative_destination, include_parent=True)
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


@router.post("/api/files/folder", status_code=201)
async def create_folder(
    body: FolderBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Create folder."""
    agent = get_agent(user.agent_id)
    await require_user_mutable_path(session, agent.id, body.path, include_parent=True)
    path = safe_path(agent.workspace_root, body.path)
    try:
        path.mkdir()
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Path already exists")
    return {"path": str(path.relative_to(agent.workspace_root))}


@router.get("/api/files/download")
async def download_file(
    path: str,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Download file."""
    agent = get_agent(user.agent_id)
    if await is_path_protected(session, agent.id, path):
        raise HTTPException(status_code=403, detail="This file is available for preview only")
    target = safe_path(agent.workspace_root, path, must_exist=True)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")
    guard = RestrictedContentGuard.build(
        agent.workspace_root, await protected_paths(session, agent.id)
    )
    if guard.is_derivative_path(path):
        raise HTTPException(
            status_code=403,
            detail="Generated copies of restricted analysis-only files cannot be downloaded",
        )
    return FileResponse(target, filename=target.name)


@router.delete("/api/files", status_code=204)
async def delete_file(
    path: str,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete file."""
    agent = get_agent(user.agent_id)
    await require_user_mutable_path(session, agent.id, path)
    if not path:
        raise HTTPException(status_code=400, detail="Workspace root cannot be deleted")
    target = safe_path(agent.workspace_root, path, must_exist=True)
    remove_path(target)


@router.patch("/api/files")
async def rename_file(
    body: RenameBody,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Rename a file or folder inside its current workspace directory."""
    agent = get_agent(user.agent_id)
    await require_user_mutable_path(session, agent.id, body.path)
    destination = rename_path(agent.workspace_root, body.path, body.new_name)
    return {"path": str(destination.relative_to(agent.workspace_root))}


def request_accepts_gzip(request: Request) -> bool:
    """Return whether an HTTP request explicitly accepts nonzero-quality gzip."""
    for option in request.headers.get("accept-encoding", "").split(","):
        name, *parameters = (part.strip() for part in option.split(";"))
        if name.lower() not in {"gzip", "*"}:
            continue
        quality = 1.0
        for parameter in parameters:
            if parameter.lower().startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
        if quality > 0:
            return True
    return False


async def preview_response(
    target: Path,
    request: Request,
    sheet: str | None = None,
) -> Response:
    """Build a compressed, server-cached structured document preview response."""
    compressed = request_accepts_gzip(request)
    content = await run_in_threadpool(
        cached_document_preview,
        target,
        settings.preview_cache_dir,
        settings.preview_cache_max_bytes,
        settings.preview_cache_max_age_seconds,
        sheet,
        compressed,
    )
    headers = {
        "Cache-Control": "no-store, private",
        "Vary": "Accept-Encoding",
        "X-Content-Type-Options": "nosniff",
    }
    if compressed:
        headers["Content-Encoding"] = "gzip"
    return Response(
        content=content,
        media_type="application/json",
        headers=headers,
    )


async def pdf_page_response(target: Path, page: int) -> StreamingResponse:
    """Build a no-store PNG response from the private server-side cache."""
    content = await run_in_threadpool(
        cached_pdf_page,
        target,
        page,
        settings.preview_cache_dir,
        settings.preview_cache_max_bytes,
        settings.preview_cache_max_age_seconds,
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def image_preview_response(target: Path) -> FileResponse:
    """Build a validated no-store inline response for a raster image."""
    kind = ensure_previewable(target)
    if kind != "image":
        raise HTTPException(status_code=415, detail="Path is not a supported image")
    metadata = await run_in_threadpool(image_preview, target)
    return FileResponse(
        target,
        media_type=metadata["media_type"],
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/files/preview")
async def preview_file(
    request: Request,
    path: str,
    sheet: str | None = None,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Preview a supported file without exposing an editing endpoint."""
    agent = get_agent(user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    if not await is_path_protected(session, agent.id, path):
        is_derivative = await run_in_threadpool(
            cached_derivative_path_check,
            agent.workspace_root,
            await protected_paths(session, agent.id),
            path,
        )
        if is_derivative:
            raise HTTPException(
                status_code=403, detail="Restricted derivative preview is unavailable"
            )
    return await preview_response(target, request, sheet)


@router.get("/api/files/preview/pdf-page")
async def preview_pdf_page(
    path: str,
    page: int = 1,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Render one PDF page for the regular-user preview."""
    agent = get_agent(user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    if not await is_path_protected(session, agent.id, path):
        is_derivative = await run_in_threadpool(
            cached_derivative_path_check,
            agent.workspace_root,
            await protected_paths(session, agent.id),
            path,
        )
        if is_derivative:
            raise HTTPException(
                status_code=403, detail="Restricted derivative preview is unavailable"
            )
    return await pdf_page_response(target, page)


@router.get("/api/files/preview/image")
async def preview_image(
    path: str,
    user: User = Depends(agent_user),
    session: AsyncSession = Depends(get_db),
):
    """Return one validated raster image for the regular-user preview."""
    agent = get_agent(user.agent_id)
    target = safe_path(agent.workspace_root, path, must_exist=True)
    if not await is_path_protected(session, agent.id, path):
        is_derivative = await run_in_threadpool(
            cached_derivative_path_check,
            agent.workspace_root,
            await protected_paths(session, agent.id),
            path,
        )
        if is_derivative:
            raise HTTPException(
                status_code=403, detail="Restricted derivative preview is unavailable"
            )
    return await image_preview_response(target)
