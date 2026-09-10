"""One isolated Scholar lookup, terminated by the parent on deadline."""

import sys

from ..audit_models import ReferenceEntry
from .google_scholar_lookup import GoogleScholarLookup


def main():
    entry = ReferenceEntry.model_validate_json(sys.stdin.buffer.read())
    result = GoogleScholarLookup().lookup(entry)
    # ASCII JSON works with Windows redirected pipes regardless of code page.
    print(result.model_dump_json().encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
