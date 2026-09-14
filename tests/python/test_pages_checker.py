from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_pages  # noqa: E402


def _documents() -> dict[str, check_pages.Document]:
    errors: list[str] = []
    documents = check_pages.check_catalog(errors)
    if errors:
        raise AssertionError("\n".join(errors))
    return documents


class PagesCheckerTests(unittest.TestCase):
    def test_repository_source_and_manifest_pass(self) -> None:
        errors: list[str] = []
        documents = check_pages.check_catalog(errors)
        check_pages.check_liquid_links(documents, errors)
        animations, statics = check_pages.check_narrative_assets(documents, errors)
        check_pages.check_site_structure(documents, errors)
        self.assertEqual(errors, [])
        self.assertEqual((animations, statics), (9, 8))

    def test_presentazione_is_additive_and_reuse_is_bound(self) -> None:
        documents = _documents()
        self.assertEqual(len(documents), 41)
        self.assertEqual(len(set(documents) - {"/presentazione/"}), 40)
        tour = documents["/presentazione/"]
        for old, new, diagnostic in (
            ('source="wang-explain-manifest-v3"', 'source="wrong"', "'source'"),
            ('label="observed"', 'label="didactic"', "'label'"),
            ('reference-trace/frame-002517.png', 'reference-trace/frame-002516.png', "'image'"),
        ):
            with self.subTest(diagnostic=diagnostic):
                changed = dict(documents)
                changed["/presentazione/"] = check_pages.Document(
                    tour.path, tour.metadata, tour.body.replace(old, new)
                )
                errors: list[str] = []
                check_pages.check_narrative_assets(changed, errors)
                self.assertIn(f"Presentazione MRV {diagnostic} disagrees", "\n".join(errors))

    def test_construction_preview_preserves_source_and_semantic_label(self) -> None:
        documents = _documents()
        tour = documents["/presentazione/"]
        for old, new in (
            ("region-construction/frame-04.png", "reference-trace/frame-000001.png"),
            ('label="canonical-construction"', 'label="observed"'),
        ):
            with self.subTest(replacement=new):
                changed = dict(documents)
                changed["/presentazione/"] = check_pages.Document(
                    tour.path, tour.metadata, tour.body.replace(old, new)
                )
                errors = []
                check_pages.check_narrative_assets(changed, errors)
                self.assertIn("construction preview differs", "\n".join(errors))

    def test_presentazione_cannot_replace_or_move_the_owner(self) -> None:
        documents = _documents()
        owner = documents["/components/reference-solver/"]
        documents["/components/reference-solver/"] = check_pages.Document(
            owner.path, owner.metadata, check_pages.NARRATIVE_INCLUDE.sub("", owner.body)
        )
        errors: list[str] = []
        check_pages.check_narrative_assets(documents, errors)
        self.assertIn("owned asset 'reference_trace' has no include", "\n".join(errors))

        documents = _documents()
        tour = documents["/presentazione/"]
        include = next(match.group(0) for match in check_pages.NARRATIVE_INCLUDE.finditer(tour.body)
                       if 'asset_id="presentazione_mrv"' in match.group(0))
        documents["/presentazione/"] = check_pages.Document(
            tour.path, tour.metadata, tour.body.replace(include, "")
        )
        owner = documents["/components/reference-solver/"]
        documents["/components/reference-solver/"] = check_pages.Document(
            owner.path, owner.metadata, owner.body + include
        )
        errors = []
        check_pages.check_narrative_assets(documents, errors)
        self.assertIn("must be a static on /presentazione/", "\n".join(errors))

    def test_artifact_rejects_unknown_extension_and_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "asset.png"
            payload.write_bytes(b"not the declared bytes")
            errors: list[str] = []
            with (
                mock.patch.object(check_pages, "NARRATIVE_ROOT", root),
                mock.patch.object(check_pages, "NARRATIVE_MANIFEST", root / "manifest.json"),
            ):
                check_pages._artifact(
                    {
                        "path": "asset.webp",
                        "sha256": hashlib.sha256(b"asset").hexdigest(),
                        "media_type": "image/png",
                    },
                    "test.extension",
                    errors,
                )
                check_pages._artifact(
                    {
                        "path": "asset.png",
                        "sha256": hashlib.sha256(b"different").hexdigest(),
                        "media_type": "image/png",
                    },
                    "test.hash",
                    errors,
                )
        joined = "\n".join(errors)
        self.assertIn("must end in .png or .gif", joined)
        self.assertIn("disagrees with manifest", joined)

    def test_search_unsat_excerpt_rejects_changed_source_or_render(self) -> None:
        documents = _documents()
        manifest = check_pages._load_manifest([])
        trace_name = next(check_pages.SEARCH_UNSAT_ROOT.glob("trace-*.json")).name
        for filename, diagnostic in (
            ("reference-manifest.json", "pinned search-UNSAT capture"),
            (trace_name, "does not match"),
            ("frame-004121.png", "pinned search-UNSAT render"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "search-unsat"
                shutil.copytree(check_pages.SEARCH_UNSAT_ROOT, copied)
                (copied / filename).write_bytes(b"changed source or render")
                errors = []
                includes = check_pages._parse_narrative_includes(documents, errors)
                with mock.patch.object(check_pages, "SEARCH_UNSAT_ROOT", copied):
                    check_pages._check_presentazione_excerpts(
                        includes, manifest["animations"]["reference_trace"], errors
                    )
                self.assertIn(diagnostic, "\n".join(errors))

    def test_search_unsat_excerpt_cannot_silently_use_a_sat_frame(self) -> None:
        documents = _documents()
        tour = documents["/presentazione/"]
        documents["/presentazione/"] = check_pages.Document(
            tour.path, tour.metadata, tour.body.replace(
                "/assets/presentazione/search-unsat/frame-004121.png",
                "/assets/narrative/reference-trace/frame-002517.png",
            )
        )
        errors = []
        check_pages.check_narrative_assets(documents, errors)
        self.assertIn("presentazione_branch_rollback 'image' disagrees", "\n".join(errors))

    def test_manifest_closes_identity_and_pdf_milestone_structure(self) -> None:
        documents = _documents()
        manifest = check_pages._load_manifest([])
        self.assertIsNotNone(manifest)

        invalid_identity = deepcopy(manifest)
        invalid_identity["identities"]["tileset"] = "not-a-digest"
        errors: list[str] = []
        with mock.patch.object(check_pages, "_load_manifest", return_value=invalid_identity):
            check_pages.check_narrative_assets(documents, errors)
        self.assertIn("identities.tileset is not a SHA-256", "\n".join(errors))

        invalid_milestone = deepcopy(manifest)
        invalid_milestone["pdf_milestones"]["reference_trace"] = ["../escape.png"]
        errors = []
        with mock.patch.object(check_pages, "_load_manifest", return_value=invalid_milestone):
            check_pages.check_narrative_assets(documents, errors)
        self.assertIn("pdf_milestones.reference_trace has invalid paths", "\n".join(errors))

    def test_incomplete_asset_records_report_controlled_diagnostics(self) -> None:
        documents = _documents()
        manifest = check_pages._load_manifest([])
        self.assertIsNotNone(manifest)

        for collection, name in (
            ("animations", "boolean_z3"),
            ("statics", "home_preview"),
        ):
            with self.subTest(collection=collection, name=name):
                invalid = deepcopy(manifest)
                del invalid[collection][name]["owner"]
                errors: list[str] = []
                with mock.patch.object(check_pages, "_load_manifest", return_value=invalid):
                    check_pages.check_narrative_assets(documents, errors)
                self.assertIn(
                    f"{collection}.{name} is not closed",
                    "\n".join(errors),
                )

    def test_public_image_inventory_rejects_an_unowned_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory)
            (images / "tile-mark.svg").write_text("<svg/>\n", encoding="utf-8")
            (images / "orphan.svg").write_text("<svg/>\n", encoding="utf-8")
            errors: list[str] = []

            check_pages.check_public_image_inventory(images, errors)

        self.assertIn(
            "unexpected public image assets: orphan.svg",
            "\n".join(errors),
        )

    def test_primary_asset_must_be_in_primary_animation_section(self) -> None:
        original = check_pages.split_front_matter
        target = check_pages.DOCS / "components/boolean-z3.md"

        def without_primary(path: Path, errors: list[str]) -> tuple[dict[str, str], str]:
            metadata, body = original(path, errors)
            if path == target:
                body = body.replace("boolean_z3", "other")
            return metadata, body

        errors: list[str] = []
        with mock.patch.object(check_pages, "split_front_matter", side_effect=without_primary):
            check_pages.check_catalog(errors)
        self.assertIn(
            "primary asset 'boolean_z3' must use a narrative include in the Primary animation section",
            "\n".join(errors),
        )

    def test_primary_asset_include_must_be_in_primary_animation_section(self) -> None:
        original = check_pages.split_front_matter
        target = check_pages.DOCS / "components/boolean-z3.md"

        def moved_include(path: Path, errors: list[str]) -> tuple[dict[str, str], str]:
            metadata, body = original(path, errors)
            if path == target:
                include = next(check_pages.NARRATIVE_INCLUDE.finditer(body)).group(0)
                body = body.replace(include, "", 1)
                body = body.replace(
                    "## Mechanism\n",
                    f"## Mechanism\n\n{include}\n",
                    1,
                )
            return metadata, body

        errors: list[str] = []
        with mock.patch.object(check_pages, "split_front_matter", side_effect=moved_include):
            check_pages.check_catalog(errors)
        self.assertIn(
            "primary asset 'boolean_z3' must use a narrative include in the Primary animation section",
            "\n".join(errors),
        )

    def test_animation_include_roles_are_bound_to_the_manifest_record(self) -> None:
        original = check_pages.split_front_matter
        target = check_pages.DOCS / "components/boolean-z3.md"

        def swapped_roles(path: Path, errors: list[str]) -> tuple[dict[str, str], str]:
            metadata, body = original(path, errors)
            if path == target:
                body = body.replace(
                    'animation="/assets/narrative/boolean-z3/trace.gif" '
                    'fallback="/assets/narrative/boolean-z3/frame-03.png" '
                    'contact_sheet="/assets/narrative/boolean-z3/contact-sheet.png"',
                    'animation="/assets/narrative/boolean-z3/contact-sheet.png" '
                    'fallback="/assets/narrative/boolean-z3/frame-03.png" '
                    'contact_sheet="/assets/narrative/boolean-z3/trace.gif"',
                )
            return metadata, body

        errors: list[str] = []
        with mock.patch.object(
            check_pages, "split_front_matter", side_effect=swapped_roles
        ):
            documents = check_pages.check_catalog(errors)
            check_pages.check_narrative_assets(documents, errors)

        joined = "\n".join(errors)
        self.assertIn("include argument 'animation'", joined)
        self.assertIn("include argument 'contact_sheet'", joined)

    def test_animation_include_metadata_is_bound_to_the_manifest_record(self) -> None:
        original = check_pages.split_front_matter
        target = check_pages.DOCS / "components/reference-solver.md"

        def wrong_label(path: Path, errors: list[str]) -> tuple[dict[str, str], str]:
            metadata, body = original(path, errors)
            if path == target:
                body = body.replace(
                    'label="observed" caption=',
                    'label="didactic" caption=',
                )
            return metadata, body

        errors: list[str] = []
        with mock.patch.object(
            check_pages, "split_front_matter", side_effect=wrong_label
        ):
            documents = check_pages.check_catalog(errors)
            check_pages.check_narrative_assets(documents, errors)

        self.assertIn("include argument 'label'", "\n".join(errors))

    def test_frozen_cross_links_must_use_relative_url(self) -> None:
        documents = _documents()
        worked = documents["/worked-example/"]
        documents["/worked-example/"] = check_pages.Document(
            worked.path,
            worked.metadata,
            worked.body.replace("'/components/boolean-z3/' | relative_url", "'/missing/' | relative_url"),
        )
        errors: list[str] = []

        check_pages.check_site_structure(documents, errors)

        self.assertIn(
            "/worked-example/ does not link frozen route /components/boolean-z3/",
            "\n".join(errors),
        )


if __name__ == "__main__":
    unittest.main()
