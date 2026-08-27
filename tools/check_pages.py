#!/usr/bin/env python3
"""Validate the GitHub Pages document catalog without third-party packages."""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

SECTIONS = {
    "Architecture and correctness",
    "Yang–Zhang reduction",
    "Solver optimization",
    "Cross-engine benchmarks",
    "Historical material",
}
REQUIRED_FIELDS = {
    "layout",
    "title",
    "permalink",
    "description",
    "section",
    "document_kind",
    "status",
    "updated",
    "nav_order",
}
FORBIDDEN_PUBLIC_PATTERNS = {
    "internal task identifier": re.compile(r"\bT\d{2,}\b"),
    "work-packet language": re.compile(r"\bpacket\b", re.IGNORECASE),
    "handoff language": re.compile(r"\bhandoff\b", re.IGNORECASE),
    "implementation-plan placeholder": re.compile(r"implementation plan", re.IGNORECASE),
}
RELATIVE_URL = re.compile(
    r"\{\{\s*['\"](?P<path>/[^'\"]+)['\"]\s*\|\s*relative_url\s*\}\}"
)
MARKDOWN_SOURCE_LINK = re.compile(r"\]\([^)]*\.md(?:[#?][^)]*)?\)")
HISTORICAL_PDF = "Wang23_C_OpenMP_Architecture_Spec_Merged.pdf"
FIGURE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<(?:img|source)\b[^>]*>", re.IGNORECASE | re.DOTALL)


def fail(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def split_front_matter(path: Path, errors: list[str]) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        fail(errors, path, "missing YAML front matter")
        return {}, text

    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(errors, path, "unterminated YAML front matter")
        return {}, text

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line.startswith((" ", "\t", "#")):
            continue
        if ":" not in line:
            fail(errors, path, f"unsupported front-matter line: {line!r}")
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("'\"")
    return metadata, "\n".join(lines[end + 1 :])


def public_documents() -> list[Path]:
    return sorted(
        path
        for path in DOCS.rglob("*.md")
        if path.name not in {"index.md", "post-template.md"}
        and "plans" not in path.relative_to(DOCS).parts
        and "_posts" not in path.relative_to(DOCS).parts
    )


def check_catalog(errors: list[str]) -> tuple[set[str], int]:
    permalinks = {"/"}
    section_orders: set[tuple[str, int]] = set()
    documents = public_documents()

    for path in documents:
        metadata, body = split_front_matter(path, errors)
        missing = sorted(REQUIRED_FIELDS - metadata.keys())
        if missing:
            fail(errors, path, f"missing fields: {', '.join(missing)}")
            continue

        for field in sorted(REQUIRED_FIELDS):
            if not metadata[field]:
                fail(errors, path, f"field {field!r} must not be empty")

        if metadata["layout"] != "page":
            fail(errors, path, "layout must be 'page'")

        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata["updated"]):
                raise ValueError
            date.fromisoformat(metadata["updated"])
        except ValueError:
            fail(errors, path, "updated must be an ISO date in YYYY-MM-DD form")

        try:
            nav_order = int(metadata["nav_order"])
        except ValueError:
            fail(errors, path, "nav_order must be a positive integer")
            nav_order = 0
        else:
            if nav_order <= 0 or str(nav_order) != metadata["nav_order"]:
                fail(errors, path, "nav_order must be a positive integer")

        section = metadata["section"]
        if section not in SECTIONS:
            fail(errors, path, f"unknown section {section!r}")

        permalink = metadata["permalink"]
        if not (permalink.startswith("/") and permalink.endswith("/")):
            fail(errors, path, "permalink must start and end with '/'")
        if permalink in permalinks:
            fail(errors, path, f"duplicate permalink {permalink!r}")
        permalinks.add(permalink)

        order_key = (section, nav_order)
        if order_key in section_orders:
            fail(errors, path, f"duplicate nav_order {order_key[1]} in {section!r}")
        section_orders.add(order_key)

        headings = re.findall(r"^#\s+\S.*$", body, flags=re.MULTILINE)
        if len(headings) != 1:
            fail(errors, path, f"expected one H1, found {len(headings)}")

        public_text = "\n".join((*metadata.values(), body))
        for label, pattern in FORBIDDEN_PUBLIC_PATTERNS.items():
            if pattern.search(public_text):
                fail(errors, path, label)

        if MARKDOWN_SOURCE_LINK.search(body):
            fail(errors, path, "link to Markdown source instead of a Pages permalink")

        if HISTORICAL_PDF in body and path.name != "historical_architecture.md":
            fail(errors, path, "historical PDF must be presented through its context page")

    return permalinks, len(documents)


def check_liquid_links(permalinks: set[str], errors: list[str]) -> None:
    index = (DOCS / "index.md").read_text(encoding="utf-8")
    index_ids = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", index))
    candidates = [
        *DOCS.rglob("*.md"),
        *DOCS.rglob("*.html"),
    ]
    for path in sorted(candidates):
        if path.name == "post-template.md" or "plans" in path.relative_to(DOCS).parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RELATIVE_URL.finditer(text):
            target = match.group("path")
            route, separator, anchor = target.partition("#")
            if separator and route == "/" and anchor not in index_ids:
                fail(errors, path, f"unresolved index anchor {target!r}")
                continue
            if route in permalinks:
                continue
            disk_target = DOCS / route.lstrip("/")
            if disk_target.is_file():
                continue
            fail(errors, path, f"unresolved relative_url target {target!r}")


def check_site_structure(errors: list[str]) -> None:
    config = (DOCS / "_config.yml").read_text(encoding="utf-8")
    for excluded in ("post-template.md", "plans"):
        if not re.search(rf"^\s*-\s+{re.escape(excluded)}\s*$", config, re.MULTILINE):
            fail(errors, DOCS / "_config.yml", f"{excluded!r} is not excluded")

    index = (DOCS / "index.md").read_text(encoding="utf-8")
    index_ids = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", index))
    for section in sorted(SECTIONS):
        if f'where: "section", "{section}"' not in index:
            fail(errors, DOCS / "index.md", f"section {section!r} is not cataloged")
    if "document-list.html" not in index:
        fail(errors, DOCS / "index.md", "document-list include is not used")
    for anchor in re.findall(r"\]\(#([^)]+)\)", index):
        if anchor not in index_ids:
            fail(errors, DOCS / "index.md", f"unresolved local anchor #{anchor}")

    css = (DOCS / "assets/css/site.css").read_text(encoding="utf-8")
    if css.count("{") != css.count("}"):
        fail(errors, DOCS / "assets/css/site.css", "unbalanced braces")


def check_animated_assets(errors: list[str]) -> None:
    """Require accessible static fallbacks and one stored copy per GIF."""
    for path in public_documents():
        text = path.read_text(encoding="utf-8")
        figures = FIGURE.findall(text)
        covered_gifs = sum(figure.lower().count(".gif") for figure in figures)
        if covered_gifs != text.lower().count(".gif"):
            fail(errors, path, "animated GIF must be contained in a figure")

        for figure in figures:
            if ".gif" not in figure.lower():
                continue
            tags = TAG.findall(figure)
            image_tags = [tag for tag in tags if tag.lower().startswith("<img")]
            source_tags = [tag for tag in tags if tag.lower().startswith("<source")]
            if not any(
                ".gif" in tag.lower()
                and re.search(r'\balt=["\'][^"\']+["\']', tag, re.IGNORECASE)
                for tag in image_tags
            ):
                fail(errors, path, "animated GIF requires nonempty img alt text")
            if not any(
                ".png" in tag.lower()
                and "prefers-reduced-motion: reduce" in tag.lower()
                for tag in source_tags
            ):
                fail(errors, path, "animated GIF requires a reduced-motion PNG source")
            if not re.search(
                r"<figcaption\b[^>]*>\s*\S.*?</figcaption>",
                figure,
                re.IGNORECASE | re.DOTALL,
            ):
                fail(errors, path, "animated GIF requires a nonempty figcaption")

    gif_hashes: dict[bytes, Path] = {}
    for path in sorted((DOCS / "assets/images").rglob("*.gif")):
        digest = hashlib.sha256(path.read_bytes()).digest()
        if digest in gif_hashes:
            fail(
                errors,
                path,
                f"duplicates animated asset {gif_hashes[digest].relative_to(ROOT)}",
            )
        gif_hashes[digest] = path


def main() -> int:
    errors: list[str] = []
    permalinks, document_count = check_catalog(errors)
    check_liquid_links(permalinks, errors)
    check_site_structure(errors)
    check_animated_assets(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"Pages checks passed: {document_count} technical documents plus the index, "
        f"{len(SECTIONS)} sections, and all literal internal links resolved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
