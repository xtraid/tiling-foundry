---
layout: story
title: Presentazione
permalink: /presentazione/
page_class: story
page_kind: presentazione
description: A compact technical tour through the construction, solver states, and independent checks.
---

# Presentazione

Use these concrete states and construction views when explaining how the
project works. The [pipeline]({{ '/pipeline/' | relative_url }}) remains the
complete component map; [Reference]({{ '/reference/' | relative_url }}) holds
the detailed specifications and implementation guides.

[Construction](#yangzhang-construction) → [native solver](#native-solver) →
[verification](#verification-dependencies) → [worked result](#one-solved-example).

## Yang–Zhang construction

**φ SAT ⇔ Rφ tileable with the fixed 23-tile set.** The construction below
belongs to the same small SAT instance used by the solver examples.

Read the colored spans from left to right: a **variable** chooses a Boolean
value; **forwarders** preserve it; **crossovers** reorder signals without
changing their values; each **clause** requires exactly one true occurrence.
The source and target rows show where each signal goes, not a chosen assignment.

{% include narrative-static.html asset_id="presentazione_construction" image="/assets/narrative/region-construction/frame-04.png" alt="Yang–Zhang construction for the canonical SAT instance: blue variable spans, green and purple forwarders, six orange crossover spans and three red clause spans; source and target rows show the reordered signals." width="1976" height="828" label="canonical-construction" caption="Follow the gadget spans across the real region and compare source with target signal order. The boundaries constrain a tiling; they do not display Boolean values chosen by a solver." source="wang-reduction-explanation-v1" %}

[Construction animation →]({{ '/components/yang-zhang/#primary-animation' | relative_url }}) ·
[Reduction statement and proof details →]({{ '/reduction_notes/' | relative_url }}).

## Native solver

[Domains](#domains-and-boundary) → [propagation](#propagation) →
[MRV and decision](#mrv-and-decision) → [conflict and rollback](#conflict-and-rollback) →
[verified SAT](#verified-sat).

### Domains and boundary

A domain is the set of tiles still permitted at an active cell. **DIDACTIC
notation** (these three cells are not an observed trace):

| State | Candidate tiles | Meaning |
| --- | --- | --- |
| Unresolved | `D(a) = {2,5,8}` | Three choices remain |
| Singleton | `D(b) = {4}` | One tile is fixed |
| Conflict | `D(c) = {}` | This active cell has no candidate |

Boundary restriction intersects each exposed cell's domain with the tiles
matching its prescribed boundary colors. The recorded root already contains
those restrictions; it does not show a before-boundary state. Inactive cells
are outside the problem: their zero masks are not conflicts.

### Propagation

In the canonical SAT capture, cell 0 supports east-edge colors 2 and 3.
Its neighbor, cell 1, loses tiles 0 and 3: neither has a supported west edge.
The neighbor's domain shrinks from eight candidates to six.

{% include narrative-static.html asset_id="presentazione_propagation" image="/assets/narrative/reference-trace/frame-000001.png" alt="Initial propagation: cell 0 restricts cell 1 from eight candidates to six, removing tiles 0 and 3 without a DFS decision." width="1976" height="828" label="observed" caption="The first neighbor reduction occurs before any DFS decision. The changed domain is recorded; the highlighted support source is derived from the validated before-state." source="wang-explain-manifest-v3" %}

Propagation only removes unsupported candidates. At a fixed point, the queue
is empty and local constraints cannot remove more; unresolved cells may remain.
[Technical details → propagation]({{ '/serial_solver_implementation_guide/#5-propagation' | relative_url }}).

### MRV and decision

Each number below is the number of candidate tiles remaining in an active
cell. Green cells are singleton domains; purple cells tie for the smallest
unresolved domain. MRV selects cell 0, highlighted in yellow: its domain has
two candidates, and row-major order breaks the tie among 363 cells.

{% include narrative-static.html asset_id="presentazione_mrv" image="/assets/narrative/reference-trace/frame-002517.png" alt="Observed MRV decision: minimum unresolved domain size two, 363 tied cells, and row-major winner cell zero highlighted in yellow. Green cells have singleton domains." width="1976" height="828" label="observed" caption="MRV chooses the smallest unresolved domain; row-major order selects cell 0 among equal minima. This decision records candidate tile 0 before its domain reduction." source="wang-explain-manifest-v3" %}

Singleton cells are not MRV candidates. A decision tries one remaining tile;
propagation removes candidates without making another DFS choice.
[Technical details → MRV]({{ '/serial_solver_implementation_guide/#mrv-selection' | relative_url }}).

### Conflict and rollback

**Separate search-UNSAT capture, reference solver.** The SAT example above
has no backtracking. Here, after the depth-one choice reaches a fixed point,
the next DFS frame selects cell 492 with `D(492) = {0,3}`. Its saved state has
recorded change marker **3990**; it tries tile 0. The table follows two cells:

| Branch state | `D(492)` | `D(614)` |
| --- | --- | --- |
| Before the choice | `{0,3}` | `{6,8}` |
| Tile 0 applied | `{0}` | `{6,8}` |
| Propagation fails | `{0}` | `{}` |
| Rollback completed | `{0,3}` | `{6,8}` |
| Next candidate applied | `{3}` | `{6,8}` |

**1. Apply the decision.** The yellow outline marks cell 492, at the left of
the third row from the bottom. Its two-candidate domain becomes a singleton.

{% include narrative-static.html asset_id="presentazione_branch_decision" image="/assets/presentazione/search-unsat/frame-003995.png" alt="Search-UNSAT reference branch at depth two: cell 492 now contains only tile 0; the other unresolved cells still have multiple candidates." width="1976" height="972" label="observed" caption="Cell 492 is restricted from {0,3} to {0}; the first trail entry after marker 3990 records its previous domain." source="wang-explain-manifest-v3" %}

**2. Propagate to an empty domain.** Later in the same branch, cell 614 loses
its last tile. This restriction follows from edge compatibility.

{% include narrative-static.html asset_id="presentazione_branch_empty" image="/assets/presentazione/search-unsat/frame-004118.png" alt="Search-UNSAT propagation removes tile 8 from cell 614, leaving an empty active domain; cell 613 is the derived support source." width="1976" height="972" label="observed" caption="Cell 614 changes from {8} to {}. The before-state identifies cell 613 as the unique adjacent support explanation." source="wang-explain-manifest-v3" %}

**3. Record the conflict.** A failed candidate is not yet an UNSAT result:
the DFS frame still has tile 3 to try.

{% include narrative-static.html asset_id="presentazione_branch_conflict" image="/assets/presentazione/search-unsat/frame-004120.png" alt="Search-UNSAT conflict at depth two: cell 614 is empty after the branch choosing tile 0 at cell 492; the trail has reached 4114." width="1976" height="972" label="observed" caption="The failed leaf belongs to the cell-492, tile-0 branch. Search must restore its entry state before another candidate." source="wang-explain-manifest-v3" %}

**4. Restore the saved state.** Rollback reverses **124 trail entries**,
affecting **122 cells**, from recorded marker 4114 back to 3990. Some cells changed more
than once. Every domain now equals its value immediately before this choice;
the depth-one decision remains in place.

{% include narrative-static.html asset_id="presentazione_branch_rollback" image="/assets/presentazione/search-unsat/frame-004121.png" alt="Search-UNSAT rollback restores 124 trail entries across 122 cells, highlighted in teal, to marker 3990; cell 492 again has candidates 0 and 3." width="1976" height="972" label="observed" caption="Reverse restoration recovers the complete pre-decision domain state, including D(492) = {0,3} and D(614) = {6,8}." source="wang-explain-manifest-v3" %}

**5. Try the next candidate.** The existing DFS frame next chooses tile 3 at
cell 492. This picture records the choice **before** its domain reduction;
the following event applies `{3}` and propagation resumes.

{% include narrative-static.html asset_id="presentazione_branch_next" image="/assets/presentazione/search-unsat/frame-004122.png" alt="Search-UNSAT next decision: the restored cell 492 still displays domain size two while the DFS frame records tile 3 as its next candidate." width="1976" height="972" label="observed" caption="The next candidate comes from the same frame after rollback; its recorded domain restriction has not yet been applied in this picture." source="wang-explain-manifest-v3" %}

The explicit stack retains each frame's cell, remaining candidates and entry
marker. It descends after successful propagation, or unwinds exhausted frames.
The complete capture finishes UNSAT after all branches; this excerpt is
observed diagnostic evidence, not an UNSAT certificate.
[Technical details → iterative DFS]({{ '/serial_solver_implementation_guide/#iterative-dfs' | relative_url }})
and [undo trail]({{ '/serial_solver_implementation_guide/#undo-trail-and-rollback' | relative_url }}).

<details class="technical-provenance" markdown="1">
<summary>Technical provenance of the branch excerpt</summary>

Source: `pipeline_unsat_search.cm13`, reference solver, complete 4,370-event
search-UNSAT capture. The five images use zero-based sequences 3995, 4118,
4120, 4121 and 4122; image headings count events from one. The before-state is
sequence 3993, decision 3994 saves marker 3990, and sequence 4123 applies the
next candidate. Replay confirms that states 3993 and 4121 are identical.
Displayed trace markers include the initial-propagation prefix; they are not
live C trail offsets, which restart from zero when search begins.

[Source formula](https://github.com/xtraid/tiling-foundry/blob/7ee5d44e16f235768b7e6e6e9b32a4f44be70411/tests/instances/pipeline_unsat_search.cm13) ·
[Trace manifest, snapshots and SHA-256 identities]({{ '/assets/presentazione/search-unsat/reference-manifest.json' | relative_url }}).

</details>

### Verified SAT

Return to the canonical SAT example: [all active domains are singleton]({{ '/assets/narrative/reference-trace/frame-002895.png' | relative_url }}).

**Singleton domains → extract tile IDs → independent verifier → publish SAT.**

The verifier checks every active placement, exposed boundary and shared edge
directly from the tileset. A rejected candidate produces ERROR. The checked
tiling can then be shown as a [Wang witness]({{ '/worked-example/#verification-and-presentation' | relative_url }}).
[Technical details → SAT publication]({{ '/serial_solver_implementation_guide/#7-mandatory-sat-verification-and-publication' | relative_url }}).

## Verification dependencies

The formula reaches Boolean Z3 directly. Yang–Zhang supplies one shared region
and tileset to both native paths and Wang Z3. Reference and optimized use the
same native core; the two Z3 encodings use the same Z3 library.

<figure class="narrative-asset" style="max-width: 35rem">
  <img src="{{ '/assets/presentazione/verification-dependencies.svg' | relative_url }}" width="560" height="700" loading="lazy" alt="Formula branches to Boolean Z3 and Yang–Zhang. The region and tileset feed Reference C, Optimized C and Wang Z3. Returned SAT assignments and tilings enter independent checks before presentation.">
  <figcaption><strong>didactic.</strong> Arrows show input and witness dependencies, not execution order. Checks also receive the original formula, region, tileset and applicable reduction provenance. <a class="full-size-image" href="{{ '/assets/presentazione/verification-dependencies.svg' | relative_url }}">Open full-size image</a></figcaption>
</figure>

Boolean Z3 bypasses the reduction; Wang Z3 bypasses native search. Independent
checks validate returned SAT witnesses. UNSAT has no witness to check, and an
observed UNSAT trace is not a certificate.
[Named checks and receipts →]({{ '/components/verification/#primary-animation' | relative_url }}) ·
[Full dependency and trust boundaries →]({{ '/pipeline/#independence' | relative_url }}).

## One solved example

**Three variables, three clauses → Boolean SAT → Yang–Zhang region → native
SAT → independent checks → verified Wang witness → optional generalized / hex.**

[Open the worked SAT example →]({{ '/worked-example/' | relative_url }}).
Its existing enlarged panels show this complete sequence on one capture,
including all six passing receipts. Square, generalized and hex are views of
the checked witness. The search-UNSAT rollback excerpt above remains separate.

## Optimized: six implementation mechanisms

The solver semantics stay the same. The [six-panel visual summary]({{ '/components/optimized-solver/#six-mechanism-summary' | relative_url }})
shows growing stack storage, initial trail omission, verified-domain ownership
transfer, byte support lookup, queue deduplication and lazy MRV indexing.
Each panel identifies the private state or work it changes; measured performance
remains in [Evidence]({{ '/evidence/' | relative_url }}).
