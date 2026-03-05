#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def strip_two_spaces(line: str) -> str:
    if line.startswith("  "):
        return line[2:]
    return line


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove exactly the first two leading spaces from each line."
    )
    parser.add_argument("input_file", help="Path to input text file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path (defaults to in-place edit)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve() if args.output else input_path
    )

    content = input_path.read_text(encoding="utf-8")
    updated = "".join(strip_two_spaces(line) for line in content.splitlines(True))
    output_path.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

