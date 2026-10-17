"""Document upload, listing and deletion HTTP endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from rag.documents import extract_text
from rag.ocr import extract_pdf_text
from rag.embedder import chunk_document, embed
from rag.store import add_document, delete_document, list_documents

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    # EN: Upload and index a document. Supports PDF, DOCX, TXT, MD.
    # ZH: 上传并索引文档，支持 PDF、DOCX、TXT、MD 格式。
    content = await file.read(MAX_FILE_SIZE + 1)
    filename = file.filename or ""
    if not filename or any(char in filename for char in ("/", "\\", "\x00")):
        raise HTTPException(status_code=400, detail="A plain document filename is required")

    # EN: Reject files exceeding the size limit before any processing.
    # ZH: 在任何处理之前拒绝超过大小限制的文件。
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 20 MB.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: PDF, DOCX, TXT, MD."
        )

    try:
        text = await run_in_threadpool(extract_text, content, ext)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or unreadable document")
    if ext == ".pdf" and not text.strip():
        try:
            text = await run_in_threadpool(extract_pdf_text, content)
        except Exception:
            logger.exception("OCR failed")
            raise HTTPException(status_code=503, detail="OCR is temporarily unavailable")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    chunks = await run_in_threadpool(chunk_document, text)
    embeddings = await run_in_threadpool(embed, chunks)
    await run_in_threadpool(add_document, chunks, embeddings, filename)

    return {"filename": filename, "chunks": len(chunks)}


@router.delete("/documents/{filename}")
async def delete(filename: str):
    # EN: Remove a document and all its chunks from the vector store.
    # ZH: 从向量数据库中删除文档及其所有分块。
    await run_in_threadpool(delete_document, filename)
    return {"deleted": filename}


@router.get("/documents")
async def documents():
    # EN: Return the list of currently indexed document filenames.
    # ZH: 返回当前已索引的文档文件名列表。
    return {"documents": await run_in_threadpool(list_documents)}
