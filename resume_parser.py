"""Safe text extraction from candidate resume files.

Supports text-based PDF and DOCX plus plain text/Markdown. Scanned PDFs need OCR
and are rejected with an actionable message rather than silently treated as empty.
"""
from pathlib import Path
import re


class ResumeParseError(ValueError):
    """The resume exists but could not be converted into usable text."""


def _clean(text):
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_resume_text(path):
    """Extract readable text from TXT, MD, PDF or DOCX without inventing data."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(str(source))
    suffix = source.suffix.lower()
    try:
        if suffix in {".txt", ".md"}:
            try:
                raw = source.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                raw = source.read_text(encoding="cp1251")
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise ResumeParseError("для PDF установите пакет pypdf") from exc
            reader = PdfReader(str(source))
            raw = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise ResumeParseError("для DOCX установите пакет python-docx") from exc
            document = Document(str(source))
            parts = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            raw = "\n".join(parts)
        else:
            raise ResumeParseError(
                f"формат {suffix or '(без расширения)'} не поддерживается; используйте TXT, MD, PDF или DOCX"
            )
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError(f"не удалось прочитать {source.name}: {type(exc).__name__}") from exc

    text = _clean(raw)
    if len(text) < 40:
        if suffix == ".pdf":
            raise ResumeParseError("в PDF не найден текстовый слой; сканированные PDF пока требуют OCR")
        raise ResumeParseError("в файле недостаточно извлекаемого текста")
    return text
