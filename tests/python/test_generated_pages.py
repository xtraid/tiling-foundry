from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from check_generated_pages import (  # noqa: E402
    COMPONENT_HEADINGS,
    COMPONENTS,
    EXPECTED_ROUTE_CLASSES,
    EXPECTED_ROUTES,
    check_site,
)


SITE_URL = "https://xtraid.github.io"
BASEURL = "/tiling-foundry"


def _html(
    route: str,
    title: str,
    body: str,
    *,
    page_class: str,
    kind: str = "page",
    component_id: str = "",
) -> str:
    return f"""<!doctype html><html lang="en"><head>
<title>{title}</title>
<meta name="description" content="Description for this page.">
<link rel="canonical" href="{SITE_URL}{BASEURL}{route}">
<link rel="stylesheet" href="{BASEURL}/assets/site.css">
</head><body data-page-kind="{kind}" data-page-class="{page_class}"
data-component-id="{component_id}">
<a href="#main-content">Skip</a><main id="main-content">{body}</main>
<script src="{BASEURL}/assets/main.js"></script></body></html>"""


def _write(root: Path, route: str, html: str) -> Path:
    path = root / "index.html" if route == "/" else root / route[1:] / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def _valid_site(root: Path) -> None:
    (root / "assets").mkdir()
    (root / "assets/site.css").write_text("body {}\n", encoding="utf-8")
    (root / "assets/main.js").write_text("export {};\n", encoding="utf-8")
    home_body = f"""<section class="layout-reading home-section"><h1>Tiling Foundry</h1>
<section id="project-map"></section><section id="reading-path"></section></section>
<section class="layout-presentation home-section" id="verified-output"></section>
<a href="{BASEURL}/development_principles/#principles">Principles</a>"""
    _write(
        root,
        "/",
        _html(
            "/",
            "Tiling Foundry",
            home_body,
            page_class="story",
            kind="home",
        ),
    )
    for route in sorted(EXPECTED_ROUTES - {"/"}):
        label = route.strip("/").replace("-", " ").replace("_", " ").title()
        component_id = COMPONENTS[route][0] if route in COMPONENTS else ""
        headings = "".join(f"<h2>{heading}</h2>" for heading in COMPONENT_HEADINGS)
        body = f'<h1 id="principles">{label}</h1>{headings}<a href="{BASEURL}/">Home</a>'
        _write(
            root,
            route,
            _html(
                route,
                f"{label} · Tiling Foundry",
                body,
                page_class=EXPECTED_ROUTE_CLASSES[route],
                component_id=component_id,
            ),
        )


def _contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class GeneratedPagesTests(unittest.TestCase):
    def test_accepts_all_routes_and_resolved_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.page_count, 40)

    def test_rejects_the_known_home_regression_and_broken_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            home = root / "index.html"
            html = home.read_text(encoding="utf-8")
            html = html.replace("<h1>Tiling Foundry</h1>", "<p># Tiling Foundry</p>")
            html = html.replace(
                "<title>Tiling Foundry</title>",
                "<title>Tiling Foundry · Tiling Foundry</title>",
            )
            html = html.replace(
                "</main>",
                f'<a href="{BASEURL}/missing/">Missing</a></main>',
            )
            home.write_text(html, encoding="utf-8")
            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
        errors = "\n".join(result.errors)
        self.assertIn("expected one non-empty H1", errors)
        self.assertIn("unexpected home title", errors)
        self.assertIn("unresolved href target", errors)

    def test_checks_generated_animation_fallback_contact_sheet_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            route = "/components/boolean-z3/"
            page = root / route.strip("/") / "index.html"
            html = page.read_text(encoding="utf-8")
            figure = f"""<figure><picture>
<source media="(prefers-reduced-motion: reduce)"
srcset="{BASEURL}/assets/narrative/boolean-z3/fallback.png">
<img src="{BASEURL}/assets/narrative/boolean-z3/animation.gif"
alt="A complete explanation." width="940" height="430">
</picture><figcaption>Caption.
<a href="{BASEURL}/assets/narrative/boolean-z3/contact-sheet.png">Contact sheet</a>
</figcaption></figure>"""
            page.write_text(html.replace("</main>", f"{figure}</main>"), encoding="utf-8")
            narrative = root / "assets/narrative/boolean-z3"
            narrative.mkdir(parents=True)
            for name in ("fallback.png", "animation.gif", "contact-sheet.png"):
                (narrative / name).write_bytes(b"asset")
            good = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
            self.assertEqual(good.errors, ())

            broken = page.read_text(encoding="utf-8")
            broken = broken.replace(' width="940" height="430"', "")
            broken = broken.replace("contact-sheet.png", "frames.png")
            page.write_text(broken, encoding="utf-8")
            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
        errors = "\n".join(result.errors)
        self.assertIn("lacks positive intrinsic dimensions", errors)
        self.assertIn("requires one contact-sheet link", errors)

    def test_rejects_narrative_animation_with_swapped_asset_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            route = "/components/boolean-z3/"
            page = root / route.strip("/") / "index.html"
            html = page.read_text(encoding="utf-8")
            figure = f"""<figure class="narrative-asset narrative-animation"
data-asset-id="boolean_z3"><picture>
<source media="(prefers-reduced-motion: reduce)"
srcset="{BASEURL}/assets/narrative/boolean-z3/fallback.png">
<img src="{BASEURL}/assets/narrative/boolean-z3/contact-sheet.png"
alt="A complete explanation." width="940" height="430">
</picture><figcaption>Caption.
<a href="{BASEURL}/assets/narrative/boolean-z3/animation.gif">Animation</a>
</figcaption></figure>"""
            page.write_text(html.replace("</main>", f"{figure}</main>"), encoding="utf-8")
            narrative = root / "assets/narrative/boolean-z3"
            narrative.mkdir(parents=True)
            for name in ("fallback.png", "animation.gif", "contact-sheet.png"):
                (narrative / name).write_bytes(b"asset")

            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)

        errors = "\n".join(result.errors)
        self.assertIn("must contain exactly one GIF", errors)
        self.assertIn("requires one contact-sheet link", errors)

    def test_rejects_missing_component_heading_and_body_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            page = root / "components/tileset/index.html"
            html = page.read_text(encoding="utf-8")
            html = html.replace("<h2>Trust boundary</h2>", "")
            html = html.replace('data-component-id="tileset"', 'data-component-id="other"')
            page.write_text(html, encoding="utf-8")
            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
        errors = "\n".join(result.errors)
        self.assertIn("expected component id", errors)
        self.assertIn("component H2 sequence", errors)

    def test_faint_and_comment_text_meet_normal_text_contrast(self) -> None:
        css = (ROOT / "docs/assets/css/site.css").read_text(encoding="utf-8")
        root_block = re.search(r":root\s*\{(.*?)\n\}", css, re.DOTALL)
        self.assertIsNotNone(root_block)
        colors = dict(
            re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6});", root_block.group(1))
        )
        comment = re.search(r"\.highlight \.cm \{ color: (#[0-9a-fA-F]{6}); \}", css)
        self.assertIsNotNone(comment)
        self.assertGreaterEqual(_contrast(colors["faint"], colors["black"]), 4.5)
        self.assertGreaterEqual(_contrast(comment.group(1), colors["black-raised"]), 4.5)


if __name__ == "__main__":
    unittest.main()
