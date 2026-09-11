import os
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

        ITERATIONS_UNTIL_FAIL = max(1, int((1 * file_size) / 100)) # 1%

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
