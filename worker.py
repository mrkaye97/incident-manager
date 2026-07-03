from hatchet_sdk import Hatchet, EmptyModel, Context
from asyncpg import connect, Connection
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import AsyncGenerator, cast


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Lifespan:
    def __init__(self, conn: Connection):
        self.conn = conn


hatchet = Hatchet()


@hatchet.task(on_events=["slack:/incident-bot-test"])
async def simple(_i: EmptyModel, _c: Context) -> None:
    print("Hello, world!")
    return None


async def lifespan() -> AsyncGenerator[Lifespan, None]:
    print("Starting lifespan...")
    settings = Settings()
    conn = cast(Connection, await connect(dsn=settings.database_url))
    print("Connected to database.")
    try:
        ls = Lifespan(conn)
        yield ls
    finally:
        await conn.close()


def main() -> None:
    worker = hatchet.worker(name="incident-bot", workflows=[simple], lifespan=lifespan)
    worker.start()


if __name__ == "__main__":
    main()
