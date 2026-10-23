"""Define SQLAlchemy records owned by the Metabase planning feature."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models import Base, utcnow


class MetabasePlanningState(Base):
    """Persist the authoritative workflow state for one planning conversation."""

    __tablename__ = "metabase_planning_states"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_state: Mapped[str] = mapped_column(
        String(32), default="collecting", server_default=text("'collecting'")
    )
    requirements_revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    workflow_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    discovery_status: Mapped[str] = mapped_column(
        String(32), default="not_started", server_default=text("'not_started'")
    )
    discovery_for_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovery_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidate_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_collection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_for_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    plan_for_requirements_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    structured_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    youtrack_issue_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    youtrack_issue_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_submitted_plan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issue_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issue_status_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issue_status_refresh_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetabasePlanningOperation(Base):
    """Persist one idempotent external or long-running planning operation."""

    __tablename__ = "metabase_planning_operations"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "idempotency_key",
            name="uq_metabase_planning_operation_idempotency",
        ),
        Index("ix_metabase_planning_operations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    operation_type: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    requirements_revision: Mapped[int] = mapped_column(Integer)
    plan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
