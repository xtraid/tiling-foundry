---
layout: page
title: CM13 parser fuzz smoke
permalink: /parser_fuzz_smoke_2026-08-22/
page_class: evidence
description: Reproducible libFuzzer smoke coverage for the canonical CM13 parser.
section: Architecture and correctness
document_kind: Test report
status: Current evidence
updated: 2026-08-22
nav_order: 41
---

# CM13 parser fuzz smoke — 22 August 2026

This report records the first coverage-guided fuzz smoke for the canonical
`.cm13` parser. It complements the deterministic parser unit tests; it does not
replace their exact status and source-location assertions.

## Harness and corpus

`tests/fuzz/fuzz_formula_parser.c` passes arbitrary bytes to
`cm13_formula_parse()` through a POSIX memory stream. Every invocation checks
the parser's transactional ownership contract: success must return a populated
canonical formula, while every rejection must leave the output empty. Owned
formula storage is destroyed before the invocation returns.

The six versioned seeds under `tests/fuzz/corpus/cm13/` include minimal and
commented valid formulas plus malformed header, domain, truncation, and
oversized-count cases. The Make target copies them to
`build/fuzz/cm13-corpus/`, which is the writable libFuzzer corpus. Findings are
also confined to `build/fuzz/artifacts/`; neither generated input nor crash
artifact is written into the source corpus or repository root.

## Reproduction and budget

On the supported Linux/POSIX platform, run:

```sh
make parser-fuzz-smoke
```

The target builds with Clang, libFuzzer, AddressSanitizer and
UndefinedBehaviorSanitizer, then uses these fixed controls:

| Control | Smoke value |
| --- | ---: |
| Random seed | `20260822` |
| Generated runs | `2,000` |
| Maximum input length | `4,096` bytes |
| Per-input timeout | `2` seconds |
| Process RSS limit | `256` MiB |

Leak detection remains enabled. `allocator_may_return_null=1` is scoped only
to the fuzz process so deliberately enormous decimal headers exercise the
parser's `CM13_PARSE_OUT_OF_MEMORY` result instead of aborting merely because
of the requested allocation size. LibFuzzer's combined allocation/RSS guard is
disabled for the same reason; AddressSanitizer supplies the equivalent runtime
guard as a 256 MiB hard RSS limit. Maximum input length and per-input timeout
are also bounded. Other sanitizer findings remain fatal.

The manual extended campaign uses the same harness and copied corpus:

```sh
make parser-fuzz
make parser-fuzz FUZZ_RUNS=1000000 FUZZ_MAX_LEN=16384 FUZZ_TIMEOUT=5
```

The default extended budget is 100,000 generated runs. It is intentionally not
part of every push; CI runs only the fixed smoke target.

## Result

The local smoke completed all 2,000 generated runs from the six seeds with no
crash, leak, sanitizer diagnostic, timeout, or abnormal memory growth. The
final libFuzzer process used 63 MiB RSS and reached 177 edge counters and 534
feature counters on this toolchain. These counters are search guidance, not a
coverage threshold or a portability claim.

Measured environment:

```text
Debian GNU/Linux 13
Linux 6.12.101+deb13-amd64 x86_64
Debian Clang 19.1.7
libFuzzer/ASan/UBSan from the Clang 19 runtime
```

The smoke is deliberately short and cannot establish absence of parser bugs.
Longer campaigns may retain newly interesting inputs only after review and
minimization; generated corpora and findings remain build artifacts by default.
