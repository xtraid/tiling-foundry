#!/usr/bin/env python3
"""Check semantics and internal targets in generated GitHub Pages HTML."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "docs/_config.yml"
REPRESENTATIVE_ROUTES = (
    "/",
    "/development_principles/",
    "/coverage_baseline_2026-08-22/",
    "/historical_architecture/",
)
HOME_IDS = {
    "main-content",
    "reading-path",
    "documentation",
    "cross-engine-benchmarks",
}
REFERENCE_ATTRIBUTES = {
    "a": "href",
    "img": "src",
    "link": "href",
    "script": "src",
    "source": "src",
}


@dataclass
class Page:
    path: Path
    route: str
    titles: list[str] = field(default_factory=list)
    h1s: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    canonicals: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    page_kinds: list[str] = field(default_factory=list)
    references: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Result:
    errors: tuple[str, ...]
    page_count: int
    reference_count: int


class Parser(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page
        self.capture: tuple[str, list[str]] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        values = {name.lower(): value or "" for name, value in attrs}
        if values.get("id"):
            self.page.ids.add(values["id"])
        self.page.classes.update(values.get("class", "").split())
        if tag in {"title", "h1"}:
            self.capture = (tag, [])
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.page.descriptions.append(values.get("content", ""))
        if tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.page.canonicals.append(values.get("href", ""))
        if tag == "body":
            self.page.page_kinds.append(values.get("data-page-kind", ""))
        attribute = REFERENCE_ATTRIBUTES.get(tag)
        if attribute and attribute in values:
            self.page.references.append((attribute, values[attribute]))

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.capture[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture and tag.lower() == self.capture[0]:
            text = " ".join("".join(self.capture[1]).split())
            target = self.page.titles if tag.lower() == "title" else self.page.h1s
            target.append(text)
            self.capture = None


def _route(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative == "index.html":
        return "/"
    if relative.endswith("/index.html"):
        return f"/{relative[:-len('index.html')]}"
    return f"/{relative}"


def _load_pages(root: Path, errors: list[str]) -> dict[str, Page]:
    pages: dict[str, Page] = {}
    for path in sorted(root.rglob("*.html")):
        page = Page(path, _route(root, path))
        try:
            parser = Parser(page)
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except (OSError, UnicodeError) as error:
            errors.append(f"{path}: cannot read generated HTML: {error}")
            continue
        pages[page.route] = page
    return pages


def _error(errors: list[str], root: Path, page: Page, message: str) -> None:
    errors.append(f"{page.path.relative_to(root).as_posix()}: {message}")


def _check_semantics(
    root: Path,
    pages: dict[str, Page],
    site_url: str,
    baseurl: str,
    errors: list[str],
) -> None:
    for page in pages.values():
        for label, values in (
            ("H1", page.h1s),
            ("title", page.titles),
            ("meta description", page.descriptions),
        ):
            if len(values) != 1 or not values[0].strip():
                _error(errors, root, page, f"expected one non-empty {label}, found {values!r}")
        expected = f"{site_url.rstrip('/')}{baseurl}{page.route}"
        if page.canonicals != [expected]:
            _error(
                errors,
                root,
                page,
                f"expected canonical {expected!r}, found {page.canonicals!r}",
            )

    home = pages.get("/")
    if not home:
        errors.append("missing generated homepage route '/'")
        return
    if home.titles != ["Tiling Foundry"]:
        _error(errors, root, home, f"unexpected home title {home.titles!r}")
    if home.h1s != ["Tiling Foundry"]:
        _error(errors, root, home, f"unexpected home H1 {home.h1s!r}")
    if home.page_kinds != ["home"]:
        _error(errors, root, home, f"unexpected home body marker {home.page_kinds!r}")
    missing = sorted(HOME_IDS - home.ids)
    if missing:
        _error(errors, root, home, f"missing home IDs: {', '.join(missing)}")
    required_classes = {"layout-reading", "layout-presentation", "home-catalog-section"}
    missing_classes = sorted(required_classes - home.classes)
    if missing_classes:
        _error(
            errors,
            root,
            home,
            f"missing home layout classes: {', '.join(missing_classes)}",
        )
    if "home-index" in home.classes:
        _error(errors, root, home, "legacy home-index layout class is still rendered")


def _local_target(
    value: str, source_route: str, site_url: str, baseurl: str
) -> tuple[str, str] | None:
    origin = urlsplit(site_url)
    resolved = urlsplit(urljoin(f"{site_url.rstrip('/')}{baseurl}{source_route}", value))
    if resolved.scheme.lower() in {"data", "javascript", "mailto", "tel"}:
        return None
    if (resolved.scheme.lower(), resolved.netloc.lower()) != (
        origin.scheme.lower(),
        origin.netloc.lower(),
    ):
        return None

    path = unquote(resolved.path)
    if baseurl and path == baseurl:
        path = "/"
    elif baseurl and path.startswith(f"{baseurl}/"):
        path = path[len(baseurl) :]
    elif baseurl:
        raise ValueError(f"internal URL escapes baseurl {baseurl!r}")

    trailing_slash = path.endswith("/")
    path = posixpath.normpath(path)
    if trailing_slash and path != "/":
        path += "/"
    return path, unquote(resolved.fragment)


def _check_references(
    root: Path,
    pages: dict[str, Page],
    site_url: str,
    baseurl: str,
    errors: list[str],
) -> int:
    pages_by_path = {page.path.resolve(): page for page in pages.values()}
    count = 0
    for page in pages.values():
        for attribute, value in page.references:
            count += 1
            try:
                target = _local_target(value, page.route, site_url, baseurl)
            except ValueError as error:
                _error(errors, root, page, f"{attribute}={value!r}: {error}")
                continue
            if target is None:
                continue
            path, fragment = target
            disk = root / path.lstrip("/")
            if path.endswith("/") or disk.is_dir():
                disk /= "index.html"
            if not disk.is_file():
                _error(errors, root, page, f"unresolved {attribute} target {value!r}")
            elif fragment:
                target_page = pages_by_path.get(disk.resolve())
                if not target_page or fragment not in target_page.ids:
                    _error(errors, root, page, f"unresolved fragment in {value!r}")
    return count


def check_site(root: Path, *, site_url: str, baseurl: str) -> Result:
    root = root.resolve()
    if not root.is_dir():
        return Result((f"generated site directory not found: {root}",), 0, 0)
    errors: list[str] = []
    pages = _load_pages(root, errors)
    if not pages:
        return Result(tuple(errors + [f"no HTML pages found under {root}"]), 0, 0)
    for route in REPRESENTATIVE_ROUTES:
        if route not in pages:
            errors.append(f"missing representative route {route!r}")
    _check_semantics(root, pages, site_url, baseurl, errors)
    references = _check_references(root, pages, site_url, baseurl, errors)
    return Result(tuple(errors), len(pages), references)


def _config_value(path: Path, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := pattern.match(line):
            return match.group(1).strip().strip("'\"")
    raise ValueError(f"missing {key!r} in {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        site_url = _config_value(args.config, "url")
        baseurl = _config_value(args.config, "baseurl").rstrip("/")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    result = check_site(args.site_root, site_url=site_url, baseurl=baseurl)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Generated Pages checks passed: {result.page_count} HTML pages and "
        f"{result.reference_count} href/src references validated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
