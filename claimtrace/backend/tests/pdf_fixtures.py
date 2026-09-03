"""Small valid PDF fixtures for backend integration tests."""

import fitz


def make_test_pdf(*lines: str) -> bytes:
    """Create a one-page PDF containing the supplied text lines."""
    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(lines or ("Test paper",)):
        page.insert_text((72, 72 + index * 18), line, fontsize=11)
    payload = document.tobytes()
    document.close()
    return payload
