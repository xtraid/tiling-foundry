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

All files tracked by that commit are present. Production code, tests, assets,
lockfile, project metadata, and license are byte-for-byte unchanged. The sole
documentary correction to the imported snapshot is in `README.md`: its stale
test totals said 135, while collection at the pinned commit yields 144 tests.
The overall and affected section totals now say 144, 18 Palette, 33
SceneParser, and 49 Blitter tests. This `UPSTREAM.md` file is local provenance,
not an upstream file.

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

The import baseline is 144 collected tests and 144 passing tests. Keep the
renderer environment under `renderer/.venv`; its local `.gitignore` excludes
that environment and generated Python/build files.

The preserved `renderer/.github/workflows/ci.yml` is nested upstream evidence;
GitHub does not run it as a workflow of the containing repository. Adding a
separate top-level renderer CI job is deliberately outside this snapshot-only
import.

## Updating the snapshot

Treat an update as a separate reviewed change:

1. Resolve and record the exact upstream commit before copying files.
2. Inspect its default branch, license, dependency metadata, repository
   instructions, tracked files, and collected test count.
3. Run its locked suite in a temporary clone before changing this directory.
4. Replace the snapshot from `git archive` so no upstream `.git` directory is
   copied. Preserve this provenance file and document every local difference.
5. Re-run the renderer suite and the Tiling Foundry repository gates, then
   inspect the complete diff, secrets, and generated artifacts.

Do not pull or merge an upstream branch directly into this repository. Do not
move Pillow, NumPy, pytest, or renderer code into the root Python project.

## Rollback

Before integration, the feature branch is the rollback boundary. After the
import is integrated, revert the complete import commit with `git revert`;
after a later snapshot update, revert that update commit. This keeps rollback
reviewable and preserves the upstream provenance history.
