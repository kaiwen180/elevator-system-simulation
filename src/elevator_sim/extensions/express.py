"""Express elevators that skip floors: layout helpers for `Config.served_floors`."""

from __future__ import annotations

from ..config import Config
from ..models import Request
from ..traffic import LOBBY


def express_bank(floors: int, local: int, express: int, split: int) -> tuple[frozenset[int], ...]:
    """Served floors per elevator: local elevators serve 1 to split, express ones serve the lobby and split + 1 up."""
    if not LOBBY < split < floors:
        raise ValueError(f"split must be between {LOBBY + 1} and {floors - 1}, got {split}")
    low = frozenset(range(LOBBY, split + 1))
    high = frozenset({LOBBY} | set(range(split + 1, floors + 1)))
    return (low,) * local + (high,) * express


def servable(requests: list[Request], config: Config) -> list[Request]:
    """The requests that at least one elevator in the layout serves end to end."""
    kept = []
    for r in requests:
        if any(config.serves(index, r.source, r.dest) for index in range(config.elevators)):
            kept.append(r)
    return kept
