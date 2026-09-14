from __future__ import annotations

import math
from datetime import datetime, timedelta

import db
from internal.types import Override, Rotation, Shift


def rotation_shifts(rotation: Rotation, start: datetime, end: datetime) -> list[Shift]:
    period = timedelta(days=rotation.period_days)
    members = rotation.member_ids
    depth = min(db.ESCALATION_LEVELS, len(members))

    first_window = max(0, math.floor((start - rotation.anchor) / period))
    shifts: list[Shift] = []

    k = first_window
    while (window_start := rotation.anchor + k * period) < end:
        for priority in range(1, depth + 1):
            shifts.append(
                Shift(
                    team_member_id=members[(k + priority - 1) % len(members)],
                    escalation_priority=priority,
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
            if o.escalation_priority != shift.escalation_priority:
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
            escalation_priority=o.escalation_priority,
            start=o.start,
            end=o.end,
            override_id=o.id,
        )
        for o in overrides
    )

    return sorted(result, key=lambda s: (s.start, s.escalation_priority))


def build_schedule(
    rotation: Rotation | None, overrides: list[Override], start: datetime, end: datetime
) -> list[Shift]:
    scheduled = rotation_shifts(rotation, start, end) if rotation else []
    return apply_overrides(scheduled, overrides)
