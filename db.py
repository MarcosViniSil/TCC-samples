import sqlite3

DB_PATH = "./db/corpus.db"


def create_database():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""PRAGMA journal_mode=WAL; """)

    conn.execute("""PRAGMA synchronous=NORMAL;""")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            corpus_name TEXT NOT NULL,
            sentence_size INTEGER NOT NULL
        )"""
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_files
        ON files(id)
    """
    )

    conn.commit()

    return conn


def get_db_connection() -> sqlite3.Connection:
    create_database()
    return sqlite3.connect(DB_PATH)


def get_sentences_count_by_corpus_name(
    conn: sqlite3.Connection, corpus_name: str
) -> int:
    row = conn.execute(
        """
            SELECT COUNT(id) AS files FROM files WHERE corpus_name = ?     
            """,
        (corpus_name,),
    ).fetchone()

    return row[0]


def is_sample_already_exists(
    conn: sqlite3.Connection, corpus_id: int, corpus_name: str
) -> bool:
    row = conn.execute(
        """
                SELECT COUNT(id) AS files FROM files WHERE id = ? AND corpus_name = ?    
                """,
        (
            corpus_id,
            corpus_name,
        ),
    ).fetchone()

    if row[0] > 1:
        raise ValueError(
            f"The is more than one sample containing the id: {corpus_id} and the corpus name {corpus_name}"
        )

    return row[0] == 1


def get_average_by_sentence(conn: sqlite3.Connection, corpus_name: str) -> tuple:
    rows = conn.execute(
        """
                SELECT sentence_size FROM files WHERE corpus_name = ?    
                """,
        (corpus_name,),
    ).fetchall()

    n = len(rows)
    sentence_sum = 0
    for row in rows:
        sentence_sum += row[0]

    return (sentence_sum, n)


def insert_file(
    conn: sqlite3.Connection, id: int, corpus_name: str, sentence_size: str
):
    conn.execute(
        """
                INSERT INTO files (id,corpus_name,sentence_size) VALUES (?,?,?)  
                """,
        (id, corpus_name, sentence_size),
    )

    conn.commit()


def delete_file(conn: sqlite3.Connection, id: int, corpus_name: str):
    conn.execute(
        """
                DELETE FORM files WHERE id = ? AND corpus_name = ? 
                """,
        (id, corpus_name),
    )

    conn.commit()
