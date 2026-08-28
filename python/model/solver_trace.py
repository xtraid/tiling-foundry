"""Immutable semantic event trace copied from one native Wang solve."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from model.tiling import TilingSolveStatus
from model.tileset import TILE_COUNT


TRACE_ROOT: Final = "root"
TRACE_PROPAGATION: Final = "propagation"
TRACE_DECISION: Final = "decision"
TRACE_DOMAIN_REDUCTION: Final = "domain_reduction"
TRACE_CONFLICT: Final = "conflict"
TRACE_BACKTRACK: Final = "backtrack"
TRACE_RESULT: Final = "result"
TRACE_KINDS: Final = frozenset(
    {
        TRACE_ROOT,
        TRACE_PROPAGATION,
        TRACE_DECISION,
        TRACE_DOMAIN_REDUCTION,
        TRACE_CONFLICT,
        TRACE_BACKTRACK,
        TRACE_RESULT,
    }
)

TRACE_INITIAL: Final = "initial"
TRACE_SEARCH: Final = "search"
TRACE_PHASES: Final = frozenset({TRACE_INITIAL, TRACE_SEARCH})

TRACE_REASON_DECISION: Final = "decision"
TRACE_REASON_PROPAGATION: Final = "propagation"
TRACE_REASONS: Final = frozenset(
    {TRACE_REASON_DECISION, TRACE_REASON_PROPAGATION}
)

SOLVER_REFERENCE: Final = "reference"
SOLVER_OPTIMIZED: Final = "optimized"
SOLVERS: Final = frozenset({SOLVER_REFERENCE, SOLVER_OPTIMIZED})

DOMAIN_ALL: Final = (1 << TILE_COUNT) - 1


@dataclass(frozen=True, slots=True)
class SolverTraceEvent:
    sequence: int
    kind: str
    phase: str | None
    reason: str | None
    depth: int
    cell: int | None
    change_mark: int
    old_domain: int | None
    new_domain: int | None
    status: TilingSolveStatus | None

    def __post_init__(self) -> None:
        for name in ("sequence", "depth", "change_mark"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"trace event {name} must be nonnegative")
        if type(self.kind) is not str or self.kind not in TRACE_KINDS:
            raise ValueError("trace event kind is invalid")
        if self.phase is not None and (
            type(self.phase) is not str or self.phase not in TRACE_PHASES
        ):
            raise ValueError("trace event phase is invalid")
        if self.reason is not None and (
            type(self.reason) is not str or self.reason not in TRACE_REASONS
        ):
            raise ValueError("trace event reason is invalid")
        if self.cell is not None and (type(self.cell) is not int or self.cell < 0):
            raise ValueError("trace event cell must be nonnegative or None")
        for name in ("old_domain", "new_domain"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not int or not 0 <= value <= DOMAIN_ALL
            ):
                raise ValueError(f"trace event {name} is not a Wang domain")
        if self.status is not None and self.status not in (
            TilingSolveStatus.SAT,
            TilingSolveStatus.UNSAT,
        ):
            raise ValueError("trace event status must be SAT, UNSAT, or None")


@dataclass(frozen=True, slots=True)
class SolverTraceCheckpoint:
    event_sequence: int
    change_mark: int
    domains: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.event_sequence) is not int or self.event_sequence < 0:
            raise ValueError("checkpoint event_sequence must be nonnegative")
        if type(self.change_mark) is not int or self.change_mark < 0:
            raise ValueError("checkpoint change_mark must be nonnegative")
        if type(self.domains) is not tuple:
            raise TypeError("checkpoint domains must be a tuple")
        _validate_domains(self.domains, "checkpoint domains")


@dataclass(frozen=True, slots=True)
class SolverTrace:
    solver: str
    status: TilingSolveStatus
    width: int
    height: int
    initial_domains: tuple[int, ...]
    events: tuple[SolverTraceEvent, ...]
    observed_event_count: int
    event_capacity: int
    truncated: bool
    checkpoints: tuple[SolverTraceCheckpoint, ...]
    checkpoint_interval: int
    checkpoint_capacity: int
    checkpoints_truncated: bool

    def __post_init__(self) -> None:
        if type(self.solver) is not str or self.solver not in SOLVERS:
            raise ValueError("solver trace engine is invalid")
        if self.status not in (TilingSolveStatus.SAT, TilingSolveStatus.UNSAT):
            raise ValueError("solver trace status must be SAT or UNSAT")
        for name in (
            "width",
            "height",
            "observed_event_count",
            "event_capacity",
            "checkpoint_interval",
            "checkpoint_capacity",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"solver trace {name} must be nonnegative")
        if self.width == 0 or self.height == 0:
            raise ValueError("solver trace dimensions must be positive")
        if self.event_capacity < 2:
            raise ValueError("solver trace event_capacity must be at least two")
        if type(self.truncated) is not bool:
            raise TypeError("solver trace truncated must be a boolean")
        if type(self.checkpoints_truncated) is not bool:
            raise TypeError("checkpoints_truncated must be a boolean")
        if type(self.initial_domains) is not tuple:
            raise TypeError("initial_domains must be a tuple")
        if type(self.events) is not tuple:
            raise TypeError("events must be a tuple")
        if type(self.checkpoints) is not tuple:
            raise TypeError("checkpoints must be a tuple")
        area = self.width * self.height
        if len(self.initial_domains) != area:
            raise ValueError("initial_domains length must match trace dimensions")
        _validate_domains(self.initial_domains, "initial domains")
        if not self.events or len(self.events) > self.event_capacity:
            raise ValueError("recorded events must fit the declared capacity")
        if self.events[0].kind != TRACE_ROOT:
            raise ValueError("the first trace event must be root")
        terminal = self.events[-1]
        if terminal.kind != TRACE_RESULT or terminal.status is not self.status:
            raise ValueError("the final trace event must publish the solve status")
        if self.observed_event_count != terminal.sequence + 1:
            raise ValueError("observed_event_count must follow the result sequence")
        if self.truncated:
            if terminal.sequence <= len(self.events) - 1:
                raise ValueError("a truncated trace must contain an event gap")
        elif self.observed_event_count != len(self.events):
            raise ValueError("a complete trace cannot contain an event gap")
        for index, event in enumerate(self.events[:-1]):
            if type(event) is not SolverTraceEvent:
                raise TypeError("events must contain SolverTraceEvent values")
            if event.sequence != index:
                raise ValueError("the recorded trace prefix must be contiguous")
        if type(terminal) is not SolverTraceEvent:
            raise TypeError("events must contain SolverTraceEvent values")
        if (self.checkpoint_interval == 0) != (self.checkpoint_capacity == 0):
            raise ValueError("checkpoint interval and capacity must be jointly set")
        if len(self.checkpoints) > self.checkpoint_capacity:
            raise ValueError("checkpoints exceed their declared capacity")
        checkpoint_opportunities = (
            0
            if self.checkpoint_interval == 0
            else (len(self.events) - int(self.truncated))
            // self.checkpoint_interval
        )
        if len(self.checkpoints) != min(
            checkpoint_opportunities,
            self.checkpoint_capacity,
        ):
            raise ValueError("checkpoint count does not match recorded events")
        if self.checkpoints_truncated != (
            checkpoint_opportunities > self.checkpoint_capacity
        ):
            raise ValueError("checkpoints_truncated is inconsistent")
        for checkpoint in self.checkpoints:
            if type(checkpoint) is not SolverTraceCheckpoint:
                raise TypeError(
                    "checkpoints must contain SolverTraceCheckpoint values"
                )
            if len(checkpoint.domains) != area:
                raise ValueError("checkpoint domains length must match trace area")
        replay_solver_trace(self)


def _validate_domains(domains: tuple[int, ...], label: str) -> None:
    for domain in domains:
        if type(domain) is not int or not 0 <= domain <= DOMAIN_ALL:
            raise ValueError(f"{label} must contain canonical Wang domains")


def replay_solver_trace(
    trace: SolverTrace,
) -> tuple[tuple[int, ...], ...]:
    """Replay the recorded prefix and return the state after every event.

    The terminal result never mutates state. For a truncated trace the returned
    terminal state is the last reconstructable prefix, not an invented final
    solver state.
    """
    domains = list(trace.initial_domains)
    changes: list[tuple[int, int]] = []
    search_change_floor: int | None = None
    states: list[tuple[int, ...]] = []
    checkpoints = {item.event_sequence: item for item in trace.checkpoints}
    if len(checkpoints) != len(trace.checkpoints):
        raise ValueError("checkpoint event sequences must be unique")

    for index, event in enumerate(trace.events):
        if event.cell is not None and event.cell >= len(domains):
            raise ValueError("trace event cell lies outside the trace")
        if event.phase == TRACE_SEARCH:
            if search_change_floor is None:
                search_change_floor = len(changes)
        elif event.phase == TRACE_INITIAL and search_change_floor is not None:
            raise ValueError("initial phase cannot follow search")
        if event.kind != TRACE_RESULT and event.status is not None:
            raise ValueError("only the result event may publish a status")
        if event.kind != TRACE_DOMAIN_REDUCTION and event.reason is not None:
            raise ValueError("only domain reduction may publish a reason")
        if event.kind not in (TRACE_DECISION, TRACE_DOMAIN_REDUCTION) and (
            event.old_domain is not None or event.new_domain is not None
        ):
            raise ValueError("only decision and reduction may publish domains")
        if event.kind == TRACE_ROOT:
            if index != 0 or event.phase != TRACE_INITIAL:
                raise ValueError("root must be the first initial-phase event")
            if event.cell is not None or event.change_mark != 0 or event.depth != 0:
                raise ValueError("root fields are inconsistent")
        elif event.kind == TRACE_DOMAIN_REDUCTION:
            if event.phase not in TRACE_PHASES or event.reason not in TRACE_REASONS:
                raise ValueError("domain reduction requires phase and reason")
            if event.cell is None:
                raise ValueError("domain reduction cell lies outside the trace")
            if event.old_domain is None or event.new_domain is None:
                raise ValueError("domain reduction requires old and new domains")
            if domains[event.cell] != event.old_domain:
                raise ValueError("domain reduction old_domain does not match replay")
            if event.new_domain == event.old_domain or (
                event.new_domain & ~event.old_domain
            ):
                raise ValueError("domain reduction must remove at least one tile")
            changes.append((event.cell, event.old_domain))
            domains[event.cell] = event.new_domain
            if event.change_mark != len(changes):
                raise ValueError("domain reduction change_mark is inconsistent")
        elif event.kind == TRACE_BACKTRACK:
            if (
                event.phase != TRACE_SEARCH
                or search_change_floor is None
                or not search_change_floor <= event.change_mark <= len(changes)
            ):
                raise ValueError("backtrack change_mark is inconsistent")
            while len(changes) > event.change_mark:
                cell, old_domain = changes.pop()
                domains[cell] = old_domain
        elif not (
            event.kind == TRACE_RESULT
            and trace.truncated
            and event.sequence != index
        ):
            if event.change_mark != len(changes):
                raise ValueError("trace event change_mark is inconsistent")

        if event.kind == TRACE_DECISION:
            if event.phase != TRACE_SEARCH or event.cell is None:
                raise ValueError("decision requires a search-phase cell")
            if event.old_domain != domains[event.cell]:
                raise ValueError("decision old_domain does not match replay")
            if event.new_domain is None or event.new_domain == 0 or (
                event.new_domain & (event.new_domain - 1)
            ):
                raise ValueError("decision new_domain must be a singleton")
            if event.old_domain is None or event.new_domain & ~event.old_domain:
                raise ValueError("decision must select from its old domain")
            next_event = trace.events[index + 1]
            if next_event.sequence == event.sequence + 1 and not (
                next_event.kind == TRACE_DOMAIN_REDUCTION
                and next_event.phase == event.phase
                and next_event.reason == TRACE_REASON_DECISION
                and next_event.depth == event.depth
                and next_event.cell == event.cell
                and next_event.old_domain == event.old_domain
                and next_event.new_domain == event.new_domain
            ):
                raise ValueError(
                    "decision does not match its following domain reduction"
                )
        elif event.kind == TRACE_PROPAGATION:
            if event.phase not in TRACE_PHASES:
                raise ValueError("propagation requires a phase")
            if (event.phase == TRACE_INITIAL) != (event.cell is None):
                raise ValueError("propagation cell does not match its phase")
            if event.phase == TRACE_INITIAL and event.depth != 0:
                raise ValueError("initial propagation must have depth zero")
        elif event.kind == TRACE_CONFLICT:
            if event.phase not in TRACE_PHASES or event.cell is None:
                raise ValueError("conflict requires a phase and cell")
            if event.cell >= len(domains) or domains[event.cell] != 0:
                raise ValueError("conflict cell must have the empty domain")
        elif event.kind == TRACE_RESULT:
            if event is not trace.events[-1] or event.phase is not None:
                raise ValueError("result must be the terminal phase-less event")
            if event.status is not trace.status:
                raise ValueError("result status does not match the trace")
            if (trace.status is TilingSolveStatus.SAT) != (event.cell is None):
                raise ValueError("result cell does not match the solve status")

        state = tuple(domains)
        checkpoint = checkpoints.get(event.sequence)
        if checkpoint is not None:
            if checkpoint.change_mark != len(changes):
                raise ValueError("checkpoint change_mark does not match replay")
            if checkpoint.domains != state:
                raise ValueError("checkpoint domains do not match replay")
        states.append(state)

    recorded_sequences = {event.sequence for event in trace.events}
    if any(
        checkpoint.event_sequence not in recorded_sequences
        for checkpoint in trace.checkpoints
    ):
        raise ValueError("checkpoint must reference a recorded event")
    return tuple(states)
