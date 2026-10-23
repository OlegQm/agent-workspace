"""Call the bounded YouTrack issue API without exposing remote response bodies."""

from typing import Any

import httpx

from features.metabase_planning.application.reviews import (
    ReviewIssue,
    ReviewIssueNotFound,
    ReviewSubmissionRejected,
    ReviewSubmissionUnavailable,
)

ISSUE_FIELDS = "id,idReadable,customFields(name,value(name))"


class YouTrackReviewClient:
    """Create, update, and inspect one configured class of review issues."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        token: str,
        project_id: str,
        assignee_id: str,
        assignee_field_id: str,
    ) -> None:
        """Bind validated server configuration to a caller-owned HTTP client."""
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.project_id = project_id
        self.assignee_id = assignee_id
        self.assignee_field_id = assignee_field_id

    async def _request(
        self,
        method: str,
        path: str,
        *,
        missing_issue_on_404: bool = False,
        **kwargs: Any,
    ) -> dict:
        """Return one JSON object or a bounded transport failure."""
        try:
            response = await self.client.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                follow_redirects=False,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            if missing_issue_on_404 and exc.response.status_code == 404:
                raise ReviewIssueNotFound("Linked YouTrack issue no longer exists") from exc
            if method != "GET" and 400 <= exc.response.status_code < 500:
                raise ReviewSubmissionRejected("YouTrack rejected the review request") from exc
            if method != "GET":
                raise ReviewSubmissionUnavailable("YouTrack write outcome is unknown") from exc
            raise RuntimeError("YouTrack request failed") from exc
        except (httpx.HTTPError, ValueError) as exc:
            if method != "GET":
                raise ReviewSubmissionUnavailable("YouTrack write outcome is unknown") from exc
            raise RuntimeError("YouTrack request failed") from exc
        if not isinstance(payload, dict):
            raise TypeError("YouTrack returned an invalid response")
        return payload

    @staticmethod
    def _issue(payload: dict) -> ReviewIssue:
        """Extract only stable issue identity and status fields."""
        issue_id = payload.get("id")
        key = payload.get("idReadable")
        if not isinstance(issue_id, str) or not isinstance(key, str):
            raise TypeError("YouTrack returned an invalid issue")
        status = None
        fields = payload.get("customFields")
        if isinstance(fields, list):
            for field in fields:
                if not isinstance(field, dict) or field.get("name") != "State":
                    continue
                value = field.get("value")
                if isinstance(value, dict) and isinstance(value.get("name"), str):
                    status = value["name"]
                    break
        return ReviewIssue(id=issue_id, key=key, status=status)

    async def create_issue(self, summary: str, description: str) -> ReviewIssue:
        """Create one issue in the configured project and assign resolved identity."""
        payload = await self._request(
            "POST",
            "/api/issues",
            params={"fields": ISSUE_FIELDS},
            json={
                "project": {"id": self.project_id},
                "summary": summary,
                "description": description,
                "customFields": [
                    {
                        "id": self.assignee_field_id,
                        "$type": "SingleUserIssueCustomField",
                        "value": {"id": self.assignee_id},
                    }
                ],
            },
        )
        return self._issue(payload)

    async def update_issue(
        self,
        issue_id: str,
        description: str,
        comment: str,
    ) -> ReviewIssue:
        """Replace an issue description and add one short revision comment."""
        payload = await self._request(
            "POST",
            f"/api/issues/{issue_id}",
            missing_issue_on_404=True,
            params={"fields": ISSUE_FIELDS},
            json={"description": description},
        )
        await self._request(
            "POST",
            f"/api/issues/{issue_id}/comments",
            params={"fields": "id"},
            json={"text": comment},
        )
        return self._issue(payload)

    async def fetch_status(self, issue_id: str) -> str | None:
        """Read the current informational workflow status for one linked issue."""
        payload = await self._request(
            "GET",
            f"/api/issues/{issue_id}",
            params={"fields": ISSUE_FIELDS},
        )
        return self._issue(payload).status
