from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from app.text_utils import read_text_safely

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def iter_supported_files(data_dir: Path) -> Iterable[Path]:
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def load_text_file(path: Path) -> str:
    return read_text_safely(path)


def load_pdf_file(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((idx, text))
    return pages
