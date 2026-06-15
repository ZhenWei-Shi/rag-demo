# EN: FastAPI application entry point — handles file upload, Q&A, and document management.
# ZH: FastAPI 主入口 —— 处理文件上传、问答和文档管理。

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import io
import json
import PyPDF2

# EN: Maximum allowed upload size (20 MB). Prevents memory exhaustion on the 2-core server.
# ZH: 最大上传文件大小（20 MB），防止服务器内存耗尽。
MAX_FILE_SIZE = 20 * 1024 * 1024

# EN: Maximum question length to prevent abuse and oversized LLM prompts.
# ZH: 最大问题长度，防止滥用和 LLM 提示词过长。
MAX_QUESTION_LENGTH = 2000

# EN: Allowed file extensions for upload.
# ZH: 允许上传的文件扩展名。
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _ocr_pdf(content: bytes) -> str:
    # EN: OCR fallback for scanned PDFs. Uses Tesseract with 2 parallel threads.
    # ZH: 扫描版 PDF 的 OCR 兜底方案，使用 Tesseract 2 线程并行处理。
    from pdf2image import convert_from_bytes
    import pytesseract
    from concurrent.futures import ThreadPoolExecutor

    images = convert_from_bytes(content, dpi=120)

    def _ocr_page(img):
        return pytesseract.image_to_string(img, lang="chi_sim+eng")

    workers = min(2, len(images))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(_ocr_page, images))

    return "\n".join(pages)


from rag.chunker import chunk_text
from rag.embedder import embed, warmup
from rag.store import add_document, delete_document, query, list_documents
from rag.generator import generate_answer, stream_answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # EN: Pre-load the embedding model on startup to avoid cold-start delay on first request.
    # ZH: 启动时预热嵌入模型，避免第一次请求的冷启动延迟。
    warmup()
    yield


app = FastAPI(title="RAG Document Q&A", lifespan=lifespan)


class Question(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # EN: Upload and index a document. Supports PDF, DOCX, TXT, MD.
    # ZH: 上传并索引文档，支持 PDF、DOCX、TXT、MD 格式。
    content = await file.read()
    filename = file.filename

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

    if filename.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # EN: If text extraction yields nothing, the PDF is likely scanned — fall back to OCR.
        # ZH: 如果文本提取为空，说明是扫描件，降级为 OCR 处理。
        if not text.strip():
            text = await run_in_threadpool(_ocr_pdf, content)
    elif filename.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif filename.endswith((".txt", ".md")):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, TXT and MD files are supported")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    chunks = chunk_text(text)
    embeddings = await run_in_threadpool(embed, chunks)
    add_document(chunks, embeddings, filename)

    return {"filename": filename, "chunks": len(chunks)}


@app.delete("/documents/{filename}")
async def delete(filename: str):
    # EN: Remove a document and all its chunks from the vector store.
    # ZH: 从向量数据库中删除文档及其所有分块。
    delete_document(filename)
    return {"deleted": filename}


@app.get("/documents")
async def documents():
    # EN: Return the list of currently indexed document filenames.
    # ZH: 返回当前已索引的文档文件名列表。
    return {"documents": list_documents()}


@app.post("/ask")
async def ask(body: Question):
    # EN: Non-streaming Q&A endpoint (kept for backward compatibility).
    # ZH: 非流式问答接口（保留以兼容旧版本）。
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(body.question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail=f"Question too long (max {MAX_QUESTION_LENGTH} chars)")

    q_embedding = (await run_in_threadpool(embed, [body.question]))[0]
    chunks = query(q_embedding)

    if not chunks:
        return {
            "answer": "No documents have been uploaded yet. Please upload a PDF or text file first.",
            "sources": [],
            "chunks": []
        }

    answer = generate_answer(body.question, chunks, body.history)
    sources = list(dict.fromkeys(c["source"] for c in chunks))

    return {"answer": answer, "sources": sources, "chunks": chunks}


@app.post("/ask/stream")
async def ask_stream(body: Question):
    # EN: Streaming Q&A endpoint using Server-Sent Events (SSE).
    #     Tokens are pushed to the client as they arrive from the LLM.
    # ZH: 基于 SSE 的流式问答接口，LLM 输出的每个 token 实时推送到客户端。
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(body.question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail=f"Question too long (max {MAX_QUESTION_LENGTH} chars)")

    q_embedding = (await run_in_threadpool(embed, [body.question]))[0]
    chunks = query(q_embedding)

    if not chunks:
        msg = "No documents have been uploaded yet. Please upload a PDF or text file first."
        async def _empty():
            yield f"data: {json.dumps({'type': 'token', 'content': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'sources': [], 'chunks': [], 'answer': msg})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    question, history, captured = body.question, body.history, chunks

    def _generate():
        # EN: Accumulate the full answer while streaming tokens to the client.
        # ZH: 在向客户端流式推送 token 的同时，累积完整答案以便最终发送 done 事件。
        full = ""
        for token in stream_answer(question, captured, history):
            full += token
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        sources = list(dict.fromkeys(c["source"] for c in captured))
        yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'chunks': captured, 'answer': full})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
