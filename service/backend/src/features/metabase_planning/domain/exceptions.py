"""Define errors raised by Metabase planning business operations."""


class PlanningError(Exception):
    """Base error for a rejected Metabase planning operation."""


class PlanningConversationNotFound(PlanningError):
    """Signal that an owned planning conversation does not exist."""


class StalePlanningState(PlanningError):
    """Signal that a command targets an obsolete workflow version."""


class PlanningConflict(PlanningError):
    """Signal that another active operation prevents the requested transition."""


class InvalidPlanningAttachment(PlanningError):
    """Signal that a planning attachment is outside its assigned workspace."""
