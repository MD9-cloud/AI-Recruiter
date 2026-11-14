from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 30_000


def extract(filename, raw):
    extension = Path(filename).suffix.lower()
    if len(raw) > MAX_BYTES:
        raise ValueError("Файл превышает 10 МБ.")
    if not raw:
        raise ValueError("Файл пуст.")
    if extension not in {".pdf", ".docx", ".txt"}:
        raise ValueError("Выберите файл PDF, DOCX или TXT.")
    try:
        if extension == ".pdf":
            if not raw.startswith(b"%PDF-"):
                raise ValueError("Содержимое файла не соответствует PDF.")
            document = PdfReader(BytesIO(raw))
            if document.is_encrypted:
                raise ValueError("PDF защищён паролем. Загрузите незашифрованную копию.")
            parts = (page.extract_text() for page in document.pages)
        elif extension == ".docx":
            with ZipFile(BytesIO(raw)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                    raise ValueError("Распакованный DOCX слишком велик.")
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Содержимое файла не соответствует DOCX.")
            document = Document(BytesIO(raw))
            parts = [paragraph.text for paragraph in document.paragraphs]
            parts.extend(cell.text for table in document.tables for row in table.rows for cell in row.cells)
        else:
            if raw.startswith((b"%PDF-", b"PK\x03\x04")) or b"\x00" in raw:
                raise ValueError("Содержимое файла не соответствует TXT.")
            parts = [raw.decode("utf-8-sig")]
        text = ""
        for part in parts:
            text += part + "\n"
            if len(text.strip()) > MAX_TEXT:
                raise ValueError("Текст превышает 30 000 символов.")
    except UnicodeError:
        raise ValueError("Сохраните TXT в кодировке UTF-8.") from None
    except ValueError:
        raise
    except Exception:
        raise ValueError("Файл повреждён или не соответствует формату.") from None
    if not text.strip():
        raise ValueError("Текст не найден. Для PDF нужен текстовый слой.")
    return text.strip()


def make_docx(title, body):
    document = Document()
    document.add_heading(title, 0)
    for line in body.splitlines():
        document.add_paragraph(line)
    output = BytesIO()
    document.save(output)
    return output.getvalue()
