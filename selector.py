import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path


DEFAULT_BATCH_SIZE = 10
DEFAULT_TARGET_AVG = 6.0

RANDOM_ATTEMPTS = 100


def count_words(text):
    if not text:
        return 0

    return len(
        re.findall(
            r"[\wáàâãéèêíïóôõöúçñ]+(?:['-][\wáàâãéèêíïóôõöúçñ]+)*", text, re.IGNORECASE
        )
    )


def sentence_lengths(text):
    if not text:
        return []

    sentences = re.split(r"[.!?]+", text)

    result = []

    for sentence in sentences:
        sentence = sentence.strip()

        if sentence:
            result.append(count_words(sentence))

    return result


def average_sentence_length(en, pt):
    lengths = sentence_lengths(en) + sentence_lengths(pt)

    if not lengths:
        return 0.0, 0

    return sum(lengths) / len(lengths), len(lengths)


def text_score(en, pt, target):

    avg, _ = average_sentence_length(en, pt)

    return abs(avg - target)


def load_json_line(line):

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj, dict):
        return None

    if "id" not in obj:
        return None

    if "en" not in obj or "pt" not in obj:
        return None

    return obj


def create_database(db_path):
    conn = sqlite3.connect(db_path)

    conn.execute("""PRAGMA journal_mode=WAL; """)

    conn.execute("""PRAGMA synchronous=NORMAL;""")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE
        )"""
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            line_number INTEGER NOT NULL,
            json TEXT NOT NULL,
            avg_sentence_length REAL,
            sentence_count INTEGER,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS selected (
            id INTEGER PRIMARY KEY,
            selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_records_file
        ON records(file_id)
    """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_records_avg
        ON records(avg_sentence_length)
    """
    )

    conn.commit()

    return conn


def already_indexed(conn, path):
    row = conn.execute("SELECT id FROM files WHERE path = ?", (str(path),)).fetchone()

    return row is not None


def index_file(conn, path):
    print(f"\nIndexando: {path}")

    if already_indexed(conn, path):
        print("Já indexado. Pulando.")
        return

    cursor = conn.cursor()

    cursor.execute("INSERT INTO files(path) VALUES (?)", (str(path),))

    file_id = cursor.lastrowid

    count = 0
    valid = 0

    with open(path, "r", encoding="utf-8") as f:

        for line_number, line in enumerate(f, start=1):

            count += 1

            obj = load_json_line(line)

            if obj is None:
                continue

            avg, sentence_count = average_sentence_length(obj["en"], obj["pt"])
            cursor.execute(
                """
                INSERT OR IGNORE INTO records
                (
                    id,
                    file_id,
                    line_number,
                    json,
                    avg_sentence_length,
                    sentence_count
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    obj["id"],
                    file_id,
                    line_number,
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    avg,
                    sentence_count,
                ),
            )

            valid += 1

            if valid % 10000 == 0:
                conn.commit()

                print(
                    f"\r  Linhas: {count:,} | " f"registros válidos: {valid:,}",
                    end="",
                    flush=True,
                )

    conn.commit()

    print(f"\n  Concluído: {count:,} linhas | " f"{valid:,} registros válidos")


def index_directory(conn, directory):

    directory = Path(directory)

    files = sorted(directory.glob("*.jsonl"))

    if not files:
        print(f"Nenhum .jsonl encontrado em {directory}")
        sys.exit(1)

    print(f"Encontrados {len(files)} arquivos JSONL.")

    for path in files:
        index_file(conn, path)


# ============================================================
# CONSULTAS
# ============================================================


def selected_ids(conn):
    """
    Retorna os IDs já selecionados.
    """

    rows = conn.execute("SELECT id FROM selected").fetchall()

    return {row[0] for row in rows}


def total_records(conn):
    return conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]


def total_selected(conn):
    return conn.execute("SELECT COUNT(*) FROM selected").fetchone()[0]


def get_random_candidates(conn, target, amount=10):
    """
    Busca candidatos aleatórios.

    Para não ter que gerar um ORDER BY RANDOM() sobre milhões
    de linhas, fazemos uma aproximação baseada no ID.

    Primeiro descobrimos a faixa de IDs e depois buscamos
    registros próximos de IDs aleatórios.
    """

    row = conn.execute(
        """
        SELECT MIN(id), MAX(id)
        FROM records
        WHERE id NOT IN (SELECT id FROM selected)
    """
    ).fetchone()

    if not row or row[0] is None:
        return []

    min_id, max_id = row

    candidates = {}

    # Primeiro tentamos encontrar candidatos próximos da média alvo.
    #
    # Isso faz com que a lista normalmente contenha frases
    # próximas de 6 palavras, mas ainda exista aleatoriedade.

    for _ in range(RANDOM_ATTEMPTS):

        if len(candidates) >= amount:
            break

        random_id = random.randint(min_id, max_id)

        rows = conn.execute(
            """
            SELECT
                id,
                json,
                avg_sentence_length,
                sentence_count
            FROM records
            WHERE id >= ?
              AND id NOT IN (SELECT id FROM selected)
            ORDER BY id
            LIMIT 3
        """,
            (random_id,),
        ).fetchall()

        for row in rows:

            record_id = row[0]

            if record_id in candidates:
                continue

            candidates[record_id] = row

            if len(candidates) >= amount:
                break

    # Se não encontramos candidatos suficientes,
    # completamos com registros aleatórios aproximados pelo target.
    if len(candidates) < amount:

        rows = conn.execute(
            """
            SELECT
                id,
                json,
                avg_sentence_length,
                sentence_count
            FROM records
            WHERE id NOT IN (SELECT id FROM selected)
            ORDER BY ABS(avg_sentence_length - ?)
            LIMIT ?
        """,
            (target, amount * 5),
        ).fetchall()

        random.shuffle(rows)

        for row in rows:

            if row[0] not in candidates:
                candidates[row[0]] = row

            if len(candidates) >= amount:
                break

    candidates = list(candidates.values())

    # Mistura novamente para que não fique ordenado por proximidade.
    random.shuffle(candidates)

    return candidates[:amount]


# ============================================================
# SELEÇÃO
# ============================================================


def print_candidate(index, row):
    """
    Mostra um candidato na tela.
    """

    record_id, json_text, avg, sentence_count = row

    try:
        obj = json.loads(json_text)
    except Exception:
        return

    print()
    print("=" * 80)
    print(f"[{index}] ID: {record_id}")
    print(f"Média: {avg:.2f} palavras/frase | " f"Frases: {sentence_count}")

    print()
    print("EN:")
    print(obj.get("en", ""))

    print()
    print("PT:")
    print(obj.get("pt", ""))


def select_candidates(conn, output_file, target, batch_size):
    """
    Loop interativo principal.
    """

    print()
    print("=" * 80)
    print("SELETOR INTERATIVO")
    print("=" * 80)

    while True:

        selected_count = total_selected(conn)
        total = total_records(conn)

        print()
        print(f"Selecionados: {selected_count:,} / " f"{total:,}")

        candidates = get_random_candidates(conn, target, batch_size)

        if not candidates:
            print("\nNão existem mais registros disponíveis.")
            break

        print(
            f"\nMostrando {len(candidates)} candidatos "
            f"(alvo: {target:.1f} palavras/frase)"
        )

        for i, row in enumerate(candidates, start=1):
            print_candidate(i, row)

        print()
        print("-" * 80)
        print("Digite os números que deseja selecionar.")
        print("Exemplo: 1,3,7")
        print()
        print("Comandos:")
        print("  q       = sair")
        print("  r       = mostrar outra rodada")
        print("  stats   = estatísticas")
        print("-" * 80)

        answer = input("\nSeleção: ").strip().lower()

        if answer == "q":
            print("Saindo...")
            break

        if answer == "r":
            continue

        if answer == "stats":
            show_stats(conn)
            continue

        if not answer:
            continue

        # Aceita:
        # 1,2,3
        # 1 2 3
        # 1, 3, 7
        answer = answer.replace(",", " ")

        try:
            indexes = [int(x) for x in answer.split()]
        except ValueError:
            print("Entrada inválida.")
            continue

        chosen = []

        for index in indexes:

            if index < 1 or index > len(candidates):
                print(f"Índice inválido: {index}")
                continue

            row = candidates[index - 1]

            if row not in chosen:
                chosen.append(row)

        if not chosen:
            print("Nenhum candidato selecionado.")
            continue

        save_selected(conn, chosen, output_file)

        print(f"\n{len(chosen)} registro(s) adicionados.")


# ============================================================
# SALVAR SELECIONADOS
# ============================================================


def save_selected(conn, rows, output_file):
    """
    Salva os registros selecionados:

    1. adiciona o ID ao SQLite;
    2. faz append no JSONL final.

    O SQLite é atualizado antes do próximo ciclo.
    """

    output_file = Path(output_file)

    # Criamos o diretório caso necessário.
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "a", encoding="utf-8") as f:

        for row in rows:

            record_id = row[0]
            json_text = row[1]

            # INSERT OR IGNORE protege contra duplicação.
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO selected(id)
                VALUES (?)
            """,
                (record_id,),
            )

            # Só escreve no arquivo se realmente foi inserido.
            if cursor.rowcount == 1:

                f.write(json_text)
                f.write("\n")

    conn.commit()


# ============================================================
# ESTATÍSTICAS
# ============================================================


def show_stats(conn):

    total = total_records(conn)
    selected = total_selected(conn)

    print()
    print("=" * 60)
    print("ESTATÍSTICAS")
    print("=" * 60)

    print(f"Total de registros: {total:,}")
    print(f"Selecionados:       {selected:,}")
    print(f"Restantes:          {total - selected:,}")

    if selected:
        row = conn.execute(
            """
            SELECT
                AVG(r.avg_sentence_length),
                MIN(r.avg_sentence_length),
                MAX(r.avg_sentence_length)
            FROM records r
            INNER JOIN selected s
                ON s.id = r.id
        """
        ).fetchone()

        print()
        print(f"Média dos selecionados: {row[0]:.2f}")
        print(f"Menor média:             {row[1]:.2f}")
        print(f"Maior média:             {row[2]:.2f}")

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================


def main():

    parser = argparse.ArgumentParser(
        description=("Seletor interativo de pares EN/PT em JSONL " "com SQLite.")
    )

    parser.add_argument(
        "--input", required=True, help="Diretório contendo os arquivos .jsonl"
    )

    parser.add_argument("--output", default="samples.jsonl", help="Arquivo JSONL final")

    parser.add_argument("--db", default="samples.db", help="Banco SQLite")

    parser.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Quantidade de candidatos por rodada",
    )

    parser.add_argument(
        "--target",
        type=float,
        default=DEFAULT_TARGET_AVG,
        help="Média desejada de palavras por frase",
    )

    parser.add_argument(
        "--reindex", action="store_true", help="Força recriação do índice"
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Banco
    # --------------------------------------------------------

    if args.reindex:

        db_path = Path(args.db)

        if db_path.exists():
            print(f"Removendo banco: {db_path}")
            db_path.unlink()

    conn = create_database(args.db)

    try:

        # ----------------------------------------------------
        # Indexação
        # ----------------------------------------------------

        index_directory(conn, args.input)

        # ----------------------------------------------------
        # Estatísticas iniciais
        # ----------------------------------------------------

        show_stats(conn)

        # ----------------------------------------------------
        # Seleção
        # ----------------------------------------------------

        select_candidates(conn, args.output, args.target, args.batch)

    finally:

        conn.close()


if __name__ == "__main__":
    main()
