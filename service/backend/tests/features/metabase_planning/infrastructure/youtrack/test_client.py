"""Test the bounded YouTrack HTTP adapter with an in-memory transport."""

import json

import httpx
import pytest

from features.metabase_planning.application.reviews import (
    ReviewIssueNotFound,
    ReviewSubmissionRejected,
    ReviewSubmissionUnavailable,
)
from features.metabase_planning.infrastructure.youtrack.client import YouTrackReviewClient


@pytest.mark.unit
async def test_create_issue_uses_configured_project_and_resolved_assignee() -> None:
    """Send only the approved plan and server-resolved YouTrack identities."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture one issue creation request and return safe fields."""
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "2-7",
                "idReadable": "BI-7",
                "customFields": [{"name": "State", "value": {"name": "Open"}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        issue = await client.create_issue("Paid revenue", "Approved plan")

    payload = json.loads(requests[0].content)
    assert requests[0].url.path == "/api/issues"
    assert payload == {
        "project": {"id": "0-1"},
        "summary": "Paid revenue",
        "description": "Approved plan",
        "customFields": [
            {
                "id": "3-4",
                "$type": "SingleUserIssueCustomField",
                "value": {"id": "1-2"},
            }
        ],
    }
    assert issue.key == "BI-7"
    assert issue.status == "Open"


@pytest.mark.unit
async def test_update_replaces_description_then_adds_revision_comment() -> None:
    """Update one linked issue and record a short revision note."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the issue update and revision-comment sequence."""
        paths.append(request.url.path)
        if request.url.path.endswith("/comments"):
            return httpx.Response(200, json={"id": "comment-1"})
        return httpx.Response(
            200,
            json={"id": "2-7", "idReadable": "BI-7", "customFields": []},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        issue = await client.update_issue("2-7", "New plan", "Revision 2")

    assert paths == ["/api/issues/2-7", "/api/issues/2-7/comments"]
    assert issue.id == "2-7"


@pytest.mark.unit
async def test_update_distinguishes_a_confirmed_missing_issue() -> None:
    """Expose only an update-target 404 as a safe signal to create a replacement."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a definitive missing response for the linked issue update."""
        paths.append(request.url.path)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        with pytest.raises(ReviewIssueNotFound):
            await client.update_issue("2-deleted", "New plan", "Revision 2")
        with pytest.raises(ReviewSubmissionRejected):
            await client._request("POST", "/api/issues/missing")

    assert paths == ["/api/issues/2-deleted", "/api/issues/missing"]


@pytest.mark.unit
async def test_status_read_returns_safe_state_and_http_failures_are_bounded() -> None:
    """Read current issue status without exposing remote response bodies."""
    def handler(request: httpx.Request) -> httpx.Response:
        """Return either a safe status or a sensitive remote failure."""
        if request.url.path.endswith("bad"):
            return httpx.Response(500, text="sensitive remote body")
        return httpx.Response(
            200,
            json={
                "id": "2-7",
                "idReadable": "BI-7",
                "customFields": [{"name": "State", "value": {"name": "Done"}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        assert await client.fetch_status("2-7") == "Done"
        with pytest.raises(RuntimeError, match="YouTrack request failed") as error:
            await client.fetch_status("bad")
        assert "sensitive" not in str(error.value)


@pytest.mark.unit
async def test_write_failures_distinguish_definitive_rejection_from_unknown_outcome() -> None:
    """Allow retries for 4xx rejection while treating 5xx as an uncertain write."""
    def handler(request: httpx.Request) -> httpx.Response:
        """Return the selected definitive or uncertain write failure."""
        return httpx.Response(400 if request.url.params.get("result") == "rejected" else 500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        with pytest.raises(ReviewSubmissionRejected):
            await client._request("POST", "/api/issues", params={"result": "rejected"})
        with pytest.raises(ReviewSubmissionUnavailable):
            await client._request("POST", "/api/issues")


@pytest.mark.unit
async def test_transport_and_payload_validation_fail_with_bounded_errors() -> None:
    """Reject network failures, invalid JSON shapes, and incomplete issue identities."""
    def handler(request: httpx.Request) -> httpx.Response:
        """Return malformed responses without contacting an external service."""
        if request.url.path.endswith("network"):
            raise httpx.ConnectError("sensitive network detail", request=request)
        if request.url.path.endswith("array"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("invalid-json"):
            return httpx.Response(200, text="not-json")
        return httpx.Response(200, json={"id": 7, "idReadable": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTrackReviewClient(
            http,
            base_url="https://tracker.example.test",
            token="hidden",
            project_id="0-1",
            assignee_id="1-2",
            assignee_field_id="3-4",
        )
        with pytest.raises(RuntimeError, match="request failed"):
            await client._request("GET", "/network")
        with pytest.raises(ReviewSubmissionUnavailable):
            await client._request("POST", "/network")
        with pytest.raises(TypeError, match="invalid response"):
            await client._request("GET", "/array")
        with pytest.raises(RuntimeError, match="request failed"):
            await client._request("GET", "/invalid-json")
        with pytest.raises(TypeError, match="invalid issue"):
            await client.fetch_status("bad-identity")


@pytest.mark.unit
def test_issue_parser_ignores_unrelated_or_malformed_custom_fields() -> None:
    """Extract only a valid State name and tolerate safe absent status data."""
    base = {"id": "2-7", "idReadable": "BI-7"}
    assert YouTrackReviewClient._issue(base).status is None
    assert YouTrackReviewClient._issue({**base, "customFields": "invalid"}).status is None
    assert YouTrackReviewClient._issue(
        {
            **base,
            "customFields": [
                "invalid",
                {"name": "Assignee", "value": {"name": "Example Reviewer"}},
                {"name": "State", "value": "invalid"},
                {"name": "State", "value": {"name": "Done"}},
            ],
        }
    ).status == "Done"
