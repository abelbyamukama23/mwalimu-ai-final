"""Shared, dependency-free helpers for the Mwalimu Django admin."""

from __future__ import annotations

from django.utils.html import format_html

# Mwalimu status palette (matches the product tokens).
_PALETTE: dict[str, tuple[str, str]] = {
    "ok": ("#e6f2ea", "#2f7a4f"),
    "warn": ("#fbf0dd", "#b8791f"),
    "err": ("#fbebe0", "#d97b3f"),
    "info": ("#e5f0f5", "#2c6e8c"),
    "muted": ("#f2eee6", "#6b6b63"),
    "neutral": ("#f2eee6", "#6b6b63"),
}


def pill(value: object, tone: str = "muted", title: str = "") -> str:
    """Render a small rounded status pill using inline styles (no extra CSS)."""
    value_str = str(value) if value is not None else "—"
    bg, fg = _PALETTE.get(tone, _PALETTE["muted"])
    title_attr = f' title="{title}"' if title else ""
    return format_html(
        '<span style="display:inline-block;padding:2px 8px;border-radius:9999px;'
        "font-size:11px;font-weight:600;background:{};color:{}\"{}>{}</span>",
        bg,
        fg,
        title_attr,
        value_str,
    )


def short(value: str | None, length: int = 60) -> str:
    """Collapse whitespace and truncate text for compact list/inline views."""
    text = value or ""
    text = " ".join(text.split())
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


# Common status -> tone mappings.
SESSION_STATUS_TONE = {"active": "ok", "archived": "muted"}
RUN_STATUS_TONE = {
    "created": "muted",
    "queued": "warn",
    "running": "info",
    "awaiting_input": "info",
    "completed": "ok",
    "failed": "err",
    "cancelled": "muted",
    "timed_out": "err",
}
RESOURCE_STATUS_TONE = {
    "pending": "warn",
    "uploading": "info",
    "ready": "ok",
    "failed": "err",
    "archived": "muted",
}
PROCESSING_STATUS_TONE = {
    "queued": "warn",
    "processing": "info",
    "ready": "ok",
    "failed": "err",
    "cancelled": "muted",
}
CONTEXT_SCOPE_TONE = {"platform": "info", "institution": "warn"}
