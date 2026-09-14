from __future__ import annotations

import asyncio
import os
import types
import typing
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from aiosql.adapters.asyncpg import AsyncPGAdapter
from aiosql.query_loader import QueryLoader
from aiosql.types import QueryDatum

import db
from internal.types import IncidentStatus

SCHEMA = Path(__file__).parent.parent / "schema.sql"
ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL", "postgresql://incident:incident@localhost:5499/postgres"
)

# postgres result type -> python type the model field should declare
PG_TYPES: dict[str, object] = {
    "int2": int,
    "int4": int,
    "int8": int,
    "bool": bool,
    "text": str,
    "varchar": str,
    "uuid": UUID,
    "timestamptz": datetime,
    "int8[]": list[int],
    "incident_status": IncidentStatus,
}

# aiosql's AsyncPGAdapter doesn't quite match its own adapter protocol
_loader = QueryLoader(AsyncPGAdapter(), db.RECORD_CLASSES)  # ty: ignore[invalid-argument-type]

# queries/ is flat, so there are no nested namespaces (dicts) in the tree
QUERIES = [
    query
    for query in _loader.load_query_data_from_dir_path(db.QUERIES_DIR).values()
    if isinstance(query, QueryDatum)
]


@pytest.fixture(scope="module")
def conn() -> Iterator[tuple[asyncio.AbstractEventLoop, asyncpg.Connection]]:
    loop = asyncio.new_event_loop()
    name = f"incident_test_{uuid4().hex}"

    try:
        admin = loop.run_until_complete(asyncpg.connect(ADMIN_URL))
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"no postgres at {ADMIN_URL}: {e}")

    loop.run_until_complete(admin.execute(f'CREATE DATABASE "{name}"'))
    test_conn = loop.run_until_complete(asyncpg.connect(ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"))

    try:
        loop.run_until_complete(test_conn.execute(SCHEMA.read_text()))
        yield loop, test_conn
    finally:
        loop.run_until_complete(test_conn.close())
        loop.run_until_complete(admin.execute(f'DROP DATABASE "{name}"'))
        loop.run_until_complete(admin.close())
        loop.close()


def _base_type(annotation: object) -> object:
    """Strip `| None` and unwrap NewTypes (e.g. `IncidentId | None` -> `UUID`), including in lists."""
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _base_type(args[0]) if len(args) == 1 else annotation

    if isinstance(annotation, typing.NewType):
        return _base_type(annotation.__supertype__)

    if typing.get_origin(annotation) is list:
        (item,) = typing.get_args(annotation)
        return list[_base_type(item)]  # ty: ignore[invalid-type-form]

    return annotation


def test_queries_loaded() -> None:
    assert QUERIES, "no queries found"


@pytest.mark.parametrize("query", QUERIES, ids=lambda q: q.query_name)
def test_query(
    query: QueryDatum, conn: tuple[asyncio.AbstractEventLoop, asyncpg.Connection]
) -> None:
    loop, connection = conn
    statement = loop.run_until_complete(connection.prepare(query.sql))

    if query.record_class is None:
        return

    columns = {attr.name: attr.type for attr in statement.get_attributes()}
    fields = query.record_class.model_fields

    assert set(columns) == set(fields), (
        f"{query.query_name}: columns {sorted(columns)} != "
        f"{query.record_class.__name__} fields {sorted(fields)}"
    )

    for name, pg_type in columns.items():
        expected = PG_TYPES.get(pg_type.name)
        assert expected is not None, f"{query.query_name}.{name}: unmapped type {pg_type.name}"

        actual = _base_type(fields[name].annotation)
        assert actual == expected, (
            f"{query.query_name}.{name}: postgres {pg_type.name} returns {expected}, "
            f"but {query.record_class.__name__}.{name} is {actual}"
        )
