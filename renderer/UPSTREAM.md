# PAP Render upstream snapshot

The renderer directory vendors one snapshot of the standalone PAP Render
project. It is intentionally isolated from the Tiling Foundry core and does
not contain a nested Git repository.

## Provenance

- Upstream: <https://github.com/xtraid/PAP_render>
- Default branch at import: `main`
- Commit: `3eba839fb0bb80a533415eb7c1c793a9edf1a1e1`
- Commit date: 2026-07-01
- License: MIT; the upstream license is preserved in `LICENSE`
- Import date: 2026-08-25

All files tracked by that commit are present. The imported production code,
tests, assets, lockfile, project metadata, and license remain byte-for-byte
unchanged. At import, the sole documentary correction was in `README.md`: its
stale test totals said 135, while collection at the pinned commit yields 144
tests. The overall and affected section totals now say 144, 18 Palette, 33
SceneParser, and 49 Blitter tests. This `UPSTREAM.md` file is local provenance,
not an upstream file.

Tiling Foundry later added its isolated Wang modules, tests, and goldens under
`test_data/`, plus clearly separated usage notes in `README.md`. The default
and explainable solution paths consume `wang-solution-v1`; the static formula,
tile-sheet, unassigned-region, and native reduction-provenance views consume
hash-bound explainability manifests. These additions do not modify or import
the legacy PAP modules. They also leave `pyproject.toml`, `uv.lock`, and the
pinned dependencies unchanged.

## Verification

The isolated upstream project requires Python 3.14 or newer. Its committed
`.python-version` selects Python 3.14, and the import verification used CPython
3.14.6. `pyproject.toml` declares NumPy, Pillow, and pytest; `uv.lock` resolves
them to NumPy 2.4.6, Pillow 12.2.0, and pytest 9.0.3 for this environment.

From `renderer/`, reproduce the locked Python 3.14 environment and run:

```sh
uv run --locked pytest --collect-only -q
uv run --locked pytest -q
```

The import baseline remains 144 collected tests and 144 passing tests. The
combined local suite is 238 tests: 144 preserved legacy tests, 45 Wang square
tests, 24 square-to-hex/hex-raster tests, and 25 static
snapshot/explainability tests. Keep the renderer environment under
`renderer/.venv`; its local `.gitignore` excludes that environment and
generated Python/build files.

The preserved `renderer/.github/workflows/ci.yml` is nested upstream evidence;
GitHub does not run it as a workflow of the containing repository. The
top-level `.github/workflows/ci.yml` instead runs the same locked suite in a
separate read-only Python 3.14 job.

## Updating the snapshot

Treat an update as a separate reviewed change:

1. Resolve and record the exact upstream commit before copying files.
2. Inspect its default branch, license, dependency metadata, repository
   instructions, tracked files, and collected test count.
3. Run its locked suite in a temporary clone before changing this directory.
4. Replace the snapshot from `git archive` so no upstream `.git` directory is
   copied. Preserve this provenance file and reapply or consciously revise the
   separately identified Wang files and README sections.
5. Re-run the renderer suite and the Tiling Foundry repository gates, then
   inspect the complete diff, secrets, and generated artifacts.

Do not pull or merge an upstream branch directly into this repository. Do not
move Pillow, NumPy, pytest, or renderer code into the root Python project.

## Rollback

Before integration, the feature branch is the rollback boundary. After the
import is integrated, revert the complete import commit with `git revert`;
after a later snapshot update, revert that update commit. This keeps rollback
reviewable and preserves the upstream provenance history.
