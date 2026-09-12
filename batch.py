import json
from pathlib import Path
from textual.binding import Binding
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, Select, SelectionList, Static
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

OUT_FOLDER = Path("out")
OUT_FOLDER.mkdir(parents=True, exist_ok=True)

MAX_TRIES = 1000

CORPUS_AVAILABLE = ["OpenSubtitles", "MDN_Web_Docs", "PHP"]

from rich.markup import escape
from textual.widgets import SelectionList


class Corpus(App[None]):

    CSS = """
    #search_result {
        width: 100%;
        height: auto;
        min-height: 3;
        max-height: 20;
        border: round $accent;
        padding: 0 1;
        overflow-y: auto;
    }

    #ids_list {
        width: 100%;
        height: auto;
        min-height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.conn = get_db_connection()
        self.corpus = ""
        self.text_by_id: dict = {}
        self.words_by_id: dict = {}
        self.raw_by_id: dict = {}
        self._sel: SelectionList | None = None
        self._details: Static | None = None
        self._ids: Static | None = None
        self._save_btn: Button | None = None
        self._panel: Vertical | None = None

    def on_unmount(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _commit_changes(self, files_modified: int) -> None:
        try:
            GitCommands.add_files()
            GitCommands.commit_changes(files_modified, self.corpus)
            GitCommands.push_changes()
        except Exception as e:
            self.notify(
                f"It was not possible to save data on git. {e}",
                severity="error",
            )

    def get_unique_samples(self) -> list[tuple[str, int]]:
        file_path = f"./{self.corpus}.jsonl"
        CommonFileOperations.file_existence(file_path)

        tries = 0
        i = 0

        self.text_by_id = {}
        self.words_by_id = {}
        self.raw_by_id = {}
        samples: list[tuple[str, int]] = []

        while i < BATCH_SIZE and tries < MAX_TRIES:
            line_raw = CommonFileOperations.get_random_line(file_path)
            if not line_raw:
                i += 1
                continue

            try:
                line_json = json.loads(line_raw)
            except json.JSONDecodeError:
                tries += 1
                continue

            sid = line_json["id"]

            if (
                is_sample_already_exists(self.conn, sid, self.corpus)
                or sid in self.words_by_id
            ):
                tries += 1
                continue

            length_sentence = CommonFileOperations.get_phrase_number(line_json["en"])

            summary = (
                f"id: {sid:<10} count: {length_sentence:<2} "
                f"en: {line_json['en']:<3} pt: {line_json['pt']:<3}"
            )

            self.text_by_id[sid] = summary
            self.words_by_id[sid] = length_sentence
            self.raw_by_id[sid] = {
                "id": sid,
                "en": line_json["en"],
                "pt": line_json["pt"],
            }
            samples.append((summary, sid))

            i += 1

        return samples

    def _update_ids(self, items: list[tuple[str, int]]) -> None:
        if self._ids is None:
            return
        ids = [str(sid) for _, sid in items]
        self._ids.update("[b]ids:[/b] " + ", ".join(ids))

    def _render_list(self, items: list[tuple[str, int]]) -> None:
        if self._panel is not None:
            self._panel.remove()

        self._sel = SelectionList[str](*items, id="samples")
        self._details = Static("None item selected.", id="details")
        self._ids = Static("", id="ids_list")
        self._save_btn = Button("Save items", id="save", variant="primary")

        self._panel = Vertical(
            Label(f"{self.corpus}", id="title"),
            VerticalScroll(self._sel),
            self._ids,
            self._details,
            self._save_btn,
            id="painel",
        )
        self.mount(self._panel)

        self._update_ids(items)

    def _reload_list(self) -> None:
        if self._sel is None or self._save_btn is None:
            items = self.get_unique_samples()
            if not items:
                self.notify("No more samples available for this corpus.",
                            severity="warning")
                return
            self._render_list(items)
            return

        items = self.get_unique_samples()
        if not items:
            self._details.update("No more samples available for this corpus.")
            self._sel.display = False
            self._save_btn.display = False
            self._update_ids([])
            return

        self._sel.clear_options()
        for summary, sid in items:
            self._sel.add_option((summary, sid))

        self._update_ids(items)
        self._details.update("None item selected.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            return

        if self._sel is None or self._save_btn is None or self._details is None:
            return

        selected = self._sel.selected

        self._save_btn.disabled = True

        saved = 0
        error = 0
        output_file = f"{OUT_FOLDER}/{self.corpus}_seed.jsonl"

        try:
            if selected:
                with open(output_file, "a", encoding="utf-8") as out:
                    for sid in selected:
                        try:
                            length_sentence = self.words_by_id[sid]
                            insert_file(self.conn, sid, self.corpus, length_sentence, True)

                            register = self.raw_by_id[sid]
                            out.write(json.dumps(register, ensure_ascii=False) + "\n")

                            saved += 1
                        except Exception as e:
                            error += 1
                            self.notify(
                                f"Error while saving id {sid}: {e}",
                                severity="error",
                            )

            for sid, _length in list(self.words_by_id.items()):
                if sid in selected:
                    continue
                if is_sample_already_exists(self.conn, sid, self.corpus):
                    continue
                try:
                    insert_file(self.conn, sid, self.corpus, _length, False)
                except Exception as e:
                    error += 1
                    self.notify(
                        f"Error while saving id {sid} for exclusion: {e}",
                        severity="error",
                    )

            self._commit_changes(saved)

            if saved:
                self.notify(f"{saved} item(s) saved.", severity="information")
            if error:
                self.notify(f"{error} item(s) failed.", severity="warning")

            self._reload_list()
        finally:
            if self._save_btn is not None and self._save_btn.is_mounted:
                self._save_btn.disabled = False

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        if self._details is None:
            return

        selected = event.selection_list.selected

        sum_db, qtd_db = get_average_by_sentence(self.conn, self.corpus)
        sum_selected = sum(self.words_by_id.get(sid, 0) for sid in selected)
        qtd_selected = len(selected)

        new_sum = sum_db + sum_selected
        new_qtd = qtd_db + qtd_selected
        new_avg = round(new_sum / new_qtd, 3) if new_qtd else 0.0

        if not selected:
            current = round(sum_db / qtd_db, 3) if qtd_db else 0.0
            self._details.update(
                f"[b]None item selected.[/b]\n"
                f"Current corpus average: {current} ({qtd_db} sentences)"
            )
            return

        self._details.update(
            f"[b]{qtd_selected} selected[/b]  |  "
            f"[b]New average, if save: {new_avg}[/b] "
            f"(sum={new_sum}, qtd={new_qtd})\n"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""

        if not text:
            return

        parts = text.split()
        if len(parts) != 1:
            self.notify("Type only the id from the corpus", severity="warning")
            return 

        try:
            sid = int(parts[0])
        except ValueError:
            self.notify(f"Invalid id: {parts[0]}", severity="warning")
            return

        self._show_details(sid)

    def _show_details(self, sid: int) -> None:
        raw = self.raw_by_id.get(sid) or self.raw_by_id.get(str(sid))
        if not raw:
            self.query_one("#search_result", Static).update(
                f"[b]None result found for id {sid}[/b]"
            )
            return

        content = (
            f"[b]id:[/b] {raw['id']}\n"
            f"[b]EN:[/b]\n{escape(raw['en'])}\n\n"
            f"[b]PT:[/b]\n{escape(raw['pt'])}"
        )
        self.query_one("#search_result", Static).update(content)


    def get_corpus_details(self) -> list[tuple[str, str]]:
        options = []
        for corpus in CORPUS_AVAILABLE:
            count = get_sentences_count_by_corpus_name(self.conn, corpus)
            options.append((f"{corpus:<15}{count:>6}", corpus))
        return options

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return

        self.corpus = event.value
        event.select.display = False

        items = self.get_unique_samples()
        if not items:
            self.mount(Static("No sample found."))
            return

        self._render_list(items)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Corpus id", id="cmd")
        yield Static("", id="search_result")
        yield Select(
            options=self.get_corpus_details(),
            prompt="Choose the corpus to select samples",
            id="Corpus",
        )
        yield Footer()


def main():
    Corpus().run()

main()
