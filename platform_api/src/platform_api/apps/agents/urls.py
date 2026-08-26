"""URL configuration for public agent sessions, runs, and internal completion."""

from __future__ import annotations

from django.urls import path

from .views import (
    RunCancelView,
    RunCompletionInternalView,
    RunDetailView,
    SessionDetailView,
    SessionListCreateView,
    SessionRunCreateView,
)

urlpatterns = [
    path(
        "sessions/",
        SessionListCreateView.as_view(),
        name="agent-session-list-create",
    ),
    path(
        "sessions/<uuid:session_id>/",
        SessionDetailView.as_view(),
        name="agent-session-detail",
    ),
    path(
        "sessions/<uuid:session_id>/runs/",
        SessionRunCreateView.as_view(),
        name="agent-session-run-create",
    ),
    path(
        "runs/<uuid:run_id>/",
        RunDetailView.as_view(),
        name="agent-run-detail",
    ),
    path(
        "runs/<uuid:run_id>/cancel/",
        RunCancelView.as_view(),
        name="agent-run-cancel",
    ),
    path(
        "internal/runs/<uuid:run_id>/completion/",
        RunCompletionInternalView.as_view(),
        name="internal-run-completion",
    ),
]
