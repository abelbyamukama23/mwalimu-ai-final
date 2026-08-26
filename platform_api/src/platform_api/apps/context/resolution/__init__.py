"""Resolution engine package for Mwalimu context domain."""

from platform_api.apps.context.resolution.dto import (
    ContextSignal,
    ExplicitGeographicIntent,
    ResolvedContext,
    ResolvedContextItem,
)
from platform_api.apps.context.resolution.geographic_intent import (
    detect_geographic_intent,
)
from platform_api.apps.context.resolution.pedagogical_signal import (
    detect_pedagogical_signal,
)
from platform_api.apps.context.resolution.resolver import ContextResolver

__all__ = [
    "ContextResolver",
    "ContextSignal",
    "ExplicitGeographicIntent",
    "ResolvedContext",
    "ResolvedContextItem",
    "detect_geographic_intent",
    "detect_pedagogical_signal",
]
