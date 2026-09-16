import asyncio
import sqlite3
import threading

import pytest

from fle.commons.db_client import SQLliteDBClient, create_default_sqlite_db

pytestmark = pytest.mark.no_factorio


def _table_names(path):
    conn = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()


def test_create_default_sqlite_db_repairs_existing_empty_file(tmp_path):
    db_file = tmp_path / "data.db"
    create_default_sqlite_db(str(db_file))
    assert "programs" in _table_names(str(db_file))

    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("DROP TABLE programs")

    create_default_sqlite_db(str(db_file))
    assert "programs" in _table_names(str(db_file))


def test_cleanup_closes_connections_from_all_threads(tmp_path):
    db_file = tmp_path / "data.db"
    create_default_sqlite_db(str(db_file))
    client = SQLliteDBClient(database_file=str(db_file))

    with client.get_connection() as conn:
        main_connection = conn

    created = {}

    def worker():
        with client.get_connection() as conn:
            created["connection"] = conn

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    asyncio.run(client.cleanup())

    for connection in (main_connection, created["connection"]):
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


def test_connection_reopens_when_database_file_changes(tmp_path):
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    create_default_sqlite_db(str(first))
    create_default_sqlite_db(str(second))
    client = SQLliteDBClient(database_file=str(first))

    with client.get_connection() as first_connection:
        pass

    client.database_file = str(second)
    with client.get_connection() as second_connection:
        assert second_connection is not first_connection
        assert (
            second_connection.execute(
                "SELECT name FROM sqlite_master WHERE name='programs'"
            ).fetchone()
            is not None
        )

    with pytest.raises(sqlite3.ProgrammingError):
        first_connection.execute("SELECT 1")
