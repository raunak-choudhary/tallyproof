"""Routes for the ledger API, mounted under /api/v1/."""

from django.urls import path

from apps.ledger.api import views

urlpatterns = [
    path("log-key", views.LogKeyView.as_view(), name="log-key"),
    path("checkpoints", views.CheckpointListView.as_view(), name="checkpoint-list"),
    path("checkpoints/latest", views.LatestCheckpointView.as_view(), name="checkpoint-latest"),
    path("checkpoints/<int:tree_size>", views.CheckpointDetailView.as_view(), name="checkpoint"),
    path("events", views.EventListView.as_view(), name="event-list"),
    path("events/<str:event_id>", views.EventDetailView.as_view(), name="event"),
    path("events/<str:event_id>/proof", views.InclusionProofView.as_view(), name="event-proof"),
    path("consistency", views.ConsistencyProofView.as_view(), name="consistency"),
]
