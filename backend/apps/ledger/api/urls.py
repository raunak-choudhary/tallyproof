"""Routes for the ledger API, mounted under /api/v1/."""

from django.urls import path

from apps.analyst import api as analyst
from apps.ledger.api import views
from apps.reconciliation import api as reconciliation

urlpatterns = [
    path("log-key", views.LogKeyView.as_view(), name="log-key"),
    path("checkpoints", views.CheckpointListView.as_view(), name="checkpoint-list"),
    path("checkpoints/latest", views.LatestCheckpointView.as_view(), name="checkpoint-latest"),
    path("checkpoints/<int:tree_size>", views.CheckpointDetailView.as_view(), name="checkpoint"),
    path("events", views.EventListView.as_view(), name="event-list"),
    path("events/<str:event_id>", views.EventDetailView.as_view(), name="event"),
    path("events/<str:event_id>/proof", views.InclusionProofView.as_view(), name="event-proof"),
    path("consistency", views.ConsistencyProofView.as_view(), name="consistency"),
    path("totals/latest", views.LatestTotalsView.as_view(), name="totals-latest"),
    path("totals/proof", views.TotalProofView.as_view(), name="total-proof"),
    path(
        "batches/<str:batch_id>/consistency",
        views.BatchConsistencyView.as_view(),
        name="batch-consistency",
    ),
    path("queries", analyst.QueryView.as_view(), name="queries"),
    path("answers/<str:answer_id>", analyst.AnswerView.as_view(), name="answer"),
    path("reconciliation/breaks", reconciliation.BreakListView.as_view(), name="break-list"),
    path(
        "reconciliation/breaks/<str:break_id>",
        reconciliation.BreakDetailView.as_view(),
        name="break",
    ),
]
