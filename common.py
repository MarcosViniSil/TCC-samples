import os
from pathlib import Path
import random
from typing import Optional
from prose_tokenizer import tokenize


class CommonFileOperations:

    def __init__(self):
        pass

    @staticmethod
    def get_random_line(file_path: str) :
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return None

        ITERATIONS_UNTIL_FAIL = max(5, min(50, int(file_size * 0.001) or 5))

        with open(file_path, "rb") as file:
            for _ in range(ITERATIONS_UNTIL_FAIL):
                pos = random.randint(0, file_size - 1)
                file.seek(pos)

                file.readline()

                line = file.readline()
                if line.strip():
                    return line.decode("utf-8", errors="replace").strip()

            file.seek(0)
            return file.readline().decode("utf-8", errors="replace").strip()

    @staticmethod
    def get_phrase_number(sentence: str) -> int:
        doc = tokenize(sentence)

        return doc.counts.word_count

    @staticmethod
    def file_existence(file_path: str) -> int:
        file_path = Path(file_path)
        
        if not file_path.is_file():
            raise ValueError(f"The file {file_path} does not exists")
