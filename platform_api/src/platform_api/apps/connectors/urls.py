"""URL routing for connectors and library connections."""

from django.urls import path

from .views import (
    ConnectorDetailView,
    ConnectorListView,
    LibraryConnectionDetailView,
    LibraryConnectionListCreateView,
    LibraryConnectionSyncListView,
    LibraryConnectionSyncTriggerView,
)

urlpatterns = [
    path("connectors/", ConnectorListView.as_view(), name="connector-list"),
    path(
        "connectors/<uuid:connector_id>/",
        ConnectorDetailView.as_view(),
        name="connector-detail",
    ),
    path(
        "libraries/<uuid:library_id>/connections/",
        LibraryConnectionListCreateView.as_view(),
        name="library-connection-list-create",
    ),
    path(
        "libraries/<uuid:library_id>/connections/<uuid:connection_id>/",
        LibraryConnectionDetailView.as_view(),
        name="library-connection-detail",
    ),
    path(
        "libraries/<uuid:library_id>/connections/<uuid:connection_id>/sync/",
        LibraryConnectionSyncTriggerView.as_view(),
        name="library-connection-sync-trigger",
    ),
    path(
        "libraries/<uuid:library_id>/connections/<uuid:connection_id>/sync-jobs/",
        LibraryConnectionSyncListView.as_view(),
        name="library-connection-sync-list",
    ),
]

