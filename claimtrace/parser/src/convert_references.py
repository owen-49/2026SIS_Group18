"""Command-line utility for extracting a PDF reference list."""

from __future__ import annotations

import argparse
from pathlib import Path

from reference_extractor import (
    extract_references,
    save_reference_list_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract a reference list from an academic PDF."
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the source PDF.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination JSON file.",
    )

    args = parser.parse_args()

    output_path = args.output or args.pdf.with_name(
        f"{args.pdf.stem}.references.json"
    )

    reference_list = extract_references(args.pdf)
    save_reference_list_json(reference_list, output_path)

    print(f"Extracted {len(reference_list.references)} references.")
    print(f"Output: {output_path}")

    for warning in reference_list.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
