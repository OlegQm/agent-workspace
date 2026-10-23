"""Characterize HTTP composition across vertical feature slices."""

from pathlib import Path
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
import respx
from fastapi import BackgroundTasks, HTTPException, UploadFile
from starlette.requests import Request
from starlette.responses import Response
from support.application import agent, login

from bootstrap import app as application
from bootstrap import http as http_boundary
from bootstrap import lifecycle
from features.agents.api import router as health_api
from features.chat.api import presenters as serializers
from features.chat.api import router as conversations_api
from features.chat.api import schemas as contracts
from features.identity.api import presenters as identity_serializers
from features.identity.api import router as sessions_api
from features.identity.api import schemas as identity_contracts
from features.workspace.api import admin_router as admin_api
from features.workspace.api import presenters as workspace_serializers
from features.workspace.api import schemas as workspace_contracts
from features.workspace.api import user_router as workspace_api
from features.workspace.domain.exceptions import InvalidWorkspacePolicyPath
from infrastructure.database.models import AgentRun, Conversation, RunStatus, User
from infrastructure.settings import settings


@pytest.mark.unit
async def test_asgi_request_limit_and_origin_guard_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve ASGI body-limit errors and same-origin production mutation enforcement."""
    events: list[dict] = []

    async def receive() -> dict:
        """Return one oversized streamed request body."""
        return {"type": "http.request", "body": b"12345", "more_body": False}

    async def send(message: dict) -> None:
        """Collect the ASGI response emitted by the limit middleware."""
        events.append(message)

    async def downstream(scope, bounded_receive, send) -> None:
        """Consume the bounded request to trigger the streamed size check."""
        await bounded_receive()

    middleware = http_boundary.RequestBodyLimitMiddleware(downstream)
    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    await middleware({"type": "http", "path": "/api/auth/login", "headers": []}, receive, send)
    assert events[0]["status"] == 413
    events.clear()
    await middleware(
        {
            "type": "http",
            "path": "/api/auth/login",
            "headers": [(b"content-length", b"invalid")],
        },
        receive,
        send,
    )
    assert events[0]["status"] == 400
    monkeypatch.setattr(settings, "app_env", "production")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/logout",
            "query_string": b"",
            "headers": [(b"host", b"localhost")],
            "server": ("localhost", 80),
        }
    )

    async def next_response(_: Request) -> Response:
        """Return a response when the guard permits a request."""
        return Response("ok")

    assert (await http_boundary.origin_guard(request, next_response)).status_code == 403
    monkeypatch.setattr(settings, "app_env", "development")
    allowed = await http_boundary.origin_guard(request, next_response)
    assert allowed.headers["x-content-type-options"] == "nosniff"


@pytest.mark.integration
async def test_application_lifespan_and_direct_error_boundaries(
    database, configured_agent: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve startup workspace preparation and fail-closed direct serializers."""
    monkeypatch.setattr(
        settings,
        "preview_cache_dir",
        configured_agent.workspace_root.parent / "preview-cache",
    )
    async with lifecycle.lifespan(application.app):
        assert (configured_agent.workspace_root / "outputs").is_dir()
        assert (configured_agent.workspace_root.parent / "workspace-access-policy.json").exists()
    with pytest.raises(RuntimeError, match="no agent assignment"):
        identity_serializers.serialize_user(User(username="bad", password_hash="unused"))
    with pytest.raises(RuntimeError, match="no agent assignment"):
        identity_serializers.serialize_admin_user(User(username="bad", password_hash="unused"))
    assert serializers.resolve_event_cursor(None, None) == 0
    with pytest.raises(ValueError, match="negative"):
        serializers.resolve_event_cursor(-1, None)


@pytest.mark.unit
def test_http_helper_contracts_cover_origins_gzip_and_serializers() -> None:
    """Preserve pure HTTP helper behavior independent of routing and persistence."""
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    request = Request(scope)
    assert http_boundary.header_origin("https://example.test/a?query=1") == "https://example.test"
    assert http_boundary.header_origin("not an origin") is None
    assert http_boundary.request_body_limit("/api/files/upload") > http_boundary.request_body_limit(
        "/api/auth/login"
    )
    assert workspace_api.request_accepts_gzip(request) is False
    gzip_request = Request({**scope, "headers": [(b"accept-encoding", b"br, gzip;q=0.5")]})
    disabled_request = Request({**scope, "headers": [(b"accept-encoding", b"gzip;q=no")]})
    assert workspace_api.request_accepts_gzip(gzip_request) is True
    assert workspace_api.request_accepts_gzip(disabled_request) is False
    assert (
        workspace_serializers.serialize_file_entries(
            [{"name": "private.xlsx", "path": "private.xlsx", "type": "file", "size": 1}],
            ["private.xlsx"],
            administrator=False,
        )[0]["can_download"]
        is False
    )


@pytest.mark.integration
async def test_remaining_file_run_and_admin_http_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterize remaining public file, run-control, preview, and administrator branches."""
    configured_agent.workspace_root.joinpath("plain.txt").write_text("plain")
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Page")
    pdf.save(configured_agent.workspace_root / "report.pdf")
    pdf.close()
    monkeypatch.setattr(
        settings, "preview_cache_dir", configured_agent.workspace_root.parent / "cache"
    )

    async def stop(_: AgentRun) -> None:
        """Represent a successful delegated runtime stop request."""

    async def approve(_: AgentRun, __: str) -> None:
        """Represent a successful delegated approval request."""

    monkeypatch.setattr(conversations_api, "stop_hermes_run", stop)
    monkeypatch.setattr(conversations_api, "approve_hermes_run", approve)
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Controls")
        session.add(conversation)
        await session.flush()
        waiting = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status="waiting_approval",
            hermes_run_id="h",
        )
        session.add(waiting)
        await session.commit()
        await session.refresh(waiting)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (
            await client.get("/api/files/download", params={"path": "plain.txt"})
        ).status_code == 200
        assert (
            await client.get("/api/files/download", params={"path": "missing.txt"})
        ).status_code == 404
        assert (await client.get("/api/files/download", params={"path": ""})).status_code == 400
        assert (await client.delete("/api/files", params={"path": "plain.txt"})).status_code == 204
        assert (
            await client.post(
                "/api/files/upload",
                data={"path": "report.pdf"},
                files={"upload": ("x.txt", b"x")},
            )
        ).status_code == 400
        assert (
            await client.get(
                "/api/files/preview/pdf-page", params={"path": "report.pdf", "page": 1}
            )
        ).status_code == 200
        assert (
            await client.get(
                "/api/files/preview/pdf-page", params={"path": "report.pdf", "page": 2}
            )
        ).status_code == 404
        assert (
            await client.post(f"/api/runs/{waiting.id}/approval", json={"decision": "once"})
        ).json() == {"status": "running"}
        assert (await client.post(f"/api/runs/{waiting.id}/stop")).json() == {"status": "stopping"}
        await client.post("/api/auth/logout")
        await login(client, "administrator")
        target = str(users[0].id)
        assert (
            await client.post(f"/api/admin/users/{target}/files/folder", json={"path": "admin"})
        ).status_code == 201
        assert (
            await client.post(f"/api/admin/users/{target}/files/folder", json={"path": "admin"})
        ).status_code == 409
        assert (
            await client.post(
                f"/api/admin/users/{target}/files/upload",
                data={"path": "admin"},
                files={"upload": ("file.txt", b"x")},
            )
        ).status_code == 201
        assert (
            await client.delete(f"/api/admin/users/{target}/files", params={"path": ""})
        ).status_code == 400
        assert (
            await client.get(f"/api/admin/users/{target}/files/download", params={"path": "admin"})
        ).status_code == 400
        assert (
            await client.get(
                f"/api/admin/users/{target}/files/preview/pdf-page",
                params={"path": "report.pdf", "page": 1},
            )
        ).status_code == 200


@pytest.mark.integration
async def test_remaining_endpoint_error_and_administrator_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve remaining route errors without making a real Hermes request."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("regular.txt").write_text("regular")
    workspace.joinpath("unsupported.bin").write_text("cannot preview when restricted")
    workspace.joinpath("folder").mkdir()
    async with database() as session:
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Saved")
        session.add(conversation)
        await session.flush()
        completed = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.completed.value,
        )
        waiting = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.waiting_approval.value,
        )
        session.add_all([completed, waiting])
        await session.commit()
        await session.refresh(conversation)
        await session.refresh(completed)
        await session.refresh(waiting)

    async def denied_approval(_: AgentRun, __: str) -> None:
        """Return the delegated runtime rejection used by the HTTP translation test."""
        raise RuntimeError("approval unavailable")

    monkeypatch.setattr(conversations_api, "approve_hermes_run", denied_approval)
    monkeypatch.setattr(settings, "preview_cache_dir", workspace.parent / "cache")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (await client.get("/api/conversations")).json()[0]["id"] == str(conversation.id)
        assert (await client.get("/api/conversations/not-a-uuid")).status_code == 422
        assert (
            await client.get("/api/runs/00000000-0000-0000-0000-000000000001")
        ).status_code == 404
        assert (
            await client.post(f"/api/runs/{completed.id}/approval", json={"decision": "once"})
        ).status_code == 409
        rejected = await client.post(f"/api/runs/{waiting.id}/approval", json={"decision": "once"})
        assert rejected.status_code == 409
        assert (await client.delete(f"/api/conversations/{conversation.id}")).status_code == 409
        await client.post("/api/auth/logout")
        await login(client, "administrator")
        target = str(users[0].id)
        assert (
            await client.get(
                f"/api/admin/users/{target}/conversations/00000000-0000-0000-0000-000000000001"
            )
        ).status_code == 404
        assert (
            await client.get("/api/admin/users/00000000-0000-0000-0000-000000000001/files")
        ).status_code == 404
        assert (
            await client.put(
                f"/api/admin/users/{target}/files/access",
                json={"path": "unsupported.bin", "no_user_access": True},
            )
        ).status_code == 400
        assert (
            await client.post(
                f"/api/admin/users/{target}/files/upload",
                data={"path": "regular.txt"},
                files={"upload": ("other.txt", b"x")},
            )
        ).status_code == 400
        assert (
            await client.get(
                f"/api/admin/users/{target}/files/download", params={"path": "missing.txt"}
            )
        ).status_code == 404


@pytest.mark.integration
async def test_queue_run_and_preview_guard_failure_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve queue precondition errors and derivative-preview refusal behavior."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("directory").mkdir()
    async with database() as session:
        conversation = Conversation(
            user_id=users[0].id, agent_id="assistant", title="New conversation"
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        with pytest.raises(Exception, match="runtime state"):
            await conversations_api.queue_run(
                conversation,
                contracts.RunBody(content="message"),
                BackgroundTasks(),
                users[0],
                session,
            )
        from infrastructure.database.models import ConversationRuntime

        session.add(
            ConversationRuntime(conversation_id=conversation.id, hermes_session_id="session")
        )
        await session.commit()

        async def unavailable(_: str) -> None:
            """Represent an unavailable runtime capability endpoint."""
            raise RuntimeError("runtime unavailable")

        monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", unavailable)
        with pytest.raises(Exception, match="runtime unavailable"):
            await conversations_api.queue_run(
                conversation,
                contracts.RunBody(content="message"),
                BackgroundTasks(),
                users[0],
                session,
            )

        async def compatible(_: str) -> None:
            """Allow attachment validation to be exercised in isolation."""

        monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
        with pytest.raises(Exception, match="Attachment is not a file"):
            await conversations_api.queue_run(
                conversation,
                contracts.RunBody(content="message", attachments=["directory"]),
                BackgroundTasks(),
                users[0],
                session,
            )

    workspace.joinpath("preview.txt").write_text("safe")
    monkeypatch.setattr(workspace_api, "cached_derivative_path_check", lambda *_: True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (
            await client.get("/api/files/preview", params={"path": "preview.txt"})
        ).status_code == 403


@pytest.mark.unit
async def test_application_pure_middleware_and_preview_response_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve ASGI and response helper branches independent of registered routes."""
    sent: list[dict] = []

    async def receive() -> dict:
        """Supply no body to the synthetic ASGI application."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        """Capture the synthetic ASGI response."""
        sent.append(message)

    called: list[str] = []

    async def non_http(scope, receive, send) -> None:
        """Record pass-through non-HTTP calls."""
        called.append(scope["type"])

    middleware = http_boundary.RequestBodyLimitMiddleware(non_http)
    await middleware({"type": "websocket"}, receive, send)
    assert called == ["websocket"]

    async def no_read(scope, receive, send) -> None:
        """Avoid consuming a body after declared-length rejection."""

    middleware = http_boundary.RequestBodyLimitMiddleware(no_read)
    await middleware(
        {"type": "http", "path": "/api/auth/login", "headers": [(b"content-length", b"-1")]},
        receive,
        send,
    )
    assert sent[-2]["status"] == 400
    await middleware(
        {"type": "http", "path": "/api/auth/login", "headers": [(b"content-length", b"99999999")]},
        receive,
        send,
    )
    assert sent[-2]["status"] == 413
    assert http_boundary.header_origin("http://[::1") is None
    assert workspace_api.request_accepts_gzip(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"accept-encoding", b"*;q=1")],
            }
        )
    )

    target = tmp_path / "target.xlsx"
    target.write_bytes(b"unused")
    monkeypatch.setattr(workspace_api, "cached_document_preview", lambda *args: b"{}")
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [(b"accept-encoding", b"gzip")]}
    )
    response = await workspace_api.preview_response(target, request)
    assert response.headers["content-encoding"] == "gzip"
    plain = await workspace_api.preview_response(
        target, Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    )
    assert "content-encoding" not in plain.headers


@pytest.mark.integration
async def test_file_and_admin_handlers_direct_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterize route-handler behavior directly with a disposable database session."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("direct.txt").write_text("direct")
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(workspace / "direct.pdf")
    pdf.close()
    monkeypatch.setattr(settings, "preview_cache_dir", workspace.parent / "cache")
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    async with database() as session:
        listing = await workspace_api.files("", users[0], session)
        assert listing["entries"]
        await workspace_api.create_folder(
            workspace_contracts.FolderBody(path="direct-folder"), users[0], session
        )
        uploaded = UploadFile(filename="upload.txt", file=__import__("io").BytesIO(b"upload"))
        assert (await workspace_api.upload_file("direct-folder", uploaded, users[0], session))[
            "size"
        ] == 6
        assert (
            await workspace_api.download_file("direct.txt", users[0], session)
        ).filename == "direct.txt"
        renamed = await workspace_api.rename_file(
            workspace_contracts.RenameBody(path="direct-folder/upload.txt", new_name="renamed.txt"),
            users[0],
            session,
        )
        assert renamed == {"path": "direct-folder/renamed.txt"}
        await workspace_api.delete_file("direct-folder/renamed.txt", users[0], session)
        assert (
            await workspace_api.preview_file(request, "direct.pdf", None, users[0], session)
        ).status_code == 200
        assert (
            await workspace_api.preview_pdf_page("direct.pdf", 1, users[0], session)
        ).status_code == 200

        assert (await admin_api.admin_files(users[0].id, "", users[1], session))["entries"]
        await admin_api.admin_create_folder(
            users[0].id, workspace_contracts.FolderBody(path="managed"), users[1], session
        )
        admin_upload = UploadFile(filename="managed.txt", file=__import__("io").BytesIO(b"managed"))
        assert (
            await admin_api.admin_upload_file(
                users[0].id, "managed", admin_upload, users[1], session
            )
        )["size"] == 7
        renamed = await admin_api.admin_rename_file(
            users[0].id,
            workspace_contracts.RenameBody(path="managed/managed.txt", new_name="renamed.txt"),
            users[1],
            session,
        )
        assert renamed == {"path": "managed/renamed.txt"}
        assert (
            await admin_api.admin_download_file(
                users[0].id, "managed/renamed.txt", users[1], session
            )
        ).filename == "renamed.txt"
        await admin_api.admin_delete_file(users[0].id, "managed/renamed.txt", users[1], session)
        assert (
            await admin_api.admin_preview_file(
                request, users[0].id, "direct.pdf", None, users[1], session
            )
        ).status_code == 200
        assert (
            await admin_api.admin_preview_pdf_page(users[0].id, "direct.pdf", 1, users[1], session)
        ).status_code == 200
        access = await admin_api.admin_set_file_access(
            users[0].id,
            workspace_contracts.AccessPolicyBody(path="direct.pdf", no_user_access=True),
            users[1],
            session,
        )
        assert access["no_user_access"] is True


@pytest.mark.integration
async def test_application_direct_auth_conversation_and_run_error_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve direct orchestration behavior for login, conversations, events, and approvals."""
    async with database() as session:
        with pytest.raises(Exception, match="Invalid credentials"):
            await sessions_api.login(
                identity_contracts.LoginBody(username="assistant-user", password="wrong"),
                Response(),
                session,
            )
        assert (await sessions_api.refresh_session(users[0]))["user_id"] == str(users[0].id)
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        assert await sessions_api.logout(request, Response(), session) is None
        assert await conversations_api.conversations(users[0], session) == []
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Existing title")
        session.add(conversation)
        await session.flush()
        from infrastructure.database.models import ConversationRuntime

        session.add(
            ConversationRuntime(conversation_id=conversation.id, hermes_session_id="session_direct")
        )
        await session.commit()

        async def compatible(_: str) -> None:
            """Allow queue orchestration without an external runtime."""

        async def no_execute(_: object) -> None:
            """Keep direct run submissions local to the test process."""

        monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
        monkeypatch.setattr(conversations_api, "execute_run", no_execute)
        run = await conversations_api.queue_run(
            conversation,
            contracts.RunBody(content="follow up"),
            BackgroundTasks(),
            users[0],
            session,
        )
        assert conversation.title == "Existing title"
        run.status = RunStatus.completed.value
        await session.commit()
        second = await conversations_api.start_run(
            conversation.id,
            contracts.RunBody(content="second"),
            BackgroundTasks(),
            users[0],
            session,
        )
        assert second["id"]
        stored_second = await session.get(AgentRun, __import__("uuid").UUID(second["id"]))
        stored_second.status = RunStatus.completed.value
        await session.commit()
        started = await conversations_api.start_new_conversation_run(
            contracts.RunBody(content="brand new"), BackgroundTasks(), users[0], session
        )
        assert started["conversation"]["title"] == "brand new"
        new_run = await session.get(AgentRun, __import__("uuid").UUID(started["run"]["id"]))
        new_run.status = RunStatus.completed.value
        await session.commit()
        with pytest.raises(HTTPException):
            await conversations_api.owned_run(__import__("uuid").uuid4(), users[0], session)

        async def stream(_: object, __: int):
            """Yield a deterministic event stream for the route response."""
            yield "event: stream-end\n\n"

        monkeypatch.setattr(conversations_api, "event_stream", stream)
        event_response = await conversations_api.run_events(
            run.id,
            Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
            None,
            users[0],
            session,
        )
        assert event_response.media_type == "text/event-stream"

        waiting = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.waiting_approval.value,
            hermes_run_id="hermes_direct",
        )
        session.add(waiting)
        await session.commit()

        async def runtime_http_error(_: AgentRun, __: str) -> None:
            """Exercise the runtime-unavailable translation path."""
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(conversations_api, "approve_hermes_run", runtime_http_error)
        with pytest.raises(Exception, match="unavailable"):
            await conversations_api.approve_run(
                waiting.id, contracts.ApprovalBody(decision="once"), users[0], session
            )


@pytest.mark.integration
async def test_application_remaining_security_and_file_error_branches(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve rejection branches for origins, files, managed users, and delegated runtime failures."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("file.txt").write_text("file")
    workspace.joinpath("directory").mkdir()
    monkeypatch.setattr(settings, "preview_cache_dir", workspace.parent / "cache")
    async with database() as session:
        unmanaged = User(username="unmanaged", password_hash="unused", is_admin=False)
        session.add(unmanaged)
        await session.commit()
        blocked_request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/api/auth/logout",
                "query_string": b"",
                "headers": [(b"host", b"localhost"), (b"origin", b"https://forbidden.test")],
                "server": ("localhost", 80),
            }
        )

        async def next_response(_: Request) -> Response:
            """Provide a response that should not be reached after origin rejection."""
            return Response("unexpected")

        assert (await http_boundary.origin_guard(blocked_request, next_response)).status_code == 403
        with pytest.raises(HTTPException, match="not a directory"):
            await workspace_api.upload_file(
                "file.txt",
                UploadFile(filename="new.txt", file=__import__("io").BytesIO(b"x")),
                users[0],
                session,
            )
        await workspace_api.create_folder(
            workspace_contracts.FolderBody(path="new-folder"), users[0], session
        )
        with pytest.raises(HTTPException, match="already exists"):
            await workspace_api.create_folder(
                workspace_contracts.FolderBody(path="new-folder"), users[0], session
            )
        with pytest.raises(HTTPException, match="not a file"):
            await workspace_api.download_file("directory", users[0], session)
        with pytest.raises(InvalidWorkspacePolicyPath, match="Invalid policy path"):
            await workspace_api.delete_file("", users[0], session)
        with pytest.raises(HTTPException, match="Managed user not found"):
            await admin_api.managed_user(unmanaged.id, session)
        assert [item["username"] for item in await admin_api.admin_users(users[1], session)] == [
            "assistant-user"
        ]
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Saved")
        session.add(conversation)
        await session.commit()
        with pytest.raises(HTTPException, match="Conversation not found"):
            await admin_api.admin_conversation_detail(
                users[0].id, __import__("uuid").uuid4(), users[1], session
            )
        with pytest.raises(HTTPException, match="not a directory"):
            await admin_api.admin_upload_file(
                users[0].id,
                "file.txt",
                UploadFile(filename="new.txt", file=__import__("io").BytesIO(b"x")),
                users[1],
                session,
            )
        await admin_api.admin_create_folder(
            users[0].id, workspace_contracts.FolderBody(path="admin-folder"), users[1], session
        )
        with pytest.raises(HTTPException, match="already exists"):
            await admin_api.admin_create_folder(
                users[0].id, workspace_contracts.FolderBody(path="admin-folder"), users[1], session
            )
        with pytest.raises(HTTPException, match="root cannot be deleted"):
            await admin_api.admin_delete_file(users[0].id, "", users[1], session)
        with pytest.raises(HTTPException, match="not a file"):
            await admin_api.admin_download_file(users[0].id, "directory", users[1], session)

        async def approval_runtime_error(_: AgentRun, __: str) -> None:
            """Exercise delegated runtime errors that map to a conflict response."""
            raise RuntimeError("rejected")

        monkeypatch.setattr(conversations_api, "approve_hermes_run", approval_runtime_error)
        waiting = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.waiting_approval.value,
        )
        session.add(waiting)
        await session.commit()
        with pytest.raises(HTTPException, match="rejected"):
            await conversations_api.approve_run(
                waiting.id, contracts.ApprovalBody(decision="once"), users[0], session
            )


@pytest.mark.integration
async def test_application_remaining_run_and_restricted_file_branches(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve active-run, runtime-health, restricted-download, and policy-directory failures."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("private.xlsx").write_text("private")
    workspace.joinpath("derivative.txt").write_text("derived")
    restricted_directory = workspace / "restricted-directory"
    restricted_directory.mkdir()
    restricted_directory.joinpath("unsupported.bin").write_text("unsupported")
    async with database() as session:
        from features.workspace.application.policies.operations import set_path_policy

        await set_path_policy(session, "assistant", "private.xlsx", True)
        with pytest.raises(HTTPException, match="preview only"):
            await workspace_api.download_file("private.xlsx", users[0], session)
        await set_path_policy(session, "assistant", "private.xlsx", False)
        monkeypatch.setattr(
            workspace_api.RestrictedContentGuard,
            "build",
            lambda *_: SimpleNamespace(is_derivative_path=lambda _: True),
        )
        with pytest.raises(HTTPException, match="Generated copies"):
            await workspace_api.download_file("derivative.txt", users[0], session)
        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Active")
        session.add(conversation)
        await session.flush()
        active = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.running.value,
        )
        session.add(active)
        await session.commit()
        with pytest.raises(HTTPException, match="Stop the active"):
            await conversations_api.delete_conversation(conversation.id, users[0], session)

        async def stopped(_: AgentRun) -> None:
            """Record the delegated successful stop operation."""

        monkeypatch.setattr(conversations_api, "stop_hermes_run", stopped)
        assert (await conversations_api.stop_run(active.id, users[0], session)) == {
            "status": "stopping"
        }
        with pytest.raises(HTTPException, match="No user access requires"):
            await admin_api.admin_set_file_access(
                users[0].id,
                workspace_contracts.AccessPolicyBody(
                    path="restricted-directory", no_user_access=True
                ),
                users[1],
                session,
            )


@pytest.mark.integration
@respx.mock
async def test_application_health_exception_and_direct_login_logout_contracts(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve health transport failure plus direct authenticated login/logout persistence."""
    configured_agent.hermes_url = "http://health-error.test"
    monkeypatch.setattr(health_api, "hermes_headers", lambda _: {})
    respx.get("http://health-error.test/v1/capabilities").mock(
        side_effect=httpx.ConnectError("offline")
    )
    async with database() as session:
        response = Response()
        result = await sessions_api.login(
            identity_contracts.LoginBody(
                username="assistant-user", password="correct horse battery staple"
            ),
            response,
            session,
        )
        assert result["user"]["username"] == "assistant-user"
        token = response.headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [(b"cookie", f"open-agent-workspace_ai_session={token}".encode())],
            }
        )
        assert await sessions_api.logout(request, Response(), session) is None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application.app), base_url="http://localhost"
    ) as client:
        await login(client, "assistant-user")
        assert (await client.get("/api/health")).json()["hermes"] == "unavailable"


@pytest.mark.integration
async def test_application_last_direct_handler_branches(
    users: tuple[User, User],
    configured_agent: SimpleNamespace,
    database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve final direct branches for deletion, duplicate runs, events, previews, and access removal."""
    workspace = configured_agent.workspace_root
    workspace.joinpath("preview.txt").write_text("preview")
    async with database() as session:
        empty = Conversation(user_id=users[0].id, agent_id="assistant", title="Empty")
        session.add(empty)
        await session.commit()
        assert await conversations_api.delete_conversation(empty.id, users[0], session) is None

        conversation = Conversation(user_id=users[0].id, agent_id="assistant", title="Run")
        session.add(conversation)
        await session.flush()
        from infrastructure.database.models import ConversationRuntime

        session.add(
            ConversationRuntime(conversation_id=conversation.id, hermes_session_id="session_last")
        )
        existing = AgentRun(
            conversation_id=conversation.id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.running.value,
        )
        session.add(existing)
        await session.commit()
        conversation_id = conversation.id

        async def compatible(_: str) -> None:
            """Allow the duplicate-run database guard to be reached."""

        monkeypatch.setattr(conversations_api, "ensure_hermes_session_capability", compatible)
        with pytest.raises(HTTPException, match="already has an active"):
            await conversations_api.queue_run(
                conversation,
                contracts.RunBody(content="duplicate"),
                BackgroundTasks(),
                users[0],
                session,
            )
        await session.refresh(existing)
        existing.status = RunStatus.completed.value
        await session.commit()
        assert (await conversations_api.stop_run(existing.id, users[0], session))[
            "status"
        ] == "completed"
        with pytest.raises(HTTPException, match="not waiting"):
            await conversations_api.approve_run(
                existing.id, contracts.ApprovalBody(decision="once"), users[0], session
            )

        async def approval_ok(_: AgentRun, __: str) -> None:
            """Model a successful approval delegation."""

        waiting = AgentRun(
            conversation_id=conversation_id,
            user_id=users[0].id,
            agent_id="assistant",
            status=RunStatus.waiting_approval.value,
            hermes_run_id="run_last",
        )
        session.add(waiting)
        await session.commit()
        monkeypatch.setattr(conversations_api, "approve_hermes_run", approval_ok)
        assert await conversations_api.approve_run(
            waiting.id, contracts.ApprovalBody(decision="always"), users[0], session
        ) == {"status": "running"}
        with pytest.raises(HTTPException, match="Invalid Last-Event-ID"):
            await conversations_api.run_events(
                waiting.id,
                Request(
                    {
                        "type": "http",
                        "method": "GET",
                        "path": "/",
                        "headers": [(b"last-event-id", b"invalid")],
                    }
                ),
                None,
                users[0],
                session,
            )

        monkeypatch.setattr(workspace_api, "is_path_protected", lambda *_: _async_true())
        monkeypatch.setattr(workspace_api, "preview_response", lambda *_: _async_response())
        assert (
            await workspace_api.preview_file(
                Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
                "preview.txt",
                None,
                users[0],
                session,
            )
        ).status_code == 200
        monkeypatch.setattr(workspace_api, "pdf_page_response", lambda *_: _async_response())
        assert (
            await workspace_api.preview_pdf_page("preview.txt", 1, users[0], session)
        ).status_code == 200
        assert await admin_api.admin_conversations(users[0].id, users[1], session)
        assert (
            await admin_api.admin_conversation_detail(
                users[0].id, conversation_id, users[1], session
            )
        )["id"] == str(conversation_id)
        assert await admin_api.admin_set_file_access(
            users[0].id,
            workspace_contracts.AccessPolicyBody(path="preview.txt", no_user_access=False),
            users[1],
            session,
        ) == {"path": "preview.txt", "no_user_access": False}


@pytest.mark.unit
async def test_application_final_middleware_preview_and_root_delete_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve final ASGI receive, gzip parameter, derivative PDF, and root-delete branches."""
    messages: list[dict] = []

    async def receive() -> dict:
        """Return a non-request ASGI message to the bounded receiver."""
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        """Collect downstream messages for the middleware harness."""
        messages.append(message)

    async def downstream(scope, bounded_receive, send) -> None:
        """Consume a non-request message without triggering a size rejection."""
        assert (await bounded_receive())["type"] == "http.disconnect"

    await http_boundary.RequestBodyLimitMiddleware(downstream)(
        {"type": "http", "path": "/", "headers": []}, receive, send
    )
    assert messages == []
    assert workspace_api.request_accepts_gzip(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(b"accept-encoding", b"gzip; level=1")],
            }
        )
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "preview.pdf"
    target.write_bytes(b"placeholder")
    configured = agent(workspace)
    user = User(username="user", password_hash="unused", agent_id="assistant")
    monkeypatch.setattr(workspace_api, "get_agent", lambda _: configured)
    monkeypatch.setattr(workspace_api, "is_path_protected", lambda *_: _async_false())
    monkeypatch.setattr(workspace_api, "protected_paths", lambda *_: _async_list())
    monkeypatch.setattr(workspace_api, "cached_derivative_path_check", lambda *_: True)
    with pytest.raises(HTTPException, match="derivative preview"):
        await workspace_api.preview_pdf_page(target.name, 1, user, object())
    monkeypatch.setattr(
        workspace_api, "require_user_mutable_path", lambda *_args, **_kwargs: _async_none()
    )
    with pytest.raises(HTTPException, match="root cannot be deleted"):
        await workspace_api.delete_file("", user, object())


async def _async_true() -> bool:
    """Return a protected-path marker for preview short-circuit tests."""
    return True


async def _async_response() -> Response:
    """Return a small response for preview helper substitutions."""
    return Response("preview")


async def _async_false() -> bool:
    """Return an unprotected-path marker for derivative checks."""
    return False


async def _async_list() -> list[str]:
    """Return an empty protected-path list for derivative checks."""
    return []


async def _async_none() -> None:
    """Provide a no-op mutable-path dependency for direct root-delete testing."""


@pytest.mark.unit
def test_application_entrypoint_and_pure_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve invalid gzip quality handling and the fixed local Uvicorn composition root."""
    assert (
        workspace_api.request_accepts_gzip(
            Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/",
                    "headers": [(b"accept-encoding", b"gzip;q=invalid, br")],
                }
            )
        )
        is False
    )
    received: dict[str, object] = {}
    import uvicorn

    monkeypatch.setattr(
        uvicorn, "run", lambda *args, **kwargs: received.update(args=args, kwargs=kwargs)
    )
    application.main()
    assert received["args"] == ("bootstrap.app:app",)
    assert received["kwargs"]["host"] == "127.0.0.1"
