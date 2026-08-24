#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


def load_servers(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("servers"), list):
        raise SystemExit(f"unsupported Harr MCP registry: {path}")
    return data["servers"]


def strip_conditional_blocks(text: str, catalog: list[dict], active: set[str]) -> str:
    for server in catalog:
        name = str(server["name"])
        start = f"<!-- harr-mcp:{name}:start -->"
        end = f"<!-- harr-mcp:{name}:end -->"
        if start not in text and end not in text:
            continue
        if start not in text or end not in text:
            raise SystemExit(f"unbalanced Harr MCP markers for {name}")
        if name in active:
            text = text.replace(start + "\n", "").replace(start, "")
            text = text.replace(end + "\n", "").replace(end, "")
        else:
            text = re.sub(r"\n?" + re.escape(start) + r".*?" + re.escape(end) + r"\n?", "\n", text, flags=re.S)
    return text


def active_names(path: Path) -> set[str]:
    return {str(item["name"]) for item in load_servers(path)}


def filter_text(args: argparse.Namespace) -> None:
    text = args.input.read_text(encoding="utf-8")
    rendered = strip_conditional_blocks(text, load_servers(args.catalog), active_names(args.registry))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


def filter_skill(args: argparse.Namespace) -> None:
    catalog = load_servers(args.catalog)
    active = active_names(args.registry)
    if args.output.exists():
        shutil.rmtree(args.output)
    shutil.copytree(args.source, args.output)
    for path in args.output.rglob("*.md"):
        path.write_text(strip_conditional_blocks(path.read_text(encoding="utf-8"), catalog, active), encoding="utf-8")
    for server in catalog:
        reference = server.get("skill_reference")
        if reference and str(server["name"]) not in active:
            target = args.output / "references" / str(reference)
            if target.exists():
                target.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Harr assets for the active MCP set")
    sub = parser.add_subparsers(dest="command", required=True)
    p_text = sub.add_parser("filter-text")
    p_text.add_argument("--catalog", type=Path, required=True)
    p_text.add_argument("--registry", type=Path, required=True)
    p_text.add_argument("--input", type=Path, required=True)
    p_text.add_argument("--output", type=Path, required=True)
    p_skill = sub.add_parser("filter-skill")
    p_skill.add_argument("--catalog", type=Path, required=True)
    p_skill.add_argument("--registry", type=Path, required=True)
    p_skill.add_argument("--source", type=Path, required=True)
    p_skill.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "filter-text":
        filter_text(args)
    else:
        filter_skill(args)


if __name__ == "__main__":
    main()
