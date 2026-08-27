"""Immutable provenance for one native Yang-Zhang reduction build."""

from dataclasses import dataclass
from typing import Final


SIGNAL_VARIABLE: Final = "variable"
SIGNAL_REDUNDANT: Final = "redundant"
SIGNAL_KINDS: Final = frozenset({SIGNAL_VARIABLE, SIGNAL_REDUNDANT})

GADGET_VARIABLE: Final = "variable"
GADGET_LEFT_FORWARD: Final = "left_forward"
GADGET_CROSSOVER: Final = "crossover"
GADGET_RIGHT_FORWARD: Final = "right_forward"
GADGET_CLAUSE: Final = "clause"
GADGET_KINDS: Final = frozenset(
    {
        GADGET_VARIABLE,
        GADGET_LEFT_FORWARD,
        GADGET_CROSSOVER,
        GADGET_RIGHT_FORWARD,
        GADGET_CLAUSE,
    }
)


@dataclass(frozen=True, slots=True)
class ReductionSignal:
    """One logical signal token at one zero-based row."""

    row: int
    kind: str
    token_id: int
    variable: int | None
    occurrence: int | None

    def __post_init__(self) -> None:
        if type(self.row) is not int or self.row < 0:
            raise ValueError("signal row must be a nonnegative integer")
        if type(self.kind) is not str or self.kind not in SIGNAL_KINDS:
            raise ValueError("signal kind is invalid")
        if type(self.token_id) is not int or self.token_id < 0:
            raise ValueError("signal token_id must be a nonnegative integer")
        if self.kind == SIGNAL_VARIABLE:
            if type(self.variable) is not int or self.variable < 0:
                raise ValueError("variable signal must identify a variable")
            if type(self.occurrence) is not int or not 0 <= self.occurrence < 3:
                raise ValueError("variable occurrence must be 0, 1, or 2")
        elif self.variable is not None or self.occurrence is not None:
            raise ValueError("redundant signal cannot identify a variable occurrence")

    @property
    def identity(self) -> tuple[str, int, int | None, int | None]:
        """Return the row-independent logical identity of this token."""

        return (self.kind, self.token_id, self.variable, self.occurrence)


@dataclass(frozen=True, slots=True)
class ReductionGadget:
    """One semantic gadget rectangle using half-open coordinates."""

    kind: str
    ordinal: int
    x_begin: int
    x_end: int
    y_begin: int
    y_end: int
    swap_row: int | None

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in GADGET_KINDS:
            raise ValueError("gadget kind is invalid")
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("gadget ordinal must be a nonnegative integer")
        for name in ("x_begin", "x_end", "y_begin", "y_end"):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"gadget {name} must be an integer")
        if self.x_begin < 0 or self.x_end <= self.x_begin:
            raise ValueError("gadget x interval must be nonempty and nonnegative")
        if self.y_begin < 0 or self.y_end <= self.y_begin:
            raise ValueError("gadget y interval must be nonempty and nonnegative")
        if self.kind == GADGET_CROSSOVER:
            if type(self.swap_row) is not int or self.swap_row < 0:
                raise ValueError("crossover gadget must identify its swap row")
            if self.x_end - self.x_begin != self.swap_row + 1:
                raise ValueError("crossover width must equal swap_row + 1")
        elif self.swap_row is not None:
            raise ValueError("only crossover gadgets can identify a swap row")


@dataclass(frozen=True, slots=True)
class ReductionExplanation:
    """Copied provenance with no native pointers or rendering metadata."""

    variable_count: int
    width: int
    height: int
    source_signals: tuple[ReductionSignal, ...]
    target_signals: tuple[ReductionSignal, ...]
    gadgets: tuple[ReductionGadget, ...]

    def __post_init__(self) -> None:
        if type(self.variable_count) is not int or self.variable_count <= 0:
            raise ValueError("variable_count must be a positive integer")
        if type(self.width) is not int or self.width <= 0:
            raise ValueError("width must be a positive integer")
        if type(self.height) is not int or self.height <= 0:
            raise ValueError("height must be a positive integer")
        if type(self.source_signals) is not tuple:
            raise TypeError("source_signals must be a tuple")
        if type(self.target_signals) is not tuple:
            raise TypeError("target_signals must be a tuple")
        if type(self.gadgets) is not tuple:
            raise TypeError("gadgets must be a tuple")
        if self.height != 4 * self.variable_count - 1:
            raise ValueError("signal height must equal 4 * variable_count - 1")
        if len(self.source_signals) != self.height:
            raise ValueError("source signal count must equal the region height")
        if len(self.target_signals) != self.height:
            raise ValueError("target signal count must equal the region height")

        source_ids = self._validate_signal_sequence(
            self.source_signals,
            "source",
        )
        target_ids = self._validate_signal_sequence(
            self.target_signals,
            "target",
        )
        if source_ids != target_ids:
            raise ValueError("source and target must contain the same signal tokens")

        for gadget in self.gadgets:
            if type(gadget) is not ReductionGadget:
                raise TypeError("gadgets must contain ReductionGadget values")
            if gadget.x_end > self.width or gadget.y_end > self.height:
                raise ValueError("gadget rectangle must lie inside the region bounds")

        crossovers = tuple(
            gadget
            for gadget in self.gadgets
            if gadget.kind == GADGET_CROSSOVER
        )
        if tuple(gadget.ordinal for gadget in crossovers) != tuple(
            range(len(crossovers))
        ):
            raise ValueError("crossover ordinals must be contiguous and ordered")
        replay = [signal.identity for signal in self.source_signals]
        for gadget in crossovers:
            swap_row = gadget.swap_row
            if swap_row is None:
                raise ValueError("crossover gadget is missing its swap row")
            if swap_row >= self.height - 1:
                raise ValueError("crossover swap row lies outside the signal rows")
            replay[swap_row], replay[swap_row + 1] = (
                replay[swap_row + 1],
                replay[swap_row],
            )
        if tuple(replay) != tuple(
            signal.identity for signal in self.target_signals
        ):
            raise ValueError("crossover program does not produce target signals")

        self._validate_gadget_population(GADGET_VARIABLE, self.variable_count)
        self._validate_gadget_population(GADGET_CLAUSE, self.variable_count)
        self._validate_gadget_population(GADGET_LEFT_FORWARD, 1)
        self._validate_gadget_population(GADGET_RIGHT_FORWARD, 1)

    def _validate_signal_sequence(
        self,
        signals: tuple[ReductionSignal, ...],
        label: str,
    ) -> frozenset[tuple[str, int, int | None, int | None]]:
        identities: set[tuple[str, int, int | None, int | None]] = set()
        token_ids: set[int] = set()
        occurrences: list[set[int]] = [set() for _ in range(self.variable_count)]
        redundant = 0
        for row, signal in enumerate(signals):
            if type(signal) is not ReductionSignal:
                raise TypeError(f"{label} signals must contain ReductionSignal values")
            if signal.row != row:
                raise ValueError(f"{label} signal rows must be contiguous and ordered")
            if signal.identity in identities:
                raise ValueError(f"{label} signal tokens must be unique")
            if signal.token_id in token_ids:
                raise ValueError(f"{label} signal token IDs must be unique")
            identities.add(signal.identity)
            token_ids.add(signal.token_id)
            if signal.kind == SIGNAL_VARIABLE:
                variable = signal.variable
                occurrence = signal.occurrence
                if variable is None or occurrence is None:
                    raise ValueError(f"{label} variable signal lacks an identity")
                if variable >= self.variable_count:
                    raise ValueError(f"{label} signal variable is outside the formula")
                occurrences[variable].add(occurrence)
            else:
                redundant += 1
        if any(values != {0, 1, 2} for values in occurrences):
            raise ValueError(
                f"{label} must contain occurrences 0, 1, and 2 per variable"
            )
        if redundant != self.variable_count - 1:
            raise ValueError(f"{label} has an invalid redundant signal count")
        return frozenset(identities)

    def _validate_gadget_population(self, kind: str, expected: int) -> None:
        gadgets = tuple(gadget for gadget in self.gadgets if gadget.kind == kind)
        if len(gadgets) != expected:
            raise ValueError(f"expected {expected} {kind} gadgets")
        if tuple(gadget.ordinal for gadget in gadgets) != tuple(range(expected)):
            raise ValueError(f"{kind} gadget ordinals must be contiguous and ordered")
