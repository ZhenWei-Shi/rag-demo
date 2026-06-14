from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import io
import json
import PyPDF2


def _ocr_pdf(content: bytes) -> str:
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
    warmup()
    yield

app = FastAPI(title="RAG Document Q&A", lifespan=lifespan)


class Question(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    filename = file.filename

    if filename.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
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
    delete_document(filename)
    return {"deleted": filename}


@app.get("/documents")
async def documents():
    return {"documents": list_documents()}


@app.post("/ask")
async def ask(body: Question):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

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
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

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
