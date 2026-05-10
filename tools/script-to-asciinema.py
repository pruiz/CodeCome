#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert script(1) timing/typescript output to asciinema v2 JSONL.",
    )
    parser.add_argument("timing", help="Path to the script timing file.")
    parser.add_argument("typescript", help="Path to the script output/typescript file.")
    parser.add_argument("output", help="Path to write the asciinema cast.")
    parser.add_argument("--width", type=int, default=100, help="Cast width. Default: 100")
    parser.add_argument("--height", type=int, default=30, help="Cast height. Default: 30")
    parser.add_argument("--title", help="Optional cast title.")
    parser.add_argument("--command", dest="command_name", help="Optional command metadata.")
    return parser.parse_args()


def build_header(args: argparse.Namespace) -> dict:
    header = {
        "version": 2,
        "width": args.width,
        "height": args.height,
    }
    if args.title:
        header["title"] = args.title
    if args.command_name:
        header["command"] = args.command_name
    return header


def iter_timing_entries(timing_path: Path):
    with timing_path.open("r", encoding="utf-8") as timing_file:
        for line_number, line in enumerate(timing_file, start=1):
            parts = line.strip().split()
            if len(parts) < 2:
                raise ValueError(f"Malformed timing line {line_number}: expected '<delay> <count>'")
            try:
                delay = float(parts[0])
                count = int(parts[1])
            except ValueError as exc:
                raise ValueError(
                    f"Malformed timing line {line_number}: {line.strip()}"
                ) from exc
            if delay < 0 or count < 0:
                raise ValueError(f"Malformed timing line {line_number}: negative values are invalid")
            yield delay, count


def convert(timing_path: Path, typescript_path: Path, output_path: Path, header: dict) -> None:
    time_offset = 0.0

    with output_path.open("w", encoding="utf-8") as out_file:
        out_file.write(json.dumps(header) + "\n")
        with typescript_path.open("rb") as typescript_file:
            for delay, count in iter_timing_entries(timing_path):
                chunk = typescript_file.read(count)
                if len(chunk) != count:
                    raise ValueError(
                        "Timing file requested more bytes than exist in the typescript output"
                    )
                time_offset += delay
                text = chunk.decode("utf-8", errors="replace")
                out_file.write(json.dumps([time_offset, "o", text]) + "\n")

            remainder = typescript_file.read(1)
            if remainder:
                raise ValueError("Typescript output contains trailing bytes not described by timing file")


def main() -> int:
    args = parse_args()
    convert(
        Path(args.timing),
        Path(args.typescript),
        Path(args.output),
        build_header(args),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
