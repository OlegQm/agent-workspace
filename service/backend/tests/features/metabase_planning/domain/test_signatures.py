"""Test agent-owned Metabase discovery signatures."""

from features.metabase_planning.domain.signatures import DiscoverySignature


def signature(**changes: str | None) -> DiscoverySignature:
    """Build a complete semantic discovery signature."""
    values = {
        "business_intent": "Track paid revenue",
        "metric_definition": "Captured payments",
        "source": "Stripe",
        "population_filter": "Active locations",
        "period_comparison": "This month versus last month",
        "granularity": "Daily",
        "visualization": "Line chart",
    }
    values.update(changes)
    return DiscoverySignature(**values)


def test_signature_preserves_the_agents_discovery_context() -> None:
    """Keep semantic fields unchanged for the agent's next planning turn."""
    value = signature(source=None, granularity="Weekly")

    assert value.source is None
    assert value.granularity == "Weekly"
