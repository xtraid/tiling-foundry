# T97 Pages Narrative Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the already-implemented T97 Pages narrative refactor with an
independent review, fresh reproducible evidence, an accurate migration
checklist, and a pull request against `main`.

**Architecture:** Preserve the two existing implementation commits and audit
their complete `origin/main...HEAD` change as one coherent migration. Make only
review-driven corrections, keep authored Markdown and the small Jekyll
layout/include layer independent from dossier generation, and validate the
same source and generated-site contracts that CI runs.

**Tech Stack:** Markdown, Jekyll/GitHub Pages, Liquid, Python 3.13 `unittest`,
the repository Makefile, `uv`, GCC/Clang, Docker using the pinned local
`ghcr.io/actions/jekyll-build-pages:v1.0.13` image, and GitHub CLI.

**Spec:** `docs/plans/2026-08-31-narrative-architecture-contract.md`

## Global Constraints

- Preserve all 27 legacy technical permalinks and the frozen T97 sitemap.
- Every component page keeps the nine frozen H2 sections in order.
- Every narrative animation has exactly one owner, one allowed semantic label,
  nonempty alt text, a caption, a reduced-motion PNG, and a contact sheet.
- Pages prose remains authored Markdown; neither `run.json` nor a dossier may
  generate prose, navigation, or sitemap content.
- The Pages build must not invoke native solving, the renderer, dossier
  generation, PDF/LaTeX, or network access.
- `pipeline_sat.cm13` remains the sole SAT narrative instance;
  `unsat-search` remains visibly and cryptographically separate.
- Existing v1 dossier contracts, core models, algorithms, ABI, and ownership
  remain unchanged.
- T98 PDF-v2 implementation and its checklist gates are outside this plan.
- Any behavioral correction follows red-green-refactor; documentation-only
  evidence updates do not require synthetic tests.
- Do not commit generated Pages output, caches, screenshots, or review scratch
  files.

---

### Task 1: Audit and remediate the existing T97 migration

**Files:**

- Review: `docs/_includes/`, `docs/_layouts/`, `docs/assets/css/site.css`
- Review: `docs/index.md`, `docs/pipeline.md`, `docs/worked-example.md`
- Review: `docs/components/*.md`, `docs/reference.md`, `docs/evidence.md`,
  `docs/run_dossiers.md`
- Review: `docs/assets/narrative/manifest.json` and tracked narrative assets
- Review: `tools/check_pages.py`, `tools/check_generated_pages.py`
- Test: `tests/python/test_pages_checker.py`
- Test: `tests/python/test_generated_pages.py`
- Test: `tests/python/test_multi_engine_dossier.py`
- Test: affected `renderer/test_wang_*.py` files
- Modify only when evidence requires it: the files above and
  `docs/plans/2026-08-31-narrative-migration-checklist.md`

**Interfaces:**

- Consumes: the frozen narrative contract, the `wang-narrative-assets-v1`
  manifest, the existing two T97 commits, and the 27 legacy routes.
- Produces: a reviewed source tree whose source checker and focused unit tests
  enforce the frozen taxonomy, ownership, accessibility, identity, and link
  contracts.

- [ ] **Step 1: Review the complete branch diff against the frozen contract**

  Inspect `git diff --find-renames origin/main...HEAD` and record every
  Critical, Important, and Minor finding with a file and line. Pay particular
  attention to route compatibility, asset deletion/rename safety, unique
  ownership, semantic labels, SAT/UNSAT separation, literal Liquid links, and
  accidental Pages dependencies on dossier or renderer output.

- [ ] **Step 2: Reproduce each behavioral finding with a focused failing test**

  Add the smallest real-behavior test to
  `tests/python/test_pages_checker.py` or
  `tests/python/test_generated_pages.py`. Run it directly with:

  ```bash
  PYTHONPATH="$PWD/python" uv run --frozen python -m unittest \
    tests.python.test_pages_checker tests.python.test_generated_pages
  ```

  The new test must fail for the identified defect, not for fixture setup or a
  source-text assertion. If the review is clean, do not invent a test or code
  change.

- [ ] **Step 3: Apply the minimal corrections and prove focused green**

  Change only the file responsible for each confirmed finding, then rerun:

  ```bash
  make pages-check
  PYTHONPATH="$PWD/python" uv run --frozen python -m unittest \
    tests.python.test_pages_checker tests.python.test_generated_pages
  ```

  Expected: the source checker reports 40 routes with the frozen class counts,
  and all focused tests pass with no warnings.

- [ ] **Step 4: Commit review-driven corrections, if any**

  Stage only reviewed source/test files. Use a result-oriented subject and do
  not add co-author trailers. If the audit finds no defect, create no empty
  commit.

### Task 2: Rebuild, verify, and reconcile the T97 evidence

**Files:**

- Modify: `docs/plans/2026-08-31-narrative-migration-checklist.md`
- Verify: the complete repository tree
- Generate only outside Git: `/tmp/t97-pages-build-20260904/`

**Interfaces:**

- Consumes: the reviewed T97 source tree from Task 1 and the pinned GitHub
  Pages builder image already present on the host.
- Produces: fresh source, generated-site, browser, compiler, sanitizer,
  analyzer, dynamic-analysis, renderer, dossier-v1, and cleanliness evidence;
  an evidence-accurate checklist; and a PR-ready branch.

- [ ] **Step 1: Build Pages from a clean external destination without network**

  Create `/tmp/t97-pages-build-20260904`, mount the repository read-only, and
  mount that directory at `/github/workspace/build/pages`. Run the pinned
  image as uid/gid `1000:1000` with `--network none` and these exact inputs:
  `GITHUB_WORKSPACE=/github/workspace`, `INPUT_SOURCE=docs`,
  `INPUT_DESTINATION=build/pages`, `INPUT_VERBOSE=false`,
  `INPUT_FUTURE=false`, `GITHUB_REPOSITORY=xtraid/tiling-foundry`,
  `GITHUB_API_URL=https://api.github.com`, and `INPUT_BUILD_REVISION` equal to
  the reviewed HEAD SHA. Pass an empty `INPUT_TOKEN`.

  Expected: the container exits zero and writes only to the external build
  directory.

- [ ] **Step 2: Validate generated output and browser-visible structure**

  Run:

  ```bash
  python3 tools/check_generated_pages.py /tmp/t97-pages-build-20260904
  ```

  Expected: 40 HTML pages and all emitted `href`, `src`, and `srcset`
  references validate. Use the local Playwright image without network to
  inspect `/`, `/pipeline/`, `/worked-example/`, and all eight component
  routes at desktop and narrow widths; verify one H1, keyboard-reachable
  navigation and links, visible focus, meaningful image alternatives, static
  reduced-motion fallbacks, and no horizontal overflow.

- [ ] **Step 3: Run the full repository verification matrix**

  Run each command on the reviewed HEAD and retain its exit status in the task
  report:

  ```bash
  make check
  make strict-check CC=gcc
  make strict-check CC=clang
  make sanitizer-check
  make analyzer-check
  make valgrind-check
  make cachegrind-check
  make parser-fuzz-smoke
  make coverage
  make run-dossier-smoke
  cd renderer && uv run --locked pytest -q
  ```

  Expected: every mandatory command exits zero. Coverage remains informative;
  no host-specific timing threshold is introduced.

- [ ] **Step 4: Reconcile only T97 checklist items proven by fresh evidence**

  Mark the duplicate section-3 Pages-build item complete after Steps 1-2.
  Mark only the T97-owned portions of the final migration audit that the fresh
  checks prove. Leave every T98 PDF-v2, cross-phase identity, or otherwise
  unverified item open.

- [ ] **Step 5: Perform publication hygiene checks and commit the evidence**

  Run:

  ```bash
  git diff --check origin/main...HEAD
  git status --short --branch
  git diff --summary origin/main...HEAD
  git ls-files build .uv-cache .venv | sed -n '1,20p'
  ```

  Confirm no generated build, cache, screenshot, credential, private key, or
  unexpected executable mode is staged. Commit only the checklist and this
  plan if they changed, using a result-oriented subject without co-author
  trailers.

### Task 3: Independent final review and pull request

**Files:**

- Review: `origin/main...HEAD`
- Read: `.github/pull_request_template.md` when present
- Create externally: one GitHub pull request against `main`

**Interfaces:**

- Consumes: the reviewed commits and complete fresh verification report.
- Produces: a published `feature/pages-narrative-v1` branch and a PR whose
  description records scope, architecture boundaries, tests, and remaining
  T98 exclusions.

- [ ] **Step 1: Obtain an independent whole-branch review**

  Review `origin/main...HEAD` against this plan, the frozen contract, and the
  migration checklist. Resolve all Critical and Important findings with a
  focused test-first fix and scoped re-review before publication.

- [ ] **Step 2: Verify the exact tree to publish**

  Re-run `make pages-check`, the external generated-site checker,
  `git diff --check origin/main...HEAD`, and `git status --short --branch`.
  Confirm HEAD and the verification report refer to the same SHA.

- [ ] **Step 3: Push the feature branch and open the PR**

  Push `feature/pages-narrative-v1` to `origin` without force, then create one
  PR against `main`. Do not merge it. Preserve the worktree for CI feedback
  and report the PR URL.
