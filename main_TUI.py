from pathlib import Path
from typing import Optional
import asyncio

from PyPDF2 import PdfReader
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Static,
)
from textual.reactive import reactive
from textual.worker import Worker, WorkerState
from textual import work
from textual.screen import ModalScreen
from rich.text import Text


# ───────────────────────────────────────────── Константы расширений

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".tiff", ".tif", ".webp"}
DOC_EXTENSIONS   = {".docx", ".doc"}
ALL_EXTENSIONS   = DOC_EXTENSIONS | IMAGE_EXTENSIONS | {".pdf"}


# ───────────────────────────────────────────── Логика (без изменений)

def get_pdf_page_count(pdf_path: Path) -> int:
    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def get_count_of_pages(file_path: Path) -> Optional[int]:
    ext = file_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        return 1

    elif ext in DOC_EXTENSIONS:
        try:
            # Пробуем через Word (Windows), иначе через LibreOffice
            try:
                from docx_to_pdf_word import convert_via_word
                temp_pdf_path = file_path.with_suffix(".pdf")
                convert_via_word(file_path, temp_pdf_path)
            except Exception:
                from docx_to_pdf_openoffice import convert_docx_to_pdf
                temp_pdf_path = file_path.with_suffix(".pdf")
                convert_docx_to_pdf(file_path, temp_pdf_path)

            page_count = get_pdf_page_count(temp_pdf_path)
            temp_pdf_path.unlink(missing_ok=True)
            return page_count
        except Exception:
            return None

    elif ext == ".pdf":
        return get_pdf_page_count(file_path)

    return None


def collect_files(directory: Path) -> list[Path]:
    """Возвращает список поддерживаемых файлов в директории."""
    files = []
    for file_path in sorted(directory.iterdir()):
        if file_path.name.startswith("~$"):
            continue
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in ALL_EXTENSIONS:
            files.append(file_path)
    return files


# ───────────────────────────────────────────── CSS

CSS = """
Screen {
    background: $surface;
}

#app-grid {
    layout: grid;
    grid-size: 2;
    grid-columns: 1fr 2fr;
    height: 1fr;
}

#left-panel {
    border: solid $primary-darken-2;
    padding: 0 1;
    height: 100%;
}

#right-panel {
    layout: vertical;
    height: 100%;
    padding: 0 1;
}

#path-row {
    layout: horizontal;
    height: 3;
    margin-bottom: 1;
    align: left middle;
}

#path-input {
    width: 1fr;
    margin-right: 1;
}

#btn-scan {
    width: 14;
}

#results-table {
    height: 1fr;
    border: solid $primary-darken-2;
}

#progress-area {
    height: 4;
    padding: 0 1;
}

#status-label {
    height: 1;
    color: $text-muted;
    margin-bottom: 1;
}

#progress-bar {
    height: 1;
}

#summary-row {
    layout: horizontal;
    height: 3;
    align: right middle;
    margin-top: 1;
}

#total-label {
    color: $success;
    text-style: bold;
    width: 1fr;
    content-align: right middle;
    padding-right: 2;
}

#btn-clear {
    width: 12;
    margin-left: 1;
}

DirectoryTree {
    height: 1fr;
    background: $surface;
}

#panel-title {
    color: $primary;
    text-style: bold;
    margin-bottom: 1;
}
"""


# ───────────────────────────────────────────── TUI App

class PageCounterApp(App):
    """TUI для подсчёта страниц в документах."""

    CSS = CSS
    TITLE = "📄 Page Counter"
    BINDINGS = [
        ("ctrl+q", "quit", "Выход"),
        ("ctrl+s", "scan", "Сканировать"),
        ("ctrl+c", "clear", "Очистить"),
    ]

    total_pages: reactive[int] = reactive(0)
    is_scanning: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="app-grid"):
            # Левая панель — дерево директорий
            with Vertical(id="left-panel"):
                yield Label("📁 Обзор файлов", id="panel-title")
                yield DirectoryTree(".", id="dir-tree")

            # Правая панель — основной контент
            with Vertical(id="right-panel"):
                # Строка ввода пути
                with Horizontal(id="path-row"):
                    yield Input(
                        placeholder="Путь к папке...",
                        id="path-input",
                    )
                    yield Button("▶ Сканировать", id="btn-scan", variant="primary")

                # Таблица результатов
                yield DataTable(id="results-table", cursor_type="row")

                # Прогресс
                with Vertical(id="progress-area"):
                    yield Label("", id="status-label")
                    yield ProgressBar(id="progress-bar", show_eta=False)

                # Итоги и кнопка очистки
                with Horizontal(id="summary-row"):
                    yield Label("Всего страниц: 0", id="total-label")
                    yield Button("🗑 Очистить", id="btn-clear", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Файл", "Тип", "Страниц")
        table.zebra_stripes = True

    # ── Обработчики событий

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan":
            self.action_scan()
        elif event.button.id == "btn-clear":
            self.action_clear()

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        path_input = self.query_one("#path-input", Input)
        path_input.value = str(event.path)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_scan()

    # ── Действия

    def action_scan(self) -> None:
        if self.is_scanning:
            return
        path_str = self.query_one("#path-input", Input).value.strip()
        if not path_str:
            self.notify("Укажи путь к папке!", severity="warning")
            return
        directory = Path(path_str)
        if not directory.exists() or not directory.is_dir():
            self.notify(f"Папка не найдена: {path_str}", severity="error")
            return

        self.action_clear()
        self.is_scanning = True
        self._start_scan(directory)

    def action_clear(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self.total_pages = 0
        self.query_one("#total-label", Label).update("Всего страниц: 0")
        self.query_one("#status-label", Label).update("")
        progress = self.query_one("#progress-bar", ProgressBar)
        progress.update(progress=0, total=100)

    # ── Фоновый воркер

    @work(exclusive=True, thread=True)
    def _start_scan(self, directory: Path) -> None:
        files = collect_files(directory)

        if not files:
            self.call_from_thread(
                self.notify, "Поддерживаемые файлы не найдены.", severity="warning"
            )
            self.call_from_thread(self._finish_scan)
            return

        total = len(files)
        self.call_from_thread(
            self.query_one("#progress-bar", ProgressBar).update,
            total=total,
            progress=0,
        )

        grand_total = 0

        for idx, file_path in enumerate(files, start=1):
            self.call_from_thread(
                self.query_one("#status-label", Label).update,
                f"⏳ Обработка ({idx}/{total}): {file_path.name}",
            )

            try:
                pages = get_count_of_pages(file_path)
            except Exception as e:
                pages = None

            ext = file_path.suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                kind = "🖼 Изображение"
            elif ext in DOC_EXTENSIONS:
                kind = "📝 Документ"
            else:
                kind = "📄 PDF"

            if pages is not None:
                grand_total += pages
                pages_text = Text(str(pages), style="bold green")
            else:
                pages_text = Text("ошибка", style="bold red")

            self.call_from_thread(
                self._add_table_row,
                file_path.name,
                kind,
                pages_text,
            )

            self.call_from_thread(
                self.query_one("#progress-bar", ProgressBar).advance, 1
            )

        self.call_from_thread(self._finish_scan, grand_total, total)

    def _add_table_row(self, name: str, kind: str, pages) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_row(name, kind, pages)

    def _finish_scan(self, grand_total: int = 0, processed: int = 0) -> None:
        self.is_scanning = False
        label = self.query_one("#total-label", Label)
        label.update(f"✅ Файлов: {processed}  │  Всего страниц: {grand_total}")
        self.query_one("#status-label", Label).update("Готово.")
        self.notify(f"Готово! Обработано {processed} файлов, {grand_total} страниц.", severity="information")


# ───────────────────────────────────────────── Точка входа

if __name__ == "__main__":
    app = PageCounterApp()
    app.run()