import sqlite3
from contextlib import contextmanager

DB_PATH = "./db/corpus.db"


def create_database() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                corpus_name TEXT NOT NULL,
                sentence_size INTEGER NOT NULL,
                is_valid BOOLEAN NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_files
            ON files(id)
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_db_connection() -> sqlite3.Connection:
    create_database()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_sentences_count_by_corpus_name(
    conn: sqlite3.Connection, corpus_name: str
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(id) FROM files
        WHERE corpus_name = ? AND is_valid = TRUE
        """,
        (corpus_name,),
    ).fetchone()
    return row[0] if row else 0


def is_sample_already_exists(
    conn: sqlite3.Connection, corpus_id: int, corpus_name: str
) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(id) FROM files
        WHERE id = ? AND corpus_name = ?
        """,
        (corpus_id, corpus_name),
    ).fetchone()

    count = row[0] if row else 0
    if count > 1:
        raise ValueError(
            f"More than one sample id={corpus_id} and corpus={corpus_name}"
        )
    return count == 1


def get_average_by_sentence(conn: sqlite3.Connection, corpus_name: str) -> tuple[int, int]:
    rows = conn.execute(
        """
        SELECT sentence_size FROM files
        WHERE corpus_name = ? AND is_valid = TRUE
        """,
        (corpus_name,),
    ).fetchall()

    sentence_sum = sum(r[0] for r in rows)
    return (sentence_sum, len(rows))


def insert_file(
    conn: sqlite3.Connection,
    id: int,
    corpus_name: str,
    sentence_size: int,
    is_valid: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO files (id, corpus_name, sentence_size, is_valid)
        VALUES (?, ?, ?, ?)
        """,
        (id, corpus_name, sentence_size, is_valid),
    )
    conn.commit()


def delete_file(conn: sqlite3.Connection, id: int, corpus_name: str) -> None:
    conn.execute(
        """
        DELETE FROM files WHERE id = ? AND corpus_name = ?
        """,
        (id, corpus_name),
    )
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise