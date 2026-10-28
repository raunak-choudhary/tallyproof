"""The Tallyproof data pipeline.

Downloads official public spending data, cleans it with Spark into bronze,
silver, and gold layers, removes personal data, checks quality with Deequ, and
turns the cleaned rows into ledger events. Like ``tallyproof_core``, it has no
Django imports.
"""
