"""
PageCounter TUI — подсчёт страниц PDF/DOCX и изображений в папке.
Зависимости: pip install textual docx2pdf PyPDF2 Pillow
"""

import sys
import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Static,
)
from textual.worker import Worker, WorkerState


# ─────────────────────────────────────────────
#  Константы расширений
# ─────────────────────────────────────────────

IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".tiff", ".tif", ".webp"}
DOC_EXTENSIONS   = {".pdf", ".docx", ".doc"}
ALL_EXTENSIONS   = DOC_EXTENSIONS | IMAGE_EXTENSIONS


# ─────────────────────────────────────────────
#  Логика подсчёта страниц
# ─────────────────────────────────────────────

class PageCounter:
    """Считает количество страниц в PDF/DOCX и кадров/страниц в изображениях."""

    def count_pages(self, file_path) -> Optional[int]:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._get_pdf_pages(path)
        elif suffix == ".docx" or suffix == ".doc":
            return self._get_docx_pages(path)
        elif suffix in IMAGE_EXTENSIONS:
            return self._get_image_pages(path)
        else:
            raise ValueError(f"Неподдерживаемый формат: '{suffix}'")

    def _get_pdf_pages(self, path: Path) -> int:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(path))
        return len(reader.pages)

    def _get_docx_pages(self, path: Path) -> Optional[int]:
        from docx2pdf import convert
        from PyPDF2 import PdfReader

        temp_pdf = Path(f"temp_page_counter_{uuid.uuid4().hex}.pdf")
        try:
            devnull = open(os.devnull, "w")
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = devnull
            sys.stderr = devnull
            try:
                convert(str(path), str(temp_pdf))
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
                devnull.close()

            with open(temp_pdf, "rb") as f:
                pdf = PdfReader(f)
                return len(pdf.pages)
        except KeyboardInterrupt:
            raise
        except Exception:
            return None
        finally:
            if temp_pdf.exists():
                try:
                    temp_pdf.unlink()
                except Exception:
                    pass

    def _get_image_pages(self, path: Path) -> int:
        """TIFF может содержать несколько кадров; остальные форматы — всегда 1."""
        from PIL import Image
        try:
            with Image.open(path) as img:
                return getattr(img, "n_frames", 1) or 1
        except Exception:
            return 1


# ─────────────────────────────────────────────
#  TUI приложение
# ─────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#app-container {
    margin: 1 2;
}

#path-row {
    height: 3;
    margin-bottom: 1;
}

#path-input {
    width: 1fr;
    margin-right: 1;
}

#scan-btn {
    width: 16;
    background: $accent;
    color: $text;
}

#scan-btn:hover {
    background: $accent-lighten-2;
}

#status-bar {
    height: 1;
    margin-bottom: 1;
    color: $text-muted;
}

#progress-bar {
    height: 1;
    margin-bottom: 1;
}

#results-table {
    height: 1fr;
    border: solid $accent;
}

#summary {
    height: 3;
    margin-top: 1;
    padding: 0 1;
    background: $boost;
    border: solid $accent;
    content-align: center middle;
    color: $text;
}

#error-label {
    color: $error;
    height: 1;
    margin-bottom: 1;
}
"""

# Иконки по расширению
EXT_ICONS = {
    "PDF":  "📕",
    "DOCX": "📘",
    "JPEG": "🖼️",
    "JPG":  "🖼️",
    "PNG":  "🖼️",
    "TIFF": "🖼️",
    "TIF":  "🖼️",
    "WEBP": "🖼️",
}


class PageCounterApp(App):
    """TUI для подсчёта страниц PDF/DOCX и изображений."""

    TITLE = "📄 PageCounter"
    SUB_TITLE = "Подсчёт страниц PDF/DOCX и изображений"
    CSS = CSS
    BINDINGS = [
        Binding("ctrl+q", "quit", "Выйти"),
        Binding("ctrl+r", "rescan", "Пересканировать"),
        Binding("f5", "rescan", "Пересканировать", show=False),
    ]

    _scanning: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="app-container"):
            with Horizontal(id="path-row"):
                yield Input(
                    placeholder="Введите путь к папке, например: C:\\Users\\Bolat\\Documents",
                    id="path-input",
                )
                yield Button("🔍 Сканировать", id="scan-btn")

            yield Label("", id="error-label")
            yield Static("Готов к работе.", id="status-bar")
            yield ProgressBar(total=100, show_eta=False, id="progress-bar")
            yield DataTable(id="results-table", zebra_stripes=True, cursor_type="row")
            yield Static("", id="summary")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Файл", "Страниц", "Тип")
        self.query_one("#progress-bar", ProgressBar).update(progress=0)

    # ── Кнопка / Enter ──────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan-btn":
            self._start_scan()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._start_scan()

    def action_rescan(self) -> None:
        self._start_scan()

    # ── Запуск сканирования ──────────────────────────────────────

    def _start_scan(self) -> None:
        if self._scanning:
            return

        path_str = self.query_one("#path-input", Input).value.strip().strip('"')
        error_lbl = self.query_one("#error-label", Label)

        if not path_str:
            error_lbl.update("⚠️  Введите путь к папке.")
            return

        folder = Path(path_str)
        if not folder.exists():
            error_lbl.update("❌ Папка не существует.")
            return
        if not folder.is_dir():
            error_lbl.update("❌ Указанный путь не является папкой.")
            return

        error_lbl.update("")
        self._clear_results()
        self._scanning = True
        self.run_worker(self._scan_folder(folder), exclusive=True)

    # ── Основная рабочая задача (async воркер) ───────────────────

    async def _scan_folder(self, folder: Path) -> None:
        files = sorted(
            f for f in folder.iterdir()
            if f.is_file()
            and not f.name.startswith("~$")
            and f.suffix.lower() in ALL_EXTENSIONS
        )

        total_files = len(files)
        if total_files == 0:
            self._on_no_files()
            return

        counter = PageCounter()
        self._set_progress_total(total_files)

        total_pages = 0
        total_images = 0
        processed = 0

        for i, file_path in enumerate(files, 1):
            self._update_status(f"⏳ Обрабатывается: {file_path.name} ({i}/{total_files})")

            pages = await asyncio.get_event_loop().run_in_executor(
                None, counter.count_pages, file_path
            )
            ext = file_path.suffix.upper().lstrip(".")
            is_image = file_path.suffix.lower() in IMAGE_EXTENSIONS

            if pages is not None:
                if is_image:
                    total_images += 1
                total_pages += pages
                processed += 1
                self._add_row(file_path.name, str(pages), ext)
            else:
                self._add_row(file_path.name, "—", ext)

            self._set_progress(i)

        self._on_done(processed, total_files, total_pages, total_images)

    # ── Helpers ──────────────────────────────────────────────────

    def _clear_results(self) -> None:
        self.query_one(DataTable).clear()
        self.query_one("#summary", Static).update("")
        self.query_one("#status-bar", Static).update("")
        self.query_one("#progress-bar", ProgressBar).update(progress=0)

    def _set_progress_total(self, total: int) -> None:
        self.query_one("#progress-bar", ProgressBar).update(total=total, progress=0)

    def _set_progress(self, value: int) -> None:
        self.query_one("#progress-bar", ProgressBar).advance(1)

    def _update_status(self, msg: str) -> None:
        self.query_one("#status-bar", Static).update(msg)

    def _add_row(self, name: str, pages: str, ext: str) -> None:
        icon = EXT_ICONS.get(ext, "📄")
        self.query_one(DataTable).add_row(f"{icon}  {name}", pages, ext)

    def _on_no_files(self) -> None:
        self._scanning = False
        self.query_one("#status-bar", Static).update(
            "⚠️  Файлы PDF, DOCX или изображений не найдены."
        )

    def _on_done(
        self, processed: int, total_files: int, total_pages: int, total_images: int
    ) -> None:
        self._scanning = False
        skipped = total_files - processed
        status = f"✅ Готово. Обработано: {processed}/{total_files}"
        if skipped:
            status += f"  |  ⚠️ Пропущено (ошибка): {skipped}"
        self.query_one("#status-bar", Static).update(status)

        doc_pages = total_pages - total_images
        parts = [
            f"📊 ИТОГО страниц: {total_pages}",
            f"📄 PDF/DOCX: {doc_pages}",
            f"🖼️  Изображений: {total_images}",
            f"Файлов: {processed}",
        ]
        self.query_one("#summary", Static).update("   •   ".join(parts))

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
            self._scanning = False
            self.query_one("#status-bar", Static).update("❌ Сканирование прервано.")


# ─────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────

if __name__ == "__main__":
    PageCounterApp().run()