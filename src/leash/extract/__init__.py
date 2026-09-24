"""Bounded extraction of purchase facts from untrusted item copy.

The returned records contain facts and provenance only. Merchant statements are
claims, even when a regular expression can read them unambiguously.
"""

from .facts import extract_event, extract_item

__all__ = ["extract_event", "extract_item"]
