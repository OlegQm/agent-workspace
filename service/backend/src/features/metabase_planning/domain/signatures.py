"""Represent the agent-owned Metabase discovery context."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverySignature:
    """Capture semantic categories the agent uses when deciding to rediscover."""

    business_intent: str | None
    metric_definition: str | None
    source: str | None
    population_filter: str | None
    period_comparison: str | None
    granularity: str | None
    visualization: str | None
