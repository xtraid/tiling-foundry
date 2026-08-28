"""Fixed LaTeX scaffolding for a validated run dossier."""

from __future__ import annotations

from typing import Final

from formats.run_dossier import (
    CLASS_PROPAGATION,
    CLASS_ROOT_CONFLICT,
    CLASS_SAT,
    CLASS_SEARCH,
    validate_run_dossier,
)


_DIAGNOSIS: Final = {
    CLASS_SAT: (
        "The native solver returned SAT, the independent Python checker accepted "
        "the copied witness, and the square and hex images derive from that same "
        "hash-bound solution."
    ),
    CLASS_ROOT_CONFLICT: (
        "A caller-supplied empty domain on an active cell was observed as an "
        "immediate initial-phase conflict. No propagation, decision, or "
        "backtracking step was needed."
    ),
    CLASS_PROPAGATION: (
        "A caller-supplied singleton was locally well formed but incompatible with "
        "the region. Initial arc propagation reduced domains until it observed an "
        "empty active-cell domain, before search began."
    ),
    CLASS_SEARCH: (
        "Initial propagation did not decide the instance. The observed solver run "
        "entered depth-two search and exhausted alternatives through multiple "
        "decisions, conflicts, and backtracks before returning UNSAT."
    ),
}


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


def _image(path: str, caption: str) -> str:
    return "\n".join(
        (
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\includegraphics[width=\textwidth,height=0.42\textheight,keepaspectratio]{{{path}}}",
            rf"\caption{{{_tex(caption)}}}",
            r"\end{figure}",
        )
    )


def render_run_report_tex(document: dict[str, object], template: str) -> str:
    """Render the sole fixed report representation from validated run.json data."""
    validate_run_dossier(document)
    if template.count("@@TITLE@@") != 1 or template.count("@@BODY@@") != 1:
        raise ValueError("report template must contain one title and one body marker")

    case = document["case"]
    source = document["source"]
    environment = document["environment"]
    solver = document["solver"]
    timings = document["timings"]
    artifacts = document["artifacts"]
    assert isinstance(case, dict)
    assert isinstance(source, dict)
    assert isinstance(environment, dict)
    assert isinstance(solver, dict)
    assert isinstance(timings, dict)
    assert isinstance(artifacts, dict)
    trace = solver["trace"]
    replay = solver["replay"]
    assert isinstance(trace, dict)
    assert isinstance(replay, dict)
    counts = trace["event_counts"]
    assert isinstance(counts, dict)

    timing_rows: list[str] = []
    for stage in timings["stages"]:
        assert isinstance(stage, dict)
        elapsed = stage["elapsed_ns"]
        value = "not applicable" if elapsed is None else f"{elapsed / 1_000_000:.3f} ms ({elapsed} ns)"
        timing_rows.append(rf"{_tex(stage['name'])} & {_tex(value)} \\")

    event_rows = [
        rf"{_tex(name)} & {value} \\"
        for name, value in counts.items()
    ]
    override_rows = [
        rf"cell {_tex(item['cell'])}: domain {_tex(item['domain'])}"
        for item in solver["initial_domain_overrides"]
    ]
    override_text = ", ".join(override_rows) if override_rows else "none"

    artifact_rows = [
        rf"{_tex(name)} & \texttt{{{_tex(item['sha256'])}}} \\"
        for name, item in artifacts.items()
        if str(item["media_type"]) == "application/json"
    ]

    figures = [
        _image(
            artifacts["formula_view"]["path"],
            "Parsed formula snapshot used by this run.",
        ),
        _image(
            artifacts["region_square"]["path"],
            "Unassigned square region and boundary constraints.",
        ),
        _image(
            artifacts["region_hex"]["path"],
            "Presentation-only Basire/Culik hex port of the same square region.",
        ),
        _image(
            artifacts["reduction_view"]["path"],
            "Native Yang--Zhang reduction provenance for the constructed region.",
        ),
        _image(
            artifacts["trace_contact_sheet"]["path"],
            "Selected states from one replay of the observed semantic trace.",
        ),
    ]
    if solver["status"] == "sat":
        figures.extend(
            (
                _image(
                    artifacts["solution_square"]["path"],
                    "Verified square witness with explainability overlays.",
                ),
                _image(
                    artifacts["solution_hex"]["path"],
                    "Checked presentation-only hex port of the same witness.",
                ),
            )
        )

    body = "\n".join(
        (
            r"\section{Run identity}",
            _tex(case["description"]),
            "",
            r"\begin{tabular}{@{}>{\bfseries}p{0.28\textwidth}p{0.64\textwidth}@{}}",
            rf"Case & {_tex(case['id'])} \\",
            rf"Classification & {_tex(case['classification'])} \\",
            rf"Source & {_tex(source['path'])} \\",
            rf"Source SHA-256 & {{\scriptsize\texttt{{{_tex(source['sha256'])}}}}} \\",
            rf"Git commit & \texttt{{{_tex(environment['git_commit'])}}} \\",
            rf"Captured & {_tex(environment['captured_at_utc'])} \\",
            rf"Platform & {{\small {_tex(environment['platform'])}}} \\",
            rf"Python & {_tex(environment['python'])} \\",
            r"\end{tabular}",
            "",
            r"\section{Pipeline and result}",
            r"\begin{tabular}{@{}>{\bfseries}p{0.28\textwidth}p{0.64\textwidth}@{}}",
            rf"Native solver & {_tex(solver['engine'])} \\",
            rf"Semantics & {_tex(solver['semantics'])} \\",
            rf"Status & {_tex(solver['status'])} \\",
            rf"Initial-domain overrides & {_tex(override_text)} \\",
            rf"Event capacity & {_tex(trace['event_capacity'])} \\",
            rf"Trace truncated & {_tex(trace['truncated'])} \\",
            rf"Checkpoint interval & {_tex(trace['checkpoint_interval'])} \\",
            rf"Checkpoint capacity & {_tex(trace['checkpoint_capacity'])} \\",
            rf"Observed checkpoints & {_tex(trace['checkpoint_count'])} \\",
            rf"Trace scope & {_tex(replay['trace_scope'])} \\",
            rf"Frame scope & {_tex(replay['frame_scope'])} \\",
            rf"UNSAT certificate & {_tex(replay['unsat_certificate'])} \\",
            r"\end{tabular}",
            "",
            _tex(_DIAGNOSIS[str(case["classification"])]),
            "",
            (
                "For UNSAT runs, the trail and conflicts are diagnostics from this "
                "observed execution; they are not a mathematical UNSAT certificate."
                if solver["status"] == "unsat"
                else "The renderer is presentation only; witness correctness remains upstream."
            ),
            "",
            r"\subsection{Observed trace counts}",
            r"\begin{tabular}{lr}",
            *event_rows,
            rf"maximum depth & {_tex(trace['max_depth'])} \\",
            rf"observed events & {_tex(trace['observed_event_count'])} \\",
            r"\end{tabular}",
            "",
            r"\section{Stage timings}",
            (
                "Durations are raw measurements of this environment and execution. "
                "They are excluded from deterministic snapshot identity. Native Wang "
                "solving has no separate Z3-style encoding phase, so encoding is "
                "reported as not applicable rather than fabricated as zero."
            ),
            "",
            r"\begin{tabular}{ll}",
            *timing_rows,
            r"\end{tabular}",
            "",
            r"\section{Hash-bound JSON inputs}",
            r"\scriptsize",
            r"\begin{tabular}{p{0.25\textwidth}p{0.68\textwidth}}",
            *artifact_rows,
            r"\end{tabular}",
            r"\normalsize",
            "",
            r"\section{Visual evidence}",
            *figures,
            r"\clearpage",
            r"\section{Reproduction boundary}",
            (
                "run.json is the authoritative record for this dossier. The trace "
                "manifest and content-addressed JSON documents are validated before "
                "rendering. Frames are composed once by the existing replay renderer; "
                "this PDF reuses selected PNGs and embeds neither GIF nor video. The "
                "LaTeX compiler is invoked without shell escape."
            ),
        )
    )
    title = _tex(case["title"])
    return template.replace("@@TITLE@@", title).replace("@@BODY@@", body)
