from __future__ import annotations

import math
from datetime import datetime, timedelta

from internal.types import Override, Rotation, Shift


def rotation_shifts(rotation: Rotation, start: datetime, end: datetime) -> list[Shift]:
    period = timedelta(days=rotation.period_days)
    members = rotation.member_ids
    shifts: list[Shift] = []

    k = max(0, math.floor((start - rotation.anchor) / period))
    while (window_start := rotation.anchor + k * period) < end:
        shifts.append(
            Shift(
                team_member_id=members[k % len(members)],
                level=rotation.level,
                start=window_start,
                end=window_start + period,
            )
        )
        k += 1

    return shifts


def apply_overrides(shifts: list[Shift], overrides: list[Override]) -> list[Shift]:
    result: list[Shift] = []

    for shift in shifts:
        pieces = [shift]
        for o in overrides:
            if o.level != shift.level:
                continue
            next_pieces: list[Shift] = []
            for piece in pieces:
                if o.end <= piece.start or o.start >= piece.end:
                    next_pieces.append(piece)
                    continue
                if piece.start < o.start:
                    next_pieces.append(piece.model_copy(update={"end": o.start}))
                if o.end < piece.end:
                    next_pieces.append(piece.model_copy(update={"start": o.end}))
            pieces = next_pieces
        result.extend(pieces)

    result.extend(
        Shift(
            team_member_id=o.team_member_id,
            level=o.level,
            start=o.start,
            end=o.end,
            override_id=o.id,
        )
        for o in overrides
    )

    return sorted(result, key=lambda s: (s.start, s.level))


def build_schedule(
    rotations: list[Rotation], overrides: list[Override], start: datetime, end: datetime
) -> list[Shift]:
    scheduled = [shift for rotation in rotations for shift in rotation_shifts(rotation, start, end)]
    return apply_overrides(scheduled, overrides)
