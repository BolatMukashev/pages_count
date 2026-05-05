import docbuilder
from pathlib import Path
import os
import sys

def convert_docx_to_pdf(input_path, output_path):
    builder = docbuilder.CDocBuilder()

    # 🔇 отключаем вывод
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')

    try:
        builder.OpenFile(str(input_path))
        builder.SaveFile("pdf", str(output_path))
        builder.CloseFile()
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout


if __name__ == "__main__":
    input_path = Path(r"C:\Users\Astana\Desktop\Client\JAF_COI.doc")
    output_path = Path("output.pdf")
    convert_docx_to_pdf(input_path, output_path)