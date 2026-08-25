from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from check_generated_pages import REPRESENTATIVE_ROUTES, check_site  # noqa: E402


SITE_URL = "https://xtraid.github.io"
BASEURL = "/tiling-foundry"


def _html(route: str, title: str, body: str, kind: str = "page") -> str:
    return f"""<!doctype html><html lang="en"><head>
<title>{title}</title>
<meta name="description" content="Description for this page.">
<link rel="canonical" href="{SITE_URL}{BASEURL}{route}">
<link rel="stylesheet" href="{BASEURL}/assets/site.css">
</head><body data-page-kind="{kind}">
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
    body = f"""<section class="layout-reading"><h1>Tiling Foundry</h1>
<section id="reading-path"></section></section>
<section class="layout-presentation home-catalog-section" id="documentation"></section>
<section id="cross-engine-benchmarks"></section>
<a href="{BASEURL}/development_principles/#principles">Principles</a>"""
    _write(root, "/", _html("/", "Tiling Foundry", body, "home"))
    for route in REPRESENTATIVE_ROUTES[1:]:
        label = route.strip("/").replace("_", " ").title()
        body = f'<h1 id="principles">{label}</h1><a href="{BASEURL}/">Home</a>'
        _write(root, route, _html(route, f"{label} · Tiling Foundry", body))


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
    def test_accepts_semantic_pages_and_resolved_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _valid_site(root)
            result = check_site(root, site_url=SITE_URL, baseurl=BASEURL)
        self.assertEqual(result.errors, ())

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
