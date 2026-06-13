# RAG Document Q&A

A production-style RAG (Retrieval-Augmented Generation) pipeline that lets you upload PDF/TXT documents and ask questions about their content in natural language — with answers grounded in your own documents.

Supports **English and Chinese** (中英文双语).

## Features

- **PDF & TXT upload** with drag-and-drop
- **Semantic retrieval** via sentence-transformers embeddings + ChromaDB
- **Local LLM generation** via Ollama (no API key needed, fully private)
- **Source citations** — every answer shows which document it came from
- **Retrieved chunk inspection** — see exactly which passages informed the answer
- **Persistent vector store** — indexed documents survive server restarts
- **Bilingual UI** — toggle between English and Chinese

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI |
| Embedding Model | `all-MiniLM-L6-v2` (sentence-transformers) |
| Vector Store | ChromaDB (persistent) |
| LLM | Ollama (`llama3.2`) — runs locally |
| PDF Parsing | PyPDF2 |
| Frontend | Vanilla JS, no build step |

## Quick Start

**Prerequisites:** [Ollama](https://ollama.com) installed and running.

```bash
# Pull the LLM (one-time, ~2 GB)
ollama pull llama3.2

# Install Python dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

Open `http://localhost:8000` in your browser.

## Project Structure

```
rag-demo/
├── app.py              # FastAPI server — upload, ask, document management
├── rag/
│   ├── chunker.py      # Sentence-boundary-aware text chunking
│   ├── embedder.py     # Embedding model singleton
│   ├── store.py        # ChromaDB persistent vector store
│   └── generator.py    # Ollama LLM wrapper
├── static/
│   └── index.html      # Single-page UI (bilingual EN/ZH)
└── requirements.txt
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload and index a PDF or TXT file |
| `POST` | `/ask` | Ask a question, returns answer + sources |
| `GET` | `/documents` | List all indexed documents |
| `DELETE` | `/documents/{filename}` | Remove a document from the index |
