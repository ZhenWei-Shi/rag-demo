from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import io
import PyPDF2

from rag.chunker import chunk_text
from rag.embedder import embed, warmup
from rag.store import add_document, delete_document, query, list_documents
from rag.generator import generate_answer

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
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")

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


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
