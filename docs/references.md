---
layout: page
title: Project references
permalink: /references/
page_class: reference
description: Primary papers and authoritative references used by Tiling Foundry.
section: Yang–Zhang reduction
document_kind: Reference bibliography
status: Current reference policy
updated: 2026-08-21
nav_order: 30
---

# Project references

This file records the primary external sources used by the project and where
their authoritative copies can be obtained. It intentionally links to papers
instead of vendoring their PDFs when the published license does not explicitly
permit third-party redistribution.

License status was checked on 11 August 2026. This is a conservative repository
policy, not legal advice.

## Fixed Wang tiles and finite-region reduction

Chao Yang and Zhujun Zhang, *NP-completeness of Tiling Finite Simply Connected
Regions with a Fixed Set of Wang Tiles*, arXiv:2405.01017v2, 2024.

- [arXiv record and PDF](https://arxiv.org/abs/2405.01017)
- [DOI](https://doi.org/10.48550/arXiv.2405.01017)
- Repository status: link only. The selected arXiv license grants arXiv a
  non-exclusive right to distribute; it does not itself grant this repository
  a redistribution license.

This is the primary source for the fixed set of 23 Wang tiles, the 14
generalized tiles, and the Cubic Monotone 1-in-3 SAT reduction implemented by
the project.

## Earlier simply-connected rectangle construction

Igor Pak and Jed Yang, *Tiling Simply Connected Regions with Rectangles*,
Journal of Combinatorial Theory, Series A 120(7), 1804--1816, 2013.

- [arXiv record and PDF](https://arxiv.org/abs/1305.2796)
- [Publisher DOI](https://doi.org/10.1016/j.jcta.2013.06.008)
- [Author-hosted copy](https://www.math.ucla.edu/~pak/papers/yang-short10.pdf)
- Repository status: link only. The arXiv submission uses the same
  non-exclusive distribution license, and no separate redistribution license
  was found on the author-hosted copy.

This is the earlier fixed-rectangle NP-completeness result improved by the
Yang–Zhang construction.

## Wang tiles, computation, and the square-to-hex motivation

Sky Basire, *Wang Tiles*, University of Canterbury summer project report, 2022.

- [Institutional repository record](https://hdl.handle.net/10092/105625)
- [DOI](https://doi.org/10.26021/14719)
- Repository status: link only. The institutional record explicitly labels the
  report **All Rights Reserved**.

The report provides an accessible overview of the Domino Problem, computation
with Wang tiles, and examples of square-to-hex Wang-tile constructions.

## Policy for adding local copies

A PDF may be added under `docs/papers/` only when at least one of the following
is recorded alongside it:

- an explicit Creative Commons or equivalent redistribution license covering
  that version;
- written permission from the copyright holder to redistribute it in this
  repository;
- a public-domain statement applicable to the work.

The local entry should preserve attribution, source URL, exact version, license
text or permission record, and the date it was retrieved. Free access or an
author-hosted download link alone is not treated as redistribution permission.
