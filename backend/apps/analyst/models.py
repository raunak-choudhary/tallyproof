"""Stored answers. An answer is never edited: a new question makes a new row."""

from django.db import models
from django.db.models.functions import Now


class AnalystAnswer(models.Model):
    """One question and what the analyst did with it, as of one checkpoint."""

    public_id = models.TextField(unique=True)
    question = models.TextField()
    status = models.TextField()
    category = models.TextField(blank=True, default="")
    refusal = models.TextField(blank=True, default="")
    text = models.TextField(blank=True, default="")
    tree_size = models.BigIntegerField()
    assurance = models.TextField(blank=True, default="")
    filter_words = models.TextField(blank=True, default="")
    body = models.JSONField(default=dict)
    """Slots, citations, quotes, and the model and prompt versions that produced them."""
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "analyst_answer"

    def __str__(self) -> str:
        return f"{self.public_id} {self.status}"
