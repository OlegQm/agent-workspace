"""Define validated Tool Gateway manifest models."""

from typing import Annotated

from pydantic import BaseModel, Field

RepositoryAlias = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]


class ExportLimit(BaseModel):
    """Define per-integration export limits."""

    max_rows: int | None = Field(default=None, gt=0)
    max_bytes: int | None = Field(default=None, gt=0)


class Resources(BaseModel):
    """Define resources exposed to one gateway role."""

    environment: str
    metabase_scope: str | None = None
    metabase_collection_ids: list[int] = Field(default_factory=list)
    metabase_database_ids: list[int] = Field(default_factory=list)
    metabase_sql_tables: list[str] = Field(default_factory=list)
    metabase_sql_denied_columns: list[str] = Field(default_factory=list)
    metabase_setting_keys: list[str] = Field(default_factory=list)
    bigquery_datasets: list[str] = Field(default_factory=list)
    google_ads_customer_ids: list[str] = Field(default_factory=list)
    meta_ad_account_ids: list[str] = Field(default_factory=list)
    google_analytics_property_ids: list[str] = Field(default_factory=list)
    superfaktura_companies: list[str] = Field(default_factory=list)
    superfaktura_company_labels: dict[str, str] = Field(default_factory=dict)
    stripe_accounts: list[str] = Field(default_factory=list)
    gopay_accounts: list[str] = Field(default_factory=list)
    clickup_workspaces: list[str] = Field(default_factory=list)
    clickup_spaces: list[str] = Field(default_factory=list)
    clickup_lists: list[str] = Field(default_factory=list)
    code_repositories: list[RepositoryAlias] = Field(default_factory=list)
    tool_export_limits: dict[str, ExportLimit] = Field(default_factory=dict)


class Manifest(BaseModel):
    """Define one role-scoped integration manifest."""

    id: str
    tools: list[str]
    resources: Resources
