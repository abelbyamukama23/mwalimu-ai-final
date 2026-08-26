"""Canonical transcript history hydration service.

Projects bounded canonical AgentSessionMessage history from the Platform API
system of record into the runtime history format required by the Agent Service.
"""

from __future__ import annotations

import logging

from .models import AgentSession, AgentSessionMessage, MessageRole

logger = logging.getLogger(__name__)

# Permitted runtime roles for multi-turn execution
RUNTIME_PERMITTED_ROLES: frozenset[str] = frozenset(
    {
        MessageRole.USER,
        MessageRole.ASSISTANT,
    }
)

DEFAULT_MAX_HYDRATED_MESSAGES = 20


def hydrate_session_history(
    session: AgentSession,
    max_messages: int = DEFAULT_MAX_HYDRATED_MESSAGES,
) -> list[dict[str, str]]:
    """Load and format bounded prior conversation history for an AgentSession.

    Invariants enforced:
    - Canonical source: AgentSessionMessage in PostgreSQL.
    - Ordering: sequence ASC.
    - Role filtering: strictly 'user' and 'assistant' roles.
    - Redaction: database IDs, session IDs, run IDs, timestamps, citations,
      and credentials are NEVER included in the hydrated runtime history.
    - Boundedness: at most `max_messages` most recent messages.

    Args:
        session: The persistent AgentSession whose history is being hydrated.
        max_messages: Maximum number of recent messages to project.

    Returns:
        List of serialized message dicts:
        [{"role": "user"|"assistant", "content": "..."}].
    """
    if max_messages <= 0:
        return []

    # Query all eligible transcript messages ordered chronologically
    qs = (
        AgentSessionMessage.objects.filter(
            session=session,
            role__in=[MessageRole.USER, MessageRole.ASSISTANT],
        )
        .order_by("sequence")
        .only("role", "content", "sequence")
    )

    # To respect max_messages while keeping sequence ASC:
    # If total messages > max_messages, select the trailing `max_messages`
    all_messages = list(qs)
    if len(all_messages) > max_messages:
        selected_messages = all_messages[-max_messages:]
    else:
        selected_messages = all_messages

    projected_history: list[dict[str, str]] = []
    for msg in selected_messages:
        if not msg.content or not msg.content.strip():
            continue

        if msg.role not in RUNTIME_PERMITTED_ROLES:
            continue

        projected_history.append(
            {
                "role": str(msg.role),
                "content": str(msg.content),
            }
        )

    logger.debug(
        "Hydrated %d historical messages for session %s (max=%d)",
        len(projected_history),
        session.pk,
        max_messages,
    )
    return projected_history
