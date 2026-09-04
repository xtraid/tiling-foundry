#!/usr/bin/env python3
"""Check semantics, accessibility, and targets in generated Pages HTML."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from check_pages import (
    ANIMATION_POLICY,
    COMPONENT_HEADINGS,
    COMPONENTS,
    EXPECTED_BY_CLASS,
    STATIC_POLICY,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "docs/_config.yml"
EXPECTED_ROUTE_CLASSES = {
    route: page_class
    for page_class, routes in EXPECTED_BY_CLASS.items()
    for route in routes
}
EXPECTED_ROUTES = frozenset(EXPECTED_ROUTE_CLASSES)
HOME_IDS = {
    "main-content",
    "project-map",
    "verified-output",
    "reading-path",
}
REFERENCE_ATTRIBUTES = {
    "a": "href",
    "img": "src",
    "link": "href",
    "script": "src",
    "source": "srcset",
}
NARRATIVE_ASSET_POLICY = {
    **{name: (route, "animation") for name, (route, _) in ANIMATION_POLICY.items()},
    **{
        name: (route, "static")
        for name, (route, _) in STATIC_POLICY.items()
        if name != "presentation_status"
    },
}


@dataclass
class Figure:
    asset_id: str = ""
    narrative_kind: str = ""
    narrative_animation: bool = False
    gif_images: list[tuple[str, str]] = field(default_factory=list)
    reduced_sources: list[str] = field(default_factory=list)
    contact_sheets: list[str] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)


@dataclass
class Page:
    path: Path
    route: str
    titles: list[str] = field(default_factory=list)
    h1s: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    canonicals: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    page_kinds: list[str] = field(default_factory=list)
    page_classes: list[str] = field(default_factory=list)
    component_ids: list[str] = field(default_factory=list)
    references: list[tuple[str, str]] = field(default_factory=list)
    images: list[tuple[str, str, str, str]] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    gifs_outside_figures: list[str] = field(default_factory=list)


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
        self.figure: Figure | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        values = {name.lower(): value or "" for name, value in attrs}
        if values.get("id"):
            self.page.ids.add(values["id"])
        self.page.classes.update(values.get("class", "").split())
        if tag in {"title", "h1", "h2", "figcaption"}:
            self.capture = (tag, [])
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.page.descriptions.append(values.get("content", ""))
        if tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.page.canonicals.append(values.get("href", ""))
        if tag == "body":
            self.page.page_kinds.append(values.get("data-page-kind", ""))
            self.page.page_classes.append(values.get("data-page-class", ""))
            component = values.get("data-component-id", "")
            if component:
                self.page.component_ids.append(component)
        if tag == "figure":
            classes = set(values.get("class", "").split())
            kinds = classes & {"narrative-animation", "narrative-static"}
            self.figure = Figure(
                asset_id=values.get("data-asset-id", ""),
                narrative_kind=(
                    "animation"
                    if kinds == {"narrative-animation"}
                    else "static"
                    if kinds == {"narrative-static"}
                    else ""
                ),
                narrative_animation="narrative-animation" in kinds,
            )
            self.page.figures.append(self.figure)
        if tag == "img":
            source = values.get("src", "")
            alt = values.get("alt", "")
            width = values.get("width", "")
            height = values.get("height", "")
            self.page.images.append((source, alt, width, height))
            if source.lower().endswith(".gif"):
                if self.figure is None:
                    self.page.gifs_outside_figures.append(source)
                else:
                    self.figure.gif_images.append((source, alt))
        if tag == "source" and self.figure is not None:
            source = values.get("srcset", "")
            media = values.get("media", "").lower()
            if source.lower().endswith(".png") and "prefers-reduced-motion: reduce" in media:
                self.figure.reduced_sources.append(source)
        if tag == "a" and self.figure is not None:
            href = values.get("href", "")
            if "contact-sheet.png" in href:
                self.figure.contact_sheets.append(href)
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
        tag = tag.lower()
        if self.capture and tag == self.capture[0]:
            text = " ".join("".join(self.capture[1]).split())
            if tag == "title":
                self.page.titles.append(text)
            elif tag == "h1":
                self.page.h1s.append(text)
            elif tag == "h2":
                self.page.h2s.append(text)
            elif self.figure is not None:
                self.figure.captions.append(text)
            self.capture = None
        if tag == "figure":
            self.figure = None


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


def _check_narrative_asset_topology(
    root: Path, pages: dict[str, Page], errors: list[str]
) -> None:
    rendered: dict[str, list[tuple[Page, int, Figure]]] = {}
    for page in pages.values():
        for index, figure in enumerate(page.figures, start=1):
            if figure.asset_id:
                rendered.setdefault(figure.asset_id, []).append((page, index, figure))
            elif figure.narrative_kind:
                _error(errors, root, page, f"figure {index} lacks data-asset-id")

    for asset_id, (owner, expected_kind) in NARRATIVE_ASSET_POLICY.items():
        occurrences = rendered.pop(asset_id, [])
        if not occurrences:
            errors.append(f"missing narrative {expected_kind} asset {asset_id!r}")
            continue
        if len(occurrences) != 1:
            errors.append(
                f"narrative asset {asset_id!r} occurs {len(occurrences)} times; expected exactly once"
            )
            continue
        page, index, figure = occurrences[0]
        if page.route != owner:
            _error(
                errors,
                root,
                page,
                f"narrative asset {asset_id!r} is rendered on {page.route!r}, expected owner {owner!r}",
            )
        if figure.narrative_kind != expected_kind:
            _error(
                errors,
                root,
                page,
                f"narrative asset {asset_id!r} must be an {expected_kind} figure",
            )
    for asset_id, occurrences in sorted(rendered.items()):
        for page, index, _ in occurrences:
            _error(errors, root, page, f"figure {index} has unexpected data-asset-id {asset_id!r}")


def _check_semantics(
    root: Path,
    pages: dict[str, Page],
    site_url: str,
    baseurl: str,
    errors: list[str],
) -> None:
    missing_routes = sorted(EXPECTED_ROUTES - pages.keys())
    extra_routes = sorted(pages.keys() - EXPECTED_ROUTES)
    if missing_routes:
        errors.append(f"missing generated routes: {', '.join(missing_routes)}")
    if extra_routes:
        errors.append(f"unexpected generated routes: {', '.join(extra_routes)}")

    for route, page in pages.items():
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
        expected_class = EXPECTED_ROUTE_CLASSES.get(route)
        if expected_class and page.page_classes != [expected_class]:
            _error(
                errors,
                root,
                page,
                f"expected page class {expected_class!r}, found {page.page_classes!r}",
            )
        if route in COMPONENTS:
            component_id = COMPONENTS[route][0]
            if page.component_ids != [component_id]:
                _error(
                    errors,
                    root,
                    page,
                    f"expected component id {component_id!r}, found {page.component_ids!r}",
                )
            if tuple(page.h2s) != COMPONENT_HEADINGS:
                _error(errors, root, page, f"component H2 sequence is {page.h2s!r}")
        elif page.component_ids:
            _error(errors, root, page, f"unexpected component id {page.component_ids!r}")
        for source, alt, width, height in page.images:
            if not alt.strip():
                _error(errors, root, page, f"image {source!r} has empty alt text")
            if "/assets/narrative/" in source:
                try:
                    valid_dimensions = int(width) > 0 and int(height) > 0
                except ValueError:
                    valid_dimensions = False
                if not valid_dimensions:
                    _error(
                        errors,
                        root,
                        page,
                        f"narrative image {source!r} lacks positive intrinsic dimensions",
                    )
        if page.gifs_outside_figures:
            _error(
                errors,
                root,
                page,
                f"GIFs outside figures: {page.gifs_outside_figures!r}",
            )
        for index, figure in enumerate(page.figures, start=1):
            if not figure.narrative_animation and not figure.gif_images:
                continue
            if len(figure.gif_images) != 1:
                _error(errors, root, page, f"figure {index} must contain exactly one GIF")
            if len(figure.reduced_sources) != 1:
                _error(errors, root, page, f"figure {index} requires one reduced-motion PNG srcset")
            if len(figure.contact_sheets) != 1:
                _error(errors, root, page, f"figure {index} requires one contact-sheet link")
            if len(figure.captions) != 1 or not figure.captions[0]:
                _error(errors, root, page, f"figure {index} requires one non-empty caption")

    _check_narrative_asset_topology(root, pages, errors)

    home = pages.get("/")
    if not home:
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
    required_classes = {"layout-reading", "layout-presentation", "home-section"}
    missing_classes = sorted(required_classes - home.classes)
    if missing_classes:
        _error(errors, root, home, f"missing home layout classes: {', '.join(missing_classes)}")


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
    gif_owners: dict[str, str] = {}
    count = 0
    for page in pages.values():
        for attribute, value in page.references:
            count += 1
            candidate_value = value.split()[0] if attribute == "srcset" else value
            try:
                target = _local_target(candidate_value, page.route, site_url, baseurl)
            except ValueError as error:
                _error(errors, root, page, f"{attribute}={value!r}: {error}")
                continue
            if target is None:
                continue
            path, fragment = target
            if path.endswith(".gif"):
                previous = gif_owners.get(path)
                if previous is not None:
                    _error(
                        errors,
                        root,
                        page,
                        f"GIF {path!r} is already embedded by {previous!r}",
                    )
                gif_owners[path] = page.route
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
        f"{result.reference_count} href/src/srcset references validated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
