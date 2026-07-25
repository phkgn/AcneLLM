"""Render ROLE-dataset user messages with the production Jinja template.

Usage:
    python datagen/render_context.py --description "Da mình dạo này sao vậy?"
    python datagen/render_context.py --description "..." --source "Nguồn y khoa tổng hợp."
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "config" / "prompts"
TEMPLATE_NAME = "stream_user.j2"


def format_sources(sources: Sequence[str]) -> str:
    """Format synthetic context using the runtime's plain source headings."""
    clean = [str(source).strip() for source in sources if str(source).strip()]
    return "\n\n".join(
        f"Nguồn {index} —\n{source}" for index, source in enumerate(clean, 1)
    )


def render_runtime_user(description: str, sources: Sequence[str] | None = None) -> str:
    """Render one user turn from the real production template, without copied markup."""
    clean_description = str(description).strip()
    if not clean_description:
        raise ValueError("description không được rỗng")
    source_list = [str(source).strip() for source in (sources or []) if str(source).strip()]
    environment = Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=False,
    )
    template = environment.get_template(TEMPLATE_NAME)
    return template.render(
        confirmed_safety_facts="",
        known_facts="",
        route_metadata="",
        completeness_hint="",
        history_block="",
        has_retrieved_context=bool(source_list),
        retrieved_context=format_sources(source_list),
        description=clean_description,
    ).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", required=True)
    parser.add_argument("--source", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(render_runtime_user(args.description, args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
