"""Pure static LaTeX formatter for caller-validated v2 dossier inputs."""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Iterable

from formats.run_dossier_v2 import validate_run_dossier_v2


_SAFE_PATH = re.compile(r"[A-Za-z0-9._/-]+\Z")


def _tex(value: object) -> str:
    text = str(value).replace("\u00a0", " ")
    text = text.replace("–", "--").replace("—", "---").replace("→", " to ")
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "%": r"\%",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _path(value: object, *, narrative: bool = False) -> str:
    """Constrain already validated paths before placing them in TeX commands."""
    text = str(value)
    parsed = PurePosixPath(text)
    if (
        _SAFE_PATH.fullmatch(text) is None
        or parsed.is_absolute()
        or parsed.as_posix() != text
        or any(part in ("", ".", "..") for part in parsed.parts)
    ):
        raise ValueError("report artifact path is not a safe normalized relative path")
    return f"assets/narrative/{text}" if narrative else text


def _wide_figure(path: str, caption: str) -> str:
    """Keep a bounded static image and its caption on the same page."""
    return "\n".join(
        (
            r"\begin{center}",
            r"\begin{minipage}{\textwidth}",
            r"\centering",
            rf"\includegraphics[width=\textwidth,height=0.48\textheight,keepaspectratio]{{{path}}}",
            rf"\par\smallskip{{\small\itshape {_tex(caption)}}}",
            r"\end{minipage}",
            r"\end{center}",
        )
    )


def _multi_panel_figure(paths: Iterable[str], caption: str) -> str:
    panels = []
    for path in paths:
        panels.extend(
            (
                r"\begin{center}",
                r"\centering",
                rf"\includegraphics[width=\textwidth,height=0.43\textheight,keepaspectratio]{{{path}}}",
                r"\end{center}",
            )
        )
    return "\n".join(
        (
            *panels,
            rf"\par\smallskip{{\small\itshape {_tex(caption)}}}",
        )
    )


def _tall_figure(path: str, caption: str) -> str:
    return "\n".join(
        (
            r"\begin{center}",
            r"\centering",
            rf"\includegraphics[width=0.82\textwidth,height=0.64\textheight,keepaspectratio]{{{path}}}",
            rf"\par\smallskip{{\small\itshape {_tex(caption)}}}",
            r"\end{center}",
        )
    )


def _compact_figure(path: str, caption: str) -> str:
    return "\n".join(
        (
            r"\begin{center}",
            r"\centering",
            rf"\includegraphics[width=0.72\textwidth,height=0.30\textheight,keepaspectratio]{{{path}}}",
            rf"\par\smallskip{{\small\itshape {_tex(caption)}}}",
            r"\end{center}",
        )
    )


def _atomic_legend_figure(path: str, caption: str) -> str:
    """Show the fixed 1732x4184 atomic legend as two readable static crops."""
    return "\n".join(
        (
            r"\clearpage",
            r"\begin{center}",
            rf"\includegraphics[viewport=0 2092 1732 4184,clip,width=0.92\textwidth]{{{path}}}",
            r"\end{center}",
            r"\clearpage",
            r"\begin{center}",
            rf"\includegraphics[viewport=0 0 1732 2092,clip,width=0.92\textwidth]{{{path}}}",
            rf"\par\smallskip{{\small\itshape {_tex(caption)}}}",
            r"\end{center}",
        )
    )


def _elapsed(value: object) -> str:
    if value is None:
        return "not applicable"
    elapsed = int(value)
    return f"{elapsed / 1_000_000:.3f} ms ({elapsed} ns)"


def _trace_summary(record: dict[str, object]) -> str:
    trace = record["trace"]
    assert isinstance(trace, dict)
    return "\n".join(
        (
            r"\begin{tabular}{@{}>{\bfseries}p{0.31\textwidth}p{0.61\textwidth}@{}}",
            rf"Status & {_tex(record['status'])} \\",
            rf"Solver & {_tex(trace['solver'])} \\",
            rf"Observed events & {_tex(trace['observed_event_count'])} \\",
            rf"Selected static milestones & {_tex(trace['selection']['selected_event_count'])} \\",
            rf"Complete / truncated & {_tex(trace['complete'])} / {_tex(trace['truncated'])} \\",
            rf"Checkpoints & {_tex(trace['checkpoint_count'])} \\",
            r"\end{tabular}",
        )
    )


def _narrative_artifact(record: dict[str, object], field: str) -> str:
    artifact = record[field]
    assert isinstance(artifact, dict)
    return _path(artifact["path"], narrative=True)


def _milestones(manifest: dict[str, object], name: str) -> tuple[str, ...]:
    milestone_map = manifest["pdf_milestones"]
    assert isinstance(milestone_map, dict)
    paths = milestone_map[name]
    assert isinstance(paths, list)
    return tuple(_path(path, narrative=True) for path in paths)


def render_run_report_v2_tex(
    document: dict[str, object],
    manifest: dict[str, object],
    template: str,
) -> str:
    """Render TeX from a validated run and caller-validated narrative manifest.

    The caller must load the manifest through ``load_narrative_assets`` before
    invoking this pure formatter. The formatter performs no file I/O, replay,
    solving, witness checking, timing, or image composition.
    """
    validate_run_dossier_v2(document)
    if template.count("@@TITLE@@") != 1 or template.count("@@BODY@@") != 1:
        raise ValueError("v2 report template must contain one title and one body marker")
    if manifest.get("schema") != "wang-narrative-assets-v1":
        raise ValueError("v2 report requires a caller-validated narrative manifest")

    case = document["case"]
    source = document["source"]
    environment = document["environment"]
    boolean_z3 = document["boolean_z3"]
    reduction = document["reduction"]
    reference = document["reference"]
    optimized = document["optimized"]
    wang_z3 = document["wang_z3"]
    verification = document["verification"]
    agreement = document["agreement"]
    timings = document["timings"]
    artifacts = document["artifacts"]
    animations = manifest["animations"]
    statics = manifest["statics"]
    assert all(
        isinstance(item, dict)
        for item in (
            case,
            source,
            environment,
            boolean_z3,
            reduction,
            reference,
            optimized,
            wang_z3,
            verification,
            agreement,
            timings,
            artifacts,
            animations,
            statics,
        )
    )
    status = str(reference["status"])

    source_artifact = artifacts["source_input"]
    assert isinstance(source_artifact, dict)
    source_path = _path(source_artifact["path"])
    formula_static = statics["formula"]
    generalized_sheet = statics["generalized_sheet"]
    atomic_legend = statics["atomic_legend"]
    assert isinstance(formula_static, dict)
    assert isinstance(generalized_sheet, dict)
    assert isinstance(atomic_legend, dict)

    boolean_animation = animations["boolean_z3"]
    reference_animation = animations["reference_trace"]
    optimized_animation = animations["optimized_trace"]
    mechanisms_animation = animations["optimized_mechanisms"]
    wang_animation = animations["wang_z3"]
    verification_animation = animations["verification"]
    assert all(
        isinstance(item, dict)
        for item in (
            boolean_animation,
            reference_animation,
            optimized_animation,
            mechanisms_animation,
            wang_animation,
            verification_animation,
        )
    )

    boolean_assignment = (
        "not applicable for this UNSAT result"
        if status == "unsat"
        else ", ".join(
            f"variable {index + 1}={'true' if value else 'false'}"
            for index, value in enumerate(boolean_z3["assignment"])
        )
    )
    witness_note = (
        "Witness verification: not applicable. Witness presentations: not "
        "applicable. No SAT witness or UNSAT certificate is fabricated. No UNSAT "
        "certificate is claimed by the observed search trace."
        if status == "unsat"
        else (
            "All six named independent witness checks passed. Presentation follows "
            "verification and does not establish satisfiability."
        )
    )

    verification_rows = []
    for name, check in verification.items():
        assert isinstance(check, dict)
        result = "not applicable" if not check["performed"] else "passed"
        verification_rows.append(
            rf"{_tex(name)} & {_tex(check['checker'])} & {_tex(result)} \\"
        )

    timing_rows = []
    for name, elapsed in timings.items():
        if name in {"clock", "identity"}:
            continue
        timing_rows.append(rf"{_tex(name)} & {_tex(_elapsed(elapsed))} \\")

    hash_blocks = []
    for name, artifact in artifacts.items():
        if artifact is None:
            continue
        assert isinstance(artifact, dict)
        hash_blocks.append(
            "\n".join(
                (
                    r"\begin{samepage}",
                    rf"\textbf{{{_tex(name)}}}\par",
                    rf"Path: \path{{{_path(artifact['path'])}}}\par",
                    rf"SHA-256: \path{{{artifact['sha256']}}}\par\smallskip",
                    r"\end{samepage}",
                )
            )
        )

    presentation_block: list[str]
    if status == "sat":
        presentation_items = []
        for name in ("square", "generalized", "hex"):
            record = statics[f"{name}_presentation"]
            assert isinstance(record, dict)
            presentation_items.append(
                (_narrative_artifact(record, "artifact"), str(record["caption"]))
            )
        presentation_block = [
            _wide_figure(path, caption) for path, caption in presentation_items
        ]
    else:
        presentation_status = statics["presentation_status"]
        assert isinstance(presentation_status, dict)
        presentation_block = [
            _compact_figure(
                _narrative_artifact(presentation_status, "artifact"),
                str(presentation_status["caption"]),
            )
        ]

    body = "\n".join(
        (
            r"\section{Summary}",
            _tex(case["purpose"]),
            "",
            r"\begin{tabular}{@{}>{\bfseries}p{0.27\textwidth}p{0.65\textwidth}@{}}",
            rf"Case & {_tex(case['id'])} \\",
            rf"Terminal status & {_tex(status.upper())} \\",
            rf"All named statuses agree & {_tex(agreement['all_status_equal'])} \\",
            rf"Agreement passed & {_tex(agreement['passed'])} \\",
            r"\end{tabular}",
            *(
                (
                    r"\par",
                    "Expected result: not supplied; result observed from four named engines.",
                )
                if case["expected_status"] is None else ()
            ),
            _multi_panel_figure(
                _milestones(manifest, "end_to_end"),
                "Static semantic milestones from this validated full-pipeline run.",
            ),
            r"\clearpage",
            r"\section{Source instance}",
            rf"Recorded source: \path{{{_path(source['path'])}}}.\par",
            rf"Source SHA-256: \path{{{source['sha256']}}}.\par",
            _wide_figure(
                _narrative_artifact(formula_static, "artifact"),
                "Parsed formula snapshot for this named source.",
            ),
            r"\verbatiminput{" + source_path + "}",
            r"\section{Boolean Z3}",
            rf"Status: {_tex(boolean_z3['status'])}. Random seed: {_tex(boolean_z3['configuration']['random_seed'])}. Threads: {_tex(boolean_z3['configuration']['threads'])}.",
            (
                rf"\par Recorded elapsed time: {_tex(_elapsed(timings['boolean_z3_ns']))}. "
                r"This run-specific observation is not a benchmark.\par"
            ),
            (
                "Source variables are written 1-based (1, 2, ...); the static "
                "encoding figure labels stored zero-based IDs (x0, x1, ...)."
            ),
            rf"Assignment: {_tex(boolean_assignment)}.",
            _tall_figure(
                _narrative_artifact(boolean_animation, "fallback"),
                str(boolean_animation["caption"]),
            ),
            r"\section{Yang--Zhang reduction}",
            (
                "The native reduction is recorded once. The figures below reuse its "
                "validated provenance and canonical generalized vocabulary."
            ),
            _multi_panel_figure(
                _milestones(manifest, "region_construction"),
                str(animations["region_construction"]["caption"]),
            ),
            _tall_figure(
                _narrative_artifact(generalized_sheet, "artifact"),
                str(generalized_sheet["caption"]),
            ),
            _atomic_legend_figure(
                _narrative_artifact(atomic_legend, "artifact"),
                str(atomic_legend["caption"]),
            ),
            r"\section{Reference solver}",
            _trace_summary(reference),
            _multi_panel_figure(
                _milestones(manifest, "reference_trace"),
                str(reference_animation["caption"]),
            ),
            r"\section{Optimized solver}",
            _trace_summary(optimized),
            _multi_panel_figure(
                _milestones(manifest, "optimized_trace"),
                str(optimized_animation["caption"]),
            ),
            _tall_figure(
                _narrative_artifact(mechanisms_animation, "fallback"),
                str(mechanisms_animation["caption"]),
            ),
            r"\section{Wang Z3}",
            rf"Status: {_tex(wang_z3['status'])}. Random seed: {_tex(wang_z3['configuration']['random_seed'])}. Threads: {_tex(wang_z3['configuration']['threads'])}.",
            (
                rf"\par Recorded elapsed time: {_tex(_elapsed(timings['wang_z3_ns']))}. "
                r"This run-specific observation is not a benchmark.\par"
            ),
            _tall_figure(
                _narrative_artifact(wang_animation, "fallback"),
                str(wang_animation["caption"]),
            ),
            r"\section{Verification and presentation}",
            witness_note,
            r"\begin{longtable}{@{}p{0.24\textwidth}p{0.52\textwidth}p{0.16\textwidth}@{}}",
            r"\textbf{Check} & \textbf{Independent checker} & \textbf{Result} \\",
            *verification_rows,
            r"\end{longtable}",
            _tall_figure(
                _narrative_artifact(verification_animation, "fallback"),
                str(verification_animation["caption"]),
            ),
            *presentation_block,
            r"\clearpage",
            r"\section{Reproducibility appendix}",
            (
                "These are raw observations from one captured environment, not a "
                "benchmark. The PDF consumes the validated run and static narrative "
                "assets; it does not solve, invoke Z3, replay traces, compose images, "
                "recount events, or independently verify a witness."
            ),
            r"\par\medskip",
            rf"\textbf{{Git commit:}} \path{{{environment['git_commit']}}}\par",
            rf"\textbf{{Captured UTC:}} {_tex(environment['captured_at_utc'])}\par",
            rf"\textbf{{Platform:}} {_tex(environment['platform'])}\par",
            rf"\textbf{{Python:}} {_tex(environment['python'])}\par",
            rf"\textbf{{Timing identity:}} {_tex(timings['identity'])}\par",
            (
                rf"\textbf{{Narrative manifest:}} {_tex(manifest['schema'])}; "
                rf"product {_tex(manifest['product'])}; selector "
                rf"{_tex(manifest['pdf_milestones']['selector'])}.\par"
            ),
            (
                r"\textbf{Reference trace parameters:} "
                rf"event capacity {_tex(reference['configuration']['event_capacity'])}; "
                rf"checkpoint interval {_tex(reference['configuration']['checkpoint_interval'])}; "
                rf"checkpoint capacity {_tex(reference['configuration']['checkpoint_capacity'])}.\par"
            ),
            (
                r"\textbf{Optimized trace parameters:} "
                rf"event capacity {_tex(optimized['configuration']['event_capacity'])}; "
                rf"checkpoint interval {_tex(optimized['configuration']['checkpoint_interval'])}; "
                rf"checkpoint capacity {_tex(optimized['configuration']['checkpoint_capacity'])}.\par"
            ),
            r"\subsection{Raw timings}",
            r"\begin{tabular}{@{}p{0.38\textwidth}p{0.54\textwidth}@{}}",
            *timing_rows,
            r"\end{tabular}",
            r"\subsection{Artifact identities}",
            r"\footnotesize",
            *hash_blocks,
            r"\normalsize",
        )
    )
    return template.replace("@@TITLE@@", _tex(case["title"])).replace(
        "@@BODY@@", body
    )
