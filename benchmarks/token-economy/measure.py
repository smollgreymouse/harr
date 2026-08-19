#!/usr/bin/env python3
"""Measure UTF-8 payloads with one pinned tokenizer.

This is a comparison aid, not a source of provider billing usage.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

try:
    import tiktoken
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with: "
        "python3 -m pip install -r benchmarks/token-economy/requirements.txt"
    ) from exc


@dataclass(frozen=True)
class Measurement:
    label: str
    path: Path
    byte_count: int
    char_count: int
    token_count: int


def measure(label: str, path: Path, encoding: tiktoken.Encoding) -> Measurement:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    return Measurement(
        label=label,
        path=path,
        byte_count=len(payload),
        char_count=len(text),
        token_count=len(encoding.encode(text)),
    )


def print_measurement(item: Measurement) -> None:
    print(
        f"{item.label}\t{item.path}\t{item.byte_count}\t"
        f"{item.char_count}\t{item.token_count}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count UTF-8 payloads with a fixed tokenizer.",
    )
    parser.add_argument(
        "--encoding",
        default="o200k_base",
        help="tiktoken encoding name (default: o200k_base)",
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help="standalone payload to measure; repeatable",
    )
    parser.add_argument(
        "--pair",
        action="append",
        nargs=3,
        metavar=("LABEL", "RAW", "LEANCTX"),
        default=[],
        help="compare raw/native payload with the exact LeanCTX result; repeatable",
    )
    args = parser.parse_args()

    encoding = tiktoken.get_encoding(args.encoding)
    print("kind\tpath\tbytes\tchars\ttokens")

    total_tokens = 0
    for path in args.file:
        item = measure("file", path, encoding)
        print_measurement(item)
        total_tokens += item.token_count

    for label, raw_path, lean_path in args.pair:
        raw = measure(f"{label}:raw", Path(raw_path), encoding)
        lean = measure(f"{label}:leanctx", Path(lean_path), encoding)
        print_measurement(raw)
        print_measurement(lean)
        saved = raw.token_count - lean.token_count
        percent = 0.0 if raw.token_count == 0 else saved / raw.token_count * 100
        print(f"pair\t{label}\t-\t-\t{saved} saved ({percent:.1f}%)")
        total_tokens += raw.token_count + lean.token_count

    print(f"total-measured-tokens\t-\t-\t-\t{total_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
