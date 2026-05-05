import win32com.client
from pathlib import Path
import pythoncom

def convert_via_word(input_path: Path, output_path: Path) -> bool:
    """Конвертация через Microsoft Word (только Windows)."""
    pythoncom.CoInitialize()
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    try:
        doc = word.Documents.Open(str(input_path.resolve()))
        doc.SaveAs(str(output_path.resolve()), FileFormat=17)  # 17 = wdFormatPDF
        doc.Close()
        return True
    finally:
        word.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    input_path = Path(r"C:\Users\Astana\Desktop\Client\Договор аренды жилого помещения К.Мырзали 8, кв58 2026 (1).docx")
    output_path = Path("output.pdf")
    convert_via_word(input_path, output_path)