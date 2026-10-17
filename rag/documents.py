"""Decode supported document formats without HTTP or storage dependencies."""
import io

import PyPDF2


def extract_text(content: bytes, ext: str) -> str:
    try:
        if ext == ".pdf":
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            doc = Document(io.BytesIO(content))
            parts = []
            for element in doc.element.body.iterchildren():
                if element.tag.endswith("}p"):
                    parts.append(Paragraph(element, doc).text)
                elif element.tag.endswith("}tbl"):
                    parts.extend(" | ".join(cell.text for cell in row.cells)
                                 for row in Table(element, doc).rows)
            return "\n".join(parts)
        return content.decode("utf-8-sig")
    except Exception as exc:
        raise ValueError("Invalid or unreadable document") from exc
