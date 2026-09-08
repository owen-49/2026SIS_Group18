"""External lookup integration boundary; no registry implementation exists yet.

The existing Engine compares metadata supplied to it; it does not query DOI
registries. A real adapter must search by DOI or bibliography/raw reference,
return traceable records, and handle its own bounded network retries/timeouts.
"""

from typing import Protocol

from ..audit_models import LookupResult, ReferenceEntry


class BibliographyLookup(Protocol):
    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        """Resolve one reference against external bibliographic records."""
        ...
