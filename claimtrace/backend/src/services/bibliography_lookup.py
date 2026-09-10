"""External lookup integration boundary.

GoogleScholarLookup adapts the Engine search module to this contract.
Implementations must return traceable publication records and distinguish
query failures from completed searches without candidates.
"""

from typing import Protocol

from ..audit_models import LookupResult, ReferenceEntry


class BibliographyLookup(Protocol):
    def lookup(self, entry: ReferenceEntry) -> LookupResult:
        """Resolve one reference against external bibliographic records."""
        ...
