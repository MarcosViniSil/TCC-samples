import json

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, Label, Select, SelectionList, Static
from textual.widgets import Button

from common import CommonFileOperations
from db import (
    get_average_by_sentence,
    get_db_connection,
    get_sentences_count_by_corpus_name,
    insert_file,
    is_sample_already_exists,
)
from gitBackup import GitCommands


JSON_FILE_PATH = "./OpenSubtitles.jsonl"
BATCH_SIZE = 10

MAX_TRIES = 1000

CORPUS_AVAILABLE = ["OpenSubtitles", "MDN_Web_Docs", "PHP", "teste"]


class Corpus(App[None]):

    def __init__(self):
        super().__init__()
        self.conn = get_db_connection()
        self.corpus = ""
        self.text_by_id = {}
        self.words_by_id = {}

    def _commit_changes(self) -> None:
        try:
            GitCommands.add_files()
            GitCommands.commit_changes(len(self.text_by_id),self.corpus)
            GitCommands.push_changes()
        except Exception as e:
            self.notify(f"It was not possible to save data on git.", severity="error")

            raise e

    def get_unique_samples(self) -> None:
        FILE_PATH = f"./{self.corpus}.jsonl"
        tries = 0
        i = 0

        self.text_by_id = {}
        self.words_by_id = {}
        samples = []

        while i < BATCH_SIZE and tries < MAX_TRIES:
            line_raw = CommonFileOperations.get_random_line(FILE_PATH)
            if line_raw:
                line_json = json.loads(line_raw)

                if is_sample_already_exists(self.conn, line_json["id"], self.corpus) or line_json["id"] in self.words_by_id:
                    tries += 1
                    continue

                length_sentence = CommonFileOperations.get_phrase_number(
                    line_json["en"]
                )

                summary = f"id: {line_json['id']:<10} count: {length_sentence:<2} en: {line_json['en']:<3} pt: {line_json['pt']:<3}"

                self.text_by_id[line_json["id"]] = summary
                self.words_by_id[line_json["id"]] = length_sentence

                samples.append((summary, line_json["id"]))

            i += 1
        return samples

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            return

        selected = self.query_one("#samples", SelectionList).selected

        if not selected:
            self.query_one("#details", Static).update(
                "[b]None selected. Select something before continue[/b]"
            )
            return

        for id in selected:
            try:
                length_sentence = self.words_by_id[id]
                insert_file(self.conn,id,self.corpus,length_sentence)
            except Exception as e:
                self.notify(f"Error while saving id {id} item saved.", severity="error")

                print(e)

        self._commit_changes()

        self.notify(f"{len(selected)} item saved.", severity="information")
    

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        selected = event.selection_list.selected

        sum_db, qtd_db = get_average_by_sentence(self.conn, self.corpus)

        sum_selected = sum(self.words_by_id.get(sid, 0) for sid in selected)
        qtd_selected = len(selected)

        new_sum = sum_db + sum_selected
        new_qtd = qtd_db + qtd_selected
        new_avg = round(new_sum / new_qtd, 3) if new_qtd else 0.0

        if not selected:
            self.query_one("#details", Static).update(
                f"[b]None item selected.[/b]\n"
                f"Current corpus average: {round(sum_db / qtd_db, 3) if qtd_db else 0.0} "
                f"({qtd_db} sentences)"
            )
            return

        self.query_one("#details", Static).update(
            f"[b]{qtd_selected} selected[/b]  |  "
            f"[b]New average, if save: {new_avg}[/b] "
            f"(sum={new_sum}, qtd={new_qtd})\n"
        )

    def get_corpus_details(self) -> list[tuple]:
        options = []
        for corpus in CORPUS_AVAILABLE:
            count = get_sentences_count_by_corpus_name(self.conn, corpus)
            options.append((f"{corpus:<15}{count:>6}", corpus))

        return options

    def compose(self) -> ComposeResult:
        yield Header()
        yield Select(
            options=self.get_corpus_details(),
            prompt="Choose the corpus to select samples",
            id="Corpus",
        )
        yield Footer()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return

        self.corpus = event.value

        self.query_one(Select).remove()

        items = self.get_unique_samples()
        if not items:
            self.mount(Static("No sample found."))
            return

        self.mount(
            Vertical(
                Label(f"{self.corpus}", id="title"),
                VerticalScroll(
                    SelectionList[str](*items, id="samples"),
                ),
                Static("Nenhum item selecionado.", id="details"),
                Button("Salvar selecionados", id="save", variant="primary"),
                id="painel",
            )
        )


def main():
    Corpus().run()
    print("Buscando 10 linhas distintas")

    for _ in range(BATCH_SIZE):
        # line = get_random_line(JSON_FILE_PATH)
        # print("Linha encontrada ", line)
        pass


main()
