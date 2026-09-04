#!/usr/bin/env python3
"""Validate the authored GitHub Pages site and its canonical narrative assets."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
NARRATIVE_ROOT = DOCS / "assets/narrative"
NARRATIVE_MANIFEST = NARRATIVE_ROOT / "manifest.json"

PUBLIC_CLASSES = {"story", "reference", "evidence", "history"}
SECTIONS = {
    "Architecture and correctness",
    "Yang–Zhang reduction",
    "Solver optimization",
    "Cross-engine benchmarks",
    "Historical material",
}
COMPONENT_HEADINGS = (
    "What it is",
    "Why it exists",
    "Inputs and outputs",
    "Mechanism",
    "Primary animation",
    "Position in the pipeline",
    "Observed example",
    "Trust boundary",
    "Artifacts and references",
)
COMPONENTS = {
    "/components/tileset/": ("tileset", 1, "generalized_sheet"),
    "/components/boolean-z3/": ("boolean-z3", 2, "boolean_z3"),
    "/components/yang-zhang/": ("yang-zhang", 3, "region_construction"),
    "/components/reference-solver/": ("reference-solver", 4, "reference_trace"),
    "/components/optimized-solver/": ("optimized-solver", 5, "optimized_trace"),
    "/components/wang-z3/": ("wang-z3", 6, "wang_z3"),
    "/components/verification/": ("verification", 7, "verification"),
    "/components/visualization/": ("visualization", 8, "witness_presentation"),
}
STORY_ROUTES = {
    "/",
    "/pipeline/",
    "/worked-example/",
    "/reference/",
    "/evidence/",
    *COMPONENTS,
}
REFERENCE_ROUTES = {
    "/development_principles/",
    "/reduction_notes/",
    "/references/",
    "/run-dossiers/",
    "/serial_solver_implementation_guide/",
    "/solver_comparison_benchmark/",
    "/solver_performance_scope/",
    "/wang-explainability-snapshots/",
    "/wang-reduction-explanation/",
    "/wang-solution-v1/",
    "/wang-solver-trace/",
    "/wang-square-to-hex/",
    "/wang_z3_edge_table_2026-08-24/",
    "/yang_zhang_builder_design/",
    "/witness_correspondence/",
}
EVIDENCE_ROUTES = {
    "/coverage_baseline_2026-08-22/",
    "/parser_fuzz_smoke_2026-08-22/",
    "/solver_byte_support_2026-08-20/",
    "/solver_comparison_smoke_2026-08-21/",
    "/solver_dynamic_stack_2026-08-17/",
    "/solver_initial_trail_2026-08-17/",
    "/solver_mrv_index_2026-08-28/",
    "/solver_queue_dedup_2026-08-20/",
    "/solver_queue_trail_profile_2026-08-20/",
    "/solver_reference_profile_2026-08-17/",
    "/solver_sat_ownership_2026-08-20/",
}
HISTORY_ROUTES = {"/historical_architecture/"}
EXPECTED_BY_CLASS = {
    "story": STORY_ROUTES,
    "reference": REFERENCE_ROUTES,
    "evidence": EVIDENCE_ROUTES,
    "history": HISTORY_ROUTES,
}
EXPECTED_ROUTES = set().union(*EXPECTED_BY_CLASS.values())

COMMON_FIELDS = {"layout", "title", "permalink", "description", "page_class"}
TECHNICAL_FIELDS = {
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
NARRATIVE_INCLUDE = re.compile(
    r"\{%\s*include\s+(?P<template>narrative-(?:animation|static)\.html)"
    r"(?P<arguments>.*?)%\}",
    re.DOTALL,
)
MARKDOWN_SOURCE_LINK = re.compile(r"\]\([^)]*\.md(?:[#?][^)]*)?\)")
HISTORICAL_PDF = "Wang23_C_OpenMP_Architecture_Spec_Merged.pdf"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ASSET_PATH = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.\.?(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
ALLOWED_LABELS = {
    "observed",
    "canonical-construction",
    "encoding-order",
    "verified-transformation",
    "didactic",
}
ANIMATION_POLICY = {
    "pipeline_overview": ("/pipeline/", "observed"),
    "boolean_z3": ("/components/boolean-z3/", "encoding-order"),
    "region_construction": ("/components/yang-zhang/", "canonical-construction"),
    "reference_trace": ("/components/reference-solver/", "observed"),
    "optimized_trace": ("/components/optimized-solver/", "observed"),
    "wang_z3": ("/components/wang-z3/", "encoding-order"),
    "verification": ("/components/verification/", "observed"),
    "witness_presentation": (
        "/components/visualization/",
        "verified-transformation",
    ),
    "optimized_mechanisms": ("/components/optimized-solver/", "didactic"),
}
STATIC_POLICY = {
    "home_preview": ("/", "observed"),
    "worked_example": ("/worked-example/", "observed"),
    "formula": ("/worked-example/", "observed"),
    "generalized_sheet": ("/components/tileset/", "canonical-construction"),
    "atomic_legend": ("/components/tileset/", "canonical-construction"),
    "square_presentation": ("/components/visualization/", "observed"),
    "generalized_presentation": (
        "/components/visualization/",
        "canonical-construction",
    ),
    "hex_presentation": (
        "/components/visualization/",
        "verified-transformation",
    ),
    "presentation_status": ("/run-dossiers/", "observed"),
}
FROZEN_CROSS_LINKS = {
    "/worked-example/": tuple(COMPONENTS),
    "/components/optimized-solver/": ("/run-dossiers/",),
    "/solver_mrv_index_2026-08-28/": ("/components/optimized-solver/",),
}
SELECTED_ANIMATIONS = {
    "pipeline_overview",
    "region_construction",
    "reference_trace",
    "optimized_trace",
}
LEGACY_ASSET_DIRECTORIES = {
    "builder-routing",
    "optimized-mechanisms",
    "solver-trace",
    "square-to-hex",
    "z3-encoding",
}
ALLOWED_PUBLIC_IMAGES = {"tile-mark.svg"}
ANIMATION_INCLUDE_FIELDS = {
    "asset_id",
    "animation",
    "fallback",
    "contact_sheet",
    "alt",
    "width",
    "height",
    "label",
    "caption",
    "source",
}
STATIC_INCLUDE_FIELDS = {
    "asset_id",
    "image",
    "alt",
    "width",
    "height",
    "label",
    "caption",
    "source",
}


@dataclass(frozen=True)
class Document:
    path: Path
    metadata: dict[str, str]
    body: str


@dataclass(frozen=True)
class NarrativeInclude:
    route: str
    path: Path
    template: str
    arguments: dict[str, str]


def _section_has_narrative_include(section: str, asset_id: str) -> bool:
    for match in NARRATIVE_INCLUDE.finditer(section):
        try:
            tokens = shlex.split(match.group("arguments"), comments=False, posix=True)
        except ValueError:
            continue
        for token in tokens:
            field, separator, value = token.partition("=")
            if separator and field == "asset_id" and value == asset_id:
                return True
    return False


def fail(errors: list[str], path: Path, message: str) -> None:
    try:
        display = path.relative_to(ROOT)
    except ValueError:
        display = path
    errors.append(f"{display}: {message}")


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
        key = key.strip()
        if key in metadata:
            fail(errors, path, f"duplicate front-matter field {key!r}")
        metadata[key] = value.strip().strip("'\"")
    return metadata, "\n".join(lines[end + 1 :])


def public_document_paths(docs: Path = DOCS) -> list[Path]:
    return sorted(
        path
        for path in docs.rglob("*.md")
        if path.name != "post-template.md"
        and "plans" not in path.relative_to(docs).parts
        and "_posts" not in path.relative_to(docs).parts
    )


def _check_iso_date(errors: list[str], document: Document) -> None:
    value = document.metadata.get("updated", "")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        date.fromisoformat(value)
    except ValueError:
        fail(errors, document.path, "updated must be an ISO date in YYYY-MM-DD form")


def check_catalog(errors: list[str]) -> dict[str, Document]:
    documents: dict[str, Document] = {}
    section_orders: set[tuple[str, int]] = set()
    class_counts: Counter[str] = Counter()

    for path in public_document_paths():
        metadata, body = split_front_matter(path, errors)
        document = Document(path, metadata, body)
        missing = sorted(COMMON_FIELDS - metadata.keys())
        if missing:
            fail(errors, path, f"missing fields: {', '.join(missing)}")
            continue
        for field in sorted(COMMON_FIELDS):
            if not metadata[field]:
                fail(errors, path, f"field {field!r} must not be empty")

        route = metadata["permalink"]
        if not (route.startswith("/") and route.endswith("/")):
            fail(errors, path, "permalink must start and end with '/'")
        if route in documents:
            fail(errors, path, f"duplicate permalink {route!r}")
        documents[route] = document

        page_class = metadata["page_class"]
        class_counts[page_class] += 1
        if page_class not in PUBLIC_CLASSES:
            fail(errors, path, f"unknown page_class {page_class!r}")
        elif route not in EXPECTED_BY_CLASS[page_class]:
            expected = next(
                (name for name, routes in EXPECTED_BY_CLASS.items() if route in routes),
                None,
            )
            fail(errors, path, f"route {route!r} must use page_class {expected!r}")

        expected_layout = "default" if route == "/" else (
            "story" if page_class == "story" else "page"
        )
        if metadata["layout"] != expected_layout:
            fail(errors, path, f"layout must be {expected_layout!r}")

        if page_class != "story":
            missing = sorted(TECHNICAL_FIELDS - metadata.keys())
            if missing:
                fail(errors, path, f"missing technical fields: {', '.join(missing)}")
            else:
                _check_iso_date(errors, document)
                section = metadata["section"]
                if section not in SECTIONS:
                    fail(errors, path, f"unknown section {section!r}")
                try:
                    nav_order = int(metadata["nav_order"])
                except ValueError:
                    fail(errors, path, "nav_order must be a positive integer")
                else:
                    if nav_order <= 0 or str(nav_order) != metadata["nav_order"]:
                        fail(errors, path, "nav_order must be a positive integer")
                    key = (section, nav_order)
                    if key in section_orders:
                        fail(errors, path, f"duplicate nav_order {nav_order} in {section!r}")
                    section_orders.add(key)

        markdown_h1s = re.findall(r"^#\s+\S.*$", body, flags=re.MULTILINE)
        html_h1s = re.findall(r"<h1(?:\s[^>]*)?>.*?</h1>", body, flags=re.DOTALL)
        h1s = [*markdown_h1s, *html_h1s]
        if len(h1s) != 1:
            fail(errors, path, f"expected one H1, found {len(h1s)}")
        h2s = tuple(re.findall(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
        if route in COMPONENTS:
            component_id, order, primary = COMPONENTS[route]
            expected = {
                "component_id": component_id,
                "pipeline_order": str(order),
                "primary_asset": primary,
            }
            for field, value in expected.items():
                if metadata.get(field) != value:
                    fail(errors, path, f"{field} must be {value!r}")
            if h2s != COMPONENT_HEADINGS:
                fail(errors, path, f"component H2 sequence is {h2s!r}")
            primary_section = re.search(
                r"^## Primary animation\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
                body,
                flags=re.MULTILINE | re.DOTALL,
            )
            if not primary_section or not _section_has_narrative_include(
                primary_section.group("body"), primary
            ):
                fail(
                    errors,
                    path,
                    f"primary asset {primary!r} must use a narrative include in the Primary animation section",
                )
        elif any(name in metadata for name in ("component_id", "pipeline_order", "primary_asset")):
            fail(errors, path, "component-only front matter appears on a non-component route")

        public_text = "\n".join((*metadata.values(), body))
        for label, pattern in FORBIDDEN_PUBLIC_PATTERNS.items():
            if pattern.search(public_text):
                fail(errors, path, label)
        if MARKDOWN_SOURCE_LINK.search(body):
            fail(errors, path, "link to Markdown source instead of a Pages permalink")
        if HISTORICAL_PDF in body and route != "/historical_architecture/":
            fail(errors, path, "historical PDF must be presented through its context page")

    missing_routes = sorted(EXPECTED_ROUTES - documents.keys())
    extra_routes = sorted(documents.keys() - EXPECTED_ROUTES)
    if missing_routes:
        fail(errors, DOCS, f"missing public routes: {', '.join(missing_routes)}")
    if extra_routes:
        fail(errors, DOCS, f"unexpected public routes: {', '.join(extra_routes)}")
    expected_counts = {name: len(routes) for name, routes in EXPECTED_BY_CLASS.items()}
    if dict(class_counts) != expected_counts:
        fail(errors, DOCS, f"page class counts {dict(class_counts)!r}, expected {expected_counts!r}")
    return documents


def check_liquid_links(documents: dict[str, Document], errors: list[str]) -> None:
    home = documents.get("/")
    home_ids = set(re.findall(r"\bid=[\"']([^\"']+)[\"']", home.body if home else ""))
    candidates = [*DOCS.rglob("*.md"), *DOCS.rglob("*.html")]
    for path in sorted(candidates):
        if path.name == "post-template.md" or "plans" in path.relative_to(DOCS).parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RELATIVE_URL.finditer(text):
            target = match.group("path")
            route, separator, anchor = target.partition("#")
            if separator and route == "/" and anchor not in home_ids:
                fail(errors, path, f"unresolved index anchor {target!r}")
                continue
            if route in documents:
                continue
            disk_target = DOCS / route.lstrip("/")
            if disk_target.is_file():
                continue
            fail(errors, path, f"unresolved relative_url target {target!r}")


def _load_manifest(errors: list[str]) -> dict[str, object] | None:
    try:
        value = json.loads(NARRATIVE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(errors, NARRATIVE_MANIFEST, f"cannot load canonical manifest: {error}")
        return None
    if type(value) is not dict:
        fail(errors, NARRATIVE_MANIFEST, "manifest root must be an object")
        return None
    return value


def _artifact(
    value: object,
    label: str,
    errors: list[str],
) -> tuple[str, str] | None:
    if type(value) is not dict or set(value) != {"path", "sha256", "media_type"}:
        fail(errors, NARRATIVE_MANIFEST, f"{label} must be a closed artifact record")
        return None
    relative = value["path"]
    digest = value["sha256"]
    media_type = value["media_type"]
    if type(relative) is not str or not ASSET_PATH.fullmatch(relative):
        fail(errors, NARRATIVE_MANIFEST, f"{label}.path is not a safe relative path")
        return None
    if type(digest) is not str or not SHA256.fullmatch(digest):
        fail(errors, NARRATIVE_MANIFEST, f"{label}.sha256 is invalid")
        return None
    if relative.endswith(".gif"):
        expected_media = "image/gif"
    elif relative.endswith(".png"):
        expected_media = "image/png"
    else:
        fail(errors, NARRATIVE_MANIFEST, f"{label}.path must end in .png or .gif")
        return None
    if media_type != expected_media:
        fail(errors, NARRATIVE_MANIFEST, f"{label}.media_type disagrees with path")
    candidate = NARRATIVE_ROOT / relative
    cursor = NARRATIVE_ROOT
    try:
        for part in Path(relative).parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("symlinks are forbidden")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(NARRATIVE_ROOT.resolve()) or not resolved.is_file():
            raise ValueError("path escapes canonical bundle")
        encoded = resolved.read_bytes()
    except (OSError, ValueError) as error:
        fail(errors, NARRATIVE_MANIFEST, f"{label}.path cannot be used: {error}")
        return None
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != digest:
        fail(errors, candidate, f"SHA-256 {actual} disagrees with manifest {digest}")
    return relative, digest


def _metadata(
    record: object,
    label: str,
    policy: tuple[str, str],
    errors: list[str],
) -> dict[str, object] | None:
    if type(record) is not dict:
        fail(errors, NARRATIVE_MANIFEST, f"{label} must be an object")
        return None
    owner, semantic_label = policy
    if record.get("owner") != owner:
        fail(errors, NARRATIVE_MANIFEST, f"{label}.owner must be {owner!r}")
    actual_label = record.get("semantic_label")
    if actual_label not in ALLOWED_LABELS or actual_label != semantic_label:
        fail(errors, NARRATIVE_MANIFEST, f"{label}.semantic_label disagrees with policy")
    for name in (
        "caption",
        "alt_text",
        "source_contract",
        "producer",
        "validator",
        "compositor",
    ):
        if type(record.get(name)) is not str or not record[name].strip():
            fail(errors, NARRATIVE_MANIFEST, f"{label}.{name} must be nonempty")
    source_sha = record.get("source_sha256")
    if type(source_sha) is not str or not SHA256.fullmatch(source_sha):
        fail(errors, NARRATIVE_MANIFEST, f"{label}.source_sha256 is invalid")
    return record


def _require_owner_copy(
    name: str,
    record: dict[str, object],
    template: str,
    roles: dict[str, str],
    documents: dict[str, Document],
    includes: dict[str, NarrativeInclude],
    errors: list[str],
) -> None:
    owner = str(record["owner"])
    if owner not in documents:
        fail(errors, NARRATIVE_MANIFEST, f"{name} names missing owner route {owner!r}")
        return
    include = includes.get(name)
    if include is None:
        fail(errors, documents[owner].path, f"owned asset {name!r} has no include")
        return
    if include.route != owner:
        fail(
            errors,
            include.path,
            f"asset include {name!r} must occur in owner {owner!r}",
        )
    if include.template != template:
        fail(
            errors,
            include.path,
            f"asset include {name!r} must use {template!r}",
        )
    expected = {
        "asset_id": name,
        "alt": str(record["alt_text"]),
        "label": str(record["semantic_label"]),
        "caption": str(record["caption"]),
        "source": str(record["source_contract"]),
        **roles,
    }
    for field, value in expected.items():
        if include.arguments.get(field) != value:
            fail(
                errors,
                include.path,
                f"asset {name!r} include argument {field!r} must be {value!r}",
            )
    for public in roles.values():
        locations = [
            route for route, document in documents.items() if public in document.body
        ]
        if locations != [owner]:
            fail(
                errors,
                NARRATIVE_MANIFEST,
                f"{name} public path {public!r} must occur only in {owner!r}, found {locations!r}",
            )


def _parse_narrative_includes(
    documents: dict[str, Document], errors: list[str]
) -> dict[str, NarrativeInclude]:
    includes: dict[str, NarrativeInclude] = {}
    for route, document in documents.items():
        for match in NARRATIVE_INCLUDE.finditer(document.body):
            template = match.group("template")
            try:
                tokens = shlex.split(match.group("arguments"), comments=False, posix=True)
            except ValueError as error:
                fail(errors, document.path, f"cannot parse narrative include: {error}")
                continue
            arguments: dict[str, str] = {}
            malformed = False
            for token in tokens:
                if "=" not in token:
                    fail(errors, document.path, f"malformed narrative include argument {token!r}")
                    malformed = True
                    continue
                field, value = token.split("=", 1)
                if not field or field in arguments:
                    fail(errors, document.path, f"duplicate narrative include argument {field!r}")
                    malformed = True
                    continue
                arguments[field] = value
            expected_fields = (
                ANIMATION_INCLUDE_FIELDS
                if template == "narrative-animation.html"
                else STATIC_INCLUDE_FIELDS
            )
            if set(arguments) != expected_fields:
                fail(
                    errors,
                    document.path,
                    "narrative include argument fields are not closed",
                )
                malformed = True
            for dimension in ("width", "height"):
                if not re.fullmatch(r"[1-9][0-9]*", arguments.get(dimension, "")):
                    fail(
                        errors,
                        document.path,
                        f"narrative include {dimension} must be a positive integer",
                    )
                    malformed = True
            asset_id = arguments.get("asset_id", "")
            if not asset_id:
                fail(errors, document.path, "narrative include asset_id must be nonempty")
                continue
            if asset_id in includes:
                fail(errors, document.path, f"duplicate narrative include asset_id {asset_id!r}")
                continue
            if not malformed:
                includes[asset_id] = NarrativeInclude(
                    route=route,
                    path=document.path,
                    template=template,
                    arguments=arguments,
                )
    return includes


def check_narrative_assets(
    documents: dict[str, Document], errors: list[str]
) -> tuple[int, int]:
    includes = _parse_narrative_includes(documents, errors)
    manifest = _load_manifest(errors)
    if manifest is None:
        return 0, 0
    expected_fields = {
        "schema",
        "product",
        "case",
        "identities",
        "animations",
        "statics",
        "pdf_milestones",
    }
    if set(manifest) != expected_fields:
        fail(errors, NARRATIVE_MANIFEST, "manifest top-level fields are not closed")
    if manifest.get("schema") != "wang-narrative-assets-v1":
        fail(errors, NARRATIVE_MANIFEST, "unexpected narrative schema")
    if manifest.get("product") != "canonical-pages":
        fail(errors, NARRATIVE_MANIFEST, "product must be canonical-pages")
    expected_case = {
        "id": "pipeline-sat-v2",
        "expected_status": "sat",
        "source_sha256": "3caaa6b29ac988fb4f51cc7071202d83ea1591ba6170e683b6da449cb3641542",
    }
    if manifest.get("case") != expected_case:
        fail(errors, NARRATIVE_MANIFEST, "case is not the canonical SAT Pages case")

    identity_names = {
        "source_formula",
        "formula_snapshot",
        "tileset",
        "region",
        "provenance",
        "boolean_z3_summary",
        "reference_trace_manifest",
        "reference_trace",
        "reference_solution",
        "optimized_trace_manifest",
        "optimized_trace",
        "optimized_solution",
        "wang_z3_summary",
    }
    identities = manifest.get("identities")
    if type(identities) is not dict or set(identities) != identity_names:
        fail(errors, NARRATIVE_MANIFEST, "identity set is not closed")
    else:
        for name, value in identities.items():
            if type(value) is not str or not SHA256.fullmatch(value):
                fail(errors, NARRATIVE_MANIFEST, f"identities.{name} is not a SHA-256")

    animations = manifest.get("animations")
    statics = manifest.get("statics")
    if type(animations) is not dict or set(animations) != set(ANIMATION_POLICY):
        fail(errors, NARRATIVE_MANIFEST, "animation set disagrees with Pages policy")
        animations = {}
    if type(statics) is not dict or set(statics) != set(STATIC_POLICY):
        fail(errors, NARRATIVE_MANIFEST, "static set disagrees with Pages policy")
        statics = {}

    owned_files: set[str] = set()
    owned_digests: dict[str, str] = {}
    assets_by_owner: defaultdict[str, set[str]] = defaultdict(set)
    animation_frames: dict[str, tuple[str, ...]] = {}

    for name, policy in ANIMATION_POLICY.items():
        record = _metadata(animations.get(name), f"animations.{name}", policy, errors)
        if record is None:
            continue
        required = {
            "owner", "semantic_label", "caption", "alt_text", "source_contract",
            "source_sha256", "producer", "validator", "compositor", "scope",
            "animation", "fallback", "contact_sheet", "frames",
        }
        if set(record) != required:
            fail(errors, NARRATIVE_MANIFEST, f"animations.{name} is not closed")
            continue
        expected_scope = {
            "complete": True,
            "selected": name in SELECTED_ANIMATIONS,
            "truncated": False,
        }
        if record.get("scope") != expected_scope:
            fail(errors, NARRATIVE_MANIFEST, f"animations.{name}.scope disagrees with policy")
        animation = _artifact(record.get("animation"), f"animations.{name}.animation", errors)
        contact = _artifact(record.get("contact_sheet"), f"animations.{name}.contact_sheet", errors)
        fallback = _artifact(record.get("fallback"), f"animations.{name}.fallback", errors)
        raw_frames = record.get("frames")
        if type(raw_frames) is not list or not raw_frames:
            fail(errors, NARRATIVE_MANIFEST, f"animations.{name}.frames must be nonempty")
            raw_frames = []
        frames = [
            value
            for index, item in enumerate(raw_frames)
            if (value := _artifact(item, f"animations.{name}.frames[{index}]", errors))
        ]
        frame_paths = {path for path, _ in frames}
        animation_frames[name] = tuple(path for path, _ in frames)
        if fallback and fallback[0] not in frame_paths:
            fail(errors, NARRATIVE_MANIFEST, f"animations.{name}.fallback is not a frame")
        primary = [value for value in (animation, contact, *frames) if value]
        record_paths = [path for path, _ in primary]
        if len(record_paths) != len(set(record_paths)):
            fail(errors, NARRATIVE_MANIFEST, f"animations.{name} reuses an artifact path")
        for relative, digest in primary:
            if relative in owned_files:
                fail(errors, NARRATIVE_MANIFEST, f"artifact {relative!r} has multiple owners")
            if digest in owned_digests and owned_digests[digest] != relative:
                fail(
                    errors,
                    NARRATIVE_MANIFEST,
                    f"artifact {relative!r} duplicates bytes from {owned_digests[digest]!r}",
                )
            owned_files.add(relative)
            owned_digests[digest] = relative
        if animation and fallback and contact:
            _require_owner_copy(
                name,
                record,
                "narrative-animation.html",
                {
                    "animation": f"/assets/narrative/{animation[0]}",
                    "fallback": f"/assets/narrative/{fallback[0]}",
                    "contact_sheet": f"/assets/narrative/{contact[0]}",
                },
                documents,
                includes,
                errors,
            )
        assets_by_owner[str(record["owner"])].add(name)

    milestones = manifest.get("pdf_milestones")
    milestone_names = {
        "selector",
        "region_construction",
        "reference_trace",
        "optimized_trace",
        "end_to_end",
    }
    if type(milestones) is not dict or set(milestones) != milestone_names:
        fail(errors, NARRATIVE_MANIFEST, "pdf_milestones set is not closed")
    else:
        if milestones["selector"] != "semantic-milestones-v1":
            fail(errors, NARRATIVE_MANIFEST, "pdf_milestones.selector is unsupported")
        expected_milestones = {
            "region_construction": animation_frames.get("region_construction", ()),
            "reference_trace": animation_frames.get("reference_trace", ()),
            "optimized_trace": animation_frames.get("optimized_trace", ()),
            "end_to_end": animation_frames.get("pipeline_overview", ()),
        }
        for name, expected in expected_milestones.items():
            value = milestones[name]
            if type(value) is not list or any(
                type(path) is not str
                or not ASSET_PATH.fullmatch(path)
                or not path.endswith(".png")
                for path in value
            ):
                fail(errors, NARRATIVE_MANIFEST, f"pdf_milestones.{name} has invalid paths")
            elif tuple(value) != expected:
                fail(
                    errors,
                    NARRATIVE_MANIFEST,
                    f"pdf_milestones.{name} disagrees with shared frame order",
                )

    for name, policy in STATIC_POLICY.items():
        raw = statics.get(name)
        if name == "presentation_status":
            if raw is not None:
                fail(errors, NARRATIVE_MANIFEST, "SAT presentation_status must be null")
            continue
        record = _metadata(raw, f"statics.{name}", policy, errors)
        if record is None:
            continue
        required = {
            "owner", "semantic_label", "caption", "alt_text", "source_contract",
            "source_sha256", "producer", "validator", "compositor", "artifact",
        }
        if set(record) != required:
            fail(errors, NARRATIVE_MANIFEST, f"statics.{name} is not closed")
            continue
        artifact = _artifact(record.get("artifact"), f"statics.{name}.artifact", errors)
        if artifact:
            relative, digest = artifact
            if relative in owned_files:
                fail(errors, NARRATIVE_MANIFEST, f"artifact {relative!r} has multiple owners")
            if digest in owned_digests and owned_digests[digest] != relative:
                fail(
                    errors,
                    NARRATIVE_MANIFEST,
                    f"artifact {relative!r} duplicates bytes from {owned_digests[digest]!r}",
                )
            owned_files.add(relative)
            owned_digests[digest] = relative
            _require_owner_copy(
                name,
                record,
                "narrative-static.html",
                {"image": f"/assets/narrative/{relative}"},
                documents,
                includes,
                errors,
            )
        assets_by_owner[str(record["owner"])].add(name)

    expected_include_ids = set(ANIMATION_POLICY) | (
        set(STATIC_POLICY) - {"presentation_status"}
    )
    if set(includes) != expected_include_ids:
        fail(
            errors,
            DOCS,
            "narrative include asset_id set disagrees with Pages policy",
        )

    actual_files = {
        path.relative_to(NARRATIVE_ROOT).as_posix()
        for path in NARRATIVE_ROOT.rglob("*")
        if path.is_file() and path != NARRATIVE_MANIFEST
    }
    if actual_files != owned_files:
        missing = sorted(owned_files - actual_files)
        orphaned = sorted(actual_files - owned_files)
        fail(
            errors,
            NARRATIVE_ROOT,
            f"bundle inventory mismatch; missing={missing!r}, orphaned={orphaned!r}",
        )

    for route, document in documents.items():
        declared = {
            item.strip()
            for item in document.metadata.get("owned_assets", "").split(",")
            if item.strip()
        }
        expected = assets_by_owner.get(route, set())
        if declared != expected:
            fail(
                errors,
                document.path,
                f"owned_assets {sorted(declared)!r}, expected {sorted(expected)!r}",
            )
    return len(ANIMATION_POLICY), len(STATIC_POLICY) - 1


def check_public_image_inventory(images: Path, errors: list[str]) -> None:
    actual = {
        path.relative_to(images).as_posix()
        for path in images.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(actual - ALLOWED_PUBLIC_IMAGES)
    if unexpected:
        fail(
            errors,
            images,
            f"unexpected public image assets: {', '.join(unexpected)}",
        )


def check_site_structure(documents: dict[str, Document], errors: list[str]) -> None:
    config = (DOCS / "_config.yml").read_text(encoding="utf-8")
    for excluded in ("post-template.md", "plans"):
        if not re.search(rf"^\s*-\s+{re.escape(excluded)}\s*$", config, re.MULTILINE):
            fail(errors, DOCS / "_config.yml", f"{excluded!r} is not excluded")
    for include in ("narrative-animation.html", "narrative-static.html"):
        if not (DOCS / "_includes" / include).is_file():
            fail(errors, DOCS / "_includes" / include, "required narrative include is missing")
    css = (DOCS / "assets/css/site.css").read_text(encoding="utf-8")
    if css.count("{") != css.count("}"):
        fail(errors, DOCS / "assets/css/site.css", "unbalanced braces")
    for name in LEGACY_ASSET_DIRECTORIES:
        path = DOCS / "assets/images" / name
        if path.exists():
            fail(errors, path, "legacy narrative bundle must be removed after migration")
    check_public_image_inventory(DOCS / "assets/images", errors)
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [*DOCS.rglob("*.md"), *DOCS.rglob("*.html")]
        if "plans" not in path.relative_to(DOCS).parts
    )
    for name in LEGACY_ASSET_DIRECTORIES:
        if f"/assets/images/{name}/" in public_text:
            fail(errors, DOCS, f"legacy asset path remains referenced: {name}")
    for route in ("/", "/pipeline/"):
        source = documents.get(route).body if route in documents else ""
        for component_route in COMPONENTS:
            literal = f"'{component_route}' | relative_url"
            if literal not in source:
                fail(
                    errors,
                    DOCS,
                    f"{route} does not link complete component route {component_route}",
                )
    for route, targets in FROZEN_CROSS_LINKS.items():
        source = documents.get(route).body if route in documents else ""
        for target in targets:
            literal = f"'{target}' | relative_url"
            if literal not in source:
                fail(
                    errors,
                    DOCS,
                    f"{route} does not link frozen route {target}",
                )


def main() -> int:
    errors: list[str] = []
    documents = check_catalog(errors)
    check_liquid_links(documents, errors)
    animations, statics = check_narrative_assets(documents, errors)
    check_site_structure(documents, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    counts = Counter(document.metadata["page_class"] for document in documents.values())
    print(
        "Pages checks passed: "
        f"{len(documents)} routes "
        f"({counts['story']} story, {counts['reference']} reference, "
        f"{counts['evidence']} evidence, {counts['history']} history), "
        f"{animations} animations and {statics} static narrative assets."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
