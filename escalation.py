from __future__ import annotations

from datetime import timedelta

from asyncpg import Connection
from hatchet_sdk import Context, DurableContext

import actions
import db
from hatchet_client import ConnectionDep, LifespanDep, hatchet
from internal.types import (
    Actor,
    EscalatePageInput,
    EscalationStepInput,
    EscalationStepResult,
    IncidentStatus,
    Page,
    PageMemberInput,
)
from pushover import PushoverClient
from slack import SlackClient

ESCALATION_DELAY = timedelta(minutes=5)
MAX_ESCALATIONS = 12
ESCALATION_ACTOR = Actor(name="Escalation")


async def page_and_escalate(
    conn: Connection,
    slack: SlackClient,
    pushover: PushoverClient | None,
    input: PageMemberInput,
) -> Page:
    page = await actions.page_member(conn, slack, pushover, input)
    await escalate_page.aio_run(EscalatePageInput(root_page_id=page.id), wait_for_result=False)
    return page


async def run_escalation_step(
    conn: Connection,
    slack: SlackClient,
    pushover: PushoverClient | None,
    input: EscalationStepInput,
) -> EscalationStepResult:
    state = await db.get_escalation_state(conn, input.root_page_id, input.step)

    if state is None or state.acknowledged or state.incident_status == IncidentStatus.RESOLVED:
        return EscalationStepResult(done=True)

    if state.step_done:
        return EscalationStepResult(done=False)

    oncall = list(dict.fromkeys(o.team_member_id for o in await db.current_oncall(conn)))

    if not oncall:
        return EscalationStepResult(done=True)

    start = oncall.index(state.root_member_id) if state.root_member_id in oncall else -1
    minutes = int(ESCALATION_DELAY.total_seconds() // 60) * input.step

    await actions.page_member(
        conn,
        slack,
        pushover,
        PageMemberInput(
            team_member_id=oncall[(start + input.step) % len(oncall)],
            incident_id=state.incident_id,
            reason=f"not acknowledged after {minutes} minutes",
            actor=ESCALATION_ACTOR,
            root_page_id=state.root_page_id,
            escalation_step=input.step,
        ),
    )

    return EscalationStepResult(done=False)


@hatchet.task(input_validator=EscalationStepInput, retries=3)
async def escalation_step(
    input: EscalationStepInput,
    _ctx: Context,
    conn: ConnectionDep,
    lifespan: LifespanDep,
) -> EscalationStepResult:
    return await run_escalation_step(conn, lifespan.slack, lifespan.pushover, input)


@hatchet.durable_task(
    input_validator=EscalatePageInput,
    execution_timeout=ESCALATION_DELAY * (MAX_ESCALATIONS + 1),
)
async def escalate_page(input: EscalatePageInput, ctx: DurableContext) -> EscalationStepResult:
    for step in range(1, MAX_ESCALATIONS + 1):
        await ctx.aio_sleep_for(ESCALATION_DELAY)
        result = await escalation_step.aio_run(
            EscalationStepInput(root_page_id=input.root_page_id, step=step)
        )

        if result.done:
            return result

    return EscalationStepResult(done=True)
