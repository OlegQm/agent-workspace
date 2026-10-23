"""Characterize the complete ClickUp adapter without network access."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.clickup.infrastructure import client as module
from tool_gateway.integrations.clickup.infrastructure.client import ClickUpClient

settings = Settings()


class Response:
    """Provide JSON and streamed response behavior."""

    def __init__(self, payload: dict, chunks: tuple[bytes, ...] = ()) -> None:
        """Store response content."""
        self.payload = payload
        self.chunks = chunks
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        """Represent a successful response."""

    def json(self) -> dict:
        """Return configured JSON."""
        return self.payload

    async def aiter_bytes(self):
        """Yield configured stream chunks."""
        for chunk in self.chunks:
            yield chunk


class Client:
    """Record HTTP calls and act as both client and stream context manager."""

    def __init__(self, responses: list[Response]) -> None:
        """Store ordered fake responses."""
        self.responses = responses
        self.calls: list[tuple] = []
        self.current: Response | None = None

    async def __aenter__(self):
        """Enter the fake context."""
        return self.current or self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake context."""

    async def get(self, url: str, **kwargs) -> Response:
        """Return the next response and record a GET."""
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def stream(self, method: str, url: str, **kwargs):
        """Return a stream context containing the next response."""
        self.calls.append((method, url, kwargs))
        self.current = self.responses.pop(0)
        return self


@pytest.fixture
def clickup_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure deterministic ClickUp resources and credentials."""
    resources = SimpleNamespace(
        clickup_workspaces=["workspace"],
        clickup_spaces=["space"],
        clickup_lists=["list"],
    )
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(
        Settings,
        "credential",
        lambda _self, source, alias: {"token": f"{source}-{alias}-token"},
    )
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    monkeypatch.setattr(Settings, "export_max_bytes", lambda _self, _source: 20)


def test_clickup_listing_and_task_operations(
    monkeypatch: pytest.MonkeyPatch,
    clickup_config: None,
) -> None:
    """Characterize list filtering, parameters, and task ownership checks."""
    adapter = ClickUpClient(settings)
    assert adapter._profile("workspace")["token"].startswith("clickup")
    assert adapter._headers("workspace")["Authorization"].endswith("token")
    with pytest.raises(ValueError, match="not allowed"):
        adapter._profile("other")

    async def run() -> None:
        """Exercise asynchronous operations."""
        client = Client(
            [
                Response({"ok": True}),
                Response({"spaces": [{"id": "space"}, {"id": "other"}]}),
                Response({"folders": []}),
                Response({"lists": [{"id": "list"}, {"id": "other"}]}),
                Response({"lists": []}),
                Response({"tasks": [{"id": "1"}, {"id": "2"}]}),
                Response({"list": {"id": "list"}, "id": "task"}),
                Response({"fields": []}),
                Response({"list": {"id": "list"}, "attachments": [{"id": "a"}]}),
                Response({"list": {"id": "other"}}),
            ]
        )
        monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
        assert await adapter._get("workspace", "/test") == {"ok": True}
        assert (await adapter.list_spaces("workspace"))["spaces"] == [{"id": "space"}]
        assert (await adapter.list_folders("workspace", "space"))["folders"] == []
        assert (await adapter.list_lists("workspace", "space", "space"))["lists"] == [
            {"id": "list"}
        ]
        assert (await adapter.list_lists("workspace", "folder", "folder"))["lists"] == []
        tasks = await adapter.list_tasks(
            "workspace", "list", page=-1, include_closed=False, subtasks=False, statuses=["open"]
        )
        assert tasks == {"rows": [{"id": "1"}], "row_count": 2, "truncated": True}
        assert (await adapter.get_task("workspace", "task"))["id"] == "task"
        assert (await adapter.get_custom_fields("workspace", "list"))["fields"] == []
        assert (await adapter.list_attachments("workspace", "task"))["row_count"] == 1
        with pytest.raises(ValueError, match="outside allowlisted"):
            await adapter.get_task("workspace", "outside")

        with pytest.raises(ValueError, match="parent_type"):
            await adapter.list_lists("workspace", "team", "space")
        with pytest.raises(ValueError, match="not allowed"):
            await adapter.list_folders("workspace", "other")

    asyncio.run(run())


def test_clickup_attachment_download(
    monkeypatch: pytest.MonkeyPatch,
    clickup_config: None,
) -> None:
    """Characterize attachment ownership, HTTPS validation, and bounded streaming."""
    adapter = ClickUpClient(settings)

    async def run() -> None:
        """Exercise missing and successful attachment branches."""
        monkeypatch.setattr(
            adapter,
            "get_task",
            lambda *_args: _async_value({"attachments": []}),
        )
        with pytest.raises(ValueError, match="not attached"):
            await adapter.download_attachment("workspace", "task", "a", "outputs/a.txt")

        monkeypatch.setattr(
            adapter,
            "get_task",
            lambda *_args: _async_value(
                {"attachments": [{"id": "a", "url": "https://files.clickup.com/a"}]}
            ),
        )
        client = Client([Response({}, (b"abc", b"def"))])
        monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
        result = await adapter.download_attachment(
            "workspace", "task", "a", "outputs/attachment.txt"
        )
        assert result == {"path": "outputs/attachment.txt", "size": 6}
        assert (settings.workspace / result["path"]).read_bytes() == b"abcdef"

    asyncio.run(run())


async def _async_value(value):
    """Return a value from a minimal awaitable helper."""
    return value
