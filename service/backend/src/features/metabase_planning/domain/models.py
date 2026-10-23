"""Define structured, provenance-aware Metabase planning values."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Provenance(StrEnum):
    """Identify where a proposed requirement or factual statement originated."""

    user_confirmed = "user_confirmed"
    authorized_discovery = "authorized_discovery"
    file_context = "file_context"


class PlanStatement(BaseModel):
    """Store one plan statement together with its evidence boundary."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=10_000)
    provenance: Provenance

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Strip surrounding whitespace and reject empty statements."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("plan statement cannot be empty")
        return normalized


class StructuredPlan(BaseModel):
    """Represent the complete machine-validated plan shown to the user."""

    model_config = ConfigDict(frozen=True)

    business_question: PlanStatement
    metrics: list[PlanStatement] = Field(min_length=1)
    sources: list[PlanStatement] = Field(min_length=1)
    period: list[PlanStatement] = Field(min_length=1)
    grain: list[PlanStatement] = Field(min_length=1)
    dimensions: list[PlanStatement]
    filters: list[PlanStatement]
    comparisons: list[PlanStatement]
    exclusions: list[PlanStatement]
    visualization: list[PlanStatement] = Field(min_length=1)
    expected_interpretation: list[PlanStatement]
    assumptions: list[PlanStatement]
    explicit_answers: list[PlanStatement]

    def statements(self) -> tuple[PlanStatement, ...]:
        """Return every statement that could enter an external review request."""
        sections = (
            self.metrics,
            self.sources,
            self.period,
            self.grain,
            self.dimensions,
            self.filters,
            self.comparisons,
            self.exclusions,
            self.visualization,
            self.expected_interpretation,
            self.assumptions,
            self.explicit_answers,
        )
        return (self.business_question, *(item for section in sections for item in section))

    def validate_for_submission(self) -> None:
        """Reject unconfirmed workspace-file context from an external handoff."""
        if any(item.provenance is Provenance.file_context for item in self.statements()):
            raise ValueError("file context must be confirmed before submission")
