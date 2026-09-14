from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from asyncpg import Connection, Pool, Record
from asyncpg.pool import PoolConnectionProxy
from hatchet_sdk import Context, Depends, Hatchet
from pydantic import BaseModel

from pushover import PushoverClient
from settings import Settings
from slack import SlackClient

hatchet = Hatchet()


class Lifespan:
    def __init__(
        self,
        pool: Pool,
        slack: SlackClient,
        pushover: PushoverClient | None,
        settings: Settings,
    ) -> None:
        self.pool = pool
        self.slack = slack
        self.pushover = pushover
        self.settings = settings


def lifespan_dep(
    _i: BaseModel,
    ctx: Context,
) -> Lifespan:
    return cast(Lifespan, ctx.lifespan)


LifespanDep = Annotated[Lifespan, Depends(lifespan_dep)]


@asynccontextmanager
async def connection(
    _i: BaseModel,
    ctx: Context,
    lifespan: LifespanDep,
) -> "AsyncGenerator[PoolConnectionProxy[Record], None]":
    async with lifespan.pool.acquire() as conn, conn.transaction():
        yield conn


ConnectionDep = Annotated[Connection, Depends(connection)]
