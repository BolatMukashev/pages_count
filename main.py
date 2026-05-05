from pathlib import Path
from typing import Optional
from PyPDF2 import PdfReader
from docx_to_pdf_openoffice import convert_docx_to_pdf
from docx_to_pdf_word import convert_via_word


# ───────────────────────────────────────────── Константы расширений


IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".tiff", ".tif", ".webp"}
DOC_EXTENSIONS   = {".docx", ".doc"}
ALL_EXTENSIONS   = DOC_EXTENSIONS | IMAGE_EXTENSIONS | {".pdf"}


# ───────────────────────────────────────────── Логика


def get_pdf_page_count(pdf_path: Path) -> int:
    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def get_count_of_pages(file_path: Path) -> Optional[int]:
    ext = file_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        return 1

    elif ext in DOC_EXTENSIONS:
        temp_pdf_path = file_path.with_suffix(".pdf")
        convert_via_word(file_path, temp_pdf_path)
        page_count = get_pdf_page_count(temp_pdf_path)
        temp_pdf_path.unlink()  # Удаляем временный PDF
        return page_count

    elif ext == ".pdf":
        return get_pdf_page_count(file_path)

    else:
        print(f"Тип файла не поддерживается: {file_path}")
        return None
    

def process_files_in_directory(directory: Path):
    count = 0
    for file_path in directory.iterdir():
        # пропускаем временные файлы
        if file_path.name.startswith("~$"):
            continue

        # ❗ пропускаем папки молча
        if not file_path.is_file():
            continue

        if file_path.is_file() and file_path.suffix.lower() in ALL_EXTENSIONS:
            page_count = get_count_of_pages(file_path)
            if page_count is not None:
                print(f"{file_path.name}: {page_count} pages")
                count += page_count
        else:
            print(f"Тип файла не поддерживается: {file_path.name}")
    print(f"Всего страниц: {count}")


# ───────────────────────────────────────────── Точка входа


if __name__ == "__main__":
    files_path = input("Укажи путь к папке с файлами: ")
    files_path = Path(files_path)
    process_files_in_directory(files_path)