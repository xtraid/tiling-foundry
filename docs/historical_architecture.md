---
layout: page
title: Initial C/OpenMP architecture specification
permalink: /historical_architecture/
page_class: history
description: Context and limitations for the project's original future-facing architecture PDF.
section: Historical material
document_kind: Historical specification
status: Superseded design context
updated: 2026-08-25
nav_order: 10
---

# Initial C/OpenMP architecture specification

The 17-page architecture specification dated 7 August 2026 records the
project’s initial target: a C17 implementation of the Yang–Zhang reduction, a
reference Wang solver, an OpenMP execution path, independent verification, and
diagnostic export. It is preserved because it explains why the repository
separates fixed tiles, per-formula geometry, transient search state,
parallel-planning ideas, and rendering.

[Download the original Italian PDF]({{ '/Wang23_C_OpenMP_Architecture_Spec_Merged.pdf' | relative_url }}){: .text-link }

## How to read it

Treat the PDF as design history, not as current API documentation. Several
sketched structures were intentionally not adopted: current `Region` storage
does not cache coordinates, neighbors, active counts, zone IDs, or signal-plan
metadata, and the implemented input format is the strict `p cm13` format rather
than the early `vars`/`clause` sketch. The current public headers and tests are
authoritative for behavior.

The serial and optimized solvers are implemented and measured. The Python
square solution contract, exporter, presentation-only square renderer, and
checked square-to-hex presentation port are also implemented. Native C JSON,
`TaskPlan`, and the native OpenMP solver remain future work.

Current boundaries and status are documented in the
[architecture page]({{ '/development_principles/' | relative_url }}), the
[solution contract]({{ '/wang-solution-v1/' | relative_url }}), the
[square-to-hex reference]({{ '/wang-square-to-hex/' | relative_url }}), and the
[solver optimization methodology]({{ '/solver_performance_scope/' | relative_url }}).

## Document metadata

- Version: 1.0, dated 7 August 2026.
- Language: Italian.
- Format: 17 A4 pages, PDF 1.7.
- Accessibility: the file is not tagged and has no embedded title, author, or
  subject metadata; this HTML page supplies its public context.
- Role: initial future-facing architecture proposal, superseded wherever it
  differs from implemented headers, tests, or current technical pages.
