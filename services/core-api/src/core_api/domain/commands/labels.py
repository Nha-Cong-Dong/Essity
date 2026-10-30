"""Labels `C1..Cn` follow the display order of the request (T9.1 review Y1)."""

import uuid
from collections.abc import Sequence


def label_map(prefix: str, display_order: Sequence[uuid.UUID]) -> dict[str, uuid.UUID]:
    """`{"C1": first, "C2": second, ...}` for the order the screen shows the items in."""
    return {f"{prefix}{i}": id_ for i, id_ in enumerate(display_order, start=1)}
