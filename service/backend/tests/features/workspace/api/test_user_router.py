"""Test regular-user workspace endpoints."""

import base64
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from support.application import login

from bootstrap import app as application
from features.workspace.api import user_router as workspace_api
from features.workspace.application.policies.operations import set_path_policy
from infrastructure.database.models import User
from infrastructure.settings import settings


@pytest.mark.integration
async def test_workspace_restriction_and_validation_error_contracts(
    users: tuple[User, User], configured_agent: SimpleNamespace, database
) -> None:
    """Verify protected-file, duplicate-folder, root-delete, and validation failures."""
    restricted = configured_agent.workspace_root / "restricted.xlsx"
    restricted.write_text("private")
    async with database() as session:
        from features.workspace.application.policies.operations import set_path_policy

        await set_path_policy(session, "assistant", "restricted.xlsx", True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (
            await client.get("/api/files/download", params={"path": "restricted.xlsx"})
        ).status_code == 403
        assert (await client.delete("/api/files", params={"path": ""})).status_code == 400
        assert (await client.post("/api/files/folder", json={"path": "same"})).status_code == 201
        assert (await client.post("/api/files/folder", json={"path": "same"})).status_code == 409
        assert (
            await client.patch(
                "/api/files", json={"path": "restricted.xlsx", "new_name": "other.xlsx"}
            )
        ).status_code == 403
        assert (await client.get("/api/runs/not-a-uuid")).status_code == 422


@pytest.mark.integration
@pytest.mark.contract
async def test_workspace_file_http_contract(
    users: tuple[User, User], configured_agent: SimpleNamespace
) -> None:
    """Verify the regular-user file list, creation, upload, rename, download, and deletion APIs."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (await client.post("/api/files/folder", json={"path": "reports"})).json() == {
            "path": "reports"
        }
        uploaded = await client.post(
            "/api/files/upload",
            data={"path": "reports"},
            files={"upload": ("budget.txt", b"budget", "text/plain")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json() == {"path": "reports/budget.txt", "size": 6}
        listing = await client.get("/api/files", params={"path": "reports"})
        assert listing.status_code == 200
        assert listing.json()["entries"][0] == {
            "name": "budget.txt",
            "path": "reports/budget.txt",
            "type": "file",
            "size": 6,
            "modified_at": pytest.approx(listing.json()["entries"][0]["modified_at"]),
            "preview_kind": "txt",
            "no_user_access": False,
            "no_user_access_explicit": False,
            "no_user_access_inherited": False,
            "can_download": True,
            "can_modify": True,
            "can_copy": True,
        }
        renamed = await client.patch(
            "/api/files", json={"path": "reports/budget.txt", "new_name": "final.txt"}
        )
        assert renamed.json() == {"path": "reports/final.txt"}
        downloaded = await client.get("/api/files/download", params={"path": "reports/final.txt"})
        assert downloaded.status_code == 200
        assert downloaded.content == b"budget"
        assert (
            await client.delete("/api/files", params={"path": "reports/final.txt"})
        ).status_code == 204


@pytest.mark.integration
async def test_workspace_preview_contract(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify bounded XLSX previews and negotiated gzip responses for regular users."""
    workbook = Workbook()
    workbook.active.append(["Metric", "Value"])
    workbook.active.append(["Revenue", 42])
    workbook.save(configured_agent.workspace_root / "report.xlsx")
    configured_agent.workspace_root.joinpath("notes.txt").write_text(
        "One\nTwo\n", encoding="utf-8"
    )
    configured_agent.workspace_root.joinpath("chart.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )
    monkeypatch.setattr(
        settings,
        "preview_cache_dir",
        configured_agent.workspace_root.parent / "preview-cache",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        preview = await client.get("/api/files/preview", params={"path": "report.xlsx"})
        assert preview.status_code == 200
        assert preview.json()["kind"] == "xlsx"
        compressed = await client.get(
            "/api/files/preview",
            params={"path": "report.xlsx"},
            headers={"Accept-Encoding": "gzip"},
        )
        assert compressed.headers["content-encoding"] == "gzip"
        text_preview = await client.get("/api/files/preview", params={"path": "notes.txt"})
        assert text_preview.json() == {
            "kind": "txt",
            "content": "One\nTwo\n",
            "truncated": False,
        }
        image_preview = await client.get("/api/files/preview", params={"path": "chart.png"})
        assert image_preview.json() == {
            "kind": "image",
            "media_type": "image/png",
            "width": 1,
            "height": 1,
        }
        image = await client.get("/api/files/preview/image", params={"path": "chart.png"})
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["content-disposition"] == "inline"
        assert image.content.startswith(b"\x89PNG")
        not_an_image = await client.get(
            "/api/files/preview/image", params={"path": "notes.txt"}
        )
        assert not_an_image.status_code == 415

        async with database() as session:
            await set_path_policy(session, "assistant", "chart.png", True)
            direct_protected = await workspace_api.preview_image(
                "chart.png", users[0], session
            )
            assert direct_protected.media_type == "image/png"
        protected_image = await client.get(
            "/api/files/preview/image", params={"path": "chart.png"}
        )
        assert protected_image.status_code == 200

        configured_agent.workspace_root.joinpath("generated.png").write_bytes(image.content)
        monkeypatch.setattr(
            workspace_api,
            "cached_derivative_path_check",
            lambda *_: True,
        )
        async with database() as session:
            with pytest.raises(HTTPException, match="derivative"):
                await workspace_api.preview_image("generated.png", users[0], session)
        derivative = await client.get(
            "/api/files/preview/image", params={"path": "generated.png"}
        )
        assert derivative.status_code == 403


@pytest.mark.integration
async def test_workspace_image_preview_requires_authentication(
    configured_agent: SimpleNamespace,
) -> None:
    """Prevent an unauthenticated request from reading workspace image bytes."""
    configured_agent.workspace_root.joinpath("private.png").write_bytes(b"private")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        response = await client.get(
            "/api/files/preview/image", params={"path": "private.png"}
        )

    assert response.status_code == 401
